"""
fal.ai LoRA 학습 서비스
- Flux LoRA Fast Training API 호출
- 학습 이미지 업로드 → 학습 시작 → 상태 폴링 → 완료 시 lora_url 반환
- 캐릭터 학습 자동화: 캡셔닝 + 리사이즈 + ZIP 패키징
"""
import asyncio
import os
import uuid
import json
import time
import logging
from typing import List, Optional
from datetime import datetime

from app.core.config import (
    CHARACTER_TRAINING_STEPS,
    CHARACTER_TRAINING_LEARNING_RATE,
    CHARACTER_TRAINING_RESOLUTION,
    CHARACTER_TRAINING_CREATE_MASKS,
)

logger = logging.getLogger(__name__)

try:
    import fal_client
except ImportError:
    fal_client = None

# ────────────────────────────────────────────
# 학습된 캐릭터 데이터 저장/로드 (JSON 파일 기반)
# ────────────────────────────────────────────
TRAINED_DIR = "trained_characters"


def _ensure_dir():
    os.makedirs(TRAINED_DIR, exist_ok=True)


def save_character(character: dict) -> str:
    """캐릭터 JSON 저장, 파일 경로 반환"""
    _ensure_dir()
    filepath = os.path.join(TRAINED_DIR, f"{character['id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(character, f, ensure_ascii=False, indent=2, default=str)
    return filepath


def load_character(character_id: str) -> Optional[dict]:
    """캐릭터 JSON 로드"""
    filepath = os.path.join(TRAINED_DIR, f"{character_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_characters() -> List[dict]:
    """모든 학습된 캐릭터 목록"""
    _ensure_dir()
    chars = []
    for fname in os.listdir(TRAINED_DIR):
        if fname.endswith(".json"):
            filepath = os.path.join(TRAINED_DIR, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    chars.append(json.load(f))
            except Exception as e:
                logger.error(f"캐릭터 파일 로드 실패: {fname} - {e}")
    # 최신 순 정렬
    chars.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return chars


def delete_character(character_id: str) -> bool:
    """캐릭터 삭제"""
    filepath = os.path.join(TRAINED_DIR, f"{character_id}.json")
    img_dir = os.path.join(TRAINED_DIR, character_id)
    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(img_dir):
        import shutil
        shutil.rmtree(img_dir, ignore_errors=True)
    return True


# ────────────────────────────────────────────
# fal.ai LoRA 학습
# ────────────────────────────────────────────
TRAINING_ENDPOINT = "fal-ai/flux-lora-fast-training"


async def start_training(
    character_id: str,
    image_urls: List[str],
    trigger_word: str = "",
    steps: int = None,
    captions: Optional[List[str]] = None,
    style_id: str = "original",
) -> dict:
    """LoRA 학습 시작

    Args:
        character_id: TrainedCharacter.id
        image_urls: 학습 이미지 URL 목록 (fal.ai가 접근 가능해야 함)
        trigger_word: 트리거 워드
        steps: 학습 스텝 수 (None이면 config 기본값 사용)
        captions: 각 이미지에 대한 캡션 리스트 (None이면 자동 생성)
        style_id: 학습 스타일 ID (자동 캡셔닝에 사용)

    Returns:
        {"job_id": str, "status": "training"} 또는 에러
    """
    if not fal_client:
        raise ImportError("fal-client 라이브러리가 설치되지 않았습니다.")

    fal_key = os.getenv("FAL_KEY", "")
    if not fal_key:
        raise ValueError("FAL_KEY 환경변수가 설정되지 않았습니다.")
    os.environ["FAL_KEY"] = fal_key

    # 학습 스텝 수: 인자 > config 기본값
    actual_steps = steps if steps is not None else CHARACTER_TRAINING_STEPS
    actual_trigger = trigger_word or f"sks_{character_id[:8]}"

    arguments = {
        "images_data_url": None,
        "trigger_word": actual_trigger,
        "steps": actual_steps,
        "create_masks": CHARACTER_TRAINING_CREATE_MASKS,
        "is_style": False,
    }

    import tempfile
    import zipfile
    import httpx

    t0 = time.time()
    logger.info(f"[LoRA Training] 이미지 {len(image_urls)}장 다운로드 시작")

    # 이미지 다운로드 + 캡셔닝 + zip 생성
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for i, url in enumerate(image_urls):
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()

                        # 이미지 리사이즈 (1024x1024) + JPG 변환
                        img_data = _resize_for_training(resp.content)
                        filename = f"{i + 1:02d}.jpg"
                        zf.writestr(filename, img_data)

                        # 캡션 파일 생성
                        if captions and i < len(captions):
                            caption_text = captions[i]
                        else:
                            caption_text = _auto_caption(actual_trigger, style_id, i)
                        zf.writestr(f"{i + 1:02d}.txt", caption_text)

                    except Exception as e:
                        logger.warning(f"이미지 다운로드 실패 ({url}): {e}")

    logger.info(f"[LoRA Training] zip 생성 완료 ({time.time() - t0:.1f}초, 캡셔닝 포함)")

    # zip 파일을 fal.ai 에 업로드
    try:
        def _upload():
            return fal_client.upload_file(zip_path)

        zip_url = await asyncio.to_thread(_upload)
        logger.info(f"[LoRA Training] zip 업로드 완료: {zip_url}")

        arguments["images_data_url"] = zip_url
    finally:
        try:
            os.unlink(zip_path)
        except OSError:
            pass

    # 학습 시작 (비동기 — submit 후 즉시 반환)
    def _submit():
        handler = fal_client.submit(TRAINING_ENDPOINT, arguments=arguments)
        return handler.request_id

    request_id = await asyncio.to_thread(_submit)
    logger.info(f"[LoRA Training] 학습 시작됨 — request_id: {request_id}")

    return {
        "job_id": request_id,
        "status": "training",
        "trigger_word": arguments["trigger_word"],
    }


def _resize_for_training(image_bytes: bytes, target_size: int = 1024) -> bytes:
    """학습용 이미지 리사이즈 (1024x1024 정사각형, JPG)"""
    try:
        from PIL import Image
        from io import BytesIO

        img = Image.open(BytesIO(image_bytes))
        img = img.convert("RGB")

        # 정사각형 크롭 후 리사이즈
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))
        img = img.resize((target_size, target_size), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"이미지 리사이즈 실패, 원본 사용: {e}")
        return image_bytes


def _auto_caption(trigger_word: str, style_id: str, index: int) -> str:
    """자동 캡션 생성 (학습 품질 향상용)"""
    from app.models.models import LORA_STYLE_PROMPTS

    style_desc = LORA_STYLE_PROMPTS.get(style_id, "")

    # 24컷 프롬프트에서 해당 인덱스의 설명 가져오기
    try:
        from app.services.character_generation_service import _load_cuts_prompts
        cuts = _load_cuts_prompts()
        if index < len(cuts):
            pose_desc = cuts[index]["prompt"]
        else:
            pose_desc = "character portrait, various pose"
    except Exception:
        pose_desc = "character portrait, various pose"

    parts = [trigger_word]
    if style_desc:
        parts.append(style_desc)
    parts.append(pose_desc)

    return ", ".join(parts)


async def check_training_status(job_id: str) -> dict:
    """학습 상태 확인

    Returns:
        {
            "status": "training" | "completed" | "failed",
            "progress": 0.0~1.0,
            "lora_url": str (완료 시),
            "error": str (실패 시)
        }
    """
    if not fal_client:
        raise ImportError("fal-client 라이브러리가 설치되지 않았습니다.")

    fal_key = os.getenv("FAL_KEY", "")
    if fal_key:
        os.environ["FAL_KEY"] = fal_key

    try:
        def _status():
            return fal_client.status(TRAINING_ENDPOINT, job_id, with_logs=True)

        status = await asyncio.to_thread(_status)

        # fal_client.status 는 InProgress / Completed / Failed 객체 반환
        status_type = type(status).__name__

        if "Completed" in status_type or hasattr(status, "response_url"):
            # 결과 가져오기
            def _result():
                return fal_client.result(TRAINING_ENDPOINT, job_id)

            result = await asyncio.to_thread(_result)
            lora_url = ""
            if isinstance(result, dict):
                # diffusers_lora_file 에서 URL 추출
                lora_file = result.get("diffusers_lora_file", {})
                lora_url = lora_file.get("url", "") if isinstance(lora_file, dict) else ""
                if not lora_url:
                    # config_file 에서도 시도
                    config = result.get("config_file", {})
                    lora_url = config.get("url", "") if isinstance(config, dict) else ""

            return {
                "status": "completed",
                "progress": 1.0,
                "lora_url": lora_url,
            }

        elif "Failed" in status_type:
            error_msg = getattr(status, "error", "Unknown error")
            return {
                "status": "failed",
                "progress": 0.0,
                "error": str(error_msg),
            }

        else:
            # InProgress
            logs = getattr(status, "logs", [])
            # 로그에서 진행률 추정 (step 기반)
            progress = 0.0
            if logs:
                for log in reversed(logs):
                    msg = getattr(log, "message", str(log))
                    if "step" in str(msg).lower():
                        # "Step 500/1000" 같은 패턴 파싱
                        import re
                        match = re.search(r"step\s+(\d+)\s*/\s*(\d+)", str(msg), re.IGNORECASE)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            progress = current / total if total > 0 else 0.0
                            break

            return {
                "status": "training",
                "progress": progress,
            }

    except Exception as e:
        logger.error(f"[LoRA Training] 상태 확인 실패: {e}")
        return {
            "status": "failed",
            "progress": 0.0,
            "error": str(e),
        }


async def upload_image_to_fal(filepath: str) -> str:
    """로컬 이미지를 fal.ai CDN에 업로드하고 URL 반환"""
    if not fal_client:
        raise ImportError("fal-client 라이브러리가 설치되지 않았습니다.")

    fal_key = os.getenv("FAL_KEY", "")
    if fal_key:
        os.environ["FAL_KEY"] = fal_key

    def _upload():
        return fal_client.upload_file(filepath)

    url = await asyncio.to_thread(_upload)
    return url
