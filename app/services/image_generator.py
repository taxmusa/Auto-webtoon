"""
이미지 생성 서비스
— Gemini (Google GenAI) 단일 모델 사용
"""
from abc import ABC, abstractmethod
import asyncio
import time
from typing import Optional, List, Union
import logging

# 이미지 생성 API 최대 대기 시간 (초)
IMAGE_GENERATION_TIMEOUT = 90

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class ImageGeneratorBase(ABC):
    """이미지 생성 모델의 공통 인터페이스"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        reference_images: Optional[List[bytes]] = None,
        size: str = "1024x1536",
        quality: str = "medium",
        seed: Optional[int] = None
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
# Google Gemini (이미지 생성 전용)
# ────────────────────────────────────────────
class GeminiGenerator(ImageGeneratorBase):
    """Gemini Pro Image — 3종 레퍼런스 + 씬 체이닝 지원"""

    def __init__(self, api_key: str, model: str = "gemini-3-pro-image-preview"):
        if not genai:
            raise ImportError("Google GenAI library is not installed")
        if not api_key:
            raise ValueError("Gemini API 키가 설정되지 않았습니다. .env 파일의 GEMINI_API_KEY를 확인해주세요.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    @staticmethod
    def _extract_image_bytes(raw_data) -> bytes:
        """Gemini inline_data.data에서 실제 이미지 바이트를 추출.

        Google GenAI SDK 버전에 따라 raw bytes 또는 base64 문자열이 반환될 수 있음.
        두 경우 모두 올바르게 처리하여 항상 raw 이미지 bytes를 반환.
        """
        import base64 as b64mod

        # str인 경우 → base64 디코딩
        if isinstance(raw_data, str):
            logger.debug(f"[_extract_image_bytes] str 타입 수신, 길이={len(raw_data)}")
            return b64mod.b64decode(raw_data)

        # bytes인 경우
        if isinstance(raw_data, (bytes, bytearray)):
            # 이미 raw 이미지인지 시그니처로 확인
            if len(raw_data) > 4:
                if raw_data[0] == 0xFF and raw_data[1] == 0xD8:
                    return bytes(raw_data)  # JPEG
                if raw_data[:4] == b'\x89PNG':
                    return bytes(raw_data)  # PNG
                if len(raw_data) > 12 and raw_data[8:12] == b'WEBP':
                    return bytes(raw_data)  # WEBP

            # raw 이미지가 아니면 base64 텍스트일 가능성
            try:
                text = raw_data.decode('ascii')
                decoded = b64mod.b64decode(text)
                logger.debug(f"[_extract_image_bytes] base64 디코딩: {len(raw_data)} → {len(decoded)} bytes")
                return decoded
            except (UnicodeDecodeError, Exception):
                return bytes(raw_data)

        logger.warning(f"[_extract_image_bytes] 예상 외 타입: {type(raw_data)}")
        return raw_data if raw_data else b""

    async def generate(self, prompt, reference_images=None, size="1024x1024", quality="medium", seed=None,
                       method_image=None, style_image=None, prev_scene_image=None, prev_scene_summaries=None,
                       prev_scene_number=None):
        """Gemini 이미지 생성 — 3종 레퍼런스 + 이전 씬 체이닝 지원
        
        Args:
            prompt: 이미지 생성 프롬프트
            reference_images: [bytes] 기존 호환용 (Character CRS 등)
            method_image: bytes — Method.jpg (구도/연출 레퍼런스)
            style_image: bytes — Style.jpg (화풍 레퍼런스)
            prev_scene_image: bytes — 직전 씬 생성 이미지 (체이닝용)
            prev_scene_summaries: List[str] — 이전 씬 텍스트 요약 목록
            prev_scene_number: int — 직전 씬 번호 (라벨 텍스트용)
        """
        t0 = time.time()
        try:
            from PIL import Image
            import io

            # 프롬프트에 레퍼런스/체이닝 지시문 추가
            full_prompt = prompt

            # 3종 레퍼런스 안내 — 프롬프트 내에서 레퍼런스 역할을 명확히 지시
            ref_count = sum(1 for x in [reference_images, method_image, style_image] if x)
            if ref_count > 0:
                ref_note_parts = []
                if reference_images and len(reference_images) > 0:
                    ref_note_parts.append("Character Reference: 캐릭터 외형 유지")
                if method_image:
                    ref_note_parts.append("Method Reference: 구도/앵글 참고")
                if style_image:
                    ref_note_parts.append("Style Reference: 화풍/색감 반드시 적용 (최우선)")
                full_prompt += f"\n\n[첨부 레퍼런스 {ref_count}장: {' | '.join(ref_note_parts)}]"

            # 이전 씬 체이닝 지시문
            if prev_scene_summaries and len(prev_scene_summaries) > 0:
                full_prompt += f"""

---
위 프롬프트가 절대적 1순위입니다. 프롬프트에 명시된 장소·배경·구도·상황을 그대로 생성하세요.
첨부된 직전 장면 이미지는 캐릭터 외형 참고용일 뿐입니다.

이전 장면 흐름(텍스트 참고만):
{chr(10).join(prev_scene_summaries)}"""

            # ★ 콘텐츠 구성: 레퍼런스 이미지(라벨 포함) → 프롬프트 → 이전 씬
            contents = []

            def _to_pil(data):
                """bytes → PIL Image 변환. 이미 PIL Image면 그대로 반환."""
                if isinstance(data, Image.Image):
                    return data
                return Image.open(io.BytesIO(data))

            # 1. Character 레퍼런스 — 캐릭터 외형 고정용
            if reference_images:
                for ref in reference_images:
                    contents.append("[Character Reference] 아래 이미지는 캐릭터 레퍼런스입니다. 이 캐릭터의 얼굴, 헤어스타일, 의상, 체형을 정확히 유지하세요.")
                    contents.append(_to_pil(ref))

            # 2. Method 레퍼런스 — 구도/연출 참조용
            if method_image:
                contents.append("[Method Reference] 아래 이미지는 연출/구도 레퍼런스입니다. 이 이미지의 카메라 앵글, 인물 배치, 구도를 참고하세요.")
                contents.append(_to_pil(method_image))

            # 3. Style 레퍼런스 — 화풍/색감 결정용 (가장 중요)
            if style_image:
                contents.append("[Style Reference — MOST IMPORTANT] 아래 이미지는 화풍 레퍼런스입니다. 반드시 이 이미지의 그림체, 색감, 선화 스타일, 질감을 그대로 적용하세요. 이 화풍을 절대 무시하지 마세요.")
                contents.append(_to_pil(style_image))

            # 4. 프롬프트 텍스트 (레퍼런스 뒤에 배치)
            contents.append(full_prompt)

            # 5. 직전 씬 이미지 (체이닝) — 장면 번호 포함 라벨
            if prev_scene_image:
                sn_label = f"(장면 {prev_scene_number})" if prev_scene_number else ""
                contents.append(f"[Previous Scene{sn_label}] 직전 장면 이미지 — 캐릭터 외형 참고용. 장소/배경은 위 프롬프트를 따를 것.")
                contents.append(_to_pil(prev_scene_image))

            def _sync_generate():
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"]
                    )
                )

            ref_detail = []
            if reference_images: ref_detail.append("Character")
            if method_image: ref_detail.append("Method")
            if style_image: ref_detail.append("Style")
            if prev_scene_image: ref_detail.append("PrevScene")

            # 최대 2회 재시도 (Gemini가 가끔 이미지 없이 응답하는 경우 대비)
            max_attempts = 2
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(_sync_generate),
                        timeout=IMAGE_GENERATION_TIMEOUT
                    )
                    logger.info("Gemini API 응답 %.1f초 (attempt=%d, model=%s, refs=[%s], contents_len=%d)", 
                                time.time() - t0, attempt, self.model,
                                ",".join(ref_detail) if ref_detail else "없음",
                                len(contents))

                    # 응답 분석 및 이미지 추출
                    if not response.candidates:
                        block_reason = getattr(response, 'prompt_feedback', None)
                        logger.warning("Gemini 응답에 candidates 없음 (attempt=%d). prompt_feedback=%s", attempt, block_reason)
                        last_error = f"Gemini가 이미지 생성을 거부했습니다 (안전 필터). feedback={block_reason}"
                        if attempt < max_attempts:
                            await asyncio.sleep(0.3)
                            continue
                        raise ValueError(last_error)

                    candidate = response.candidates[0]
                    finish_reason = getattr(candidate, 'finish_reason', None)
                    
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if part.inline_data:
                                return self._extract_image_bytes(part.inline_data.data)
                        
                        # 이미지가 없고 텍스트만 있는 경우
                        text_parts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                        if text_parts:
                            logger.warning("Gemini가 이미지 대신 텍스트 반환 (attempt=%d): %s", attempt, text_parts[0][:200])
                            last_error = f"Gemini가 이미지 대신 텍스트를 반환했습니다. finish_reason={finish_reason}"
                            if attempt < max_attempts:
                                await asyncio.sleep(0.3)
                                continue
                            raise ValueError(last_error)
                    
                    logger.warning("Gemini 응답에 이미지 없음 (attempt=%d). finish_reason=%s", attempt, finish_reason)
                    last_error = f"Gemini 응답에 이미지가 없습니다 (finish_reason={finish_reason})"
                    if attempt < max_attempts:
                        await asyncio.sleep(0.3)
                        continue
                    raise ValueError(last_error)

                except asyncio.TimeoutError:
                    raise  # 타임아웃은 재시도하지 않음
                except ValueError:
                    if attempt >= max_attempts:
                        raise
                    continue

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
_GEMINI_MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",          # 빠름
    "nano-banana-pro": "gemini-3-pro-image-preview",  # 고품질 (기본)
}


def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    """model_name 을 기반으로 Gemini Generator 인스턴스를 반환"""
    real_model = _GEMINI_MODEL_MAP.get(model_name, model_name)
    return GeminiGenerator(api_key, real_model)
