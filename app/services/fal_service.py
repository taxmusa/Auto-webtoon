"""
fal.ai LoRA 학습 서비스
- Flux LoRA Fast Training API 호출
- 학습 이미지 업로드 → 학습 시작 → 상태 폴링 → 완료 시 lora_url 반환
"""
import asyncio
import os
import uuid
import json
import time
import logging
from typing import List, Optional
from datetime import datetime

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
    steps: int = 1000,
) -> dict:
    """LoRA 학습 시작

    Args:
        character_id: TrainedCharacter.id
        image_urls: 학습 이미지 URL 목록 (fal.ai가 접근 가능해야 함)
        trigger_word: 트리거 워드
        steps: 학습 스텝 수 (기본 1000)

    Returns:
        {"job_id": str, "status": "training"} 또는 에러
    """
    if not fal_client:
        raise ImportError("fal-client 라이브러리가 설치되지 않았습니다.")

    fal_key = os.getenv("FAL_KEY", "")
    if not fal_key:
        raise ValueError("FAL_KEY 환경변수가 설정되지 않았습니다.")
    os.environ["FAL_KEY"] = fal_key

    # 이미지 URL 을 fal.ai 학습 포맷으로 변환
    # fal.ai 는 images_data_url (zip) 또는 images 리스트를 받음
    training_images = []
    for url in image_urls:
        training_images.append({"url": url})

    arguments = {
        "images_data_url": None,  # zip 대신 개별 이미지 사용 시 None
        "trigger_word": trigger_word or f"sks_{character_id[:8]}",
        "steps": steps,
        "create_masks": True,   # 자동 마스크 생성 (배경 제거)
        "is_style": False,      # 캐릭터 학습 (스타일이 아님)
    }

    # 이미지 URL 리스트를 전달하는 방식 결정
    # fal.ai flux-lora-fast-training 은 images_data_url (zip URL) 을 받음
    # 개별 이미지는 zip 으로 묶어서 업로드하거나, data URI 변환 필요
    # → fal_client.upload 을 사용하여 zip 생성 후 URL 획득
    import tempfile
    import zipfile
    import httpx

    t0 = time.time()
    logger.info(f"[LoRA Training] 이미지 {len(image_urls)}장 다운로드 시작")

    # 이미지 다운로드 + zip 생성
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for i, url in enumerate(image_urls):
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        ext = "png"  # 기본 확장자
                        if "jpeg" in resp.headers.get("content-type", ""):
                            ext = "jpg"
                        zf.writestr(f"image_{i:03d}.{ext}", resp.content)
                    except Exception as e:
                        logger.warning(f"이미지 다운로드 실패 ({url}): {e}")

    logger.info(f"[LoRA Training] zip 생성 완료 ({time.time() - t0:.1f}초)")

    # zip 파일을 fal.ai 에 업로드
    try:
        def _upload():
            return fal_client.upload_file(zip_path)

        zip_url = await asyncio.to_thread(_upload)
        logger.info(f"[LoRA Training] zip 업로드 완료: {zip_url}")

        arguments["images_data_url"] = zip_url
    finally:
        # 임시 zip 파일 삭제
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
