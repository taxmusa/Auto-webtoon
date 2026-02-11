from abc import ABC, abstractmethod
import asyncio
import os
import time
from typing import Optional, List, Union
import logging

import httpx  # requirements.txt 에 이미 포함

# 이미지 생성 API 최대 대기 시간 (초)
IMAGE_GENERATION_TIMEOUT = 90  # 90초로 단축 (URL 방식은 더 빠름)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class ImageGeneratorBase(ABC):
    """모든 이미지 생성 모델의 공통 인터페이스"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        reference_images: Optional[List[bytes]] = None,
        size: str = "1024x1536",
        quality: str = "medium"
    ) -> Union[bytes, str]:
        pass

    @abstractmethod
    async def edit_with_reference(
        self,
        prompt: str,
        reference_image: bytes,
        size: str = "1024x1536"
    ) -> bytes:
        pass


# ────────────────────────────────────────────
# OpenAI (DALL-E 2/3, GPT Image 1 계열)
# ────────────────────────────────────────────
class OpenAIGenerator(ImageGeneratorBase):
    """GPT Image 1 Mini / 1 / 1.5 / DALL-E 3 / DALL-E 2"""

    # 실제 API 에 보낼 모델 이름. 존재하지 않는 모델이면 OpenAI 가 에러를 내므로
    # 여기서 매핑하지 않고 그대로 전달한다. (2026-02 기준 gpt-image-1 등 신규 모델 지원)
    def __init__(self, api_key: str, model: str = "gpt-image-1-mini"):
        if not OpenAI:
            raise ImportError("OpenAI library is not installed")
        if not api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다. .env 파일의 OPENAI_API_KEY를 확인해주세요.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    # dall-e 계열("standard"/"hd") → gpt-image 계열("low"/"medium"/"high") 매핑
    _GPT_IMG_QUALITY = {"standard": "medium", "hd": "high", "low": "low", "medium": "medium", "high": "high"}
    # gpt-image 허용 사이즈
    _GPT_IMG_SIZES = {"1024x1024", "1024x1536", "1536x1024"}
    # dall-e-2 허용 사이즈
    _DALLE2_SIZES = {"256x256", "512x512", "1024x1024"}

    async def generate(self, prompt, reference_images=None, size="1024x1024", quality="standard"):
        """
        모델에 따라 적절한 파라미터로 이미지 생성.
        ─ gpt-image-1 계열: size, quality, output_format 지원 / response_format 미지원
        ─ dall-e-3         : size, quality, response_format 지원
        ─ dall-e-2         : size, response_format 지원 / quality 미지원
        """
        import base64
        t0 = time.time()

        is_gpt_image = self.model.startswith("gpt-image")
        is_dalle2 = (self.model == "dall-e-2")

        def _sync_generate():
            params = dict(
                model=self.model,
                prompt=prompt,
                n=1,
            )
            if is_gpt_image:
                # gpt-image 계열: size, quality, output_format 지원
                # response_format 은 미지원 (항상 b64_json 반환)
                params["size"] = size if size in self._GPT_IMG_SIZES else "1024x1024"
                params["quality"] = self._GPT_IMG_QUALITY.get(quality, "medium")
                params["output_format"] = "webp"  # PNG 대비 5~10배 작아 전송 빠름
            elif is_dalle2:
                # DALL-E 2: quality 파라미터 미지원
                params["size"] = size if size in self._DALLE2_SIZES else "1024x1024"
                params["response_format"] = "url"
            else:
                # dall-e-3: size, quality, response_format 모두 지원
                params["size"] = size
                params["quality"] = quality
                params["response_format"] = "url"

            logger.info("OpenAI API 호출 파라미터: %s", {k: v for k, v in params.items() if k != "prompt"})
            return self.client.images.generate(**params)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_generate),
                timeout=IMAGE_GENERATION_TIMEOUT
            )
            t_api = time.time() - t0
            logger.info("OpenAI API 응답 %.1f초 (model=%s)", t_api, self.model)

            result_data = response.data[0]

            # gpt-image 계열은 b64_json 으로 반환
            if hasattr(result_data, "b64_json") and result_data.b64_json:
                image_bytes = base64.b64decode(result_data.b64_json)
                logger.info("b64 디코딩 완료 (총 %.1f초, %dKB)", time.time() - t0, len(image_bytes) // 1024)
                return image_bytes

            # dall-e 계열은 URL 반환 → 다운로드
            if hasattr(result_data, "url") and result_data.url:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    dl = await client.get(result_data.url)
                    dl.raise_for_status()
                logger.info("이미지 다운로드 완료 (총 %.1f초, %dKB)", time.time() - t0, len(dl.content) // 1024)
                return dl.content

            raise ValueError("OpenAI 응답에서 이미지를 찾을 수 없습니다.")

        except asyncio.TimeoutError:
            elapsed = time.time() - t0
            logger.error("OpenAI 이미지 생성 타임아웃 (%.0f초, 제한 %ss)", elapsed, IMAGE_GENERATION_TIMEOUT)
            raise TimeoutError(
                f"이미지 생성이 {IMAGE_GENERATION_TIMEOUT}초 안에 완료되지 않았습니다. "
                "네트워크나 API 상태를 확인한 뒤 다시 시도해주세요."
            )
        except Exception as e:
            logger.error("OpenAI Image Generation Failed (%.1f초): %s", time.time() - t0, e)
            raise

    async def edit_with_reference(self, prompt, reference_image, size="1024x1024"):
        pass


# ────────────────────────────────────────────
# Google Gemini (Nano Banana 계열)
# ────────────────────────────────────────────
class GeminiGenerator(ImageGeneratorBase):
    """Nano Banana / Nano Banana Pro (via Google GenAI)"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        if not genai:
            raise ImportError("Google GenAI library is not installed")
        if not api_key:
            raise ValueError("Gemini API 키가 설정되지 않았습니다. .env 파일의 GEMINI_API_KEY를 확인해주세요.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate(self, prompt, reference_images=None, size="1024x1024", quality="medium"):
        t0 = time.time()
        try:
            contents = [prompt]
            if reference_images:
                from PIL import Image
                import io
                for ref_bytes in reference_images:
                    img = Image.open(io.BytesIO(ref_bytes))
                    contents.append(img)

            def _sync_generate():
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"]
                    )
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_generate),
                timeout=IMAGE_GENERATION_TIMEOUT
            )
            logger.info("Gemini API 응답 %.1f초 (model=%s)", time.time() - t0, self.model)

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        return part.inline_data.data
            raise ValueError("No image found in Gemini response")

        except asyncio.TimeoutError:
            logger.error("Gemini 이미지 생성 타임아웃 (%.0f초)", time.time() - t0)
            raise TimeoutError(
                f"이미지 생성이 {IMAGE_GENERATION_TIMEOUT}초 안에 완료되지 않았습니다. "
                "네트워크나 API 상태를 확인한 뒤 다시 시도해주세요."
            )
        except Exception as e:
            logger.error("Gemini Image Generation Failed (%.1f초): %s", time.time() - t0, e)
            raise

    async def edit_with_reference(self, prompt, reference_image, size="1024x1024"):
        return await self.generate(prompt, reference_images=[reference_image], size=size)


# ────────────────────────────────────────────
# 팩토리
# ────────────────────────────────────────────
# UI 에서 선택하는 모델 이름 → 실제 API 모델 이름 매핑
# 2026-02-11 ListModels 실제 테스트로 검증 완료
_GEMINI_MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",        # 빠름, 이미지 생성 확인됨
    "nano-banana-pro": "nano-banana-pro-preview",    # 고품질, 이미지 생성 확인됨
}


def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    """model_name 을 기반으로 적절한 Generator 인스턴스를 반환"""
    if "gpt" in model_name or "dall-e" in model_name:
        return OpenAIGenerator(api_key, model_name)
    elif "nano" in model_name or "gemini" in model_name:
        real_model = _GEMINI_MODEL_MAP.get(model_name, model_name)
        return GeminiGenerator(api_key, real_model)
    else:
        return OpenAIGenerator(api_key, model_name)
