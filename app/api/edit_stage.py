"""
이미지 편집 단계 API 라우터
- 톤 조절 (전체/개별)
- 씬 확정/되돌리기
- 씬 재생성 (프롬프트 수정)
- 사용자 이미지 업로드
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
import os
import logging

from app.models.models import ImageEditStatus, GeneratedImage
from app.services.image_editor import (
    get_tone_adjuster, get_history_manager, parse_tone_command
)

router = APIRouter(prefix="/api/edit-stage", tags=["edit-stage"])
logger = logging.getLogger(__name__)


# ============================================
# Request/Response 모델
# ============================================

class ToneAdjustRequest(BaseModel):
    """톤 조절 요청"""
    command: str                          # 사용자 자연어 명령 (예: "전체적으로 밝게")
    scene_numbers: Optional[List[int]] = None  # None이면 전체 적용


class ToneAnalyzeResponse(BaseModel):
    """톤 조절 분석 결과"""
    type: str             # "pillow" | "ai_required" | "unknown"
    effects: list = []    # [{"effect": "brightness", "value": 1.3}]
    cost: int = 0         # 비용 (0=무료)
    message: str = ""     # 사용자에게 표시할 메시지


class ToneApplyRequest(BaseModel):
    """톤 조절 적용 요청"""
    effects: list         # [{"effect": "brightness", "value": 1.3}]
    scene_numbers: Optional[List[int]] = None  # None이면 전체 적용


class SceneConfirmRequest(BaseModel):
    """씬 확정 요청"""
    scene_number: int


class SceneRegenerateRequest(BaseModel):
    """씬 재생성 요청"""
    scene_number: int
    new_prompt: Optional[str] = None  # None이면 기존 프롬프트 재사용


class EditStageStatusResponse(BaseModel):
    """편집 단계 전체 상태"""
    total_scenes: int
    confirmed_count: int
    pending_count: int
    all_confirmed: bool
    scenes: list  # [{scene_number, status, image_url, has_history}]


# ============================================
# 세션 접근 헬퍼 (workflow.py의 세션 공유)
# ============================================

def _get_session(session_id: str):
    """workflow.py의 세션 딕셔너리에서 세션 가져오기"""
    from app.api.workflow import sessions
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}")
    return session


# ============================================
# API 엔드포인트
# ============================================

@router.get("/{session_id}/status", response_model=EditStageStatusResponse)
async def get_edit_stage_status(session_id: str):
    """편집 단계 전체 상태 조회"""
    session = _get_session(session_id)

    scenes_info = []
    confirmed = 0
    pending = 0

    for img in session.images:
        has_history = len(img.image_history) > 0
        scenes_info.append({
            "scene_number": img.scene_number,
            "edit_status": img.edit_status.value,
            "image_url": img.image_url,
            "local_path": img.local_path,
            "prompt_used": img.prompt_used,
            "has_history": has_history,
            "tone_adjusted": img.tone_adjusted,
        })

        if img.edit_status == ImageEditStatus.CONFIRMED:
            confirmed += 1
        else:
            pending += 1

    return EditStageStatusResponse(
        total_scenes=len(session.images),
        confirmed_count=confirmed,
        pending_count=pending,
        all_confirmed=(pending == 0 and len(session.images) > 0),
        scenes=scenes_info,
    )


@router.post("/{session_id}/tone-analyze")
async def analyze_tone_command(session_id: str, req: ToneAdjustRequest):
    """자연어 명령 분석 - Pillow로 처리 가능한지 판별"""
    _get_session(session_id)  # 세션 존재 확인

    result = parse_tone_command(req.command)

    if result is None:
        return ToneAnalyzeResponse(
            type="unknown",
            effects=[],
            cost=0,
            message="😅 명령을 인식하지 못했습니다. '밝게', '채도 높여', '따뜻하게' 같은 표현을 사용해 주세요."
        )

    return ToneAnalyzeResponse(
        type=result["type"],
        effects=result.get("effects", []),
        cost=result.get("cost", 0),
        message=result.get("message", ""),
    )


@router.post("/{session_id}/tone-apply")
async def apply_tone_adjustment(session_id: str, req: ToneApplyRequest):
    """Pillow 톤 조절 실제 적용"""
    session = _get_session(session_id)
    adjuster = get_tone_adjuster()
    history_mgr = get_history_manager()

    target_images = session.images
    if req.scene_numbers:
        target_images = [img for img in session.images if img.scene_number in req.scene_numbers]

    if not target_images:
        raise HTTPException(status_code=400, detail="적용할 이미지가 없습니다.")

    results = []
    for img in target_images:
        if not img.local_path or not os.path.exists(img.local_path):
            results.append({"scene_number": img.scene_number, "status": "skip", "reason": "이미지 파일 없음"})
            continue

        # 원본 백업
        if not img.original_path:
            img.original_path = img.local_path

        # 이력 저장
        history_path = history_mgr.save_to_history(img.local_path, session_id, img.scene_number)
        img.image_history.append(history_path)

        # 톤 조절 적용 (현재 이미지에 덮어쓰기)
        from PIL import Image
        pil_img = Image.open(img.local_path).convert("RGB")

        for adj in req.effects:
            effect = adj.get("effect", "")
            value = adj.get("value", 1.0)
            pil_img = adjuster.apply_adjustment(pil_img, effect, value)

        pil_img.save(img.local_path, quality=95)
        img.tone_adjusted = True

        results.append({
            "scene_number": img.scene_number,
            "status": "success",
            "image_path": img.local_path,
        })

    # 톤 조절 이력 기록
    session.global_tone_adjustments.append({
        "effects": req.effects,
        "scene_numbers": req.scene_numbers,
        "count": len(results),
    })

    logger.info(f"[톤 조절] 세션 {session_id}: {len(results)}개 이미지 처리 완료")
    return {"success": True, "results": results}


@router.post("/{session_id}/scene/{scene_num}/confirm")
async def confirm_scene(session_id: str, scene_num: int):
    """씬 이미지 확정"""
    session = _get_session(session_id)

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    target.edit_status = ImageEditStatus.CONFIRMED
    logger.info(f"[확정] 세션 {session_id}: 씬 {scene_num} 확정됨")
    return {"success": True, "scene_number": scene_num, "status": "confirmed"}


@router.post("/{session_id}/scene/{scene_num}/unconfirm")
async def unconfirm_scene(session_id: str, scene_num: int):
    """씬 확정 해제"""
    session = _get_session(session_id)

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    target.edit_status = ImageEditStatus.PENDING
    return {"success": True, "scene_number": scene_num, "status": "pending"}


@router.post("/{session_id}/scene/{scene_num}/undo")
async def undo_scene(session_id: str, scene_num: int):
    """씬 이미지 되돌리기 (마지막 이력으로 복원)"""
    session = _get_session(session_id)
    history_mgr = get_history_manager()

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    if not target.image_history:
        raise HTTPException(status_code=400, detail="되돌릴 이력이 없습니다.")

    # 마지막 이력에서 복원
    prev_path = target.image_history.pop()
    if target.local_path and os.path.exists(prev_path):
        history_mgr.restore_from_history(prev_path, target.local_path)
        target.tone_adjusted = len(target.image_history) > 0

    return {"success": True, "scene_number": scene_num, "remaining_history": len(target.image_history)}


@router.post("/{session_id}/scene/{scene_num}/regenerate")
async def regenerate_scene(session_id: str, scene_num: int, req: SceneRegenerateRequest):
    """씬 이미지 재생성 (프롬프트 수정 포함)"""
    session = _get_session(session_id)
    history_mgr = get_history_manager()

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    # 현재 이미지 이력 저장
    if target.local_path and os.path.exists(target.local_path):
        history_path = history_mgr.save_to_history(target.local_path, session_id, scene_num)
        target.image_history.append(history_path)

    # 프롬프트 업데이트
    new_prompt = req.new_prompt or target.prompt_used
    if req.new_prompt:
        target.prompt_history.append(target.prompt_used)
        target.prompt_used = new_prompt

    target.edit_status = ImageEditStatus.REGENERATING

    # 이미지 재생성 (workflow.py generate-images와 동일한 패턴 사용)
    try:
        import os
        import uuid
        from app.services.image_generator import get_generator
        from app.models.models import Scene
        from app.api.workflow import build_styled_prompt
        from app.api.styles import get_character_style, get_background_style

        # 세션에 저장된 이미지 모델 사용 (탭4에서 선택한 모델)
        model_name = session.settings.image.model if hasattr(session.settings, 'image') and session.settings.image else "dall-e-3"

        # API 키 결정
        from app.core.config import get_settings
        _settings = get_settings()
        if "gpt" in model_name or "dall-e" in model_name:
            api_key = _settings.openai_api_key or ""
        else:
            api_key = _settings.gemini_api_key or ""

        generator = get_generator(model_name, api_key)

        # 스타일 로드
        char_style_id = session.settings.image.character_style_id if hasattr(session.settings, 'image') and session.settings.image else None
        bg_style_id = session.settings.image.background_style_id if hasattr(session.settings, 'image') and session.settings.image else None
        char_style = get_character_style(char_style_id) if char_style_id else None
        bg_style = get_background_style(bg_style_id) if bg_style_id else None
        overrides = session.settings.image.manual_overrides if hasattr(session.settings, 'image') and session.settings.image else None

        # 프롬프트 빌드
        temp_scene = Scene(
            scene_number=scene_num,
            scene_description=new_prompt,
            dialogues=[],
            narration=""
        )

        characters = session.story.characters if session.story else None
        prompt = build_styled_prompt(
            scene=temp_scene,
            characters=characters,
            character_style=char_style,
            background_style=bg_style,
            manual_overrides=overrides
        )

        # 이미지 생성
        image_data = await generator.generate(prompt)

        # 파일 저장
        filename = f"scene_{scene_num}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join("output", filename)
        os.makedirs("output", exist_ok=True)

        with open(filepath, "wb") as f:
            if isinstance(image_data, bytes):
                f.write(image_data)

        target.local_path = filepath
        target.image_url = f"/output/{filename}"
        target.edit_status = ImageEditStatus.PENDING  # 재확정 필요
        target.tone_adjusted = False

        logger.info(f"[재생성] 세션 {session_id}: 씬 {scene_num} 재생성 완료 (모델: {model_name})")
        return {
            "success": True,
            "scene_number": scene_num,
            "image_url": target.image_url,
            "local_path": target.local_path,
            "new_prompt": new_prompt,
            "model_used": model_name,
        }

    except Exception as e:
        target.edit_status = ImageEditStatus.PENDING
        logger.error(f"[재생성 실패] 세션 {session_id}: 씬 {scene_num}: {e}")
        raise HTTPException(status_code=500, detail=f"재생성 실패: {str(e)}")


@router.post("/{session_id}/scene/{scene_num}/upload")
async def upload_scene_image(session_id: str, scene_num: int, file: UploadFile = File(...)):
    """사용자 이미지 업로드로 씬 교체"""
    session = _get_session(session_id)
    history_mgr = get_history_manager()

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    # 허용 확장자 검사
    allowed_ext = {".png", ".jpg", ".jpeg", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다. ({', '.join(allowed_ext)})")

    # 현재 이미지 이력 저장
    if target.local_path and os.path.exists(target.local_path):
        history_path = history_mgr.save_to_history(target.local_path, session_id, scene_num)
        target.image_history.append(history_path)

    # 업로드 파일 저장
    upload_dir = os.path.join("output", session_id, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    upload_path = os.path.join(upload_dir, f"scene_{scene_num}_upload{ext}")

    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    target.local_path = upload_path
    target.edit_status = ImageEditStatus.PENDING  # 업로드 후 재확정 필요
    target.tone_adjusted = False

    logger.info(f"[업로드] 세션 {session_id}: 씬 {scene_num} 이미지 교체")
    return {
        "success": True,
        "scene_number": scene_num,
        "uploaded_path": upload_path,
    }


@router.post("/{session_id}/confirm-all")
async def confirm_all_scenes(session_id: str):
    """전체 씬 일괄 확정"""
    session = _get_session(session_id)

    for img in session.images:
        img.edit_status = ImageEditStatus.CONFIRMED

    logger.info(f"[전체 확정] 세션 {session_id}: {len(session.images)}개 씬 확정")
    return {"success": True, "confirmed_count": len(session.images)}


@router.get("/{session_id}/scene/{scene_num}/prompt")
async def get_scene_prompt(session_id: str, scene_num: int):
    """씬의 현재 프롬프트 조회 (수정 모달용)"""
    session = _get_session(session_id)

    target = next((img for img in session.images if img.scene_number == scene_num), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"씬 {scene_num}을(를) 찾을 수 없습니다.")

    return {
        "scene_number": scene_num,
        "current_prompt": target.prompt_used,
        "prompt_history": target.prompt_history,
    }


# ============================================
# Playwright 말풍선 오버레이 API
# ============================================

class BubbleOverlayRequest(BaseModel):
    """말풍선 오버레이 요청"""
    scene_numbers: Optional[List[int]] = None  # None이면 전체 적용
    font_family: str = "Nanum Gothic"
    bubble_style: str = "round"  # round | square | shout | thought


@router.post("/{session_id}/apply-bubbles")
async def apply_bubble_overlay(session_id: str, req: BubbleOverlayRequest):
    """모든 씬에 Playwright 말풍선 오버레이 적용

    스토리의 대사(dialogues)와 나레이션(narration)을
    Playwright HTML/CSS → 투명 PNG → 합성 방식으로 적용합니다.
    """
    session = _get_session(session_id)

    if not session.story or not session.story.scenes:
        raise HTTPException(status_code=400, detail="스토리가 없습니다.")

    from app.services.render_service import composite_bubble_on_image

    target_images = session.images
    if req.scene_numbers:
        target_images = [img for img in session.images if img.scene_number in req.scene_numbers]

    if not target_images:
        raise HTTPException(status_code=400, detail="적용할 이미지가 없습니다.")

    history_mgr = get_history_manager()
    results = []

    for img in target_images:
        if not img.local_path or not os.path.exists(img.local_path):
            results.append({"scene_number": img.scene_number, "status": "skip", "reason": "이미지 없음"})
            continue

        # 해당 씬 찾기
        scene = next(
            (s for s in session.story.scenes if s.scene_number == img.scene_number),
            None
        )
        if not scene or not scene.dialogues:
            results.append({"scene_number": img.scene_number, "status": "skip", "reason": "대사 없음"})
            continue

        # 원본 백업 (이력 저장)
        history_path = history_mgr.save_to_history(img.local_path, session_id, img.scene_number)
        img.image_history.append(history_path)

        # 대사 데이터 변환 (position 자동 배치)
        dialogues = []
        positions = ["top-left", "top-right", "mid-left"]
        for i, d in enumerate(scene.dialogues[:3]):
            dialogues.append({
                "character": d.character,
                "text": d.text,
                "position": positions[i] if i < len(positions) else "mid-center",
            })

        narration = scene.narration or ""

        try:
            # Playwright 합성
            result_bytes = await composite_bubble_on_image(
                base_image_path=img.local_path,
                dialogues=dialogues,
                narration=narration,
                output_path=img.local_path,  # 덮어쓰기
                font_family=req.font_family,
                bubble_style=req.bubble_style,
            )

            results.append({
                "scene_number": img.scene_number,
                "status": "success",
                "dialogue_count": len(dialogues),
                "has_narration": bool(narration),
            })
            logger.info(f"[말풍선] 씬 {img.scene_number}: 대사 {len(dialogues)}개 + 나레이션 적용 완료")

        except Exception as e:
            logger.error(f"[말풍선] 씬 {img.scene_number} 오버레이 실패: {e}")
            results.append({
                "scene_number": img.scene_number,
                "status": "error",
                "reason": str(e),
            })

    return {
        "success": True,
        "total": len(target_images),
        "applied": sum(1 for r in results if r.get("status") == "success"),
        "results": results,
    }


@router.post("/{session_id}/scene/{scene_num}/apply-bubble")
async def apply_single_bubble(session_id: str, scene_num: int, req: BubbleOverlayRequest):
    """단일 씬에 말풍선 오버레이 적용"""
    req.scene_numbers = [scene_num]
    return await apply_bubble_overlay(session_id, req)
