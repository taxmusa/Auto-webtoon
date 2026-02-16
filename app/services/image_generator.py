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

    def __init__(self, api_key: str, model: str = "gemini-3-pro-image-preview"):
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

            # aspect_ratio: SDK 버전에 따라 ImageConfig 사용 (없으면 프롬프트 힌트에만 의존)
            _gen_config_kwargs = {"response_modalities": ["IMAGE"]}
            if aspect_ratio and hasattr(types, 'ImageConfig'):
                try:
                    _gen_config_kwargs["image_config"] = types.ImageConfig(
                        aspect_ratio=aspect_ratio
                    )
                    logger.info(f"[Gemini] ImageConfig aspect_ratio={aspect_ratio} 적용")
                except Exception:
                    logger.warning(f"[Gemini] ImageConfig 미지원 — 프롬프트 힌트로 대체")
            elif aspect_ratio:
                logger.info(f"[Gemini] ImageConfig 미지원 SDK — 프롬프트 힌트로 비율 {aspect_ratio} 전달")

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

            # ★ 에러 타입별 재시도 설정
            RETRY_DELAYS = {
                "rate_limit": [5, 15, 30],      # 429: 최대 3회, 지수 백오프
                "timeout": [10, 20],             # 타임아웃: 최대 2회
                "server_error": [5, 10],          # 504 등 서버 에러: 최대 2회
                "content_empty": [1],             # 이미지 미포함: 1회
                "safety_filter": [],              # 안전 필터: 재시도 불가
            }
            
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
            
            max_attempts = 4  # 최대 시도 횟수 (첫 시도 + 재시도 3회)
            last_error = None
            error_type = None
            retry_count = 0
            
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
                        error_type = "safety_filter"
                        delays = RETRY_DELAYS.get(error_type, [])
                        if retry_count < len(delays):
                            await asyncio.sleep(delays[retry_count])
                            retry_count += 1
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
                            error_type = "content_empty"
                            delays = RETRY_DELAYS.get(error_type, [])
                            if retry_count < len(delays):
                                await asyncio.sleep(delays[retry_count])
                                retry_count += 1
                                continue
                            raise ValueError(last_error)
                    
                    logger.warning("Gemini 응답에 이미지 없음 (attempt=%d). finish_reason=%s", attempt, finish_reason)
                    last_error = f"Gemini 응답에 이미지가 없습니다 (finish_reason={finish_reason})"
                    error_type = "content_empty"
                    delays = RETRY_DELAYS.get(error_type, [])
                    if retry_count < len(delays):
                        await asyncio.sleep(delays[retry_count])
                        retry_count += 1
                        continue
                    raise ValueError(last_error)

                except asyncio.TimeoutError:
                    # ★ 타임아웃도 재시도 (기존: 즉시 실패)
                    error_type = "timeout"
                    delays = RETRY_DELAYS.get(error_type, [])
                    logger.warning(f"Gemini 타임아웃 (attempt={attempt}, {time.time()-t0:.0f}초)")
                    if retry_count < len(delays):
                        logger.info(f"[재시도] 타임아웃 → {delays[retry_count]}초 후 재시도 ({retry_count+1}/{len(delays)})")
                        await asyncio.sleep(delays[retry_count])
                        retry_count += 1
                        continue
                    raise
                except ValueError:
                    if attempt >= max_attempts:
                        raise
                    continue
                except Exception as e:
                    # ★ 429/504 등 API 에러 분류 후 재시도
                    error_type = _classify_error(e)
                    delays = RETRY_DELAYS.get(error_type, [])
                    logger.warning(f"Gemini 에러 분류={error_type} (attempt={attempt}): {e}")
                    if retry_count < len(delays):
                        wait = delays[retry_count]
                        logger.info(f"[재시도] {error_type} → {wait}초 후 재시도 ({retry_count+1}/{len(delays)})")
                        await asyncio.sleep(wait)
                        retry_count += 1
                        continue
                    raise

        except asyncio.TimeoutError:
            logger.error("Gemini 이미지 생성 타임아웃 (%.0f초, 재시도 소진)", time.time() - t0)
            raise TimeoutError(
                "이미지 생성이 시간 초과되었습니다. 잠시 후 다시 시도해주세요."
            )
        except Exception as e:
            # ★ 사용자 친화적 에러 메시지
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "quota" in err_str:
                friendly = "Gemini API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            elif "504" in err_str or "503" in err_str or "unavailable" in err_str:
                friendly = "Gemini 서버가 일시적으로 바쁩니다. 잠시 후 다시 시도해주세요."
            elif "safety" in err_str or "block" in err_str:
                friendly = "안전 필터에 의해 이미지 생성이 거부되었습니다. 프롬프트를 수정해주세요."
            else:
                friendly = str(e)
            logger.error("Gemini Image Generation Failed (%.1f초, type=%s): %s", time.time() - t0, error_type or "unknown", e)
            raise type(e)(friendly) from e

    async def edit_with_reference(self, prompt, reference_image):
        return await self.generate(prompt, reference_images=[reference_image])


# ────────────────────────────────────────────
# 팩토리
# ────────────────────────────────────────────
# UI 에서 선택하는 모델 이름 → 실제 API 모델 이름 매핑
_GEMINI_MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",          # 빠름
    "nano-banana-pro": "gemini-3-pro-image-preview",  # 고품질 (기본)
}


_generator_cache: dict[str, GeminiGenerator] = {}

def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    """model_name 을 기반으로 Gemini Generator 인스턴스를 반환 (동일 키+모델은 캐싱)"""
    real_model = _GEMINI_MODEL_MAP.get(model_name, model_name)
    cache_key = f"{api_key}:{real_model}"
    if cache_key not in _generator_cache:
        _generator_cache[cache_key] = GeminiGenerator(api_key, real_model)
    return _generator_cache[cache_key]
