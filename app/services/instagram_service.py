"""
Instagram 서비스 - Graph API 연동
캐러셀 발행
"""
import httpx
from typing import List, Optional
from datetime import datetime

from app.core.config import get_settings
from app.models.models import PublishData


class InstagramService:
    """Instagram Graph API 서비스"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        settings = get_settings()
        self.access_token = settings.instagram_access_token
        self.user_id = settings.instagram_user_id
    
    async def create_image_container(self, image_url: str) -> Optional[str]:
        """개별 이미지 컨테이너 생성"""
        if not self.access_token or not self.user_id:
            return None
        
        url = f"{self.BASE_URL}/{self.user_id}/media"
        params = {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": self.access_token
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, params=params, timeout=60.0)
                if response.status_code == 200:
                    return response.json().get("id")
                return None
            except Exception:
                return None
    
    async def create_carousel_container(
        self,
        container_ids: List[str],
        caption: str
    ) -> Optional[str]:
        """캐러셀 컨테이너 생성"""
        if not self.access_token or not self.user_id:
            return None
        
        url = f"{self.BASE_URL}/{self.user_id}/media"
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(container_ids),
            "caption": caption,
            "access_token": self.access_token
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, params=params, timeout=60.0)
                if response.status_code == 200:
                    return response.json().get("id")
                return None
            except Exception:
                return None
    
    async def publish_carousel(self, carousel_container_id: str) -> Optional[str]:
        """캐러셀 발행"""
        if not self.access_token or not self.user_id:
            return None
        
        url = f"{self.BASE_URL}/{self.user_id}/media_publish"
        params = {
            "creation_id": carousel_container_id,
            "access_token": self.access_token
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, params=params, timeout=60.0)
                if response.status_code == 200:
                    return response.json().get("id")
                return None
            except Exception:
                return None
    
    async def publish_workflow(self, publish_data: PublishData) -> dict:
        """전체 캐러셀 발행 워크플로우"""
        if not self.access_token or not self.user_id:
            return {"success": False, "error": "Instagram credentials not configured"}
        
        if len(publish_data.images) > 10:
            return {"success": False, "error": "Maximum 10 images per carousel"}
        
        # 1. 각 이미지의 미디어 컨테이너 생성
        container_ids = []
        for image_url in publish_data.images:
            container_id = await self.create_image_container(image_url)
            if container_id:
                container_ids.append(container_id)
            else:
                return {"success": False, "error": f"Failed to create container for {image_url}"}
        
        # 2. 캐러셀 컨테이너 생성
        full_caption = publish_data.caption
        if publish_data.hashtags:
            full_caption += "\n\n" + " ".join(publish_data.hashtags)
        
        carousel_id = await self.create_carousel_container(container_ids, full_caption)
        if not carousel_id:
            return {"success": False, "error": "Failed to create carousel container"}
        
        # 3. 발행
        media_id = await self.publish_carousel(carousel_id)
        if not media_id:
            return {"success": False, "error": "Failed to publish carousel"}
        
        return {"success": True, "media_id": media_id}


# 싱글톤
_instagram_service: Optional[InstagramService] = None

def get_instagram_service() -> InstagramService:
    global _instagram_service
    if _instagram_service is None:
        _instagram_service = InstagramService()
    return _instagram_service
