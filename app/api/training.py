"""
LoRA 학습 API 라우터
- 캐릭터 등록/관리
- 학습 이미지 업로드
- LoRA 학습 시작/상태 확인
- 학습된 캐릭터 목록/삭제
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
import logging
from datetime import datetime

from app.services import fal_service
from app.models.models import TrainingStatus

router = APIRouter(prefix="/api/training", tags=["training"])
logger = logging.getLogger(__name__)

# 진행 중인 학습 작업 추적: character_id → job_info
active_jobs: dict[str, dict] = {}

TRAINED_DIR = "trained_characters"


# ============================================
# Request/Response 모델
# ============================================

class CreateCharacterRequest(BaseModel):
    name: str
    trigger_word: Optional[str] = None
    description: Optional[str] = None
    style_tags: List[str] = []


class StartTrainingRequest(BaseModel):
    character_id: str
    steps: int = 1000  # 학습 스텝 (기본 1000, 빠른 학습)


class CheckStatusRequest(BaseModel):
    character_id: str


# ============================================
# 캐릭터 관리
# ============================================

@router.post("/characters/create")
async def create_character(request: CreateCharacterRequest):
    """새 학습 캐릭터 등록 (학습 전 — 이미지 업로드용 슬롯 생성)"""
    char_id = str(uuid.uuid4())[:12]
    trigger_word = request.trigger_word or f"sks_{char_id.replace('-', '')}"

    character = {
        "id": char_id,
        "name": request.name,
        "trigger_word": trigger_word,
        "lora_url": "",
        "training_images": [],
        "training_count": 0,
        "training_rounds": 0,
        "status": TrainingStatus.PENDING.value,
        "preview_image": None,
        "description": request.description,
        "style_tags": request.style_tags,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "error_message": None,
    }

    fal_service.save_character(character)
    logger.info(f"[Training] 캐릭터 생성: {char_id} ({request.name})")

    return {"success": True, "character": character}


@router.get("/characters")
async def list_characters():
    """학습된 캐릭터 목록"""
    chars = fal_service.list_characters()
    return {"characters": chars}


@router.get("/characters/{character_id}")
async def get_character(character_id: str):
    """캐릭터 상세 정보"""
    char = fal_service.load_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")
    return char


@router.delete("/characters/{character_id}")
async def delete_character(character_id: str):
    """캐릭터 삭제 (학습 데이터 포함)"""
    fal_service.delete_character(character_id)
    active_jobs.pop(character_id, None)
    return {"success": True}


# ============================================
# 이미지 업로드
# ============================================

@router.post("/characters/{character_id}/upload-images")
async def upload_training_images(
    character_id: str,
    files: List[UploadFile] = File(...)
):
    """학습용 이미지 업로드 (여러 장)"""
    char = fal_service.load_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")

    # 이미지 저장 디렉토리
    img_dir = os.path.join(TRAINED_DIR, character_id, "images")
    os.makedirs(img_dir, exist_ok=True)

    saved_paths = []
    for file in files:
        # 파일명 충돌 방지
        ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
        fname = f"{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(img_dir, fname)

        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)
        saved_paths.append(filepath)

    # 캐릭터 데이터 업데이트
    char["training_images"].extend(saved_paths)
    char["training_count"] = len(char["training_images"])
    char["updated_at"] = datetime.now().isoformat()

    # 첫 이미지를 미리보기로 설정 (없다면)
    if not char.get("preview_image") and saved_paths:
        char["preview_image"] = saved_paths[0]

    fal_service.save_character(char)
    logger.info(f"[Training] 이미지 {len(saved_paths)}장 업로드 완료 (캐릭터: {character_id})")

    return {
        "success": True,
        "uploaded_count": len(saved_paths),
        "total_images": char["training_count"],
        "paths": saved_paths,
    }


@router.delete("/characters/{character_id}/images")
async def clear_training_images(character_id: str):
    """학습 이미지 전부 삭제"""
    char = fal_service.load_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")

    img_dir = os.path.join(TRAINED_DIR, character_id, "images")
    if os.path.exists(img_dir):
        import shutil
        shutil.rmtree(img_dir, ignore_errors=True)

    char["training_images"] = []
    char["training_count"] = 0
    char["preview_image"] = None
    char["updated_at"] = datetime.now().isoformat()
    fal_service.save_character(char)

    return {"success": True}


# ============================================
# LoRA 학습 시작/상태/결과
# ============================================

@router.post("/start")
async def start_training(request: StartTrainingRequest):
    """LoRA 학습 시작

    학습 이미지를 fal.ai CDN 에 업로드 후 Flux LoRA Fast Training 호출
    """
    char = fal_service.load_character(request.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")

    images = char.get("training_images", [])
    if len(images) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"학습 이미지가 최소 5장 필요합니다 (현재 {len(images)}장)"
        )

    # 이미지를 fal.ai CDN 에 업로드
    char["status"] = TrainingStatus.UPLOADING.value
    char["updated_at"] = datetime.now().isoformat()
    fal_service.save_character(char)

    try:
        image_urls = []
        for img_path in images:
            if os.path.exists(img_path):
                url = await fal_service.upload_image_to_fal(img_path)
                image_urls.append(url)
            elif img_path.startswith("http"):
                image_urls.append(img_path)

        if len(image_urls) < 5:
            raise ValueError(f"유효한 이미지가 부족합니다 ({len(image_urls)}장)")

        # 학습 시작
        result = await fal_service.start_training(
            character_id=request.character_id,
            image_urls=image_urls,
            trigger_word=char.get("trigger_word", ""),
            steps=request.steps,
        )

        # 상태 업데이트
        char["status"] = TrainingStatus.TRAINING.value
        char["trigger_word"] = result.get("trigger_word", char.get("trigger_word", ""))
        char["training_rounds"] = char.get("training_rounds", 0) + 1
        char["updated_at"] = datetime.now().isoformat()
        fal_service.save_character(char)

        # 작업 추적
        active_jobs[request.character_id] = {
            "job_id": result["job_id"],
            "started_at": datetime.now().isoformat(),
        }

        logger.info(f"[Training] 학습 시작: {request.character_id}, job_id: {result['job_id']}")

        return {
            "success": True,
            "job_id": result["job_id"],
            "trigger_word": result.get("trigger_word"),
            "image_count": len(image_urls),
            "steps": request.steps,
        }

    except Exception as e:
        char["status"] = TrainingStatus.FAILED.value
        char["error_message"] = str(e)
        char["updated_at"] = datetime.now().isoformat()
        fal_service.save_character(char)
        logger.error(f"[Training] 학습 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def check_status(request: CheckStatusRequest):
    """학습 상태 확인"""
    char = fal_service.load_character(request.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")

    job_info = active_jobs.get(request.character_id)
    if not job_info:
        # 이미 완료되었거나 시작하지 않은 경우
        return {
            "status": char.get("status", "pending"),
            "progress": 1.0 if char.get("status") == "completed" else 0.0,
            "lora_url": char.get("lora_url", ""),
        }

    try:
        result = await fal_service.check_training_status(job_info["job_id"])

        if result["status"] == "completed":
            # 학습 완료 — 캐릭터 업데이트
            char["status"] = TrainingStatus.COMPLETED.value
            char["lora_url"] = result.get("lora_url", "")
            char["updated_at"] = datetime.now().isoformat()
            char["error_message"] = None
            fal_service.save_character(char)
            active_jobs.pop(request.character_id, None)
            logger.info(f"[Training] 학습 완료: {request.character_id}")

        elif result["status"] == "failed":
            char["status"] = TrainingStatus.FAILED.value
            char["error_message"] = result.get("error", "Unknown error")
            char["updated_at"] = datetime.now().isoformat()
            fal_service.save_character(char)
            active_jobs.pop(request.character_id, None)
            logger.error(f"[Training] 학습 실패: {request.character_id} - {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[Training] 상태 확인 오류: {e}")
        return {
            "status": "error",
            "progress": 0.0,
            "error": str(e),
        }
