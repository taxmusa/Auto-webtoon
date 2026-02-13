"""
LoRA 학습 API 라우터
- 캐릭터 등록/관리
- 학습 이미지 업로드
- LoRA 학습 시작/상태 확인
- 학습된 캐릭터 목록/삭제
- ★ 자동 학습: Grid 이미지 업로드 → 자동 분할 → 이름 입력 → 학습 → 완료
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
import logging
from datetime import datetime

from app.services import fal_service
from app.services import character_generation_service as char_gen
from app.models.models import TrainingStatus
from app.core.config import (
    LORA_SCALE_DEFAULT,
)

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


class SplitGridRequest(BaseModel):
    session_id: str
    cols: int = 4
    rows: int = 6


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

@router.post("/upload-grid")
async def upload_grid(file: UploadFile = File(...)):
    """Step 1: 24컷 합본 이미지 업로드

    사용자가 나노바나나 등에서 직접 만든 24컷 grid 이미지를 업로드합니다.
    이후 split-grid API로 자동 분할합니다.

    Returns:
        session_id, photo_url, 이미지 크기 정보
    """
    # 파일 유효성 검사
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 파일만 지원합니다.")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB (합본 이미지는 크기가 클 수 있음)
        raise HTTPException(status_code=400, detail="파일 크기가 20MB를 초과합니다.")

    # 이미지 크기 확인
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(content))
    img_width, img_height = img.size

    # 로컬 저장
    save_dir = os.path.join(TRAINED_DIR, "_uploads")
    os.makedirs(save_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "grid.png")[1] or ".png"
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(save_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    local_url = f"/trained_characters/_uploads/{filename}"

    # 세션 생성
    session = char_gen.create_session(
        photo_url=local_url,
        photo_local_path=filepath,
    )
    session["grid_image_path"] = filepath
    session["grid_image_url"] = local_url
    session["image_width"] = img_width
    session["image_height"] = img_height
    char_gen.save_session(session)

    # grid 크기 추천 (24 = 4x6, 6x4, 3x8, 8x3)
    aspect = img_width / img_height
    if aspect > 1.2:
        # 가로가 긴 이미지 → 6열 x 4행
        recommended = {"cols": 6, "rows": 4}
    elif aspect < 0.8:
        # 세로가 긴 이미지 → 4열 x 6행
        recommended = {"cols": 4, "rows": 6}
    else:
        # 정사각형에 가까움 → 5열 x 5행 (25컷) 또는 4x6
        recommended = {"cols": 4, "rows": 6}

    logger.info(f"[AutoTrain] Grid 이미지 업로드: session={session['session_id']}, size={img_width}x{img_height}")

    return {
        "session_id": session["session_id"],
        "grid_image_url": local_url,
        "image_width": img_width,
        "image_height": img_height,
        "recommended_grid": recommended,
    }


@router.post("/split-grid")
async def split_grid(request: SplitGridRequest):
    """Step 2: Grid 이미지를 자동 분할하여 개별 컷으로 저장

    Args:
        session_id: 세션 ID
        cols: 열 수 (기본 4)
        rows: 행 수 (기본 6)

    Returns:
        분할된 각 컷의 URL 목록
    """
    from PIL import Image
    from io import BytesIO

    session = char_gen.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    grid_path = session.get("grid_image_path")
    if not grid_path or not os.path.exists(grid_path):
        raise HTTPException(status_code=400, detail="Grid 이미지를 찾을 수 없습니다. 먼저 이미지를 업로드해주세요.")

    cols = request.cols
    rows = request.rows
    total_cuts = cols * rows

    # 이미지 열기
    img = Image.open(grid_path)
    img_w, img_h = img.size
    cut_w = img_w // cols
    cut_h = img_h // rows

    # 분할 저장 디렉토리
    save_dir = os.path.join(TRAINED_DIR, "_temp_cuts", request.session_id[:12])
    os.makedirs(save_dir, exist_ok=True)

    cuts = []
    cut_urls = []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c + 1
            box = (c * cut_w, r * cut_h, (c + 1) * cut_w, (r + 1) * cut_h)
            cut_img = img.crop(box)

            # 학습에 적합한 크기로 리사이즈 (512x512 이상 권장)
            if cut_w < 512 or cut_h < 512:
                cut_img = cut_img.resize((max(cut_w, 512), max(cut_h, 512)), Image.LANCZOS)

            cut_filename = f"cut_{idx:02d}.png"
            cut_filepath = os.path.join(save_dir, cut_filename)
            cut_img.save(cut_filepath, "PNG")

            cut_url = f"/trained_characters/_temp_cuts/{request.session_id[:12]}/{cut_filename}"
            cuts.append({
                "id": idx,
                "url": cut_url,
                "selected": True,  # 기본 전체 선택
            })
            cut_urls.append(cut_url)

    # 세션 업데이트
    session["generated_cuts"] = cuts
    session["selected_cut_ids"] = list(range(1, total_cuts + 1))
    session["grid_cols"] = cols
    session["grid_rows"] = rows
    session["total_cuts"] = total_cuts
    session["status"] = "split_completed"
    char_gen.save_session(session)

    logger.info(f"[AutoTrain] Grid 분할 완료: {cols}x{rows}={total_cuts}컷, session={request.session_id}")

    return {
        "session_id": request.session_id,
        "total_cuts": total_cuts,
        "cols": cols,
        "rows": rows,
        "cut_size": f"{cut_w}x{cut_h}",
        "cuts": cuts,
    }


@router.post("/prepare-and-train")
async def prepare_and_train(request: PrepareAndTrainRequest):
    """Step 3: 이름 입력 + LoRA 학습 시작 (통합)

    Grid 분할 완료된 세션에서 분할 이미지들을 수집하여 LoRA 학습을 시작합니다.
    """
    session = char_gen.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    generated_cuts = session.get("generated_cuts", [])

    # 분할된 컷의 URL 수집 (전체 사용)
    cut_urls = [cut["url"] for cut in generated_cuts if cut.get("url")]

    if len(cut_urls) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"학습에 최소 5장의 이미지가 필요합니다. (현재 {len(cut_urls)}장)"
        )

    # 트리거 워드 생성
    existing_chars = fal_service.list_characters()
    existing_words = [c.get("trigger_word", "") for c in existing_chars]

    trigger_word = request.trigger_word
    if not trigger_word:
        trigger_word = char_gen.generate_trigger_word(request.character_name, existing_words)

    # 캐릭터 슬롯 생성
    char_id = str(uuid.uuid4())[:12]
    character = {
        "id": char_id,
        "name": request.character_name,
        "trigger_word": trigger_word,
        "lora_url": "",
        "training_images": cut_urls,
        "training_count": len(cut_urls),
        "training_rounds": 1,
        "status": TrainingStatus.UPLOADING.value,
        "preview_image": session.get("grid_image_url", cut_urls[0] if cut_urls else ""),
        "description": f"Grid 분할 학습 ({len(cut_urls)}컷)",
        "style_tags": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "error_message": None,
        "lora_scale_default": LORA_SCALE_DEFAULT,
        "original_photo_url": session.get("grid_image_url", ""),
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
            image_urls=cut_urls,
            trigger_word=trigger_word,
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
            "image_count": len(cut_urls),
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


@router.get("/grid-guide")
async def get_grid_guide():
    """24컷 정형 가이드 반환 — 사용자가 grid 이미지를 만들 때 참고"""
    return {
        "total_cuts": 24,
        "recommended_layout": "4x6",
        "categories": [
            {"name": "표정", "count": 10, "items": [
                "정면 미소", "활짝 웃음", "놀람", "화남", "슬픔",
                "당황", "자신감", "생각 중", "무표정", "윙크"
            ]},
            {"name": "각도", "count": 4, "items": [
                "좌측 45도", "우측 45도", "좌측 프로필", "우측 프로필"
            ]},
            {"name": "상반신 포즈", "count": 6, "items": [
                "팔짱", "손 흔들기", "엄지 척", "한 손 가리키기", "양손 위로", "설명하는 포즈"
            ]},
            {"name": "전신", "count": 2, "items": [
                "서있는 정면", "앉은 포즈"
            ]},
            {"name": "장면", "count": 2, "items": [
                "일상 배경", "걷는 포즈"
            ]},
        ],
    }
