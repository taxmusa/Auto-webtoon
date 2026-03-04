"""
이미지 생성 서비스
— Gemini (Google GenAI) 단일 모델 사용
— 워터마크 자동 제거 포함
"""
from abc import ABC, abstractmethod
import asyncio
import time
from typing import Optional, List, Union
import logging

from app.services.pillow_service import PillowService

# 이미지 생성 API 최대 대기 시간 (초) — config.py에서 중앙 관리
from app.core.config import (
    IMAGE_GENERATION_TIMEOUT,
    MODEL_ALIAS_MAP,
    DEFAULT_IMAGE_MODEL,
)

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
        quality: str = "medium",
        seed: Optional[int] = None
    ) -> Union[bytes, str]:
        pass

    @abstractmethod
    async def edit_with_reference(
        self,
        prompt: str,
        reference_image: bytes
    ) -> bytes:
        pass


# ────────────────────────────────────────────
# Google Gemini (이미지 생성 전용)
# ────────────────────────────────────────────
class GeminiGenerator(ImageGeneratorBase):
    """Gemini Pro Image — 3종 레퍼런스 + 씬 체이닝 지원"""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-image-preview"):
        if not genai:
            raise ImportError("Google GenAI library is not installed")
        if not api_key:
            raise ValueError("Gemini API 키가 설정되지 않았습니다. .env 파일의 GEMINI_API_KEY를 확인해주세요.")
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=180_000)  # 180초 (밀리초 단위)
        )
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

    async def generate(self, prompt, reference_images=None, quality="medium", seed=None,
                       method_image=None, style_image=None, prev_scene_image=None, prev_scene_summaries=None,
                       prev_scene_number=None, aspect_ratio=None):
        """Gemini 이미지 생성 — 3종 레퍼런스 + 이전 씬 체이닝 지원
        
        Args:
            prompt: 이미지 생성 프롬프트
            reference_images: [bytes] 기존 호환용 (Character CRS 등)
            method_image: bytes — Method.jpg (구도/연출 레퍼런스)
            style_image: bytes — Style.jpg (화풍 레퍼런스)
            prev_scene_image: bytes — 직전 씬 생성 이미지 (체이닝용)
            prev_scene_summaries: List[str] — 이전 씬 텍스트 요약 목록
            prev_scene_number: int — 직전 씬 번호 (라벨 텍스트용)
            aspect_ratio: str — 이미지 비율 ("4:5", "9:16", "1:1" 등, Gemini 공식 지원)
        """
        t0 = time.time()
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

        # ★ 콘텐츠 구성 (toonstoons 참조):
        #   프롬프트 텍스트 → 레퍼런스 이미지 → 이전 씬 이미지
        #   텍스트를 먼저 배치하면 모델이 의도를 먼저 파악 → 이미지 생성 성공률 향상
        contents = []

        def _to_part(data):
            """이미지 데이터 → types.Part (JPEG bytes 직접 전달).
            SDK의 PIL→PNG 재인코딩을 우회하여 전송량 80% 감소."""
            if isinstance(data, bytes):
                return types.Part.from_bytes(data=data, mime_type="image/jpeg")
            # PIL Image가 들어온 경우 JPEG bytes로 변환
            from PIL import Image as PILImage
            if isinstance(data, PILImage.Image):
                buf = io.BytesIO()
                rgb = data.convert("RGB") if data.mode != "RGB" else data
                rgb.save(buf, format="JPEG", quality=85)
                return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
            # 예외: 그 외 타입은 그대로 전달 (텍스트 등)
            return data

        # responseModalities + ImageConfig(aspect_ratio) 설정
        _gen_config_kwargs = {"response_modalities": ["TEXT", "IMAGE"]}
        if aspect_ratio:
            _gen_config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect_ratio)
            logger.info(f"[Gemini] aspect_ratio={aspect_ratio} ImageConfig로 전달")

        # 1. 프롬프트 텍스트 (가장 먼저 — 모델이 의도를 먼저 이해)
        contents.append(full_prompt)

        # 2. 레퍼런스 이미지들 (각 이미지 앞에 역할 라벨 — 모델이 용도 구분)
        if reference_images:
            contents.append("[Character Reference] 캐릭터 외형(얼굴, 체형, 의상)을 이 이미지와 동일하게 유지하세요.")
            for ref in reference_images:
                contents.append(_to_part(ref))

        if method_image:
            contents.append("[Method Reference] 구도와 앵글을 참고하세요.")
            contents.append(_to_part(method_image))

        if style_image:
            contents.append("[Style Reference] 이 화풍과 색감을 적용하세요.")
            contents.append(_to_part(style_image))

        # 3. 직전 씬 이미지 (체이닝) — 캐릭터 외형 참고용
        if prev_scene_image:
            sn_label = f"(장면 {prev_scene_number})" if prev_scene_number else ""
            contents.append(f"[보조 참고] 직전 장면{sn_label} 이미지 - 캐릭터 외형 참고용. 장소/배경은 현재 프롬프트를 따를 것")
            contents.append(_to_part(prev_scene_image))

        def _sync_generate():
            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(**_gen_config_kwargs)
            )

        ref_detail = []
        if reference_images: ref_detail.append("Character")
        if method_image: ref_detail.append("Method")
        if style_image: ref_detail.append("Style")
        if prev_scene_image: ref_detail.append("PrevScene")

        # ★ 단일 루프 재시도 — 최대 2회 (첫 시도 + 재시도 1회)
        import random
        MAX_RETRIES = 2
        RETRY_DELAYS = [3]  # 503/429일 때만 3초 후 1회 재시도

        def _classify_error(exc):
            """에러 타입 분류"""
            err_str = str(exc).lower()
            if "429" in err_str or "rate" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                return "rate_limit"
            if "504" in err_str or "503" in err_str or "unavailable" in err_str or "cancelled" in err_str:
                return "server_error"
            if "safety" in err_str or "block" in err_str or "refused" in err_str:
                return "safety_filter"
            return "server_error"

        last_error = None
        error_type = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(_sync_generate),
                    timeout=IMAGE_GENERATION_TIMEOUT
                )
                logger.info("Gemini API 응답 %.1f초 (attempt=%d/%d, model=%s, refs=[%s])",
                            time.time() - t0, attempt, MAX_RETRIES, self.model,
                            ",".join(ref_detail) if ref_detail else "없음")

                # 응답 분석 및 이미지 추출
                if not response.candidates:
                    block_reason = getattr(response, 'prompt_feedback', None)
                    logger.warning("Gemini candidates 없음 (attempt=%d). feedback=%s", attempt, block_reason)
                    last_error = f"Gemini가 이미지 생성을 거부했습니다 (안전 필터). feedback={block_reason}"
                    error_type = "safety_filter"
                    raise ValueError(last_error)

                candidate = response.candidates[0]
                finish_reason = getattr(candidate, 'finish_reason', None)

                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            raw_bytes = self._extract_image_bytes(part.inline_data.data)
                            # Gemini sparkle 워터마크 자동 제거
                            return PillowService.remove_gemini_watermark(raw_bytes)

                    # TEXT+IMAGE 모드에서 텍스트만 온 경우
                    text_parts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                    if text_parts:
                        logger.warning("Gemini가 텍스트만 반환 (attempt=%d): %s", attempt, text_parts[0][:200])

                last_error = f"Gemini 응답에 이미지 없음 (finish_reason={finish_reason})"
                error_type = "content_empty"
                raise ValueError(last_error)

            except (asyncio.TimeoutError, TimeoutError) as e:
                error_type = "timeout"
                last_error = str(e)
                logger.warning("Gemini 타임아웃 (attempt=%d/%d, %.0f초)", attempt, MAX_RETRIES, time.time() - t0)
                break  # 타임아웃은 재시도 불가 (서버 상태 동일)
            except ValueError:
                pass  # last_error와 error_type은 위에서 설정됨
            except Exception as e:
                error_type = _classify_error(e)
                last_error = str(e)
                logger.warning("Gemini 에러 [%s] (attempt=%d/%d): %s", error_type, attempt, MAX_RETRIES, e)

            # 안전 필터/타임아웃은 재시도 불가
            if error_type in ("safety_filter", "timeout"):
                break

            # 재시도 가능한 경우: 대기 후 재시도
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1] * random.uniform(0.7, 1.3)
                logger.info("[재시도] %s → %.1f초 후 재시도 (%d/%d)", error_type, delay, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(delay)

        # 모든 시도 실패
        logger.warning("[Gemini] %s 모든 시도 실패 (%.0f초, type=%s)", self.model, time.time() - t0, error_type or "unknown")

        # ★ 사용자 친화적 에러 메시지
        if error_type == "timeout":
            raise TimeoutError("이미지 생성이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.")

        err_str = (last_error or "").lower()
        if "429" in err_str or "rate" in err_str or "quota" in err_str:
            friendly = "Gemini API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
        elif "504" in err_str or "503" in err_str or "unavailable" in err_str:
            friendly = "Gemini 서버가 일시적으로 바쁩니다. 잠시 후 다시 시도해주세요."
        elif "safety" in err_str or "block" in err_str:
            friendly = "안전 필터에 의해 이미지 생성이 거부되었습니다. 프롬프트를 수정해주세요."
        else:
            friendly = last_error or "이미지 생성에 실패했습니다."
        logger.error("Gemini Image Generation Failed (%.1f초, type=%s): %s", time.time() - t0, error_type or "unknown", last_error)
        raise RuntimeError(friendly)

    async def edit_with_reference(self, prompt, reference_image):
        return await self.generate(prompt, reference_images=[reference_image])


# ────────────────────────────────────────────
# 대체 모델 매핑 — 비활성화됨
# (gemini-2.5-flash-image fallback이 워터마크를 추가하는 문제)
# ────────────────────────────────────────────
_IMAGE_MODEL_FALLBACKS = {}  # 워터마크 방지를 위해 비활성화

# ────────────────────────────────────────────
# 팩토리
# ────────────────────────────────────────────
_generator_cache: dict[str, GeminiGenerator] = {}

def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    """model_name 을 기반으로 Gemini Generator 인스턴스를 반환 (동일 키+모델은 캐싱).
    빈 model_name이면 기본 이미지 모델(config.DEFAULT_IMAGE_MODEL) 사용."""
    if not model_name:
        real_model = DEFAULT_IMAGE_MODEL
    else:
        real_model = MODEL_ALIAS_MAP.get(model_name, model_name)
    cache_key = f"{api_key}:{real_model}"
    if cache_key not in _generator_cache:
        _generator_cache[cache_key] = GeminiGenerator(api_key, real_model)
    return _generator_cache[cache_key]
