"""
Cloudinary 서비스 - 이미지 호스팅 (공식 SDK 기반)
인스타그램 발행을 위해 공개 HTTPS URL 필요

★ Instagram 이미지 요구사항 (Meta 공식):
  - 포맷: JPEG만 지원
  - 크기: 8MB 이하
  - 비율: 4:5 ~ 1.91:1
  - 너비: 320~1440px
  - 색공간: sRGB
"""
import os
import asyncio
import logging
from typing import Optional
from io import BytesIO

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import (
    Error as CloudinaryError,
    BadRequest,
    AuthorizationRequired,
    RateLimited,
    NotFound,
)
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CloudinaryService:
    """Cloudinary 이미지 업로드 서비스 (공식 SDK)"""

    # __init__ 제거 — @property로 매 호출마다 최신 설정 사용 (싱글톤 갱신 버그 수정)

    @property
    def cloud_name(self) -> str:
        return get_settings().cloudinary_cloud_name or ""

    @property
    def api_key(self) -> str:
        return get_settings().cloudinary_api_key or ""

    @property
    def api_secret(self) -> str:
        return get_settings().cloudinary_api_secret or ""

    def _ensure_config(self):
        """매 업로드 호출 전 최신 설정으로 SDK 구성"""
        if self.cloud_name and self.api_key and self.api_secret:
            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                secure=True,
            )

    async def upload_image(self, image: Image.Image, title: str = "") -> Optional[str]:
        """PIL 이미지를 Cloudinary에 업로드하고 secure_url 반환.
        
        ★ Instagram 호환: JPEG 포맷으로 업로드 (Meta 공식 - JPEG only)
        """
        if not self.cloud_name:
            logger.error("[Cloudinary] cloud_name 미설정")
            return None

        self._ensure_config()

        buffer = BytesIO()
        # ★ Instagram은 JPEG만 공식 지원 (Meta 공식 문서)
        # RGBA/P 모드는 JPEG 불가 → RGB 변환
        upload_image = image
        if image.mode in ("RGBA", "P", "LA"):
            upload_image = image.convert("RGB")
        upload_image.save(buffer, format="JPEG", quality=95)
        buffer.seek(0)

        try:
            result = await asyncio.to_thread(
                cloudinary.uploader.upload,
                buffer,
                folder="tax_webtoon",
                resource_type="image",
                format="jpg",  # Cloudinary에도 JPEG 명시
            )
            url = result.get("secure_url")
            logger.info(f"[Cloudinary] PIL 이미지 업로드 성공 (JPEG) → {url}")
            return url
        except BadRequest as e:
            logger.error(f"[Cloudinary] 잘못된 요청: {e}")
        except AuthorizationRequired as e:
            logger.error(f"[Cloudinary] 인증 실패 (API 키 확인): {e}")
        except RateLimited as e:
            logger.error(f"[Cloudinary] 요청 제한 초과: {e}")
        except CloudinaryError as e:
            logger.error(f"[Cloudinary] 업로드 에러: {e}")
        except Exception as e:
            logger.error(f"[Cloudinary] 예상치 못한 에러: {e}")
        return None

    async def upload_from_url(self, image_url: str, title: str = "") -> Optional[str]:
        """URL의 이미지를 Cloudinary에 업로드 (JPEG 변환)"""
        if not self.cloud_name:
            logger.error("[Cloudinary] cloud_name 미설정")
            return None

        self._ensure_config()

        try:
            result = await asyncio.to_thread(
                cloudinary.uploader.upload,
                image_url,
                folder="tax_webtoon",
                resource_type="image",
                format="jpg",  # ★ JPEG 변환 (Instagram 호환)
            )
            url = result.get("secure_url")
            logger.info(f"[Cloudinary] URL 업로드 성공 (JPEG): {image_url[:80]} → {url}")
            return url
        except BadRequest as e:
            logger.error(f"[Cloudinary] URL 업로드 잘못된 요청: {e}")
        except AuthorizationRequired as e:
            logger.error(f"[Cloudinary] URL 업로드 인증 실패: {e}")
        except CloudinaryError as e:
            logger.error(f"[Cloudinary] URL 업로드 에러: {e}")
        except Exception as e:
            logger.error(f"[Cloudinary] URL 업로드 예상치 못한 에러: {e}")
        return None

    async def upload_batch(self, images: list[Image.Image]) -> list[str]:
        """여러 이미지를 순차 업로드"""
        urls = []
        for i, img in enumerate(images):
            url = await self.upload_image(img, f"scene_{i+1}")
            if url:
                urls.append(url)
            else:
                logger.warning(f"[Cloudinary] 배치 업로드 {i+1}번째 실패")
        return urls

    async def upload_from_path(self, file_path: str) -> Optional[str]:
        """로컬 파일 경로에서 직접 Cloudinary에 업로드 후 secure_url 반환 (JPEG 변환)"""
        if not self.cloud_name:
            logger.error("[Cloudinary] cloud_name 미설정")
            return None

        self._ensure_config()

        # 절대/상대 경로 처리
        path = file_path if os.path.isabs(file_path) else os.path.join(os.getcwd(), file_path.lstrip("/\\"))
        if not os.path.isfile(path):
            logger.error(f"[Cloudinary] 파일 없음: {path}")
            return None

        logger.info(f"[Cloudinary] 파일 업로드 시작: {path}")
        try:
            # SDK는 파일 경로를 직접 받을 수 있음 (PIL/base64 변환 불필요)
            result = await asyncio.to_thread(
                cloudinary.uploader.upload,
                path,
                folder="tax_webtoon",
                resource_type="image",
                format="jpg",  # ★ JPEG 변환 (Instagram 호환)
            )
            url = result.get("secure_url")
            logger.info(f"[Cloudinary] 파일 업로드 성공 (JPEG): {path} → {url}")
            return url
        except BadRequest as e:
            logger.error(f"[Cloudinary] 파일 업로드 잘못된 요청 ({path}): {e}")
        except AuthorizationRequired as e:
            logger.error(f"[Cloudinary] 파일 업로드 인증 실패 ({path}): {e}")
        except RateLimited as e:
            logger.error(f"[Cloudinary] 파일 업로드 요청 제한 ({path}): {e}")
        except CloudinaryError as e:
            logger.error(f"[Cloudinary] 파일 업로드 에러 ({path}): {e}")
        except Exception as e:
            logger.error(f"[Cloudinary] 파일 업로드 예상치 못한 에러 ({path}): {e}")
        return None


# 싱글톤
_cloudinary_service: Optional[CloudinaryService] = None


def get_cloudinary_service() -> CloudinaryService:
    global _cloudinary_service
    if _cloudinary_service is None:
        _cloudinary_service = CloudinaryService()
    return _cloudinary_service
