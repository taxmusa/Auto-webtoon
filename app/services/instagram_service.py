"""
Instagram 서비스 - Graph API 연동
캐러셀 발행 + 단일 이미지 발행 + 예약 발행
"""
import httpx
import logging
from typing import List, Optional
from datetime import datetime

from app.core.config import get_settings
from app.models.models import PublishData

logger = logging.getLogger(__name__)


class InstagramService:
    """Instagram Graph API 서비스"""
    
    BASE_URL = "https://graph.facebook.com/v21.0"
    
    def __init__(self):
        settings = get_settings()
        self.access_token = settings.instagram_access_token
        self.user_id = settings.instagram_user_id
    
    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.user_id)

    async def _api_post(self, url: str, params: dict, timeout: float = 60.0) -> dict:
        """공통 POST 요청 헬퍼"""
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, timeout=timeout)
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200:
                return {"ok": True, "data": data}
            err = data.get("error", {})
            msg = err.get("message", response.text or f"HTTP {response.status_code}")
            return {"ok": False, "error": msg, "error_code": err.get("code")}

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
    # 컨테이너 생성
    # =============================================

    async def create_image_container(self, image_url: str, is_carousel_item: bool = True) -> tuple[Optional[str], Optional[str]]:
        """개별 이미지 컨테이너 생성. (container_id, error_message) 반환."""
        if not self.is_configured:
            return None, "Instagram 토큰 또는 USER_ID가 .env에 없습니다."
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
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Instagram] 이미지 컨테이너 생성 실패: {e}")
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
                return result["data"].get("id"), None
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
                return result["data"].get("id"), None
            return None, result["error"]
        except Exception as e:
            logger.error(f"[Instagram] 단일 이미지 컨테이너 생성 실패: {e}")
            return None, str(e)

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
        """컨테이너 상태 확인 (FINISHED, IN_PROGRESS, ERROR 등)"""
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
        """전체 발행 워크플로우.
        
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
                for image_url in publish_data.images:
                    cid, err = await self.create_image_container(image_url, is_carousel_item=True)
                    if err:
                        return {"success": False, "error": f"이미지 컨테이너 실패: {err}"}
                    if cid:
                        container_ids.append(cid)
                    else:
                        return {"success": False, "error": "이미지 컨테이너 ID를 받지 못했습니다."}

                container_id, err = await self.create_carousel_container(
                    container_ids, full_caption,
                    scheduled_publish_time=scheduled_publish_time
                )
                if err:
                    return {"success": False, "error": f"캐러셀 생성 실패: {err}"}

            if not container_id:
                return {"success": False, "error": "컨테이너 ID를 받지 못했습니다."}

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
            media_id, err = await self.publish_container(container_id)
            if err:
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
            logger.error(f"[Instagram] 발행 워크플로우 오류: {e}")
            return {"success": False, "error": str(e)}


# 싱글톤
_instagram_service: Optional[InstagramService] = None

def get_instagram_service() -> InstagramService:
    global _instagram_service
    if _instagram_service is None:
        _instagram_service = InstagramService()
    return _instagram_service
