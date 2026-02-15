"""
Threads 서비스 - Meta Threads API 연동
Instagram 발행과 동시에 Threads에도 자동 게시

API Docs: https://developers.facebook.com/docs/threads
Base URL: https://graph.threads.net/v1.0
"""
import asyncio
import logging
import httpx
from typing import List, Optional
from datetime import datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ThreadsService:
    """Meta Threads API 서비스"""

    BASE_URL = "https://graph.threads.net/v1.0"

    def __init__(self):
        settings = get_settings()
        # Threads는 Instagram과 같은 Facebook OAuth 토큰 사용 가능
        # 단, threads_basic + threads_content_publish 권한 필요
        self.access_token = getattr(settings, "threads_access_token", None) or getattr(settings, "instagram_access_token", None)
        self.user_id = getattr(settings, "threads_user_id", None) or getattr(settings, "instagram_user_id", None)

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.user_id)

    async def _api_post(self, url: str, params: dict, timeout: float = 60.0) -> dict:
        """공통 POST 헬퍼"""
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, timeout=timeout)
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200:
                return {"ok": True, "data": data}
            err = data.get("error", {})
            msg = err.get("message", response.text or f"HTTP {response.status_code}")
            return {"ok": False, "error": msg, "error_code": err.get("code")}

    async def _api_get(self, url: str, params: dict, timeout: float = 15.0) -> dict:
        """공통 GET 헬퍼"""
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=timeout)
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200:
                return {"ok": True, "data": data}
            err = data.get("error", {})
            return {"ok": False, "error": err.get("message", response.text)}

    # =============================================
    # 토큰 / 상태 확인
    # =============================================

    async def check_connection(self) -> dict:
        """Threads API 연결 상태 확인"""
        if not self.is_configured:
            return {"ok": False, "error": "Threads 토큰 또는 USER_ID 미설정"}
        
        # Threads 프로필 조회
        result = await self._api_get(
            f"{self.BASE_URL}/me",
            params={
                "fields": "id,username,threads_profile_picture_url",
                "access_token": self.access_token
            }
        )
        if result["ok"]:
            return {
                "ok": True,
                "username": result["data"].get("username", ""),
                "user_id": result["data"].get("id", "")
            }
        return {"ok": False, "error": result.get("error", "알 수 없는 오류")}

    async def check_rate_limit(self) -> dict:
        """발행 제한 확인 (24시간 내 250개)"""
        if not self.is_configured:
            return {"error": "미설정"}
        result = await self._api_get(
            f"{self.BASE_URL}/{self.user_id}/threads_publishing_limit",
            params={
                "fields": "quota_usage,config",
                "access_token": self.access_token
            }
        )
        if result["ok"]:
            data = result["data"].get("data", [{}])[0] if result["data"].get("data") else {}
            return {
                "quota_usage": data.get("quota_usage", 0),
                "quota_total": data.get("config", {}).get("quota_total", 250),
            }
        return {"error": result.get("error")}

    # =============================================
    # 컨테이너 생성
    # =============================================

    async def create_image_container(
        self,
        image_url: str,
        is_carousel_item: bool = False,
        text: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """이미지 컨테이너 생성. (container_id, error) 반환."""
        if not self.is_configured:
            return None, "Threads 미설정"

        params = {
            "media_type": "IMAGE",
            "image_url": image_url,
            "access_token": self.access_token,
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"
        if text and not is_carousel_item:
            params["text"] = text

        try:
            result = await self._api_post(f"{self.BASE_URL}/{self.user_id}/threads", params)
            if result["ok"]:
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Threads] 이미지 컨테이너 생성 실패: {e}")
            return None, str(e)

    async def create_carousel_container(
        self,
        children_ids: List[str],
        text: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """캐러셀 컨테이너 생성. (container_id, error) 반환."""
        if not self.is_configured:
            return None, "Threads 미설정"

        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "access_token": self.access_token,
        }
        if text:
            params["text"] = text

        try:
            result = await self._api_post(f"{self.BASE_URL}/{self.user_id}/threads", params)
            if result["ok"]:
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Threads] 캐러셀 컨테이너 생성 실패: {e}")
            return None, str(e)

    # =============================================
    # 발행
    # =============================================

    async def publish_container(self, container_id: str) -> tuple[Optional[str], Optional[str]]:
        """컨테이너 발행. (media_id, error) 반환.
        
        주의: 컨테이너 생성 후 최소 30초 대기 후 호출 권장.
        """
        if not self.is_configured:
            return None, "Threads 미설정"

        try:
            result = await self._api_post(
                f"{self.BASE_URL}/{self.user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
                timeout=120.0
            )
            if result["ok"]:
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Threads] 발행 실패: {e}")
            return None, str(e)

    # =============================================
    # 통합 발행 워크플로우
    # =============================================

    async def publish_workflow(
        self,
        image_urls: List[str],
        caption: str = "",
        wait_seconds: int = 5
    ) -> dict:
        """Threads 발행 워크플로우.
        
        Args:
            image_urls: 공개 이미지 URL 목록
            caption: 텍스트 캡션 (500자 제한)
            wait_seconds: 컨테이너 생성 후 발행까지 대기 시간
        """
        if not self.is_configured:
            return {"success": False, "error": "Threads 토큰이 설정되지 않았습니다. .env에 THREADS_ACCESS_TOKEN을 설정하세요."}

        if not image_urls:
            return {"success": False, "error": "발행할 이미지가 없습니다."}

        # Threads 캡션 500자 제한
        threads_caption = caption[:500] if caption else ""

        try:
            is_single = len(image_urls) == 1

            if is_single:
                # 단일 이미지 발행
                container_id, err = await self.create_image_container(
                    image_url=image_urls[0],
                    text=threads_caption
                )
                if err:
                    return {"success": False, "error": f"Threads 컨테이너 실패: {err}"}
            else:
                # 캐러셀 (2~20장)
                if len(image_urls) > 20:
                    image_urls = image_urls[:20]
                    logger.warning("[Threads] 이미지 20장 초과 → 20장으로 제한")

                children_ids = []
                for url in image_urls:
                    cid, err = await self.create_image_container(url, is_carousel_item=True)
                    if err:
                        return {"success": False, "error": f"Threads 자식 컨테이너 실패: {err}"}
                    children_ids.append(cid)

                container_id, err = await self.create_carousel_container(
                    children_ids, text=threads_caption
                )
                if err:
                    return {"success": False, "error": f"Threads 캐러셀 실패: {err}"}

            if not container_id:
                return {"success": False, "error": "Threads 컨테이너 ID 없음"}

            # Threads는 컨테이너 생성 후 최소 30초 대기 권장
            # 실제로는 5~10초로도 충분한 경우가 많음
            logger.info(f"[Threads] 컨테이너 처리 대기 중... ({wait_seconds}초)")
            await asyncio.sleep(wait_seconds)

            # 발행
            media_id, err = await self.publish_container(container_id)
            if err:
                # 첫 시도 실패 → 30초 더 대기 후 재시도
                logger.warning(f"[Threads] 1차 발행 실패, 30초 대기 후 재시도: {err}")
                await asyncio.sleep(30)
                media_id, err = await self.publish_container(container_id)
                if err:
                    return {"success": False, "error": f"Threads 발행 실패 (재시도 후): {err}"}

            logger.info(f"[Threads] 발행 완료! media_id={media_id}")
            return {
                "success": True,
                "media_id": media_id,
                "image_count": len(image_urls),
                "platform": "threads"
            }

        except Exception as e:
            logger.error(f"[Threads] 발행 워크플로우 오류: {e}")
            return {"success": False, "error": str(e)}


# 싱글톤
_threads_service: Optional[ThreadsService] = None

def get_threads_service() -> ThreadsService:
    global _threads_service
    if _threads_service is None:
        _threads_service = ThreadsService()
    return _threads_service
