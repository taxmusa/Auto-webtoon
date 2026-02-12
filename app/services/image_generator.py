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

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        if not genai:
            raise ImportError("Google GenAI library is not installed")
        if not api_key:
            raise ValueError("Gemini API 키가 설정되지 않았습니다. .env 파일의 GEMINI_API_KEY를 확인해주세요.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate(self, prompt, reference_images=None, size="1024x1024", quality="medium", seed=None):
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
        """text2img: 텍스트→이미지 (Flux Dev)"""
        w, h = self._parse_size(size)
        safe_prompt = self._sanitize_prompt(prompt)

        def _sync():
            args = {
                "prompt": safe_prompt,
                "image_size": {"width": w, "height": h},
                "num_images": 1,
                "output_format": "png",
                "num_inference_steps": 35,  # ★ 품질 향상 (기본 28 → 35)
            }
            if seed is not None:
                args["seed"] = seed
            handler = fal_client.submit(self._TEXT2IMG_MODEL, arguments=args)
            return handler.get()

        result = await asyncio.wait_for(
            asyncio.to_thread(_sync),
            timeout=IMAGE_GENERATION_TIMEOUT
        )
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

        def _sync():
            args = {
                "prompt": safe_prompt,
                "image_url": data_uri,
                "num_images": 1,
                "output_format": "png",
                # ★ guidance_scale 7.0: CRS 참조 방식에 최적화
                #   - 4.5~5.0: 참조 이미지의 포즈/구도까지 복사됨 (나쁨!)
                #   - 7.0: 씬 설명대로 새 장면 그리되, 캐릭터 외모는 CRS에서 유지
                #   - 9.0+: 참조를 완전 무시 (일관성 깨짐)
                "guidance_scale": 7.0,
                # ★ num_inference_steps 35: 품질 향상 (28 → 35)
                #   - 28: 빠르지만 디테일 부족
                #   - 35: 최적 품질 (속도 대비 품질 균형)
                #   - 50: 높은 품질이지만 속도 2배
                "num_inference_steps": 35,
            }
            if seed is not None:
                args["seed"] = seed
            handler = fal_client.submit(self.endpoint, arguments=args)
            return handler.get()

        result = await asyncio.wait_for(
            asyncio.to_thread(_sync),
            timeout=IMAGE_GENERATION_TIMEOUT
        )
        image_url = result["images"][0]["url"]
        return await self._download_image(image_url)

    async def edit_with_reference(self, prompt, reference_image, size="1024x1536"):
        """참조 이미지로 편집 (Kontext 핵심 기능)"""
        return await self.generate(prompt, reference_images=[reference_image], size=size)

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
# fal.ai — Flux LoRA (학습된 캐릭터로 생성)
# ────────────────────────────────────────────
class FluxLoraGenerator(ImageGeneratorBase):
    """학습된 LoRA 모델로 이미지 생성 (fal.ai)

    사용 흐름:
      1. fal_service.py 에서 LoRA 학습 → lora_url 획득
      2. FluxLoraGenerator(api_key, lora_url=...) 생성
      3. generate("sks_character in a cafe") → 학습된 캐릭터로 이미지 생성
    """

    _ENDPOINT = "fal-ai/flux-lora"

    def __init__(self, api_key: str, model: str = "flux-lora",
                 lora_url: str = "", trigger_word: str = ""):
        if not fal_client:
            raise ImportError("fal-client 라이브러리가 설치되지 않았습니다. pip install fal-client")
        if not api_key:
            raise ValueError("fal.ai API 키가 설정되지 않았습니다. .env 파일의 FAL_KEY를 확인해주세요.")
        os.environ["FAL_KEY"] = api_key
        self.model = model
        self.lora_url = lora_url
        self.trigger_word = trigger_word

    async def generate(self, prompt, reference_images=None, size="1024x1536", quality="medium", seed=None):
        """LoRA 학습 모델로 이미지 생성"""
        t0 = time.time()
        w, h = FluxKontextGenerator._parse_size(size)

        # 트리거 워드가 프롬프트에 없으면 앞에 추가
        if self.trigger_word and self.trigger_word not in prompt:
            prompt = f"{self.trigger_word}, {prompt}"

        # 한국어 제거 (fal.ai는 영어만)
        safe_prompt = FluxKontextGenerator._sanitize_prompt(prompt)

        try:
            def _sync():
                arguments = {
                    "prompt": safe_prompt,
                    "image_size": {"width": w, "height": h},
                    "num_images": 1,
                    "output_format": "png",
                }
                # LoRA 가중치가 있으면 적용
                if self.lora_url:
                    arguments["loras"] = [{"path": self.lora_url, "scale": 1.0}]
                # Seed 고정 (캐릭터 일관성)
                if seed is not None:
                    arguments["seed"] = seed

                handler = fal_client.submit(self._ENDPOINT, arguments=arguments)
                return handler.get()

            result = await asyncio.wait_for(
                asyncio.to_thread(_sync),
                timeout=IMAGE_GENERATION_TIMEOUT
            )
            logger.info("Flux LoRA 이미지 생성 완료 %.1f초 (trigger=%s)",
                        time.time() - t0, self.trigger_word)

            image_url = result["images"][0]["url"]
            return await FluxKontextGenerator._download_image(image_url)

        except asyncio.TimeoutError:
            logger.error("Flux LoRA 이미지 생성 타임아웃 (%.0f초)", time.time() - t0)
            raise TimeoutError(
                f"이미지 생성이 {IMAGE_GENERATION_TIMEOUT}초 안에 완료되지 않았습니다."
            )
        except Exception as e:
            logger.error("Flux LoRA Image Generation Failed (%.1f초): %s", time.time() - t0, e)
            raise

    async def edit_with_reference(self, prompt, reference_image, size="1024x1536"):
        """LoRA 모델은 참조 이미지 편집 미지원 → 일반 생성으로 대체"""
        return await self.generate(prompt, size=size)


# ────────────────────────────────────────────
# 팩토리
# ────────────────────────────────────────────
# UI 에서 선택하는 모델 이름 → 실제 API 모델 이름 매핑
# 2026-02-11 ListModels 실제 테스트로 검증 완료
_GEMINI_MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",        # 빠름, 이미지 생성 확인됨
    "nano-banana-pro": "nano-banana-pro-preview",    # 고품질, 이미지 생성 확인됨
}


def get_generator(model_name: str, api_key: str,
                  lora_url: str = "", trigger_word: str = "") -> ImageGeneratorBase:
    """model_name 을 기반으로 적절한 Generator 인스턴스를 반환

    Args:
        model_name: UI 에서 선택한 모델명
        api_key: 해당 모델의 API 키
        lora_url: (LoRA 전용) 학습된 LoRA 가중치 URL
        trigger_word: (LoRA 전용) 학습된 트리거 워드
    """
    # ── fal.ai Flux 계열 ──
    if "flux-kontext" in model_name:
        return FluxKontextGenerator(api_key, model_name)
    elif "flux-lora" in model_name:
        return FluxLoraGenerator(api_key, model_name,
                                 lora_url=lora_url, trigger_word=trigger_word)

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
