"""
Instagram 서비스 - Graph API 연동
캐러셀 발행 + 단일 이미지 발행 + 예약 발행
컨테이너 상태 폴링 (Meta 공식 권장 패턴)

[발행 실패 원인 후보 — 공식 문서/커뮤니티 기반]
1. 이미지 포맷: Meta 공식 - "JPEG is the only image format supported" → PNG 전송 시 실패 가능
2. 재시도 간격: Meta 공식 에러코드 2207008 - "30초~2분 후 재시도" 권장
3. 토큰 권한: instagram_content_publish scope 필수
4. PPA (Page Publishing Authorization): Facebook 페이지에서 완료 필요
5. 이미지 URL 접근 불가: Instagram 서버가 cURL로 다운로드 실패 (에러코드 9004/2207052)
6. 컨테이너 만료: 24시간 후 만료 (에러코드 24/2207008)
7. 이미지 사양: 8MB 이하, 비율 4:5~1.91:1, 너비 320~1440px, sRGB
"""
import asyncio
import time
import httpx
import logging
from typing import List, Optional
from datetime import datetime

from app.core.config import get_settings
from app.models.models import PublishData

logger = logging.getLogger(__name__)

# ★ 코드 버전 확인용 (서버 시작 시 로그 출력)
logger.info("[Instagram] 서비스 모듈 로드됨 (v2 - JPEG+진단+30s재시도+토큰검증)")


class InstagramService:
    """Instagram Graph API 서비스"""
    
    BASE_URL = "https://graph.facebook.com/v21.0"
    
    # __init__ 제거 — @property로 매 호출마다 최신 토큰 사용 (싱글톤 갱신 버그 수정)
    
    @property
    def access_token(self) -> str:
        return get_settings().instagram_access_token or ""

    @property
    def user_id(self) -> str:
        return get_settings().instagram_user_id or ""
    
    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.user_id)

    async def _api_post(self, url: str, params: dict, timeout: float = 60.0, max_retries: int = 3) -> dict:
        """공통 POST 요청 헬퍼 (일시적 에러 자동 재시도 + 상세 에러 진단)"""
        # 재시도 대상 HTTP 상태 코드 (일시적 서버 에러)
        RETRYABLE_STATUS = {500, 502, 503, 504}
        # 재시도 대상 Instagram API 에러 메시지 패턴
        RETRYABLE_MESSAGES = [
            "an unexpected error",
            "media id is not available",
            "please retry",
            "temporarily unavailable",
        ]
        # 재시도 대상 Meta API 에러 코드
        RETRYABLE_CODES = {2, 4, 17, -1}
        
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, params=params, timeout=timeout)
                    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    
                    if response.status_code == 200:
                        return {"ok": True, "data": data}
                    
                    # ★ 상세 에러 정보 추출 (Meta 공식 에러 응답 구조)
                    err = data.get("error", {})
                    msg = err.get("message", response.text or f"HTTP {response.status_code}")
                    error_code = err.get("code")
                    error_subcode = err.get("error_subcode")
                    error_type = err.get("type", "")
                    is_transient = err.get("is_transient", False)
                    fbtrace_id = err.get("fbtrace_id", "")
                    error_user_msg = err.get("error_user_msg", "")
                    last_error = msg
                    
                    # ★ 상세 에러 로깅 (진단용)
                    logger.error(
                        f"[Instagram] API POST 실패 (시도 {attempt}/{max_retries}): "
                        f"status={response.status_code}, "
                        f"code={error_code}, subcode={error_subcode}, "
                        f"type={error_type}, is_transient={is_transient}, "
                        f"fbtrace_id={fbtrace_id}, "
                        f"message={msg}"
                        + (f", user_msg={error_user_msg}" if error_user_msg else "")
                    )
                    
                    # 재시도 가능한 에러인지 판단
                    is_retryable = response.status_code in RETRYABLE_STATUS or is_transient
                    if not is_retryable and error_code in RETRYABLE_CODES:
                        is_retryable = True
                    if not is_retryable:
                        msg_lower = msg.lower()
                        is_retryable = any(pat in msg_lower for pat in RETRYABLE_MESSAGES)
                    
                    if is_retryable and attempt < max_retries:
                        # ★ Meta 공식 권장: 30초~2분 간격 재시도
                        wait = 30 * attempt  # 30초, 60초, 90초
                        logger.warning(f"[Instagram] → {wait}초 후 재시도 예정")
                        await asyncio.sleep(wait)
                        continue
                    
                    return {
                        "ok": False, 
                        "error": msg, 
                        "error_code": error_code,
                        "error_subcode": error_subcode,
                        "error_type": error_type,
                        "fbtrace_id": fbtrace_id,
                        "error_user_msg": error_user_msg,
                    }
                    
            except httpx.TimeoutException:
                last_error = f"요청 타임아웃 ({timeout}초)"
                if attempt < max_retries:
                    wait = 30 * attempt
                    logger.warning(f"[Instagram] API POST 타임아웃 (시도 {attempt}/{max_retries}) → {wait}초 후 재시도")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[Instagram] API POST 타임아웃 최종 실패: {url}")
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    wait = 15 * attempt
                    logger.warning(f"[Instagram] API POST 예외 (시도 {attempt}/{max_retries}): {e} → {wait}초 후 재시도")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[Instagram] API POST 예외 최종 실패: {e}")
        
        return {"ok": False, "error": last_error}

    async def _api_get(self, url: str, params: dict, timeout: float = 30.0) -> dict:
        """공통 GET 요청 헬퍼"""
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=timeout)
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200:
                return {"ok": True, "data": data}
            err = data.get("error", {})
            msg = err.get("message", response.text or f"HTTP {response.status_code}")
            return {"ok": False, "error": msg}

    # =============================================
    # 발행 전 토큰/권한 사전 검증
    # =============================================

    async def _validate_token_permissions(self) -> tuple[bool, str]:
        """발행 전 토큰 유효성 + 필수 권한(scope) 확인.
        
        Returns:
            (valid: bool, error_message: str) — error_message는 실패 시 구체적 안내 포함
        """
        url = f"{self.BASE_URL}/debug_token"
        params = {"input_token": self.access_token, "access_token": self.access_token}
        
        try:
            result = await self._api_get(url, params)
            if not result["ok"]:
                return False, f"토큰 검증 실패: {result.get('error', '알 수 없음')}"
            
            token_data = result["data"].get("data", {})
            
            # 토큰 유효성
            if not token_data.get("is_valid", False):
                return False, "토큰이 만료되었거나 무효합니다. 설정 페이지에서 토큰을 재발급해주세요."
            
            # 필수 scope 확인
            scopes = token_data.get("scopes", [])
            required_scopes = ["instagram_content_publish", "instagram_basic"]
            missing = [s for s in required_scopes if s not in scopes]
            if missing:
                return False, (
                    f"토큰에 필수 권한이 없습니다: {', '.join(missing)}. "
                    f"현재 권한: {', '.join(scopes)}. "
                    f"Meta 앱 설정에서 Content Publishing 권한을 추가하고 토큰을 재발급해주세요."
                )
            
            # 만료 임박 경고
            expires_at = token_data.get("expires_at", 0)
            if expires_at > 0:
                remaining = expires_at - int(time.time())
                if remaining < 86400:  # 24시간 미만
                    logger.warning(f"[Instagram] 토큰 만료 임박: {remaining // 3600}시간 남음")
            
            logger.info(f"[Instagram] 토큰 검증 통과: scopes={scopes}")
            return True, ""
            
        except Exception as e:
            logger.warning(f"[Instagram] 토큰 검증 예외 (발행은 시도): {e}")
            # 검증 실패해도 발행은 시도 (네트워크 일시 장애 가능)
            return True, ""

    # =============================================
    # 컨테이너 생성
    # =============================================

    async def create_image_container(self, image_url: str, is_carousel_item: bool = True) -> tuple[Optional[str], Optional[str]]:
        """개별 이미지 컨테이너 생성. (container_id, error_message) 반환."""
        if not self.is_configured:
            return None, "Instagram 토큰 또는 USER_ID가 .env에 없습니다."
        
        logger.info(f"[Instagram] 이미지 컨테이너 생성: image_url={image_url[:100]}")
        url = f"{self.BASE_URL}/{self.user_id}/media"
        params = {
            "image_url": image_url,
            "access_token": self.access_token
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"
        try:
            result = await self._api_post(url, params)
            if result["ok"]:
                cid = result["data"].get("id")
                logger.info(f"[Instagram] 이미지 컨테이너 생성 성공: container_id={cid}")
                return cid, None
            # ★ 상세 에러 메시지 구성
            err_detail = result.get("error", "알 수 없음")
            subcode = result.get("error_subcode")
            fbtrace = result.get("fbtrace_id", "")
            extra = ""
            if subcode == 2207052:
                extra = " (Instagram이 이미지 URL에 접근할 수 없습니다. 공개 URL인지 확인하세요)"
            elif subcode == 2207005:
                extra = " (이미지 포맷 미지원. JPEG만 허용됩니다)"
            elif subcode == 2207004:
                extra = " (이미지 크기 초과. 8MB 이하여야 합니다)"
            logger.error(f"[Instagram] 이미지 컨테이너 실패: url={image_url[:80]}, error={err_detail}{extra}")
            return None, f"{err_detail}{extra}" + (f" [fbtrace:{fbtrace}]" if fbtrace else "")
        except Exception as e:
            logger.error(f"[Instagram] 이미지 컨테이너 생성 예외: {e}")
            return None, str(e)
    
    async def create_carousel_container(
        self,
        container_ids: List[str],
        caption: str,
        scheduled_publish_time: Optional[int] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """캐러셀 컨테이너 생성. (carousel_id, error_message) 반환."""
        if not self.is_configured:
            return None, "Instagram 토큰 또는 USER_ID가 .env에 없습니다."
        
        logger.info(f"[Instagram] 캐러셀 컨테이너 생성: children={len(container_ids)}개")
        url = f"{self.BASE_URL}/{self.user_id}/media"
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(container_ids),
            "caption": caption,
            "access_token": self.access_token
        }
        if scheduled_publish_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = str(scheduled_publish_time)
        try:
            result = await self._api_post(url, params)
            if result["ok"]:
                cid = result["data"].get("id")
                logger.info(f"[Instagram] 캐러셀 컨테이너 생성 성공: carousel_id={cid}")
                return cid, None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Instagram] 캐러셀 컨테이너 생성 실패: {e}")
            return None, str(e)

    async def create_single_image_container(
        self,
        image_url: str,
        caption: str,
        scheduled_publish_time: Optional[int] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """단일 이미지 게시물 컨테이너 생성."""
        if not self.is_configured:
            return None, "Instagram 토큰 또는 USER_ID가 .env에 없습니다."
        
        logger.info(f"[Instagram] 단일 이미지 컨테이너 생성: image_url={image_url[:100]}")
        url = f"{self.BASE_URL}/{self.user_id}/media"
        params = {
            "image_url": image_url,
            "caption": caption,
            "access_token": self.access_token
        }
        if scheduled_publish_time:
            params["published"] = "false"
            params["scheduled_publish_time"] = str(scheduled_publish_time)
        try:
            result = await self._api_post(url, params)
            if result["ok"]:
                cid = result["data"].get("id")
                logger.info(f"[Instagram] 단일 이미지 컨테이너 성공: container_id={cid}")
                return cid, None
            err_detail = result.get("error", "알 수 없음")
            subcode = result.get("error_subcode")
            fbtrace = result.get("fbtrace_id", "")
            extra = ""
            if subcode == 2207052:
                extra = " (Instagram이 이미지 URL에 접근할 수 없습니다)"
            elif subcode == 2207005:
                extra = " (이미지 포맷 미지원. JPEG만 허용됩니다)"
            logger.error(f"[Instagram] 단일 이미지 컨테이너 실패: url={image_url[:80]}, error={err_detail}{extra}")
            return None, f"{err_detail}{extra}" + (f" [fbtrace:{fbtrace}]" if fbtrace else "")
        except Exception as e:
            logger.error(f"[Instagram] 단일 이미지 컨테이너 생성 실패: {e}")
            return None, str(e)

    # =============================================
    # 컨테이너 상태 폴링 (Meta 공식 권장)
    # =============================================

    async def _wait_container_ready(self, container_id: str, timeout: int = 300) -> tuple[bool, Optional[str]]:
        """컨테이너가 FINISHED 상태가 될 때까지 폴링.
        
        Meta 공식 문서 권장: 약 1분 간격, 최대 5분.
        
        Returns:
            (ready: bool, error_message: Optional[str])
        """
        elapsed = 0
        interval = 30  # 30초 간격 (Meta 권장 60초와 사용성 사이 타협)
        while elapsed < timeout:
            status = await self.check_container_status(container_id)
            code = status.get("status_code", "")
            logger.info(f"[Instagram] 컨테이너 상태 확인: id={container_id}, status_code={code}, elapsed={elapsed}s")
            
            if code == "FINISHED":
                return True, None
            if code == "ERROR":
                err_detail = status.get("status", "알 수 없는 에러")
                logger.error(f"[Instagram] 컨테이너 처리 실패: {err_detail}")
                return False, f"Instagram 컨테이너 처리 실패: {err_detail}"
            if code == "EXPIRED":
                return False, "컨테이너가 만료되었습니다 (24시간 초과). 다시 시도해주세요."
            if "error" in status:
                logger.warning(f"[Instagram] 상태 확인 에러: {status['error']}")
            
            await asyncio.sleep(interval)
            elapsed += interval
        
        logger.warning(f"[Instagram] 컨테이너 상태 확인 타임아웃 ({timeout}초)")
        return False, f"컨테이너 처리 대기 시간 초과 ({timeout}초). Instagram 서버가 이미지를 처리 중입니다. 잠시 후 다시 시도해주세요."

    # =============================================
    # 발행
    # =============================================

    async def publish_container(self, container_id: str) -> tuple[Optional[str], Optional[str]]:
        """컨테이너 발행 (캐러셀 또는 단일). (media_id, error_message) 반환."""
        if not self.is_configured:
            return None, "Instagram 토큰 또는 USER_ID가 .env에 없습니다."
        url = f"{self.BASE_URL}/{self.user_id}/media_publish"
        params = {
            "creation_id": container_id,
            "access_token": self.access_token
        }
        try:
            result = await self._api_post(url, params, timeout=120.0)
            if result["ok"]:
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Instagram] 발행 실패: {e}")
            return None, str(e)

    # 하위 호환성
    async def publish_carousel(self, carousel_container_id: str) -> tuple[Optional[str], Optional[str]]:
        return await self.publish_container(carousel_container_id)

    # =============================================
    # 상태 확인
    # =============================================

    async def check_container_status(self, container_id: str) -> dict:
        """컨테이너 상태 확인 (FINISHED, IN_PROGRESS, ERROR, EXPIRED 등)"""
        if not self.is_configured:
            return {"error": "미설정"}
        url = f"{self.BASE_URL}/{container_id}"
        params = {
            "fields": "status,status_code",
            "access_token": self.access_token
        }
        try:
            result = await self._api_get(url, params)
            if result["ok"]:
                return result["data"]
            return {"error": result.get("error", "알 수 없음")}
        except Exception as e:
            return {"error": str(e)}

    async def check_token_validity(self) -> dict:
        """액세스 토큰 유효성 확인"""
        if not self.is_configured:
            return {"valid": False, "error": "토큰 또는 USER_ID 미설정"}
        url = f"{self.BASE_URL}/me"
        params = {
            "fields": "id,name",
            "access_token": self.access_token
        }
        try:
            result = await self._api_get(url, params)
            if result["ok"]:
                return {"valid": True, "user": result["data"]}
            return {"valid": False, "error": result.get("error", "")}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    # =============================================
    # 워크플로우 (즉시 발행 / 예약 발행)
    # =============================================

    async def publish_workflow(
        self,
        publish_data: PublishData,
        scheduled_publish_time: Optional[int] = None
    ) -> dict:
        """전체 발행 워크플로우 (토큰 검증 + 컨테이너 상태 폴링 포함).
        
        Args:
            publish_data: 이미지 URL 목록 + 캡션
            scheduled_publish_time: 예약 발행 Unix 타임스탬프 (None이면 즉시 발행)
        """
        if not self.is_configured:
            return {"success": False, "error": "Instagram credentials not configured. .env에 INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID를 설정하세요."}
        
        if not publish_data.images:
            return {"success": False, "error": "발행할 이미지가 없습니다."}
        
        if len(publish_data.images) > 10:
            return {"success": False, "error": "인스타그램 캐러셀은 최대 10장까지 가능합니다."}

        # ★ 발행 전 토큰 검증 (권한 + 유효성)
        valid, err_msg = await self._validate_token_permissions()
        if not valid:
            return {"success": False, "error": err_msg}

        full_caption = publish_data.caption or ""
        if publish_data.hashtags:
            full_caption += "\n\n" + " ".join(publish_data.hashtags)

        is_single = len(publish_data.images) == 1

        try:
            if is_single:
                # 단일 이미지 발행
                container_id, err = await self.create_single_image_container(
                    image_url=publish_data.images[0],
                    caption=full_caption,
                    scheduled_publish_time=scheduled_publish_time
                )
                if err:
                    return {"success": False, "error": f"이미지 컨테이너 실패: {err}"}
            else:
                # 캐러셀 발행 (2~10장)
                container_ids = []
                for idx, image_url in enumerate(publish_data.images):
                    logger.info(f"[Instagram] 캐러셀 아이템 {idx+1}/{len(publish_data.images)} 생성 중...")
                    cid, err = await self.create_image_container(image_url, is_carousel_item=True)
                    if err:
                        return {"success": False, "error": f"이미지 컨테이너 실패 ({idx+1}번째): {err}"}
                    if cid:
                        container_ids.append(cid)
                    else:
                        return {"success": False, "error": f"이미지 컨테이너 ID를 받지 못했습니다 ({idx+1}번째)."}

                container_id, err = await self.create_carousel_container(
                    container_ids, full_caption,
                    scheduled_publish_time=scheduled_publish_time
                )
                if err:
                    return {"success": False, "error": f"캐러셀 생성 실패: {err}"}

            if not container_id:
                return {"success": False, "error": "컨테이너 ID를 받지 못했습니다."}

            # ★ 컨테이너 상태 폴링 (Meta 공식 권장: FINISHED 확인 후 발행, 1분 간격 최대 5분)
            logger.info(f"[Instagram] 컨테이너 상태 폴링 시작: container_id={container_id}")
            ready, poll_err = await self._wait_container_ready(container_id, timeout=300)
            if not ready:
                return {"success": False, "error": poll_err or "컨테이너가 준비되지 않았습니다."}

            # 예약 발행이면 publish 호출 불필요 (자동 발행됨)
            if scheduled_publish_time:
                scheduled_dt = datetime.fromtimestamp(scheduled_publish_time)
                logger.info(f"[Instagram] 예약 발행 등록 완료 → {scheduled_dt.isoformat()}")
                return {
                    "success": True,
                    "scheduled": True,
                    "container_id": container_id,
                    "scheduled_time": scheduled_dt.isoformat(),
                    "image_count": len(publish_data.images)
                }

            # 즉시 발행
            logger.info(f"[Instagram] 즉시 발행 시도: container_id={container_id}")
            media_id, err = await self.publish_container(container_id)
            if err:
                # 사용자 친화적 에러 메시지 + 진단 정보
                err_lower = err.lower()
                if "media id is not available" in err_lower:
                    return {"success": False, "error": "발행 실패: Instagram이 이미지를 아직 처리 중입니다. 잠시 후 다시 시도해주세요. (이미지가 JPEG 포맷인지 확인하세요)"}
                if "unexpected error" in err_lower:
                    return {"success": False, "error": "발행 실패: Instagram 서버 일시적 오류입니다. 잠시 후 다시 시도해주세요."}
                return {"success": False, "error": f"발행 실패: {err}"}
            if not media_id:
                return {"success": False, "error": "발행 후 미디어 ID를 받지 못했습니다."}

            logger.info(f"[Instagram] 즉시 발행 완료 → media_id={media_id}")
            return {
                "success": True,
                "scheduled": False,
                "media_id": media_id,
                "image_count": len(publish_data.images)
            }

        except Exception as e:
            logger.error(f"[Instagram] 발행 워크플로우 오류: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# 싱글톤
_instagram_service: Optional[InstagramService] = None

def get_instagram_service() -> InstagramService:
    global _instagram_service
    if _instagram_service is None:
        _instagram_service = InstagramService()
    return _instagram_service
