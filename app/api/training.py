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
    """새 학습 캐릭터 등록 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.get("/characters")
async def list_characters():
    """학습된 캐릭터 목록 — fal.ai 지원 중단으로 비활성화"""
    return {"characters": [], "message": "LoRA 학습 기능은 현재 지원되지 않습니다."}


@router.get("/characters/{character_id}")
async def get_character(character_id: str):
    """캐릭터 상세 정보 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.delete("/characters/{character_id}")
async def delete_character(character_id: str):
    """캐릭터 삭제 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


# ============================================
# 이미지 업로드
# ============================================

@router.post("/characters/{character_id}/upload-images")
async def upload_training_images(
    character_id: str,
    files: List[UploadFile] = File(...)
):
    """학습용 이미지 업로드 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.delete("/characters/{character_id}/images")
async def clear_training_images(character_id: str):
    """학습 이미지 전부 삭제 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


# ============================================
# LoRA 학습 시작/상태/결과
# ============================================

@router.post("/start")
async def start_training(request: StartTrainingRequest):
    """LoRA 학습 시작 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.post("/status")
async def check_status(request: CheckStatusRequest):
    """학습 상태 확인 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


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
    """Step 3: 이름 입력 + LoRA 학습 시작 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.get("/training-status/{character_id}")
async def get_training_status(character_id: str):
    """Step 6: 학습 진행 상태 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


@router.post("/characters/{character_id}/test-generate")
async def test_generate(character_id: str, request: TestGenerateRequest):
    """Step 7: 학습된 캐릭터로 테스트 이미지 생성 — fal.ai 지원 중단으로 비활성화"""
    raise HTTPException(
        status_code=501,
        detail="LoRA 학습 기능은 fal.ai 서비스 의존성 제거로 현재 지원되지 않습니다."
    )


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
