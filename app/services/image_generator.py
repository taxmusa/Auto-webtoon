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

    async def generate(self, prompt, reference_images=None, size="1024x1024", quality="standard", seed=None):
        """
        모델에 따라 적절한 파라미터로 이미지 생성.
        ─ gpt-image-1 계열: size, quality, output_format 지원 / response_format 미지원
        ─ dall-e-3         : size, quality, response_format 지원
        ─ dall-e-2         : size, response_format 지원 / quality 미지원
        (seed는 OpenAI 모델에서는 무시됨)
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
            # 레퍼런스를 프롬프트 앞에 배치하여 AI가 스타일/캐릭터를 먼저 인식하도록 함
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
                            await asyncio.sleep(1)
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
                                await asyncio.sleep(1)
                                continue
                            raise ValueError(last_error)
                    
                    logger.warning("Gemini 응답에 이미지 없음 (attempt=%d). finish_reason=%s", attempt, finish_reason)
                    last_error = f"Gemini 응답에 이미지가 없습니다 (finish_reason={finish_reason})"
                    if attempt < max_attempts:
                        await asyncio.sleep(1)
                        continue
                    raise ValueError(last_error)

                except asyncio.TimeoutError:
                    raise  # 타임아웃은 재시도하지 않음
                except ValueError:
                    if attempt >= max_attempts:
                        raise
                    # 재시도
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
# fal.ai — Flux Kontext (참조 이미지 기반 편집)
# ────────────────────────────────────────────
try:
    import fal_client
except ImportError:
    fal_client = None


class FluxKontextGenerator(ImageGeneratorBase):
    """Flux Kontext Dev/Pro — 참조 이미지 기반 캐릭터 일관성 (fal.ai)

    사용 흐름:
      씬 1: generate(prompt)                         → 텍스트→이미지 (첫 씬)
      씬 2+: generate(prompt, reference_images=[씬1]) → 이미지→이미지 (일관성 유지)
    """

    # fal.ai 모델 엔드포인트
    _MODEL_MAP = {
        "flux-kontext-dev": "fal-ai/flux-kontext/dev",
        "flux-kontext-pro": "fal-ai/flux-kontext/pro",
    }
    # 참조 이미지 없을 때 (첫 씬) 사용할 텍스트→이미지 모델
    _TEXT2IMG_MODEL = "fal-ai/flux/dev"

    def __init__(self, api_key: str, model: str = "flux-kontext-dev"):
        if not fal_client:
            raise ImportError("fal-client 라이브러리가 설치되지 않았습니다. pip install fal-client")
        if not api_key:
            raise ValueError("fal.ai API 키가 설정되지 않았습니다. .env 파일의 FAL_KEY를 확인해주세요.")
        # fal_client 는 환경변수 FAL_KEY 를 자동 참조하지만, 명시적으로도 설정
        os.environ["FAL_KEY"] = api_key
        self.model = model
        self.endpoint = self._MODEL_MAP.get(model, "fal-ai/flux-kontext/dev")

    async def generate(self, prompt, reference_images=None, size="1024x1536", quality="medium", seed=None):
        """
        reference_images 가 있으면 → Kontext (이미지→이미지, 캐릭터 유지)
        reference_images 가 없으면 → Flux Dev (텍스트→이미지, 첫 씬)
        seed: 동일 seed 사용 시 캐릭터 일관성 향상. None이면 랜덤.
        최대 2회 재시도.
        """
        max_retries = 2
        last_err = None

        if seed is not None:
            logger.info("[Flux] 고정 seed 사용: %d", seed)

        for attempt in range(max_retries + 1):
            t0 = time.time()
            try:
                if reference_images and len(reference_images) > 0:
                    image_data = await self._generate_with_reference(prompt, reference_images[0], size, seed=seed)
                else:
                    image_data = await self._generate_text2img(prompt, size, seed=seed)

                logger.info("Flux 이미지 생성 완료 %.1f초 (model=%s, ref=%s, attempt=%d)",
                            time.time() - t0, self.model,
                            "있음" if reference_images else "없음", attempt + 1)
                return image_data

            except asyncio.TimeoutError:
                logger.error("Flux 이미지 생성 타임아웃 (%.0f초, attempt=%d)", time.time() - t0, attempt + 1)
                last_err = TimeoutError(
                    f"이미지 생성이 {IMAGE_GENERATION_TIMEOUT}초 안에 완료되지 않았습니다. "
                    "네트워크나 fal.ai 상태를 확인한 뒤 다시 시도해주세요."
                )
            except Exception as e:
                import traceback
                err_msg = str(e)
                logger.error("Flux 생성 실패 (%.1f초, attempt=%d): %s\n%s", 
                           time.time() - t0, attempt + 1, e, traceback.format_exc())
                
                # fal.ai 잔액 부족 — 재시도 무의미, 즉시 중단
                if "Exhausted balance" in err_msg or "locked" in err_msg.lower():
                    raise RuntimeError(
                        "fal.ai 잔액이 소진되었습니다. "
                        "https://fal.ai/dashboard/billing 에서 충전 후 다시 시도해주세요."
                    ) from e
                
                # 인증 오류 — 재시도 무의미
                if "401" in err_msg or "403" in err_msg or "Unauthorized" in err_msg:
                    raise RuntimeError(
                        "fal.ai 인증 실패. .env 파일의 FAL_KEY를 확인해주세요. "
                        "(https://fal.ai/dashboard/keys 에서 발급)"
                    ) from e
                
                last_err = e

            if attempt < max_retries:
                wait = 2 ** attempt
                logger.info(f"[Flux] {wait}초 후 재시도...")
                await asyncio.sleep(wait)

        raise last_err

    @staticmethod
    def _sanitize_prompt(prompt: str) -> str:
        """프롬프트의 한국어를 영어로 번역하여 fal.ai에 전달.
        
        SmartTranslator를 사용한 3단계 번역:
          1. 캐시 히트 → 비용 0
          2. 로컬 사전(prompt_dictionary.json) → 비용 0
          3. Gemini AI → 미번역 부분만 호출
        + 최종: 비-ASCII 문자 강제 제거 (fal_client가 ASCII만 허용)
        """
        import re
        from app.services.smart_translator import translate_prompt
        
        translated = translate_prompt(prompt)
        
        # ── 최종 안전장치: fal_client는 비-ASCII를 전혀 허용하지 않음 ──
        # 번역 후에도 남은 한국어/특수문자를 공백으로 치환
        ascii_safe = translated.encode('ascii', errors='replace').decode('ascii')
        # '?' 문자(치환 결과)를 공백으로 변환 후 정리
        ascii_safe = ascii_safe.replace('?', ' ')
        ascii_safe = re.sub(r'\s+', ' ', ascii_safe).strip()
        
        if len(ascii_safe) < 20:
            ascii_safe = "Korean webtoon style, clean professional illustration. " + ascii_safe
        
        # ── 텍스트/로고/마크 금지 보장 (앞 + 뒤 이중 배치) ──
        # Flux는 프롬프트의 앞부분과 뒷부분을 가장 강하게 따름
        anti_front = "no text, no speech bubbles, no logos, no watermarks, no writing, no symbols, no icons, no marks"
        anti_back = "Pure illustration only. Absolutely no text or logos anywhere."
        
        if "no text" not in ascii_safe.lower():
            ascii_safe = anti_front + ". " + ascii_safe
        
        # 프롬프트 끝에도 안티텍스트 리마인더 추가
        if not ascii_safe.rstrip().endswith("logos.") and not ascii_safe.rstrip().endswith("logos"):
            ascii_safe = ascii_safe.rstrip() + " " + anti_back
        
        if ascii_safe != translated:
            logger.info("[Flux] ASCII 강제 정리 적용 (비-ASCII 문자 제거됨)")
        
        return ascii_safe

    async def _generate_text2img(self, prompt: str, size: str, seed=None) -> bytes:
        """text2img: 텍스트→이미지 (Flux Dev) — 비동기 폴링으로 타임아웃 제어"""
        w, h = self._parse_size(size)
        safe_prompt = self._sanitize_prompt(prompt)
        t0 = time.time()

        from app.services.prompt_rules import get_negative_prompt
        args = {
            "prompt": safe_prompt,
            "negative_prompt": get_negative_prompt(),
            "image_size": {"width": w, "height": h},
            "num_images": 1,
            "output_format": "png",
            "num_inference_steps": 35,
        }
        if seed is not None:
            args["seed"] = seed

        handler = await asyncio.to_thread(
            fal_client.submit, self._TEXT2IMG_MODEL, arguments=args
        )
        request_id = handler.request_id

        result = await self._async_poll(self._TEXT2IMG_MODEL, request_id, t0)
        image_url = result["images"][0]["url"]
        return await self._download_image(image_url)

    async def _generate_with_reference(self, prompt: str, ref_bytes: bytes, size: str, seed=None) -> bytes:
        """참조 이미지 기반 편집 (Kontext) — CRS 참조 방식의 핵심
        
        ★ CRS 참조 방식:
          CRS (캐릭터 레퍼런스 시트, 흰배경 정면) → 모든 씬 (img2img, CRS 참조)
          
        guidance_scale 설계:
          - 4.0~5.0: CRS의 포즈/구도까지 복사됨 (나쁨!)
          - 7.0: 씬 설명대로 새 장면 + 캐릭터만 CRS에서 유지 (최적!)
          - 9.0+: CRS를 완전 무시 (일관성 깨짐 - 나쁨)
        """
        import base64

        safe_prompt = self._sanitize_prompt(prompt)

        b64 = base64.b64encode(ref_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        t0 = time.time()
        from app.services.prompt_rules import get_negative_prompt
        args = {
            "prompt": safe_prompt,
            "negative_prompt": get_negative_prompt(),
            "image_url": data_uri,
            "num_images": 1,
            "output_format": "png",
            "guidance_scale": 7.0,
            "num_inference_steps": 35,
        }
        if seed is not None:
            args["seed"] = seed

        handler = await asyncio.to_thread(
            fal_client.submit, self.endpoint, arguments=args
        )
        request_id = handler.request_id

        result = await self._async_poll(self.endpoint, request_id, t0)
        image_url = result["images"][0]["url"]
        return await self._download_image(image_url)

    async def edit_with_reference(self, prompt, reference_image, size="1024x1536"):
        """참조 이미지로 편집 (Kontext 핵심 기능)"""
        return await self.generate(prompt, reference_images=[reference_image], size=size)

    async def _async_poll(self, endpoint, request_id, t0, timeout=None):
        """fal.ai 요청을 비동기 폴링으로 대기 (타임아웃 제어 가능)
        
        기존 handler.get()은 동기 무한 폴링이라 asyncio 취소/타임아웃 불가.
        이 메서드는 asyncio.sleep() 기반이라 취소 가능.
        """
        if timeout is None:
            timeout = IMAGE_GENERATION_TIMEOUT
        poll_interval = 1.0
        
        while (time.time() - t0) < timeout:
            await asyncio.sleep(poll_interval)
            elapsed = time.time() - t0
            
            try:
                status = await asyncio.to_thread(
                    fal_client.status, endpoint, request_id, with_logs=False
                )
            except Exception:
                continue
            
            status_name = type(status).__name__
            
            if status_name == "Completed":
                result = await asyncio.to_thread(
                    fal_client.result, endpoint, request_id
                )
                return result
            
            if status_name == "Failed":
                error_msg = getattr(status, 'error', 'Unknown error')
                raise RuntimeError(f"fal.ai 이미지 생성 실패: {error_msg}")
            
            # InProgress / Queued → 계속 대기
            if elapsed > 30:
                poll_interval = 2.0
        
        raise TimeoutError(f"이미지 생성이 {timeout}초 안에 완료되지 않았습니다.")

    @staticmethod
    def _parse_size(size: str) -> tuple:
        """'1024x1536' → (1024, 1536)"""
        try:
            parts = size.split("x")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 1024, 1536

    @staticmethod
    async def _download_image(url: str) -> bytes:
        """URL 에서 이미지 다운로드"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content


# ────────────────────────────────────────────
# 팩토리
# ────────────────────────────────────────────
# UI 에서 선택하는 모델 이름 → 실제 API 모델 이름 매핑
# 2026-02-11 ListModels 실제 테스트로 검증 완료
_GEMINI_MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",          # Nano Banana (빠름)
    "nano-banana-pro": "gemini-3-pro-image-preview",  # Nano Banana Pro (고품질 — Gemini 3 Pro Image)
}


def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    """model_name 을 기반으로 적절한 Generator 인스턴스를 반환

    Args:
        model_name: UI 에서 선택한 모델명
        api_key: 해당 모델의 API 키
    """
    # ── fal.ai Flux Kontext ──
    if "flux-kontext" in model_name:
        return FluxKontextGenerator(api_key, model_name)

    # ── OpenAI 계열 ──
    elif "gpt" in model_name or "dall-e" in model_name:
        return OpenAIGenerator(api_key, model_name)

    # ── Gemini 계열 ──
    elif "nano" in model_name or "gemini" in model_name:
        real_model = _GEMINI_MODEL_MAP.get(model_name, model_name)
        return GeminiGenerator(api_key, real_model)

    # ── 기본값: OpenAI ──
    else:
        return OpenAIGenerator(api_key, model_name)
