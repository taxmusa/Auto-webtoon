"""
LoRA 학습 API 라우터
- 캐릭터 등록/관리
- 학습 이미지 업로드
- LoRA 학습 시작/상태 확인
- 학습된 캐릭터 목록/삭제
- ★ 자동 학습: 사진 1장 → 스타일 선택 → 24컷 생성 → 선별 → 학습
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid
import os
import logging
from datetime import datetime

from app.services import fal_service
from app.services import character_generation_service as char_gen
from app.models.models import TrainingStatus, LORA_STYLE_LABELS, LORA_STYLE_PROMPTS
from app.core.config import (
    MVP_ACTIVE_STYLES,
    LORA_SCALE_DEFAULT,
    MIN_SELECTED_CUTS,
    GENERATION_CUTS_COUNT,
)

router = APIRouter(prefix="/api/training", tags=["training"])
logger = logging.getLogger(__name__)

# 진행 중인 학습 작업 추적: character_id → job_info
active_jobs: dict[str, dict] = {}

# 백그라운드 24컷 생성 작업 추적: session_id → task
_generation_tasks: dict[str, dict] = {}

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


class SelectStyleRequest(BaseModel):
    session_id: str
    style_id: str = "original"
    custom_prompt: Optional[str] = None


class SelectCutsRequest(BaseModel):
    session_id: str
    selected_cut_ids: List[int]


class PrepareAndTrainRequest(BaseModel):
    session_id: str
    character_name: str
    trigger_word: Optional[str] = None


class TestGenerateRequest(BaseModel):
    prompt: Optional[str] = None
    lora_scale: float = LORA_SCALE_DEFAULT


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


# ============================================
# ★ 자동 학습 워크플로우 (사진 1장 → 24컷 → 학습)
# ============================================

@router.post("/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    """Step 1: 사진 1장 업로드 → 생성 세션 시작

    Returns:
        session_id, photo_url, 스타일 목록, 비용 추정
    """
    # 파일 유효성 검사
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 파일만 지원합니다.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="파일 크기가 10MB를 초과합니다.")

    # 로컬 저장
    save_dir = os.path.join(TRAINED_DIR, "_uploads")
    os.makedirs(save_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "photo.png")[1] or ".png"
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(save_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    local_url = f"/trained_characters/_uploads/{filename}"

    # Cloudinary 업로드 (공개 URL 확보 - Flux Kontext용)
    public_url = local_url
    try:
        from app.services.cloudinary_service import get_cloudinary_service
        from PIL import Image
        from io import BytesIO

        service = get_cloudinary_service()
        if service.cloud_name:
            img = Image.open(BytesIO(content))
            url = await service.upload_image(img, "character_photo")
            if url:
                public_url = url
    except Exception as e:
        logger.warning(f"Cloudinary 업로드 실패, 로컬 URL 사용: {e}")

    # 세션 생성
    session = char_gen.create_session(
        photo_url=public_url,
        photo_local_path=filepath,
    )

    # 스타일 목록 + 비용 추정
    styles = []
    for sid, label in LORA_STYLE_LABELS.items():
        styles.append({
            "id": sid,
            "label": label,
            "active": sid in MVP_ACTIVE_STYLES,
        })

    cost = char_gen.estimate_cost("original")

    logger.info(f"[AutoTrain] 사진 업로드 완료: session={session['session_id']}")

    return {
        "session_id": session["session_id"],
        "photo_url": public_url,
        "photo_local_url": local_url,
        "styles": styles,
        "estimated_cost": cost,
    }


@router.post("/select-style")
async def select_style(request: SelectStyleRequest):
    """Step 2: 스타일 선택"""
    session = char_gen.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # MVP에서 활성 스타일만 허용
    if request.style_id not in MVP_ACTIVE_STYLES and request.style_id != "custom":
        raise HTTPException(
            status_code=400,
            detail=f"현재 지원하지 않는 스타일입니다. 지원: {MVP_ACTIVE_STYLES}"
        )

    session["style_id"] = request.style_id
    session["custom_prompt"] = request.custom_prompt
    char_gen.save_session(session)

    cost = char_gen.estimate_cost(request.style_id)

    return {
        "session_id": request.session_id,
        "selected_style": request.style_id,
        "style_label": LORA_STYLE_LABELS.get(request.style_id, ""),
        "estimated_cost": cost,
    }


@router.post("/generate-24-cuts")
async def generate_24_cuts(
    session_id: str = Form(...),
    background_tasks: BackgroundTasks = None,
):
    """Step 3: 24컷 자동 생성 시작 (백그라운드)"""
    session = char_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    if session.get("status") == "generating":
        return {
            "session_id": session_id,
            "status": "already_generating",
            "message": "이미 생성 중입니다.",
        }

    # 백그라운드에서 생성 시작
    import asyncio

    async def _bg_generate():
        try:
            await char_gen.generate_24_cuts(session_id)
        except Exception as e:
            logger.error(f"[AutoTrain] 24컷 생성 실패: {e}")
            s = char_gen.get_session(session_id)
            if s:
                s["status"] = "failed"
                char_gen.save_session(s)

    task = asyncio.create_task(_bg_generate())
    _generation_tasks[session_id] = {"task": task, "started_at": datetime.now().isoformat()}

    session["status"] = "generating"
    char_gen.save_session(session)

    logger.info(f"[AutoTrain] 24컷 생성 시작: session={session_id}")

    return {
        "session_id": session_id,
        "status": "generating",
        "total_cuts": GENERATION_CUTS_COUNT,
        "message": "24컷 생성이 시작되었습니다.",
    }


@router.get("/generation-status/{session_id}")
async def get_generation_status(session_id: str):
    """Step 3: 24컷 생성 진행 상태 (polling)"""
    session = char_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    generated = session.get("generated_cuts", [])
    total = session.get("total_cuts", GENERATION_CUTS_COUNT)
    completed = len([c for c in generated if c.get("url")])

    return {
        "session_id": session_id,
        "status": session.get("status", "idle"),
        "completed_cuts": completed,
        "total_cuts": total,
        "generated_cuts": generated,
    }


@router.post("/select-cuts")
async def select_cuts(request: SelectCutsRequest):
    """Step 4: 이미지 선별 (사용자가 체크박스로 선택)"""
    session = char_gen.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 선택된 컷 업데이트
    session["selected_cut_ids"] = request.selected_cut_ids

    # 생성된 컷의 selected 상태 업데이트
    for cut in session.get("generated_cuts", []):
        cut["selected"] = cut["id"] in request.selected_cut_ids

    char_gen.save_session(session)

    selected_count = len(request.selected_cut_ids)
    meets_minimum = selected_count >= MIN_SELECTED_CUTS

    return {
        "session_id": request.session_id,
        "selected_count": selected_count,
        "meets_minimum": meets_minimum,
        "min_required": MIN_SELECTED_CUTS,
        "message": "" if meets_minimum else f"최소 {MIN_SELECTED_CUTS}장 이상을 권장합니다.",
    }


@router.post("/prepare-and-train")
async def prepare_and_train(request: PrepareAndTrainRequest):
    """Step 5+6: 학습 데이터 패키징 + LoRA 학습 시작 (통합)"""
    session = char_gen.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    selected_ids = session.get("selected_cut_ids", [])
    generated_cuts = session.get("generated_cuts", [])

    # 선택된 컷의 URL 수집
    selected_urls = []
    for cut in generated_cuts:
        if cut["id"] in selected_ids and cut.get("url"):
            selected_urls.append(cut["url"])

    if len(selected_urls) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"학습에 최소 5장의 이미지가 필요합니다. (현재 {len(selected_urls)}장)"
        )

    # 트리거 워드 생성
    existing_chars = fal_service.list_characters()
    existing_words = [c.get("trigger_word", "") for c in existing_chars]

    trigger_word = request.trigger_word
    if not trigger_word:
        trigger_word = char_gen.generate_trigger_word(request.character_name, existing_words)

    style_id = session.get("style_id", "original")

    # 캐릭터 슬롯 생성
    char_id = str(uuid.uuid4())[:12]
    character = {
        "id": char_id,
        "name": request.character_name,
        "trigger_word": trigger_word,
        "lora_url": "",
        "training_images": selected_urls,
        "training_count": len(selected_urls),
        "training_rounds": 1,
        "status": TrainingStatus.UPLOADING.value,
        "preview_image": selected_urls[0] if selected_urls else None,
        "description": f"자동 학습 ({LORA_STYLE_LABELS.get(style_id, style_id)})",
        "style_tags": [style_id],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "error_message": None,
        # 명세서 추가 필드
        "style_id": style_id,
        "style_label": LORA_STYLE_LABELS.get(style_id, ""),
        "lora_scale_default": LORA_SCALE_DEFAULT,
        "original_photo_url": session.get("photo_url", ""),
        "sample_images": [],
        "training_steps": 1500,
    }
    fal_service.save_character(character)

    session["character_id"] = char_id
    char_gen.save_session(session)

    # 학습 시작
    try:
        result = await fal_service.start_training(
            character_id=char_id,
            image_urls=selected_urls,
            trigger_word=trigger_word,
            style_id=style_id,
        )

        # 상태 업데이트
        character["status"] = TrainingStatus.TRAINING.value
        character["updated_at"] = datetime.now().isoformat()
        fal_service.save_character(character)

        # 작업 추적
        active_jobs[char_id] = {
            "job_id": result["job_id"],
            "started_at": datetime.now().isoformat(),
            "session_id": request.session_id,
        }

        session["training_job_id"] = result["job_id"]
        char_gen.save_session(session)

        logger.info(f"[AutoTrain] 학습 시작: char={char_id}, job={result['job_id']}")

        return {
            "success": True,
            "character_id": char_id,
            "job_id": result["job_id"],
            "trigger_word": trigger_word,
            "image_count": len(selected_urls),
            "character": character,
        }

    except Exception as e:
        character["status"] = TrainingStatus.FAILED.value
        character["error_message"] = str(e)
        fal_service.save_character(character)
        logger.error(f"[AutoTrain] 학습 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-status/{character_id}")
async def get_training_status(character_id: str):
    """Step 6: 학습 진행 상태 (polling) — 기존 /status와 별도 경로"""
    char = fal_service.load_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다.")

    job_info = active_jobs.get(character_id)
    if not job_info:
        return {
            "status": char.get("status", "pending"),
            "progress": 1.0 if char.get("status") == "completed" else 0.0,
            "lora_url": char.get("lora_url", ""),
            "character": char,
        }

    try:
        result = await fal_service.check_training_status(job_info["job_id"])

        if result["status"] == "completed":
            char["status"] = TrainingStatus.COMPLETED.value
            char["lora_url"] = result.get("lora_url", "")
            char["updated_at"] = datetime.now().isoformat()
            char["error_message"] = None
            fal_service.save_character(char)
            active_jobs.pop(character_id, None)

            # 학습 완료 시 테스트 이미지 자동 생성 (백그라운드)
            if char.get("lora_url"):
                import asyncio

                async def _bg_test():
                    try:
                        test_urls = await char_gen.generate_test_images(
                            trigger_word=char.get("trigger_word", ""),
                            lora_url=char["lora_url"],
                        )
                        # 테스트 이미지 저장
                        c = fal_service.load_character(character_id)
                        if c:
                            c["sample_images"] = test_urls
                            c["updated_at"] = datetime.now().isoformat()
                            fal_service.save_character(c)
                        logger.info(f"[AutoTrain] 테스트 이미지 {len(test_urls)}장 생성 완료")
                    except Exception as e:
                        logger.error(f"[AutoTrain] 테스트 이미지 생성 실패: {e}")

                asyncio.create_task(_bg_test())

            logger.info(f"[AutoTrain] 학습 완료: {character_id}")

        elif result["status"] == "failed":
            char["status"] = TrainingStatus.FAILED.value
            char["error_message"] = result.get("error", "Unknown error")
            char["updated_at"] = datetime.now().isoformat()
            fal_service.save_character(char)
            active_jobs.pop(character_id, None)

        result["character"] = char
        return result

    except Exception as e:
        logger.error(f"[AutoTrain] 상태 확인 오류: {e}")
        return {
            "status": "error",
            "progress": 0.0,
            "error": str(e),
            "character": char,
        }


@router.post("/characters/{character_id}/test-generate")
async def test_generate(character_id: str, request: TestGenerateRequest):
    """Step 7: 학습된 캐릭터로 테스트 이미지 생성"""
    char = fal_service.load_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다.")

    if not char.get("lora_url"):
        raise HTTPException(status_code=400, detail="아직 학습이 완료되지 않았습니다.")

    try:
        if request.prompt:
            # 사용자 정의 프롬프트
            from app.services.image_generator import FluxLoraGenerator
            from app.core.config import get_settings

            settings = get_settings()
            generator = FluxLoraGenerator(
                api_key=settings.fal_key,
                model="flux-lora",
                lora_url=char["lora_url"],
                trigger_word=char.get("trigger_word", ""),
            )
            result = await generator.generate(
                prompt=request.prompt,
                size="1024x1024",
            )
            if isinstance(result, bytes):
                url = await char_gen._save_and_get_url(result, 999)
            else:
                url = result
            return {"success": True, "image_url": url}
        else:
            # 기본 테스트 이미지 3장 생성
            test_urls = await char_gen.generate_test_images(
                trigger_word=char.get("trigger_word", ""),
                lora_url=char["lora_url"],
                lora_scale=request.lora_scale,
            )

            # 저장
            char["sample_images"] = test_urls
            char["updated_at"] = datetime.now().isoformat()
            fal_service.save_character(char)

            return {"success": True, "test_images": test_urls}

    except Exception as e:
        logger.error(f"[AutoTrain] 테스트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-styles")
async def get_available_styles():
    """사용 가능한 학습 스타일 목록 반환"""
    styles = []
    for sid, label in LORA_STYLE_LABELS.items():
        styles.append({
            "id": sid,
            "label": label,
            "prompt": LORA_STYLE_PROMPTS.get(sid, ""),
            "active": sid in MVP_ACTIVE_STYLES,
        })
    return {"styles": styles}


@router.get("/cost-estimate")
async def get_cost_estimate(style_id: str = "original", cuts_count: int = 24):
    """비용 추정"""
    return char_gen.estimate_cost(style_id, cuts_count)
