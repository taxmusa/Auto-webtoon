"""
Cloudinary 서비스 - 이미지 호스팅
인스타그램 발행을 위해 공개 URL 필요
Imgur 대비 API 발급이 훨씬 간단함
"""
import httpx
from typing import Optional
import base64
import hashlib
import time
from io import BytesIO
from PIL import Image

from app.core.config import get_settings


class CloudinaryService:
    """Cloudinary 이미지 업로드 서비스"""
    
    UPLOAD_URL = "https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    
    def __init__(self):
        settings = get_settings()
        self.cloud_name = settings.cloudinary_cloud_name
        self.api_key = settings.cloudinary_api_key
        self.api_secret = settings.cloudinary_api_secret
    
    def _generate_signature(self, params: dict) -> str:
        """API 서명 생성"""
        sorted_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        to_sign = sorted_params + self.api_secret
        return hashlib.sha1(to_sign.encode()).hexdigest()
    
    async def upload_image(self, image: Image.Image, title: str = "") -> Optional[str]:
        """PIL 이미지를 Cloudinary에 업로드하고 URL 반환"""
        if not self.cloud_name or not self.api_key or not self.api_secret:
            return None
        
        # 이미지를 base64로 변환
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        timestamp = str(int(time.time()))
        
        params = {
            "timestamp": timestamp,
            "folder": "tax_webtoon"
        }
        
        signature = self._generate_signature(params)
        
        data = {
            "file": f"data:image/png;base64,{image_base64}",
            "api_key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "folder": "tax_webtoon"
        }
        
        url = self.UPLOAD_URL.format(cloud_name=self.cloud_name)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data, timeout=60.0)
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("secure_url")
                return None
                
            except Exception:
                return None
    
    async def upload_from_url(self, image_url: str, title: str = "") -> Optional[str]:
        """URL의 이미지를 Cloudinary에 업로드"""
        if not self.cloud_name or not self.api_key or not self.api_secret:
            return None
        
        timestamp = str(int(time.time()))
        
        params = {
            "timestamp": timestamp,
            "folder": "tax_webtoon"
        }
        
        signature = self._generate_signature(params)
        
        data = {
            "file": image_url,
            "api_key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "folder": "tax_webtoon"
        }
        
        url = self.UPLOAD_URL.format(cloud_name=self.cloud_name)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data, timeout=60.0)
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("secure_url")
                return None
                
            except Exception:
                return None
    
    async def upload_batch(self, images: list[Image.Image]) -> list[str]:
        """여러 이미지를 순차 업로드"""
        urls = []
        for i, img in enumerate(images):
            url = await self.upload_image(img, f"scene_{i+1}")
            if url:
                urls.append(url)
        return urls


# 싱글톤
_cloudinary_service: Optional[CloudinaryService] = None

def get_cloudinary_service() -> CloudinaryService:
    global _cloudinary_service
    if _cloudinary_service is None:
        _cloudinary_service = CloudinaryService()
    return _cloudinary_service
