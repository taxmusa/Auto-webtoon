"""
캐릭터 LoRA 자동 학습 — 세션 관리 + 테스트 이미지 서비스

핵심 흐름 (v2 — Grid 분할 방식):
  1. 24컷 합본 이미지 업로드
  2. 자동 분할 (4x6 등)
  3. 캐릭터 이름 입력 + LoRA 학습 시작
  4. 학습 완료 후 테스트 이미지 3장 생성
"""
import os
import logging
import uuid
from typing import List, Optional, Dict

from app.core.config import (
    get_settings,
    LORA_SCALE_DEFAULT,
)
from app.models.models import GenerationSession

logger = logging.getLogger(__name__)


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


async def generate_test_images(
    trigger_word: str,
    lora_url: str,
    lora_scale: float = LORA_SCALE_DEFAULT,
) -> List[str]:
    """학습 완료 후 테스트 이미지 3장 자동 생성

    fal.ai 서비스 의존성 제거로 현재 비활성화되었습니다.

    Args:
        trigger_word: 학습된 트리거 워드
        lora_url: LoRA 가중치 URL
        lora_scale: LoRA 강도 (기본 0.8)

    Returns:
        빈 리스트 (기능 비활성화)
    """
    logger.warning("LoRA 테스트 이미지 생성은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다.")
    return []


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

    return f"/trained_characters/_temp_cuts/{filename}"


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

    romanized = _romanize_korean(name)
    base_word = f"sks_{romanized}"

    word = base_word
    counter = 2
    while word in existing_words:
        word = f"{base_word}{counter}"
        counter += 1

    return word


def _romanize_korean(text: str) -> str:
    """간단한 한글 → 영문 변환 (트리거 워드용)"""
    CHOSUNG = [
        'g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp',
        's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h'
    ]
    JUNGSUNG = [
        'a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye',
        'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we',
        'wi', 'yu', 'eu', 'ui', 'i'
    ]
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
            offset = code - 0xAC00
            cho = offset // (21 * 28)
            jung = (offset % (21 * 28)) // 28
            jong = offset % 28
            result.append(CHOSUNG[cho])
            result.append(JUNGSUNG[jung])
            result.append(JONGSUNG[jong])
        elif char.isascii() and char.isalnum():
            result.append(char.lower())

    romanized = "".join(result)
    if not romanized:
        romanized = "char"
    return romanized
