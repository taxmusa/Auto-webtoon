"""
캐릭터 LoRA 자동 학습 — 24컷 생성 + 테스트 이미지 서비스

핵심 흐름:
  1. 사진 1장 업로드 → 저장
  2. 스타일 선택 (original / realistic_sketch / ...)
  3. 24컷 자동 생성 (경로 A: Flux Kontext, 경로 B: GPT Image 등)
  4. 테스트 이미지 3장 생성 (학습 완료 후)
"""
import asyncio
import json
import os
import logging
import uuid
import time
from typing import List, Optional, Dict
from pathlib import Path

import httpx

from app.core.config import (
    get_settings,
    GENERATION_CUTS_COUNT,
    LORA_SCALE_DEFAULT,
    COST_PER_IMAGE_GENERATION,
    COST_PER_LORA_TRAINING,
    COST_PER_LORA_INFERENCE,
)
from app.models.models import (
    LORA_STYLE_PROMPTS,
    LORA_STYLE_LABELS,
    GenerationSession,
)

logger = logging.getLogger(__name__)

# 24컷 프롬프트 로드
_CUTS_PROMPTS: Optional[List[dict]] = None

def _load_cuts_prompts() -> List[dict]:
    """24컷 프롬프트 JSON 로드 (캐시)"""
    global _CUTS_PROMPTS
    if _CUTS_PROMPTS is None:
        prompts_path = Path(__file__).parent.parent / "data" / "prompts" / "24cuts_prompts.json"
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _CUTS_PROMPTS = data["cuts"]
    return _CUTS_PROMPTS


# ─── 인메모리 세션 저장소 ───
_generation_sessions: Dict[str, dict] = {}


def get_session(session_id: str) -> Optional[dict]:
    return _generation_sessions.get(session_id)


def save_session(session: dict):
    _generation_sessions[session["session_id"]] = session


def create_session(photo_url: str, photo_local_path: str = "") -> dict:
    """새 생성 세션 생성"""
    session_id = str(uuid.uuid4())
    session = GenerationSession(
        session_id=session_id,
        photo_url=photo_url,
        photo_local_path=photo_local_path,
    ).model_dump()
    session["created_at"] = str(session["created_at"])
    save_session(session)
    return session


def build_generation_prompt(style_id: str, pose_prompt: str, custom_prompt: str = None) -> str:
    """24컷 각각에 대한 프롬프트를 생성한다.

    Args:
        style_id: 선택된 스타일 ("original", "realistic_sketch", ...)
        pose_prompt: 해당 컷의 포즈/표정 설명 (영어)
        custom_prompt: style_id가 "custom"일 때 사용자 입력 스타일

    Returns:
        완성된 프롬프트 문자열
    """
    style_prompts = dict(LORA_STYLE_PROMPTS)
    if custom_prompt:
        style_prompts["custom"] = custom_prompt

    style_part = style_prompts.get(style_id, "")

    if style_id == "original":
        # 원본 스타일: 스타일 변환 프롬프트 없이 포즈/표정만 지시
        prompt = f"same person, same style as the input image, {pose_prompt}, clean background"
    else:
        # 스타일 변환: 스타일 프롬프트 + 포즈/표정
        prompt = f"{style_part}, {pose_prompt}"

    return prompt


async def generate_single_cut(
    photo_url: str,
    photo_bytes: Optional[bytes],
    style_id: str,
    cut_prompt: dict,
    custom_prompt: str = None,
) -> Optional[str]:
    """단일 컷 이미지 생성

    Args:
        photo_url: 업로드된 원본 사진 URL
        photo_bytes: 원본 사진 바이트 데이터 (Flux Kontext용)
        style_id: 스타일 ID
        cut_prompt: {"id": 1, "category": "expression", "prompt": "...", "label_ko": "..."}
        custom_prompt: 커스텀 스타일 프롬프트

    Returns:
        생성된 이미지의 fal.ai URL 또는 None
    """
    from app.services.image_generator import FluxKontextGenerator, get_generator

    settings = get_settings()
    prompt = build_generation_prompt(style_id, cut_prompt["prompt"], custom_prompt)

    try:
        if style_id == "original":
            # ── 경로 A: Flux Kontext (img2img) ──
            # 원본 사진을 input으로 넣고, 포즈/표정만 변경
            if not settings.fal_key:
                raise ValueError("FAL_KEY가 설정되지 않았습니다.")

            generator = FluxKontextGenerator(settings.fal_key, "flux-kontext-dev")

            if photo_bytes:
                # 참조 이미지로 생성
                result = await generator.generate(
                    prompt=prompt,
                    reference_images=[photo_bytes],
                    size="1024x1024",
                )
            else:
                raise ValueError("original 스타일은 사진 바이트 데이터가 필요합니다.")

        else:
            # ── 경로 B: 기존 이미지 생성 모델 (스타일 변환) ──
            # GPT Image로 스타일 변환 (레퍼런스 이미지를 프롬프트에 설명으로 포함)
            if settings.openai_api_key:
                generator = get_generator("gpt-image-1-mini", settings.openai_api_key)
            elif settings.gemini_api_key:
                generator = get_generator("nano-banana", settings.gemini_api_key)
            else:
                raise ValueError("이미지 생성 API 키가 설정되지 않았습니다. (OpenAI 또는 Gemini)")

            # 레퍼런스 이미지 포함 생성
            if photo_bytes:
                result = await generator.generate(
                    prompt=prompt,
                    reference_images=[photo_bytes],
                    size="1024x1024",
                )
            else:
                result = await generator.generate(
                    prompt=prompt,
                    size="1024x1024",
                )

        # 결과가 bytes이면 로컬에 저장하고 URL 반환
        if isinstance(result, bytes):
            return await _save_and_get_url(result, cut_prompt["id"])
        elif isinstance(result, str):
            # 이미 URL인 경우
            return result
        else:
            return None

    except Exception as e:
        logger.error(f"컷 #{cut_prompt['id']} ({cut_prompt['label_ko']}) 생성 실패: {e}")
        return None


async def _save_and_get_url(image_bytes: bytes, cut_id: int) -> str:
    """이미지 바이트를 로컬에 저장하고 서빙 URL 반환"""
    save_dir = os.path.join("trained_characters", "_temp_cuts")
    os.makedirs(save_dir, exist_ok=True)

    filename = f"cut_{cut_id:02d}_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(save_dir, filename)

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    # Cloudinary에 업로드 시도
    try:
        from app.services.cloudinary_service import get_cloudinary_service
        from PIL import Image
        from io import BytesIO

        service = get_cloudinary_service()
        if service.cloud_name:
            img = Image.open(BytesIO(image_bytes))
            url = await service.upload_image(img, f"cut_{cut_id:02d}")
            if url:
                return url
    except Exception as e:
        logger.warning(f"Cloudinary 업로드 실패, 로컬 URL 사용: {e}")

    # Cloudinary 실패 시 로컬 서빙 URL
    return f"/trained_characters/_temp_cuts/{filename}"


async def generate_24_cuts(
    session_id: str,
    callback=None,
) -> dict:
    """24컷 자동 생성 (비동기)

    Args:
        session_id: 생성 세션 ID
        callback: 진행 상태 콜백 (optional)

    Returns:
        {"status": "completed"/"failed", "generated_cuts": [...]}
    """
    session = get_session(session_id)
    if not session:
        return {"status": "failed", "error": "세션을 찾을 수 없습니다."}

    photo_url = session["photo_url"]
    style_id = session.get("style_id", "original")
    custom_prompt = session.get("custom_prompt")

    # 원본 사진 다운로드 (Flux Kontext용)
    photo_bytes = await _download_photo(photo_url, session.get("photo_local_path", ""))

    cuts_prompts = _load_cuts_prompts()
    session["status"] = "generating"
    session["generated_cuts"] = []
    save_session(session)

    generated = []
    for i, cut in enumerate(cuts_prompts):
        try:
            url = await generate_single_cut(
                photo_url=photo_url,
                photo_bytes=photo_bytes,
                style_id=style_id,
                cut_prompt=cut,
                custom_prompt=custom_prompt,
            )

            cut_result = {
                "id": cut["id"],
                "category": cut["category"],
                "label_ko": cut["label_ko"],
                "url": url or "",
                "selected": url is not None,  # 생성 성공하면 기본 선택
            }
            generated.append(cut_result)

            # 세션 업데이트
            session["generated_cuts"] = generated
            save_session(session)

            logger.info(f"[24컷] {i + 1}/{len(cuts_prompts)} 완료: {cut['label_ko']} {'✓' if url else '✗'}")

        except Exception as e:
            logger.error(f"[24컷] 컷 #{cut['id']} 생성 중 오류: {e}")
            generated.append({
                "id": cut["id"],
                "category": cut["category"],
                "label_ko": cut["label_ko"],
                "url": "",
                "selected": False,
            })

    # 완료 처리
    success_count = sum(1 for c in generated if c["url"])
    session["status"] = "completed" if success_count > 0 else "failed"
    session["generated_cuts"] = generated
    # 성공한 컷만 기본 선택
    session["selected_cut_ids"] = [c["id"] for c in generated if c["selected"]]
    save_session(session)

    logger.info(f"[24컷] 생성 완료: {success_count}/{len(cuts_prompts)}장 성공")

    return {
        "status": session["status"],
        "generated_cuts": generated,
        "success_count": success_count,
        "total_cuts": len(cuts_prompts),
    }


async def _download_photo(photo_url: str, local_path: str = "") -> Optional[bytes]:
    """사진 다운로드 (URL 또는 로컬 경로)"""
    # 로컬 경로가 있으면 직접 읽기
    if local_path and os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return f.read()

    # 로컬 서빙 URL이면 로컬 파일 읽기
    if photo_url.startswith("/"):
        abs_path = photo_url.lstrip("/")
        if os.path.exists(abs_path):
            with open(abs_path, "rb") as f:
                return f.read()

    # 외부 URL이면 다운로드
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(photo_url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.error(f"사진 다운로드 실패: {e}")
        return None


async def generate_test_images(
    trigger_word: str,
    lora_url: str,
    lora_scale: float = LORA_SCALE_DEFAULT,
) -> List[str]:
    """학습 완료 후 테스트 이미지 3장 자동 생성

    Args:
        trigger_word: 학습된 트리거 워드
        lora_url: LoRA 가중치 URL
        lora_scale: LoRA 강도 (기본 0.8)

    Returns:
        생성된 테스트 이미지 URL 리스트
    """
    from app.services.image_generator import FluxLoraGenerator

    settings = get_settings()
    if not settings.fal_key:
        logger.error("FAL_KEY가 설정되지 않아 테스트 이미지를 생성할 수 없습니다.")
        return []

    test_prompts = [
        f"{trigger_word}, front view, confident smile, white background",
        f"{trigger_word}, sitting at desk, explaining something, office background",
        f"{trigger_word}, full body, standing, waving hand, simple background",
    ]

    generator = FluxLoraGenerator(
        api_key=settings.fal_key,
        model="flux-lora",
        lora_url=lora_url,
        trigger_word=trigger_word,
    )

    test_urls = []
    for i, prompt in enumerate(test_prompts):
        try:
            result = await generator.generate(
                prompt=prompt,
                size="1024x1024",
            )

            if isinstance(result, bytes):
                url = await _save_and_get_url(result, 100 + i)
            else:
                url = result

            test_urls.append(url)
            logger.info(f"[테스트] {i + 1}/3 생성 완료")

        except Exception as e:
            logger.error(f"[테스트] 이미지 {i + 1} 생성 실패: {e}")

    return test_urls


def estimate_cost(style_id: str, cuts_count: int = 24) -> dict:
    """비용 추정

    Returns:
        {
            "generation_cost": float,  # 24컷 생성 비용
            "training_cost": float,    # LoRA 학습 비용
            "test_cost": float,        # 테스트 이미지 비용
            "total_cost": float,       # 총 비용
        }
    """
    gen_cost = COST_PER_IMAGE_GENERATION * cuts_count
    train_cost = COST_PER_LORA_TRAINING
    test_cost = COST_PER_LORA_INFERENCE * 3

    return {
        "generation_cost": round(gen_cost, 2),
        "training_cost": round(train_cost, 2),
        "test_cost": round(test_cost, 2),
        "total_cost": round(gen_cost + train_cost + test_cost, 2),
        "currency": "USD",
    }


def generate_trigger_word(name: str, existing_words: List[str] = None) -> str:
    """한글 캐릭터 이름에서 트리거 워드 자동 생성

    Args:
        name: 캐릭터 이름 (한글/영어)
        existing_words: 이미 사용 중인 트리거 워드 목록 (중복 방지)

    Returns:
        "sks_영문이름" 형식의 트리거 워드
    """
    if existing_words is None:
        existing_words = []

    # 한글 → 로마자 변환 (간단한 매핑)
    romanized = _romanize_korean(name)

    # sks_ 접두사 추가
    base_word = f"sks_{romanized}"

    # 중복 체크
    word = base_word
    counter = 2
    while word in existing_words:
        word = f"{base_word}{counter}"
        counter += 1

    return word


def _romanize_korean(text: str) -> str:
    """간단한 한글 → 영문 변환 (로마자 표기법 간략)

    완벽한 로마자 변환이 아닌, 트리거 워드로 사용 가능한 수준의 변환.
    """
    # 한글 자모 초성
    CHOSUNG = [
        'g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp',
        's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h'
    ]
    # 한글 자모 중성
    JUNGSUNG = [
        'a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye',
        'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we',
        'wi', 'yu', 'eu', 'ui', 'i'
    ]
    # 한글 자모 종성
    JONGSUNG = [
        '', 'k', 'k', 'k', 'n', 'n', 'n', 't',
        'l', 'l', 'l', 'l', 'l', 'l', 'l', 'l',
        'm', 'p', 'p', 's', 's', 'ng', 'j', 'j',
        'k', 't', 'p', 'h'
    ]

    result = []
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            # 한글 음절 분리
            offset = code - 0xAC00
            cho = offset // (21 * 28)
            jung = (offset % (21 * 28)) // 28
            jong = offset % 28
            result.append(CHOSUNG[cho])
            result.append(JUNGSUNG[jung])
            result.append(JONGSUNG[jong])
        elif char.isascii() and char.isalnum():
            result.append(char.lower())
        # 그 외 문자는 무시

    romanized = "".join(result)
    # 빈 문자열 방지
    if not romanized:
        romanized = "char"
    return romanized
