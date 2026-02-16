"""
워크플로우 API 라우터
웹툰 생성 전체 흐름 관리
"""
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.models.models import (
    WorkflowSession, WorkflowState, WorkflowMode,
    Story, Scene, CharacterSettings, SpecializedField,
    ManualPromptOverrides, ThumbnailData, ThumbnailSource, ThumbnailPosition,
    SeriesInfo, SeriesEpisode, ToBeContinuedStyle, GeneratedImage,
    BubbleLayer, BubbleOverlay, BubblePosition, BubbleShape, CHARACTER_COLORS,
    InstagramCaption, FieldInfo
)
from app.services.gemini_service import get_gemini_service
from app.services.image_generator import get_generator
from app.services.prompt_builder import build_styled_prompt
from app.api.styles import get_character_style, get_background_style
import asyncio
import os
import json
import glob
from datetime import datetime
import logging

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# 로거 설정
logger = logging.getLogger(__name__)

# 메모리 기반 세션 저장 (실제 서비스에서는 DB 사용)
sessions: dict[str, WorkflowSession] = {}

# 이미지 생성 중단 신호: session_id → True 이면 즉시 루프 중단
stop_signals: dict[str, bool] = {}

# ★ 공통 헬퍼: aspect_ratio → 이미지 사이즈 변환 (전체 생성 + 개별 재생성 통일)
def _resolve_api_key(model_name: str) -> str:
    """Gemini API 키를 반환하는 헬퍼"""
    from app.core.config import get_settings
    settings = get_settings()
    return settings.gemini_api_key or ""


# ============================================
# Request/Response 모델
# ============================================

class StartWorkflowRequest(BaseModel):
    mode: str = "auto"  # auto | manual
    keyword: Optional[str] = None
    model: str = "gemini-3-flash-preview"


class StartWorkflowResponse(BaseModel):
    session_id: str
    state: str
    field: Optional[str] = None
    field_requires_verification: bool = False


class GenerateStoryRequest(BaseModel):
    session_id: str
    questioner_type: str = "curious_beginner"
    expert_type: str = "friendly_expert"
    scene_count: int = 8
    model: str = "gemini-3-flash-preview"
    character_names: str = ""  # 쉼표 구분 등장인물 이름 (빈 문자열이면 AI 자동 생성)
    characters_input: Optional[List[dict]] = None  # 구조적 캐릭터 입력 [{"name":"소미","role":"expert"}, ...]
    collected_data: Optional[List[dict]] = None  # 프론트엔드에서 수정된 수집 데이터
    monologue_mode: bool = False  # 독백 모드 (1인 캐릭터만 등장)
    monologue_character: str = ""  # 독백 시 사용할 캐릭터 이름


class UpdateSceneRequest(BaseModel):
    session_id: str
    scene_number: int
    scene_description: Optional[str] = None
    image_prompt: Optional[str] = None  # 이미지 생성용 상세 시각 프롬프트
    dialogues: Optional[List[dict]] = None
    narration: Optional[str] = None


class GenerateImagesRequest(BaseModel):
    session_id: str
    style: str = "webtoon"
    sub_style: str = "normal"
    aspect_ratio: str = "4:5"
    model: str = "nano-banana-pro"  # Gemini 3.0 Preview 고정
    
    # Style System 2.0
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    manual_overrides: Optional[dict] = None
    
    # 3종 레퍼런스 & 씬 체이닝
    use_reference_images: bool = True    # 레퍼런스 이미지 사용 여부
    scene_chaining: bool = True          # 이전 씬 참조 (직전 씬 이미지 + 텍스트 요약)
    
    # 시리즈 필터링
    target_series: Optional[int] = None  # None=전체, 1/2/3=해당 시리즈만


class GeneratePreviewRequest(BaseModel):
    session_id: str
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    sub_style: Optional[str] = None # Added for compatibility
    manual_overrides: Optional[dict] = None # ManualPromptOverrides
    model: str = "nano-banana-pro"  # Gemini 3.0 Preview 고정


class GenerateCaptionRequest(BaseModel):
    session_id: str


# ... (middle parts omitted) ...

@router.post("/start", response_model=StartWorkflowResponse)
async def start_workflow(request: StartWorkflowRequest):
    """워크플로우 시작"""
    try:
        session_id = str(uuid.uuid4())
        
        mode = WorkflowMode.AUTO if request.mode == "auto" else WorkflowMode.MANUAL
        
        session = WorkflowSession(
            session_id=session_id,
            mode=mode,
            keyword=request.keyword,
            state=WorkflowState.INITIALIZED
        )
        
        # 자동 모드: 분야 감지
        field_name = None
        requires_verification = False
        
        if mode == WorkflowMode.AUTO and request.keyword:
            gemini = get_gemini_service()
            # AI 자동 감지 호출 (Async) - 모델 파라미터 전달
            field_info = await gemini.detect_field(request.keyword, request.model)
            session.field_info = field_info
            session.state = WorkflowState.COLLECTING_INFO
            field_name = field_info.field.value
            requires_verification = field_info.requires_legal_verification
        
        sessions[session_id] = session
        
        return StartWorkflowResponse(
            session_id=session_id,
            state=session.state.value,
            field=field_name,
            field_requires_verification=requires_verification
        )
    except Exception as e:
        logger.error(f"[start_workflow] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"워크플로우 시작 실패: {str(e)}")


@router.post("/generate-story")
async def generate_story(request: GenerateStoryRequest):
    """스토리 생성"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.keyword:
         raise HTTPException(status_code=400, detail="Keyword is required")
         
    session.state = WorkflowState.GENERATING_STORY
    
    try:
        gemini = get_gemini_service()
        
        field_info = session.field_info or await gemini.detect_field(session.keyword)
        
        # 수집 데이터: 프론트엔드에서 수정본이 전달되면 우선 사용, 아니면 세션 저장본 사용
        if request.collected_data and len(request.collected_data) > 0:
            collected_data = request.collected_data
            session.collected_data = collected_data  # 세션에도 최신본 반영
            logger.info(f"[generate_story] 프론트엔드에서 수정된 수집 데이터 사용 ({len(collected_data)}개)")
        else:
            collected_data = session.collected_data or []
        
        if not collected_data:
            # 수집 자료가 없는 경우 즉석으로 수집
            collected_data = await gemini.collect_data(session.keyword, field_info)
            session.collected_data = collected_data
        
        character_settings = CharacterSettings(
            questioner_type=request.questioner_type,
            expert_type=request.expert_type
        )
        
        # 프로젝트 설정의 규칙 적용
        rule_settings = session.settings.rules
        
        logger.info(f"[generate_story] 스토리 생성 시작 - keyword: {session.keyword}, scene_count: {request.scene_count}, model: {request.model}, characters_input: {request.characters_input}")
        
        story = await gemini.generate_story(
            keyword=session.keyword,
            field_info=field_info,
            collected_data=collected_data,
            scene_count=request.scene_count,
            character_settings=character_settings,
            rule_settings=rule_settings,
            model=request.model,
            character_names=request.character_names,
            characters_input=request.characters_input,
            monologue_mode=request.monologue_mode,
            monologue_character=request.monologue_character
        )
        
        if not story:
            raise ValueError("스토리 생성 결과가 없습니다")
        
        logger.info(f"[generate_story] 스토리 생성 완료 - 씬 수: {len(story.scenes) if story.scenes else 0}")
        
        session.story = story
        session.images = []  # 새 스토리 생성 시 이전 이미지 초기화
        session.state = WorkflowState.REVIEWING_SCENES
        
        # 스토리 히스토리 저장
        try:
            save_story_to_history(session)
        except Exception as e:
            logger.error(f"Failed to save story history: {e}")
        
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "story": story.model_dump()
        }
    except Exception as e:
        import traceback
        logger.error(f"[generate_story] 오류: {str(e)}")
        logger.error(traceback.format_exc())
        session.state = WorkflowState.ERROR
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """세션 정보 조회"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session.model_dump()


@router.post("/update-scene")
async def update_scene(request: UpdateSceneRequest):
    """씬 수정"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    try:
        for scene in session.story.scenes:
            if scene.scene_number == request.scene_number:
                if request.scene_description:
                    scene.scene_description = request.scene_description
                if request.image_prompt is not None:
                    scene.image_prompt = request.image_prompt
                if request.dialogues:
                    from app.models.models import Dialogue
                    scene.dialogues = [
                        Dialogue(character=d["character"], text=d["text"])
                        for d in request.dialogues
                    ]
                if request.narration is not None:
                    scene.narration = request.narration
                scene.status = "approved"
                break
        
        return {"success": True, "story": session.story.model_dump()}
    except Exception as e:
        logger.error(f"[update_scene] 씬 {request.scene_number} 수정 실패: {e}")
        raise HTTPException(status_code=500, detail=f"씬 수정 실패: {str(e)}")


class BulkUpdateScenesRequest(BaseModel):
    session_id: str
    scenes: List[dict]  # [{scene_number, scene_description, image_prompt, dialogues, narration}, ...]


@router.post("/update-scenes-bulk")
async def update_scenes_bulk(request: BulkUpdateScenesRequest):
    """씬 일괄 수정 — 프론트엔드에서 편집한 모든 씬을 한 번에 동기화"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    try:
        updated_count = 0
        for scene_data in request.scenes:
            sn = scene_data.get("scene_number")
            if sn is None:
                continue
            for scene in session.story.scenes:
                if scene.scene_number == sn:
                    if "scene_description" in scene_data and scene_data["scene_description"]:
                        scene.scene_description = scene_data["scene_description"]
                    if "image_prompt" in scene_data and scene_data["image_prompt"] is not None:
                        scene.image_prompt = scene_data["image_prompt"]
                    if "dialogues" in scene_data and scene_data["dialogues"]:
                        from app.models.models import Dialogue
                        scene.dialogues = [
                            Dialogue(
                                character=d.get("character", ""),
                                text=d.get("text", ""),
                                emotion=d.get("emotion", None)
                            )
                            for d in scene_data["dialogues"]
                        ]
                    if "narration" in scene_data and scene_data["narration"] is not None:
                        scene.narration = scene_data["narration"]
                    scene.status = "approved"
                    updated_count += 1
                    break
        
        logger.info(f"[update-scenes-bulk] 세션 {request.session_id}: {updated_count}개 씬 일괄 업데이트 완료")
        return {"success": True, "updated_count": updated_count}
    except Exception as e:
        logger.error(f"[update-scenes-bulk] 일괄 수정 실패: {e}")
        raise HTTPException(status_code=500, detail=f"씬 일괄 수정 실패: {str(e)}")


class RegenerateImagePromptRequest(BaseModel):
    session_id: str
    scene_number: int
    model: str = "gemini-3-flash-preview"


@router.post("/regenerate-image-prompt")
async def regenerate_image_prompt(request: RegenerateImagePromptRequest):
    """특정 씬의 이미지 프롬프트를 AI로 다시 생성"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    target_scene = None
    for scene in session.story.scenes:
        if scene.scene_number == request.scene_number:
            target_scene = scene
            break
    
    if not target_scene:
        raise HTTPException(status_code=404, detail=f"Scene {request.scene_number} not found")
    
    try:
        from app.services.gemini_service import get_gemini_service
        gemini = get_gemini_service()
        
        # 캐릭터 정보 구성
        char_info = ""
        if session.story.characters:
            char_names = [c.name for c in session.story.characters]
            char_descs = []
            for c in session.story.characters:
                desc = c.appearance or ""
                if hasattr(c, 'visual_identity') and c.visual_identity:
                    vi = c.visual_identity
                    desc += f" / {vi.get('hair_style', '')} {vi.get('hair_color', '')}, {vi.get('outfit', '')}"
                char_descs.append(f"- {c.name}({c.role}): {desc}")
            char_info = "\n".join(char_descs)
        
        regen_prompt = f"""아래 씬의 "image_prompt"를 다시 작성해주세요.
image_prompt는 AI 이미지 생성 모델에게 전달되는 시각 묘사입니다.

[등장 캐릭터]
{char_info}

[씬 설명]
{target_scene.scene_description}

[작성 규칙]
1. 한국어로 작성
2. 대사/텍스트/글자 절대 포함 금지 — 순수하게 그림만 묘사
3. 포함해야 할 요소: 스타일, 배경/장소, 캐릭터 위치·포즈·표정, 조명/분위기, 카메라 앵글
4. 80~150자 범위
5. "웹툰 스타일."로 시작

image_prompt만 텍스트로 반환하세요. 다른 설명이나 JSON 없이 프롬프트 텍스트만."""

        from google import genai as _genai
        client = _genai.Client(api_key=gemini._api_key)
        response = await client.aio.models.generate_content(model=request.model, contents=regen_prompt)
        new_prompt = response.text.strip().strip('"').strip("'")
        
        # 씬에 저장
        target_scene.image_prompt = new_prompt
        
        return {
            "success": True,
            "scene_number": request.scene_number,
            "image_prompt": new_prompt
        }
    except Exception as e:
        logger.error(f"이미지 프롬프트 재생성 실패 (씬 {request.scene_number}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve-scenes")
async def approve_all_scenes(session_id: str):
    """모든 씬 승인"""
    session = sessions.get(session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    try:
        for scene in session.story.scenes:
            scene.status = "approved"
        
        session.state = WorkflowState.GENERATING_IMAGES
        
        return {"success": True, "state": session.state.value}
    except Exception as e:
        logger.error(f"[approve_scenes] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"씬 승인 실패: {str(e)}")


@router.post("/generate-preview")
async def generate_preview(request: GeneratePreviewRequest):
    """스타일 미리보기 생성 (1장)"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        char_style = get_character_style(request.character_style_id) if request.character_style_id else None
        bg_style = get_background_style(request.background_style_id) if request.background_style_id else None

        overrides_obj = None
        if request.manual_overrides:
            overrides_obj = ManualPromptOverrides(**request.manual_overrides)

        # Use first scene or placeholder
        if session.story and session.story.scenes:
            target_scene = session.story.scenes[0]
            characters = session.story.characters
        else:
            target_scene = Scene(
                scene_number=1, 
                scene_description="A generic scene for style preview. A character standing in a simple background.", 
                dialogues=[],
                image_prompt="A character standing in a simple background."
            )
            characters = []
        
        # Build Prompt
        prompt = build_styled_prompt(
            scene=target_scene,
            characters=characters,
            character_style=char_style,
            background_style=bg_style,
            manual_overrides=overrides_obj,
            sub_style_name=request.sub_style
        )
        
        api_key = _resolve_api_key(request.model)
        generator = get_generator(request.model, api_key)

        print(f"[PREVIEW] model={request.model}, prompt_len={len(prompt)}자, api_key={'SET' if api_key else 'MISSING'}")
        logger.info(f"미리보기 생성 시작 (model={request.model}, prompt_len={len(prompt)}자)")
        
        image_data = await asyncio.wait_for(
            generator.generate(prompt, quality="standard", aspect_ratio="4:5"),
            timeout=95.0
        )

        import base64
        if isinstance(image_data, bytes):
            b64_img = base64.b64encode(image_data).decode('utf-8')
            return {"success": True, "image_b64": b64_img, "prompt_used": prompt}
        else:
            return {"success": True, "image_url": image_data, "prompt_used": prompt}

    except asyncio.TimeoutError:
        logger.error("Preview generation timed out (95s)")
        return JSONResponse(
            status_code=504,
            content={
                "detail": "이미지 생성이 시간 초과되었습니다(90초). API가 지연 중이거나 네트워크 문제일 수 있습니다. 잠시 후 다시 시도해주세요."
            }
        )
    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        return JSONResponse(status_code=500, content={"detail": f"Preview generation failed: {str(e)}"})


async def _run_image_generation(request: GenerateImagesRequest):
    """백그라운드에서 실행: 씬 전처리, 레퍼런스 로드, 씬별 이미지 생성 루프. 완료 시 session.state = REVIEWING_IMAGES."""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        logger.warning(f"[이미지 생성] 세션 없음 또는 스토리 없음: {request.session_id}")
        return
    try:
        from app.services.reference_service import ReferenceService
        from app.services.prompt_builder import build_scene_chaining_context
        from app.models.models import GeneratedImage

        # Load styles
        char_style = get_character_style(request.character_style_id) if request.character_style_id else None
        bg_style = get_background_style(request.background_style_id) if request.background_style_id else None
        overrides = session.settings.image.manual_overrides
        sub_style = request.sub_style

        api_key = _resolve_api_key(request.model)
        generator = get_generator(request.model, api_key)

        # ★★★ 씬 설명 전처리 ★★★
        if session.story and session.story.scenes:
            try:
                from app.services.scene_preprocessor import preprocess_scenes_for_image_gen
                session.story.scenes = await preprocess_scenes_for_image_gen(session.story.scenes)
                logger.info("[전처리] 씬 설명 전처리 완료 (숫자/인포그래픽 → 시각적 비유)")
            except Exception as pp_err:
                logger.warning(f"[전처리] 씬 설명 전처리 실패, 원본 유지: {pp_err}")

        # ★★★ 3종 레퍼런스 비동기 로드 ★★★
        ref_service = ReferenceService(request.session_id)
        logger.info(f"[레퍼런스] 세션 디렉토리: {ref_service.ref_dir}")
        ref_data = await ref_service.load_for_model(request.model) if request.use_reference_images else {}

        character_ref_bytes = ref_data.get("character")
        method_ref_bytes = ref_data.get("method")
        style_ref_bytes = ref_data.get("style")

        logger.info(f"[레퍼런스] Character: {len(character_ref_bytes) if character_ref_bytes else 'None'}bytes, "
                    f"Method: {len(method_ref_bytes) if method_ref_bytes else 'None'}bytes, "
                    f"Style: {len(style_ref_bytes) if style_ref_bytes else 'None'}bytes")

        model_lower = request.model.lower() if request.model else ""
        is_gemini = any(k in model_lower for k in ["gemini", "nano-banana"])
        ref_status = []
        if character_ref_bytes: ref_status.append("Character")
        if method_ref_bytes: ref_status.append("Method")
        if style_ref_bytes: ref_status.append("Style")
        logger.info(f"[레퍼런스] 사용 가능: {', '.join(ref_status) if ref_status else '없음'} (모델: {request.model})")

        if is_gemini:
            from PIL import Image as PILImg
            from io import BytesIO as BIO
            if character_ref_bytes:
                character_ref_bytes = PILImg.open(BIO(character_ref_bytes))
            if method_ref_bytes:
                method_ref_bytes = PILImg.open(BIO(method_ref_bytes))
            if style_ref_bytes:
                style_ref_bytes = PILImg.open(BIO(style_ref_bytes))

        os.makedirs("output", exist_ok=True)

        async def generate_single_scene(scene, ref_image_bytes=None,
                                         method_bytes=None, style_bytes=None,
                                         prev_scene_image=None, prev_scene_summaries=None):
            try:
                prompt = build_styled_prompt(
                    scene=scene,
                    characters=session.story.characters,
                    character_style=char_style,
                    background_style=bg_style,
                    manual_overrides=overrides,
                    sub_style_name=sub_style,
                    aspect_ratio=request.aspect_ratio
                )
                _prev_sn = scene.scene_number - 1 if prev_scene_image else None
                image_data = await generator.generate(
                    prompt,
                    reference_images=[ref_image_bytes] if ref_image_bytes else None,
                    method_image=method_bytes,
                    style_image=style_bytes,
                    prev_scene_image=prev_scene_image,
                    prev_scene_summaries=prev_scene_summaries,
                    prev_scene_number=_prev_sn,
                    aspect_ratio=request.aspect_ratio
                )
                ref_count = sum(1 for x in [ref_image_bytes, method_bytes, style_bytes] if x)
                logger.info(f"[Gemini] 씬 {scene.scene_number}: {ref_count}종 레퍼런스"
                            f"{' + 씬체이닝' if prev_scene_image else ''}")
                filename = f"scene_{scene.scene_number}_{uuid.uuid4().hex[:6]}.png"
                filepath = os.path.join("output", filename)
                if isinstance(image_data, bytes):
                    def _save_file():
                        with open(filepath, "wb") as f:
                            f.write(image_data)
                    await asyncio.to_thread(_save_file)
                return {
                    "scene_number": scene.scene_number,
                    "prompt_used": prompt,
                    "local_path": filepath,
                    "status": "generated",
                    "image_bytes": image_data if isinstance(image_data, bytes) else b""
                }
            except Exception as e:
                import traceback
                logger.error(f"Error generating scene {scene.scene_number}: {e}\n{traceback.format_exc()}")
                return {
                    "scene_number": scene.scene_number,
                    "prompt_used": "Error",
                    "status": "error",
                    "error": str(e)
                }

        session.images = []
        stop_signals[request.session_id] = False
        generated_scene_images = {}

        scenes_to_generate = session.story.scenes
        if request.target_series and session.story.series_info:
            episodes = session.story.series_info.episodes
            target_ep = next((ep for ep in episodes if ep.episode_number == request.target_series), None)
            if target_ep:
                scenes_to_generate = session.story.scenes[target_ep.scene_start:target_ep.scene_end]
                logger.info(f"[시리즈] 시리즈 {request.target_series} 씬만 생성: 인덱스 {target_ep.scene_start}~{target_ep.scene_end-1} ({len(scenes_to_generate)}장)")

        for scene_idx, scene in enumerate(scenes_to_generate):
            if stop_signals.get(request.session_id, False):
                logger.info(f"[STOP] 세션 {request.session_id} 이미지 생성 중단됨 "
                            f"({len(session.images)}/{len(session.story.scenes)} 완료)")
                break
            if scene_idx > 0:
                await asyncio.sleep(1)

            prev_scene_image = None
            prev_scene_summaries = None
            if request.scene_chaining and scene.scene_number > 1:
                prev_summaries, prev_sn = build_scene_chaining_context(
                    session.story.scenes, scene.scene_number
                )
                prev_scene_summaries = prev_summaries if prev_summaries else None
                if prev_sn and prev_sn in generated_scene_images:
                    prev_scene_image = generated_scene_images[prev_sn]

            mode_parts = []
            if character_ref_bytes: mode_parts.append("Character")
            if method_ref_bytes: mode_parts.append("Method")
            if style_ref_bytes: mode_parts.append("Style")
            if prev_scene_image: mode_parts.append("체이닝")
            mode_str = f"레퍼런스({'+'.join(mode_parts)})" if mode_parts else "독립 생성"
            logger.info(f"[생성] 씬 {scene.scene_number}/{len(session.story.scenes)} — {mode_str}")

            # 내부 재시도(image_generator.py)가 4회까지 자동 처리하므로 외부 재시도 불필요
            res = await generate_single_scene(
                scene,
                ref_image_bytes=character_ref_bytes,
                method_bytes=method_ref_bytes,
                style_bytes=style_ref_bytes,
                prev_scene_image=prev_scene_image,
                prev_scene_summaries=prev_scene_summaries
            )
            if res.get("status") == "error":
                logger.error(f"씬 {scene.scene_number} 생성 실패: {res.get('error', '')}")

            if res.get("image_bytes"):
                generated_scene_images.clear()
                generated_scene_images[scene.scene_number] = res["image_bytes"]

            if res.get("local_path"):
                img = GeneratedImage(
                    scene_number=res["scene_number"],
                    prompt_used=res["prompt_used"],
                    local_path=res["local_path"],
                    status="generated"
                )
            else:
                img = GeneratedImage(
                    scene_number=res["scene_number"],
                    prompt_used=res.get("prompt_used", "Error"),
                    local_path="",
                    status="error"
                )
            session.images.append(img)

        stop_signals.pop(request.session_id, None)
        session.state = WorkflowState.REVIEWING_IMAGES
        logger.info(f"[이미지 생성] 완료: 세션 {request.session_id}, {len(session.images)}장")
    except Exception as e:
        import traceback
        logger.error(f"[이미지 생성] 백그라운드 실패: {e}\n{traceback.format_exc()}")
        stop_signals.pop(request.session_id, None)
        session = sessions.get(request.session_id)
        if session:
            session.state = WorkflowState.REVIEWING_IMAGES
            # 에러 메시지를 세션에 저장 → 프론트 폴링 시 사용자에게 전달
            session.last_error = f"이미지 생성 중 오류: {str(e)[:200]}"


@router.post("/generate-images")
async def generate_images(request: GenerateImagesRequest):
    """이미지 일괄 생성 (Style System 2.0) — 작업 시작만 하고 즉시 202 반환, 진행률은 세션 API 폴링"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")

    session.state = WorkflowState.GENERATING_IMAGES
    session.settings.image.model = request.model
    session.settings.image.character_style_id = request.character_style_id
    session.settings.image.background_style_id = request.background_style_id
    session.settings.image.sub_style = request.sub_style
    if request.manual_overrides:
        session.settings.image.manual_overrides = ManualPromptOverrides(**request.manual_overrides)

    asyncio.create_task(_run_image_generation(request))
    return JSONResponse(
        status_code=202,
        content={
            "session_id": session.session_id,
            "state": "generating",
            "message": "이미지 생성이 백그라운드에서 시작되었습니다. 진행률은 세션 API로 조회하세요."
        }
    )


class StopGenerationRequest(BaseModel):
    session_id: str

@router.post("/stop-generation")
async def stop_generation(request: StopGenerationRequest):
    """이미지 생성 중단 신호 전송"""
    stop_signals[request.session_id] = True
    return {"status": "stop_signal_sent", "session_id": request.session_id}


@router.post("/generate-caption")
async def generate_caption(request: GenerateCaptionRequest):
    """캡션 생성"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    session.state = WorkflowState.GENERATING_CAPTION
    
    gemini = get_gemini_service()
    
    # 가상 캐릭터 고유 이름 목록 수집 (캡션 노출 방지용)
    char_names = [c.name for c in session.story.characters] if session.story.characters else []
    
    # 스토리 전체 요약 생성 (캐릭터 고유 이름 제거)
    story_summary = f"제목: {session.story.title}\n"
    scene_lines = []
    for s in session.story.scenes:
        desc = s.scene_description
        for cname in char_names:
            desc = desc.replace(cname, "")
        scene_lines.append(f"씬{s.scene_number}: {desc}")
    story_summary += "\n".join(scene_lines)
    # 대사 내용만 요약에 포함 (캐릭터 고유 이름 제거)
    dialogues_summary = []
    for s in session.story.scenes[:5]:
        for d in s.dialogues[:2]:
            clean_text = d.text
            for cname in char_names:
                clean_text = clean_text.replace(cname, "")
            dialogues_summary.append(f"  \"{clean_text}\"")
    if dialogues_summary:
        story_summary += "\n주요 대사:\n" + "\n".join(dialogues_summary)
    
    field = session.field_info.field if session.field_info else SpecializedField.GENERAL
    
    try:
        caption = await gemini.generate_caption(
            keyword=session.keyword or session.story.title,
            field=field,
            story_summary=story_summary,
            character_names=char_names  # 캐릭터명 후처리 제거용
        )
    except Exception as e:
        logger.error(f"[generate_caption] 예외 발생: {e}", exc_info=True)
        # 500 대신 기본 캡션 반환
        caption = InstagramCaption(
            hook=f"📌 {session.keyword or '정보'} 알아보기",
            body=f"{session.keyword or '유용한 정보'}에 대해 웹툰으로 정리했어요!\n\n저장해두고 필요할 때 확인해보세요 ✅",
            expert_tip="전문가 팁은 저장 필수!",
            hashtags=["#웹툰", "#정보", "#꿀팁"]
        )
    
    session.caption = caption
    session.state = WorkflowState.REVIEWING_CAPTION
    
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "caption": caption.model_dump()
    }


# ============================================
# 공통 캡션 생성 API (캐러셀/카드뉴스용)
# ============================================

class CommonCaptionRequest(BaseModel):
    topic: str = ""
    content: str = ""
    content_type: str = "webtoon"  # webtoon | carousel | cardnews


@router.post("/generate-common-caption")
async def generate_common_caption(request: CommonCaptionRequest):
    """콘텐츠 타입에 맞는 캡션 생성 (세션 불필요)"""
    from google import genai as _genai
    from app.core.config import get_settings as _gs
    api_key = _gs().gemini_api_key or ""
    client = _genai.Client(api_key=api_key)

    type_label = {
        "webtoon": "인스타그램 웹툰",
        "carousel": "인스타그램 캐러셀",
        "cardnews": "인스타그램 카드뉴스",
    }.get(request.content_type, "인스타그램 콘텐츠")

    prompt = f"""당신은 {type_label} 마케팅 전문가입니다.

주제: {request.topic}
콘텐츠 요약:
{request.content[:2000]}

위 콘텐츠의 인스타그램 캡션을 생성해주세요.

규칙:
1. 훅 문장: 호기심을 유발하는 첫 줄 (이모지 포함, 30자 이내)
2. 본문: 핵심 가치를 전달 (이모지+줄바꿈 활용, 200자 내외)
3. CTA: 행동 유도 문장 포함
4. 해시태그: 관련 해시태그 10~15개

반드시 아래 JSON으로만 응답:
{{"hook": "훅 문장", "body": "본문 캡션", "hashtags": "#태그1 #태그2 ..."}}
"""

    try:
        response = await client.aio.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        text = response.text.strip()

        import json
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        return {
            "hook": data.get("hook", ""),
            "body": data.get("body", ""),
            "hashtags": data.get("hashtags", ""),
        }
    except Exception as e:
        logger.error(f"[공통 캡션] 생성 실패: {e}")
        return {
            "hook": f"{request.topic} 알아보기",
            "body": "자세한 내용은 캐러셀을 넘겨보세요!",
            "hashtags": "#웹툰 #정보 #꿀팁",
        }


# ============================================
# 모델 테스트 API
# ============================================

class TestModelRequest(BaseModel):
    model: str = "gemini-3-flash-preview"


@router.post("/test-model")
async def test_model(request: TestModelRequest):
    """특정 AI 모델의 동작 상태 확인"""
    from google import genai as _genai
    from app.core.config import get_settings as _gs
    import asyncio, logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[test-model] 테스트 시작: {request.model}")
    
    try:
        client = _genai.Client(api_key=_gs().gemini_api_key or "")
        response = await client.aio.models.generate_content(
            model=request.model,
            contents="Say 'Hello' in Korean"
        )
        
        return {
            "model": request.model,
            "status": "success",
            "response": response.text[:100] if response.text else "(empty)"
        }
    except Exception as e:
        logger.error(f"[test-model] 모델 오류: {request.model} - {str(e)}")
        return {
            "model": request.model,
            "status": "error",
            "error": str(e)
        }


# ============================================
# 자료 수집 API
# ============================================

class CollectDataRequest(BaseModel):
    session_id: Optional[str] = None
    keyword: str
    model: str = "gemini-3-flash-preview"
    expert_mode: bool = False


@router.post("/collect-data")
async def collect_data(request: CollectDataRequest):
    """자료 수집. 세션이 없으면 자동 생성하여 프롬프트만으로 진행 가능하게 함."""
    import logging
    logger = logging.getLogger(__name__)

    session = sessions.get(request.session_id) if request.session_id else None
    if not session:
        new_id = str(uuid.uuid4())
        session = WorkflowSession(
            session_id=new_id,
            mode=WorkflowMode.AUTO,
            keyword=request.keyword,
            state=WorkflowState.COLLECTING_INFO
        )
        sessions[new_id] = session
        logger.info(f"[collect_data] 세션 없음 → 새 세션 생성: {new_id}")

    gemini = get_gemini_service()
    
    # AI를 사용해 상세 정보 수집 (1회 API 호출로 분야 판단 + 자료 수집 동시 수행)
    try:
        logger.info(f"[collect_data] 모델: {request.model}, 키워드: {request.keyword}")

        # 세션에 이미 분야 정보가 있으면 힌트로 전달 (없으면 AI가 자동 판단)
        field_info = session.field_info if hasattr(session, 'field_info') else None
        items = await gemini.collect_data(request.keyword, field_info, request.model, request.expert_mode)
        logger.info(f"[collect_data] 자료 수집 완료: {len(items)}개 항목 (전문가모드: {request.expert_mode})")
        
        # 세션에 저장 (상세 내용 포함)
        session.collected_data = items
        
        return {
            "session_id": session.session_id,
            "items": items,
            "model_used": request.model
        }
    except asyncio.TimeoutError:
        logger.error(f"[collect_data] 전체 타임아웃 - 모델: {request.model}")
        return JSONResponse(
            status_code=504,
            content={"detail": "AI 응답이 시간 초과되었습니다. 잠시 후 다시 시도해 주세요."}
        )
    except Exception as e:
        logger.error(f"[collect_data] 오류 발생 - 모델: {request.model}, 에러: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        err_str = str(e).lower()
        if "504" in err_str or "deadline" in err_str or "unavailable" in err_str:
            return JSONResponse(
                status_code=504,
                content={"detail": "AI 서버가 일시적으로 바쁩니다. 잠시 후 다시 시도해 주세요."}
            )
        if "429" in err_str or "rate" in err_str or "quota" in err_str:
            return JSONResponse(
                status_code=429,
                content={"detail": "AI 요청 한도를 초과했습니다. 1분 후 다시 시도해 주세요."}
            )
        raise HTTPException(status_code=500, detail=f"자료 수집 오류: {str(e)}")


class ParseManualContentRequest(BaseModel):
    session_id: str
    content: str
    title: Optional[str] = None


@router.post("/parse-manual-content")
async def parse_manual_content(request: ParseManualContentRequest):
    """수동 모드: 사용자가 입력한 텍스트를 파싱하여 자료 항목으로 변환"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # 텍스트 파싱: 번호 패턴(1. 2. 3.) 또는 더블 뉴라인으로 분리
    import re
    
    # 번호 패턴으로 분리 시도 (1. 또는 1) 또는 - 로 시작하는 항목)
    numbered_pattern = r'(?:^|\n)(?:\d+[.\)]\s*|[-•]\s*)'
    
    # 먼저 번호 패턴이 있는지 확인
    if re.search(numbered_pattern, content):
        # 번호 패턴으로 분리
        parts = re.split(numbered_pattern, content)
        parts = [p.strip() for p in parts if p.strip()]
    else:
        # 더블 뉴라인으로 분리
        parts = content.split('\n\n')
        parts = [p.strip() for p in parts if p.strip()]
    
    # 항목이 하나뿐이면 문장 단위로 더 분리 시도
    if len(parts) == 1 and len(parts[0]) > 200:
        # 마침표 + 공백으로 분리 (문장 단위)
        sentences = re.split(r'(?<=[.!?])\s+', parts[0])
        # 2-3문장씩 그룹핑
        parts = []
        for i in range(0, len(sentences), 2):
            group = ' '.join(sentences[i:i+2])
            if group.strip():
                parts.append(group.strip())
    
    # 각 파트를 자료 항목으로 변환
    items = []
    base_title = request.title or "수동 입력 자료"
    
    for i, part in enumerate(parts):
        # 첫 줄을 제목으로 사용하거나, 없으면 자동 생성
        lines = part.split('\n')
        first_line = lines[0].strip()
        
        # 첫 줄이 짧으면 제목으로 사용
        if len(first_line) < 50 and len(lines) > 1:
            title = first_line
            content_text = '\n'.join(lines[1:]).strip()
        else:
            title = f"{base_title} #{i+1}"
            content_text = part
        
        items.append({
            "title": title,
            "content": content_text
        })
    
    # 세션에 저장
    session.collected_data = items
    
    # 수동 모드용 키워드 설정 (스토리 생성에 필요)
    if request.title:
        session.keyword = request.title
    elif not session.keyword:
        session.keyword = "수동 입력 콘텐츠"
    
    return {
        "session_id": session.session_id,
        "items": items,
        "item_count": len(items)
    }


# ============================================
# 씬/이미지 재생성 API
# ============================================

class RegenerateSceneRequest(BaseModel):
    session_id: str
    scene_index: int
    model: str = "gemini-3-flash-preview"


@router.post("/regenerate-scene")
async def regenerate_scene(request: RegenerateSceneRequest):
    """씬 재생성"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    if request.scene_index >= len(session.story.scenes):
        raise HTTPException(status_code=400, detail="Invalid scene index")
    
    gemini = get_gemini_service()
    old_scene = session.story.scenes[request.scene_index]
    
    prompt = f"""
다음 웹툰 씬을 새롭게 작성해주세요. 같은 주제로 다른 대화와 장면을 만들어주세요.

기존 씬 설명: {old_scene.scene_description}
씬 번호: {old_scene.scene_number}
전체 스토리 제목: {session.story.title}

JSON 형식으로 응답:
{{
  "scene_number": {old_scene.scene_number},
  "scene_description": "새 장면 설명",
  "dialogues": [{{"character": "민지", "text": "대사"}}],
  "narration": "나레이션",
  "status": "pending"
}}
"""
    
    try:
        response = await gemini.model.generate_content_async(prompt)
        import json
        import re
        
        text = response.text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            from app.models.models import Dialogue
            
            new_scene = Scene(
                scene_number=data.get("scene_number", old_scene.scene_number),
                scene_description=data.get("scene_description", ""),
                dialogues=[Dialogue(**d) for d in data.get("dialogues", [])],
                narration=data.get("narration", ""),
                status="pending"
            )
            session.story.scenes[request.scene_index] = new_scene
            
            return {"scene": new_scene.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Failed to regenerate scene")


class RegenerateImageRequest(BaseModel):
    session_id: str
    scene_index: int
    model: str = "nano-banana-pro"
    aspect_ratio: Optional[str] = "4:5"


@router.post("/regenerate-image")
async def regenerate_image(request: RegenerateImageRequest):
    """이미지 재생성 — 메인 생성과 동일한 generator + prompt_builder 방식"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    if request.scene_index >= len(session.story.scenes):
        raise HTTPException(status_code=400, detail="Invalid scene index")
    
    # images가 없으면 빈 리스트로 초기화
    if not session.images:
        session.images = [
            GeneratedImage(scene_number=s.scene_number, prompt_used="", status="pending")
            for s in session.story.scenes
        ]
    # images 길이가 부족하면 확장
    while len(session.images) < len(session.story.scenes):
        s = session.story.scenes[len(session.images)]
        session.images.append(
            GeneratedImage(scene_number=s.scene_number, prompt_used="", status="pending")
        )
    
    scene = session.story.scenes[request.scene_index]
    
    # 세션에 저장된 설정 가져오기
    char_style = None
    bg_style = None
    overrides = None
    sub_style = None
    
    if session.settings and session.settings.image:
        if session.settings.image.character_style_id:
            char_style = get_character_style(session.settings.image.character_style_id)
        if session.settings.image.background_style_id:
            bg_style = get_background_style(session.settings.image.background_style_id)
        overrides = session.settings.image.manual_overrides
        sub_style = session.settings.image.sub_style
    
    # 프롬프트 빌드
    prompt = build_styled_prompt(
        scene=scene,
        characters=session.story.characters,
        character_style=char_style,
        background_style=bg_style,
        manual_overrides=overrides,
        sub_style_name=sub_style
    )
    
    # API 키 결정 — 모델별 자동 선택
    model_name = request.model or "nano-banana-pro"
    api_key = _resolve_api_key(model_name)
    generator = get_generator(model_name, api_key)
    
    try:
        ar = request.aspect_ratio or "4:5"
        
        # ★ Gemini 재생성: 3종 레퍼런스 + 씬 체이닝 지원
        from app.services.reference_service import ReferenceService
        from app.services.prompt_builder import build_scene_chaining_context
        
        ref_service = ReferenceService(request.session_id)
        logger.info(f"[재생성] 세션 디렉토리: {ref_service.ref_dir}")
        ref_data = await ref_service.load_for_model(model_name)
        character_ref = ref_data.get("character")
        method_ref = ref_data.get("method")
        style_ref = ref_data.get("style")
        logger.info(f"[재생성] Character: {len(character_ref) if character_ref else 'None'}bytes, "
                    f"Method: {len(method_ref) if method_ref else 'None'}bytes, "
                    f"Style: {len(style_ref) if style_ref else 'None'}bytes")
        
        # 씬 체이닝: 직전 씬 이미지 + 이전 씬 요약
        prev_scene_image = None
        prev_scene_summaries = None
        prev_scene_number = None
        
        if scene.scene_number > 1:
            summaries, prev_sn = build_scene_chaining_context(
                session.story.scenes, scene.scene_number
            )
            prev_scene_summaries = summaries if summaries else None
            prev_scene_number = prev_sn
            
            # 직전 씬 이미지 로드 (비동기 래핑으로 이벤트 루프 블로킹 방지)
            if prev_sn and session.images:
                for img_entry in session.images:
                    if (img_entry.scene_number == prev_sn and 
                        img_entry.status == "generated" and 
                        img_entry.local_path and os.path.exists(img_entry.local_path)):
                        prev_scene_image = await asyncio.to_thread(
                            lambda p=img_entry.local_path: open(p, "rb").read()
                        )
                        break
        
        ref_count = sum(1 for x in [character_ref, method_ref, style_ref] if x)
        logger.info(f"[재생성] 씬 {scene.scene_number}: {ref_count}종 레퍼런스"
                    f"{' + 씬체이닝' if prev_scene_image else ''}")
        
        image_data = await generator.generate(
            prompt,
            reference_images=[character_ref] if character_ref else None,
            method_image=method_ref,
            style_image=style_ref,
            prev_scene_image=prev_scene_image,
            prev_scene_summaries=prev_scene_summaries,
            prev_scene_number=prev_scene_number,
            aspect_ratio=ar
        )
        
        # ── 재생성 전 기존 이미지 히스토리 저장 ──
        from app.services.image_editor import get_history_manager
        old_img = session.images[request.scene_index]
        old_history = list(old_img.image_history) if old_img.image_history else []
        old_prompts = list(old_img.prompt_history) if old_img.prompt_history else []
        
        if old_img.local_path and old_img.status == "generated" and os.path.exists(old_img.local_path):
            history_mgr = get_history_manager()
            hist_path = history_mgr.save_to_history(
                old_img.local_path, request.session_id, scene.scene_number
            )
            old_history.append(hist_path)
            if old_img.prompt_used:
                old_prompts.append(old_img.prompt_used)
            logger.info(f"[재생성] 이전 이미지 히스토리 저장: {hist_path} (총 {len(old_history)}개)")
        
        # 파일 저장
        filename = f"scene_{scene.scene_number}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join("output", filename)
        os.makedirs("output", exist_ok=True)
        
        if isinstance(image_data, bytes):
            with open(filepath, "wb") as f:
                f.write(image_data)
        
        new_img = GeneratedImage(
            scene_number=scene.scene_number,
            prompt_used=prompt,
            local_path=filepath,
            status="generated",
            image_history=old_history,
            prompt_history=old_prompts,
        )
        session.images[request.scene_index] = new_img
        return {
            "image": new_img.model_dump(),
            "history_count": len(old_history),
        }
    except Exception as e:
        import traceback
        logger.error(f"[REGEN ERROR] scene {scene.scene_number}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"재생성 실패: {str(e)}")


# ============================================
# 이미지 되돌리기 API
# ============================================

class UndoImageRequest(BaseModel):
    session_id: str
    scene_index: int

@router.post("/undo-image")
async def undo_image(request: UndoImageRequest):
    """씬 검토 단계에서 이미지 되돌리기 (마지막 히스토리로 복원)"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    if not session.images or request.scene_index >= len(session.images):
        raise HTTPException(status_code=400, detail="유효하지 않은 씬 인덱스입니다")
    
    target = session.images[request.scene_index]
    
    if not target.image_history:
        raise HTTPException(status_code=400, detail="되돌릴 이력이 없습니다")
    
    # 마지막 히스토리에서 복원
    prev_path = target.image_history.pop()
    prev_prompt = target.prompt_history.pop() if target.prompt_history else target.prompt_used
    
    if not os.path.exists(prev_path):
        raise HTTPException(status_code=404, detail="이전 이미지 파일을 찾을 수 없습니다")
    
    # 현재 이미지 경로를 이전 이미지로 교체
    old_local = target.local_path
    target.local_path = prev_path
    target.prompt_used = prev_prompt
    
    logger.info(f"[되돌리기] 씬 {target.scene_number}: {old_local} → {prev_path} (남은 히스토리: {len(target.image_history)}개)")
    
    return {
        "success": True,
        "image": target.model_dump(),
        "remaining_history": len(target.image_history),
    }


# ============================================
# 발행 API
# ============================================

class PublishRequest(BaseModel):
    session_id: str
    caption: str
    images: List[str] = []
    target_series: Optional[int] = None  # 시리즈 번호 (None이면 전체)
    scheduled_publish_time: Optional[int] = None  # Unix 타임스탬프 (None이면 즉시 발행)


class InstagramTestRequest(BaseModel):
    images: List[str] = []
    caption: str = "테스트 발행"


@router.post("/instagram-test")
async def instagram_test(req: InstagramTestRequest = InstagramTestRequest()):
    """세션 없이 인스타 발행만 테스트. body: {"images": ["url1"], "caption": "..."} 없으면 샘플 이미지 1장."""
    from app.services.instagram_service import get_instagram_service
    from app.models.models import PublishData
    urls = (req.images or [])[:10]
    if not urls:
        urls = ["https://res.cloudinary.com/demo/image/upload/sample.jpg"]
    instagram = get_instagram_service()
    result = await instagram.publish_workflow(PublishData(images=urls, caption=req.caption or "테스트 발행"))
    return result


@router.get("/instagram-check")
async def instagram_check():
    """인스타 토큰·USER_ID 설정 여부 및 토큰 유효성 확인."""
    import httpx
    from app.core.config import get_settings
    settings = get_settings()
    token = (settings.instagram_access_token or "").strip()
    user_id = (settings.instagram_user_id or "").strip()
    if not token or not user_id:
        return {
            "ok": False,
            "configured": False,
            "message": "INSTAGRAM_ACCESS_TOKEN 또는 INSTAGRAM_USER_ID가 .env에 없습니다."
        }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://graph.facebook.com/v18.0/me",
                params={"fields": "id", "access_token": token}
            )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200:
            err = data.get("error", {})
            return {
                "ok": False,
                "configured": True,
                "message": err.get("message", r.text or f"HTTP {r.status_code}")
            }
        return {"ok": True, "configured": True, "message": "인스타 설정 정상."}
    except Exception as e:
        return {"ok": False, "configured": True, "message": str(e)}


@router.post("/publish")
async def publish(request: PublishRequest):
    """Instagram 발행 (즉시 또는 예약). 로컬 이미지는 Cloudinary 업로드 후 발행."""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        from app.services.instagram_service import get_instagram_service
        from app.services.cloudinary_service import get_cloudinary_service
        from app.models.models import PublishData
        from urllib.parse import urlparse, unquote
        
        image_urls = []
        cloudinary = get_cloudinary_service()
        
        logger.info(f"[발행] 시작 — 프론트엔드에서 받은 이미지: {request.images}")
        
        # 1) request.images 처리: 모든 이미지를 공개 HTTPS URL로 변환
        if request.images:
            for idx, raw in enumerate(request.images):
                # ★ URL 인코딩된 한글 경로 디코딩 (%EB%B0%9C → 발)
                raw = unquote(raw)
                logger.info(f"[발행] 이미지 {idx+1}/{len(request.images)} 처리: {raw[:100]}")
                
                # (a) localhost/127.0.0.1 URL → 로컬 경로 추출 후 Cloudinary 업로드
                if raw.startswith("http://localhost") or raw.startswith("http://127.0.0.1"):
                    local_path = unquote(urlparse(raw).path.lstrip("/"))
                    logger.info(f"[발행] localhost URL 감지 → 로컬 경로: {local_path}")
                    if cloudinary.cloud_name and local_path:
                        url = await cloudinary.upload_from_path(local_path)
                        if url:
                            image_urls.append(url)
                            logger.info(f"[발행] Cloudinary 업로드 성공: {url}")
                        else:
                            logger.error(f"[발행] Cloudinary 업로드 실패: {local_path}")
                            return {"success": False, "error": f"이미지 업로드 실패: {local_path} — 서버 로그를 확인하세요."}
                    else:
                        return {"success": False, "error": f"Cloudinary 설정이 필요합니다. .env 파일을 확인하세요."}
                
                # (b) 이미 공개 HTTPS URL인 경우
                elif raw.startswith("https://"):
                    image_urls.append(raw)
                    logger.info(f"[발행] HTTPS URL 그대로 사용: {raw[:80]}")
                
                # (c) http:// (localhost 아닌 외부) — 경고 후 사용
                elif raw.startswith("http://"):
                    logger.warning(f"[발행] 비-HTTPS URL 감지: {raw[:80]} — Instagram이 거부할 수 있습니다")
                    image_urls.append(raw)
                
                # (d) 상대 경로 (/output/... 등) → Cloudinary 업로드
                else:
                    clean_path = raw.lstrip("/")
                    logger.info(f"[발행] 로컬 경로 → Cloudinary 업로드: {clean_path}")
                    if cloudinary.cloud_name:
                        url = await cloudinary.upload_from_path(clean_path)
                        if url:
                            image_urls.append(url)
                            logger.info(f"[발행] Cloudinary 업로드 성공: {url}")
                        else:
                            logger.error(f"[발행] Cloudinary 업로드 실패: {clean_path}")
                            return {"success": False, "error": f"이미지 업로드 실패: {clean_path} — 서버 로그를 확인하세요."}
                    else:
                        return {"success": False, "error": "Cloudinary 설정이 필요합니다. .env 파일을 확인하세요."}

        # 2) request.images가 비어있으면 세션의 final_images / 원본 images 사용
        if not image_urls:
            logger.info("[발행] request.images에서 URL 확보 실패 → 세션 이미지 fallback")
            source_images = []
            if hasattr(session, 'final_images') and session.final_images:
                for fi in session.final_images:
                    if isinstance(fi, str) and fi:
                        source_images.append(fi)
                    elif hasattr(fi, 'export_path'):
                        ep = fi.export_path or getattr(fi, 'local_path', None)
                        if ep:
                            source_images.append(ep)
            if not source_images and session.images:
                for img in session.images:
                    lp = getattr(img, "local_path", None)
                    if lp:
                        source_images.append(lp)
            logger.info(f"[발행] 세션 이미지 {len(source_images)}장 발견")
            for path in source_images:
                if str(path).startswith("https://"):
                    image_urls.append(path)
                elif cloudinary.cloud_name and path:
                    url = await cloudinary.upload_from_path(path)
                    if url:
                        image_urls.append(url)
                    else:
                        return {"success": False, "error": f"이미지 업로드 실패: {path}"}
                else:
                    return {"success": False, "error": "로컬 이미지는 Cloudinary 설정이 필요합니다. .env에 CLOUDINARY_* 를 넣어주세요."}
        
        if not image_urls:
            return {"success": False, "error": "발행할 이미지가 없습니다."}
        
        # ★ URL 검증 게이트: Instagram은 공개 HTTPS URL만 허용
        for url in image_urls:
            if not url.startswith("https://"):
                logger.error(f"[발행] 비-HTTPS URL이 Instagram에 전달될 뻔함: {url}")
                return {"success": False, "error": f"Instagram은 공개 HTTPS URL만 허용합니다. 문제 URL: {url[:80]}"}
        
        # ★ Cloudinary URL JPEG 변환 보장 (Instagram은 JPEG만 공식 지원)
        for i, u in enumerate(image_urls):
            if "res.cloudinary.com" in u and "/image/upload/" in u:
                # URL에 f_jpg 변환이 없으면 삽입: /image/upload/ → /image/upload/f_jpg,q_95/
                if "/f_jpg" not in u and "/f_auto" not in u:
                    image_urls[i] = u.replace("/image/upload/", "/image/upload/f_jpg,q_95/")
                    logger.info(f"[발행] Cloudinary URL JPEG 변환 적용: {image_urls[i][:100]}")
        
        logger.info(f"[발행] 최종 URL {len(image_urls)}개 검증 완료 → Instagram 발행 시작")
        for i, u in enumerate(image_urls):
            logger.info(f"[발행]   URL {i+1}: {u}")
        
        # 예약 발행 시간 처리 + 백엔드 검증
        scheduled_time = None
        if hasattr(request, 'scheduled_publish_time') and request.scheduled_publish_time:
            import time as _time
            now_ts = int(_time.time())
            st = request.scheduled_publish_time
            # ★ C8: 과거 시간 방어
            if st < now_ts:
                raise HTTPException(status_code=400, detail="예약 시간이 현재보다 과거입니다.")
            # 최소 10분 뒤
            if st - now_ts < 10 * 60:
                raise HTTPException(status_code=400, detail="예약 시간은 현재로부터 최소 10분 이후여야 합니다.")
            # 최대 75일 이내
            if st - now_ts > 75 * 24 * 60 * 60:
                raise HTTPException(status_code=400, detail="예약 시간은 최대 75일 이내여야 합니다.")
            scheduled_time = st

        instagram = get_instagram_service()
        publish_data = PublishData(images=image_urls, caption=request.caption)
        result = await instagram.publish_workflow(publish_data, scheduled_publish_time=scheduled_time)
        
        if not result.get("success"):
            # ★ 진단 정보를 사용자에게 직접 표시
            diag = {
                "error_code": result.get("error_code"),
                "error_subcode": result.get("error_subcode"),
                "error_type": result.get("error_type"),
                "fbtrace_id": result.get("fbtrace_id"),
                "image_urls": [u[:80] for u in image_urls],
            }
            logger.error(f"[발행] Instagram 발행 실패: {result.get('error')} | 진단: {diag}")
            return {"success": False, "error": result.get("error", "Unknown error"), "diagnostics": diag}
        
        session.state = WorkflowState.PUBLISHED
        
        response = {
            "success": True,
            "post_id": result.get("media_id", ""),
            "scheduled": result.get("scheduled", False),
            "scheduled_time": result.get("scheduled_time"),
            "image_count": result.get("image_count", len(image_urls)),
        }
        
        logger.info(f"[발행] 완료: {response}")
        return response
    except Exception as e:
        logger.error(f"[발행] 오류: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ============================================
# 9. 스토리 히스토리 API
# ============================================

class ManualSaveStoryRequest(BaseModel):
    session_id: Optional[str] = None
    save_name: str  # 사용자 지정 저장 이름
    story_data: Optional[dict] = None  # 세션이 없을 때 프론트엔드에서 직접 전달
    keyword: Optional[str] = None


@router.post("/story/save")
async def save_story_manual(request: ManualSaveStoryRequest):
    """스토리 수동 저장 (사용자 이름 지정) — 세션이 없어도 프론트에서 직접 데이터 전달 가능"""
    session = sessions.get(request.session_id) if request.session_id else None
    
    # 세션에서 데이터 가져오기 또는 프론트엔드 직접 전달 데이터 사용
    if session and session.story:
        story_dict = session.story.model_dump()
        keyword = session.keyword
        collected_data = session.collected_data
        char_settings = session.settings.character.model_dump() if session.settings else None
    elif request.story_data:
        story_dict = request.story_data
        keyword = request.keyword or ""
        collected_data = None
        char_settings = None
    else:
        raise HTTPException(status_code=404, detail="저장할 스토리가 없습니다. 세션이 만료되었을 수 있습니다.")
    
    # 이미지 데이터 수집 (세션에 생성된 이미지가 있는 경우)
    images_data = None
    if session and session.images:
        images_data = [img.model_dump(mode='json') for img in session.images]

    save_dir = "output/stories"
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    import re
    safe_name = re.sub(r'[^\w\s가-힣-]', '', request.save_name).strip()
    if not safe_name:
        safe_name = "unnamed"
    filename = f"{timestamp}_{safe_name}.json"
    filepath = os.path.join(save_dir, filename)

    data = {
        "timestamp": datetime.now().isoformat(),
        "save_name": request.save_name,
        "keyword": keyword,
        "story": story_dict,
        "collected_data": collected_data,
        "character_settings": char_settings,
        "images": images_data  # 생성된 이미지 정보 포함
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"[story/save] 수동 저장: {filepath}")
    return {"success": True, "filename": filename, "message": f"'{request.save_name}' 저장 완료"}


@router.delete("/story/delete/{filename}")
async def delete_story(filename: str):
    """저장된 스토리 삭제"""
    filepath = os.path.join("output/stories", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    os.remove(filepath)
    logger.info(f"[story/delete] 삭제: {filepath}")
    return {"success": True, "message": "삭제 완료"}


@router.get("/history/stories")
async def list_story_history():
    """저장된 스토리 목록 조회 (전체, 최신순)"""
    history_dir = "output/stories"
    if not os.path.exists(history_dir):
        return []
    
    files = glob.glob(os.path.join(history_dir, "*.json"))
    files.sort(key=os.path.getmtime, reverse=True)
    
    result = []
    for f in files:
        try:
            filename = os.path.basename(f)
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                result.append({
                    "filename": filename,
                    "save_name": data.get("save_name", ""),
                    "keyword": data.get("keyword", "Unknown"),
                    "timestamp": data.get("timestamp", ""),
                    "title": data.get("story", {}).get("title", "Untitled"),
                    "scene_count": len(data.get("story", {}).get("scenes", []))
                })
        except Exception as e:
            logger.error(f"Error reading history file {f}: {e}")
            
    return result


class LoadStoryRequest(BaseModel):
    session_id: Optional[str] = None
    filename: str


@router.post("/history/load")
async def load_story_history(request: LoadStoryRequest):
    """저장된 스토리 불러오기"""
    # 세션 ID가 없거나 유효하지 않으면 새 세션 생성
    session = sessions.get(request.session_id) if request.session_id else None
    
    if not session:
        # Create new session
        new_id = str(uuid.uuid4())
        session = WorkflowSession(session_id=new_id)
        sessions[new_id] = session
        # We will return this new ID
    
    history_dir = "output/stories"
    filepath = os.path.join(history_dir, request.filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Story file not found")
        
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)
            
        # 세션 복원
        session.keyword = data.get("keyword")
        session.story = Story(**data.get("story"))
        session.state = WorkflowState.REVIEWING_SCENES
        
        # 수집 데이터도 복원 (있다면)
        if "collected_data" in data:
            session.collected_data = data["collected_data"]
            
        # 이미지 데이터 복원 (있다면) — 기존 세션 재사용 시 중복 방지
        session.images = []
        images_list = []
        if data.get("images"):
            for img_data in data["images"]:
                try:
                    # local_path가 유효한지 확인 (파일 존재 여부)
                    local_path = img_data.get("local_path")
                    if local_path and os.path.exists(local_path):
                        img = GeneratedImage(**img_data)
                        session.images.append(img)
                        images_list.append(img.model_dump())
                    else:
                        # 파일은 없지만 메타데이터는 보존
                        img = GeneratedImage(**img_data)
                        img.status = "missing"
                        session.images.append(img)
                        images_list.append(img.model_dump())
                        logger.warning(f"[history/load] 이미지 파일 없음: {local_path}")
                except Exception as img_err:
                    logger.error(f"[history/load] 이미지 복원 실패: {img_err}")
        
        return {
            "success": True,
            "session_id": session.session_id, # Return the (possibly new) session ID
            "story": session.story.model_dump(),
            "collected_data": session.collected_data,
            "images": images_list  # 이미지 데이터 반환
        }
    except Exception as e:
        logger.error(f"Failed to load story: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load story: {str(e)}")


def save_story_to_history(session: WorkflowSession):
    """스토리를 JSON 파일로 저장"""
    history_dir = "output/stories"
    os.makedirs(history_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_keyword = "".join([c for c in (session.keyword or "unknown") if c.isalnum() or c in (' ', '_', '-')]).strip()
    filename = f"{timestamp}_{safe_keyword}.json"
    filepath = os.path.join(history_dir, filename)
    
    # 이미지 데이터도 함께 저장
    images_data = []
    for img in session.images:
        try:
            images_data.append(img.model_dump())
        except Exception:
            pass
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "keyword": session.keyword,
        "story": session.story.model_dump(),
        "collected_data": session.collected_data,
        "character_settings": session.settings.character.model_dump(),
        "images": images_data
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Story saved to {filepath}")


# ============================================
# 썸네일(커버) 생성/편집 API
# ============================================

class ThumbnailGenerateRequest(BaseModel):
    session_id: str
    source: str = "ai_generate"         # ai_generate | select_scene | upload
    selected_scene_number: Optional[int] = None  # select_scene일 때
    title_text: Optional[str] = None
    subtitle_text: Optional[str] = None
    title_position: str = "center"       # top | center | bottom
    title_color: str = "#FFFFFF"
    title_size: int = 48


@router.post("/thumbnail/generate")
async def generate_thumbnail(request: ThumbnailGenerateRequest):
    """썸네일(커버 이미지) 생성"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not session.story:
        raise HTTPException(status_code=400, detail="스토리가 없습니다")

    from app.services.pillow_service import get_pillow_service
    from PIL import Image
    from io import BytesIO

    pillow = get_pillow_service()
    output_dir = f"output/{request.session_id}"
    os.makedirs(output_dir, exist_ok=True)
    thumbnail_path = os.path.join(output_dir, "thumbnail.png")

    # 제목 기본값: 스토리 제목
    title = request.title_text or session.story.title

    if request.source == "select_scene" and request.selected_scene_number is not None:
        # 본편 이미지에서 선택
        scene_idx = request.selected_scene_number - 1
        if scene_idx < 0 or scene_idx >= len(session.images):
            raise HTTPException(status_code=400, detail="유효하지 않은 씬 번호")
        img_info = session.images[scene_idx]
        img_path = img_info.local_path or img_info.image_url
        if not img_path or not os.path.exists(img_path):
            raise HTTPException(status_code=400, detail="해당 씬 이미지를 찾을 수 없습니다")
        base_image = Image.open(img_path)

    elif request.source == "ai_generate":
        # AI로 커버 이미지 생성
        char_style = None
        if session.settings.image.character_style_id:
            char_style = get_character_style(session.settings.image.character_style_id)
        style_prompt = char_style.prompt_block if char_style else "Korean webtoon style"

        cover_prompt = (
            f"Cover art for a webtoon titled \"{title}\". "
            f"{style_prompt}. "
            f"Eye-catching composition, character close-up or impactful scene, "
            f"leave empty space at {'top' if request.title_position == 'top' else 'center' if request.title_position == 'center' else 'bottom'} for title text. "
            f"No text, no speech bubbles, no letters, no typography."
        )

        from app.core.config import get_settings as _gs2
        api_key = _gs2().openai_api_key or ""
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다")

        model_name = session.settings.image.model or "gpt-image-1"
        generator = get_generator(model_name, api_key)
        image_bytes = await generator.generate(cover_prompt, quality="medium", aspect_ratio="4:5")

        if not isinstance(image_bytes, bytes):
            raise HTTPException(status_code=500, detail="이미지 생성 실패")

        base_image = Image.open(BytesIO(image_bytes))

    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 source: {request.source}")

    # 제목 텍스트 오버레이
    if title:
        base_image = pillow.render_thumbnail_title(
            image=base_image,
            title=title,
            subtitle=request.subtitle_text,
            position=request.title_position,
            title_color=request.title_color,
            title_size=request.title_size
        )

    # 저장
    base_image.save(thumbnail_path, "PNG")

    # 세션에 저장
    session.thumbnail = ThumbnailData(
        enabled=True,
        source=ThumbnailSource(request.source),
        image_path=thumbnail_path,
        selected_scene_number=request.selected_scene_number,
        title_text=title,
        subtitle_text=request.subtitle_text,
        title_position=ThumbnailPosition(request.title_position),
        title_color=request.title_color,
        title_size=request.title_size
    )

    return {
        "success": True,
        "thumbnail_path": thumbnail_path,
        "title": title,
        "source": request.source
    }


class ThumbnailToggleRequest(BaseModel):
    session_id: str
    enabled: bool


@router.post("/thumbnail/toggle")
async def toggle_thumbnail(request: ThumbnailToggleRequest):
    """썸네일 ON/OFF 토글"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    if session.thumbnail:
        session.thumbnail.enabled = request.enabled
    else:
        session.thumbnail = ThumbnailData(enabled=request.enabled)

    return {"success": True, "enabled": request.enabled}


@router.get("/thumbnail/{session_id}")
async def get_thumbnail(session_id: str):
    """현재 썸네일 정보 조회"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    if not session.thumbnail:
        return {"enabled": True, "has_thumbnail": False}

    return {
        "enabled": session.thumbnail.enabled,
        "has_thumbnail": session.thumbnail.image_path is not None,
        "thumbnail_path": session.thumbnail.image_path,
        "title": session.thumbnail.title_text,
        "subtitle": session.thumbnail.subtitle_text,
        "source": session.thumbnail.source.value if session.thumbnail.source else None,
        "title_position": session.thumbnail.title_position.value if session.thumbnail.title_position else "center",
        "title_color": session.thumbnail.title_color,
        "title_size": session.thumbnail.title_size
    }


# ============================================
# "다음편에 계속" API
# ============================================

class ToBeContinuedRequest(BaseModel):
    session_id: str
    enabled: bool = True
    style: str = "fade_overlay"     # fade_overlay | badge | full_overlay
    text: str = "다음편에 계속 →"


@router.post("/to-be-continued/apply")
async def apply_to_be_continued(request: ToBeContinuedRequest):
    """시리즈 각 편의 마지막 씬에 '다음편에 계속' 오버레이 적용 (최종편 제외)"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not session.story:
        raise HTTPException(status_code=400, detail="스토리가 없습니다")

    story = session.story

    # 시리즈 분할 안 됐거나 마지막 편이면 적용 불필요
    if not story.series_info:
        return {"success": False, "reason": "시리즈가 아닙니다"}
    if story.series_info.total <= 1:
        return {"success": False, "reason": "1편뿐이므로 '다음편에 계속'이 불필요합니다"}
    if not request.enabled:
        story.to_be_continued_enabled = False
        return {"success": True, "enabled": False, "applied_scenes": []}

    if not session.images:
        return {"success": False, "reason": "생성된 이미지가 없습니다"}

    from app.services.pillow_service import get_pillow_service
    from PIL import Image

    pillow = get_pillow_service()
    applied_scenes = []

    # 시리즈별 마지막 씬에 오버레이 적용 (최종편은 제외)
    episodes = story.series_info.episodes
    for ep in episodes:
        # 최종편이면 건너뜀 (마지막 편에는 "다음편에 계속"이 불필요)
        if ep.episode_number >= story.series_info.total:
            continue

        # 이 편의 마지막 씬 인덱스 = scene_end - 1
        last_scene_idx = ep.scene_end - 1
        if last_scene_idx < 0:
            continue

        # 해당 씬 번호의 이미지 찾기 (scene_number는 1-based)
        target_scene_num = last_scene_idx + 1  # 0-based → 1-based
        target_img = next(
            (img for img in session.images if img.scene_number == target_scene_num),
            None
        )

        if not target_img:
            # scene_number 매칭 실패 시 인덱스로 시도
            if last_scene_idx < len(session.images):
                target_img = session.images[last_scene_idx]

        if not target_img or not target_img.local_path:
            logger.warning(f"[다음편에 계속] 시리즈 {ep.episode_number}편 마지막 씬 이미지 없음 (인덱스 {last_scene_idx})")
            continue

        img_path = target_img.local_path
        if not os.path.exists(img_path):
            logger.warning(f"[다음편에 계속] 이미지 파일 없음: {img_path}")
            continue

        try:
            base_image = Image.open(img_path)
            result_image = pillow.add_to_be_continued(
                image=base_image,
                text=request.text,
                style=request.style
            )
            result_image.save(img_path, "PNG")
            applied_scenes.append({
                "episode": ep.episode_number,
                "scene_number": target_img.scene_number,
                "scene_index": last_scene_idx
            })
            logger.info(f"[다음편에 계속] 시리즈 {ep.episode_number}편 마지막 씬 {target_img.scene_number}에 적용 완료")
        except Exception as e:
            logger.error(f"[다음편에 계속] 시리즈 {ep.episode_number}편 적용 실패: {e}")

    story.to_be_continued_enabled = True
    story.to_be_continued_style = ToBeContinuedStyle(request.style)

    return {
        "success": True,
        "enabled": True,
        "style": request.style,
        "applied_count": len(applied_scenes),
        "applied_scenes": applied_scenes
    }


# ============================================
# 비파괴 말풍선 레이어 API (Non-destructive Bubble Layer)
# ============================================

@router.post("/bubble-layers/{session_id}/init")
async def init_bubble_layers(session_id: str):
    """스토리 대사를 기반으로 말풍선 레이어 초기화
    
    원본 이미지는 절대 수정하지 않음.
    대사/나레이션을 BubbleOverlay JSON으로 분리 저장.
    """
    session = sessions.get(session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="세션 또는 스토리를 찾을 수 없습니다")
    
    # 캐릭터별 색상 매핑 생성
    char_names = list({c.name for c in session.story.characters})
    char_color_map = {}
    for i, name in enumerate(char_names):
        char_color_map[name] = CHARACTER_COLORS[i % len(CHARACTER_COLORS)]
    
    layers = []
    for scene in session.story.scenes:
        bubbles = []
        
        # 대사 → BubbleOverlay 변환
        for j, dialogue in enumerate(scene.dialogues):
            # 위치 자동 배정: 대사 인덱스에 따라 다른 위치
            positions = [
                BubblePosition.TOP_LEFT, BubblePosition.TOP_RIGHT,
                BubblePosition.TOP_CENTER, BubblePosition.MIDDLE_LEFT,
                BubblePosition.MIDDLE_RIGHT
            ]
            pos = positions[j % len(positions)]
            
            bubbles.append(BubbleOverlay(
                id=f"s{scene.scene_number}_d{j}",
                type="dialogue",
                character=dialogue.character,
                text=dialogue.text,
                position=pos,
                shape=BubbleShape.ROUND,
                tail_direction="bottom-left" if j % 2 == 0 else "bottom-right",
                bg_color="#FFFFFF",
                text_color="#000000",
                border_color="#333333",
                font_size=18,
                text_align="left",
                visible=True
            ))
        
        # 나레이션 → BubbleOverlay (하단 중앙 기본값)
        if scene.narration:
            bubbles.append(BubbleOverlay(
                id=f"s{scene.scene_number}_narr",
                type="narration",
                character="",
                text=scene.narration,
                position=BubblePosition.BOTTOM_CENTER,
                shape=BubbleShape.SQUARE,
                bg_color="rgba(0,0,0,0.7)",
                text_color="#FFFFFF",
                border_color="transparent",
                font_family="Nanum Gothic",
                font_size=15,
                bold=True,
                text_align="center",
                visible=True,
                opacity=0.85,
                x=5.0,
                y=78.0,
                w=90.0,
                h=12.0
            ))
        
        layers.append(BubbleLayer(
            scene_number=scene.scene_number,
            bubbles=bubbles,
            show_all=True,
            font_family="Jua"
        ))
    
    session.bubble_layers = layers
    
    return {
        "success": True,
        "layers_count": len(layers),
        "layers": [layer.model_dump() for layer in layers],
        "char_color_map": char_color_map
    }


@router.get("/bubble-layers/{session_id}")
async def get_bubble_layers(session_id: str):
    """세션의 전체 말풍선 레이어 조회"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    return {
        "success": True,
        "layers": [layer.model_dump() for layer in session.bubble_layers]
    }


class UpdateBubbleLayerRequest(BaseModel):
    bubbles: List[dict] = []
    show_all: bool = True
    font_family: str = "Nanum Gothic"


@router.put("/bubble-layers/{session_id}/{scene_num}")
async def update_bubble_layer(session_id: str, scene_num: int, request: UpdateBubbleLayerRequest):
    """특정 씬의 말풍선 레이어 업데이트 (비파괴 — 원본 이미지 수정 없음)"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    # 해당 씬 레이어 찾기
    target = None
    for layer in session.bubble_layers:
        if layer.scene_number == scene_num:
            target = layer
            break
    
    if not target:
        # 없으면 새로 생성
        target = BubbleLayer(scene_number=scene_num, bubbles=[], show_all=True)
        session.bubble_layers.append(target)
    
    # 업데이트
    target.bubbles = [BubbleOverlay(**b) for b in request.bubbles]
    target.show_all = request.show_all
    target.font_family = request.font_family
    
    return {"success": True, "scene_number": scene_num}


def _draw_wrapped_text(draw, text, font, x, y, max_width, fill="black", align="left"):
    """텍스트를 지정 폭에 맞게 자동 줄바꿈하여 그리기"""
    words = list(text)  # 한글은 글자 단위로 줄바꿈
    lines = []
    current_line = ""
    
    for char in words:
        if char == '\n':
            lines.append(current_line)
            current_line = ""
            continue
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    
    line_y = y
    for line in lines:
        if align == "center":
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            draw.text((x + (max_width - line_w) // 2, line_y), line, fill=fill, font=font)
        else:
            draw.text((x, line_y), line, fill=fill, font=font)
        bbox = draw.textbbox((0, 0), line, font=font)
        line_y += (bbox[3] - bbox[1]) + 4


@router.delete("/session/{session_id}/delete-scene/{scene_num}")
async def delete_scene_from_session(session_id: str, scene_num: int):
    """세션에서 특정 씬을 삭제 (이미지 + 말풍선 레이어 + 스토리)"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    scene_idx = scene_num - 1  # 0-based
    
    # 1. 이미지 삭제
    if session.images and scene_idx < len(session.images):
        img = session.images[scene_idx]
        if img.local_path and os.path.exists(img.local_path):
            try:
                os.remove(img.local_path)
                logger.info(f"[씬 삭제] 이미지 파일 삭제: {img.local_path}")
            except Exception as e:
                logger.warning(f"[씬 삭제] 이미지 파일 삭제 실패: {e}")
        session.images.pop(scene_idx)
        # 이미지 씬 번호 재정렬
        for i, img in enumerate(session.images):
            img.scene_number = i + 1
    
    # 2. 스토리 씬 삭제
    if session.story and session.story.scenes and scene_idx < len(session.story.scenes):
        session.story.scenes.pop(scene_idx)
        for i, sc in enumerate(session.story.scenes):
            sc.scene_number = i + 1
    
    # 3. 말풍선 레이어 삭제
    if hasattr(session, 'bubble_layers') and session.bubble_layers and scene_idx < len(session.bubble_layers):
        session.bubble_layers.pop(scene_idx)
        for i, layer in enumerate(session.bubble_layers):
            layer['scene_number'] = i + 1
    
    logger.info(f"[씬 삭제] 세션 {session_id}: 씬 {scene_num} 삭제 완료")
    return {"success": True, "message": f"씬 {scene_num} 삭제 완료"}


@router.post("/bubble-layers/{session_id}/export")
async def export_with_bubbles(session_id: str):
    """말풍선이 합성된 최종 이미지 내보내기 (Pillow 기반)
    
    이때만 원본 이미지 + 말풍선을 합성함 (비파괴 원칙 유지).
    합성 결과는 별도 파일로 저장 → 원본은 그대로 보존.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    if not session.images:
        raise HTTPException(status_code=400, detail="생성된 이미지가 없습니다")
    
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    import base64
    
    export_dir = os.path.join("output", "export")
    os.makedirs(export_dir, exist_ok=True)
    
    exported = []
    
    for img_data in session.images:
        scene_num = img_data.scene_number
        img_path = img_data.local_path
        
        if not img_path or not os.path.exists(img_path):
            continue
        
        img = Image.open(img_path).convert("RGBA")
        
        # 해당 씬의 bubble layer 찾기
        layer = None
        for bl in session.bubble_layers:
            if bl.scene_number == scene_num:
                layer = bl
                break
        
        if layer and layer.show_all:
            # Pillow로 말풍선 합성 (자유 위치 x,y,w,h 퍼센트 기반)
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            img_w, img_h = img.size
            
            # 9-Grid → 퍼센트 변환 (호환용)
            pos_to_pct = {
                "top-left": (5, 3), "top-center": (25, 3), "top-right": (55, 3),
                "middle-left": (5, 35), "middle-center": (25, 35), "middle-right": (55, 35),
                "bottom-left": (5, 65), "bottom-center": (15, 78), "bottom-right": (55, 65),
            }
            
            for bubble in layer.bubbles:
                if not bubble.visible or not bubble.text:
                    continue
                
                # 자유 위치 (퍼센트) → 픽셀
                bx_pct = getattr(bubble, 'x', None)
                by_pct = getattr(bubble, 'y', None)
                bw_pct = getattr(bubble, 'w', None)
                bh_pct = getattr(bubble, 'h', None)
                
                # 기존 9-Grid 데이터 호환
                if bx_pct is None or by_pct is None:
                    fallback = pos_to_pct.get(bubble.position, (25, 10))
                    bx_pct = fallback[0]
                    by_pct = fallback[1]
                if bw_pct is None:
                    bw_pct = 90 if bubble.type == "narration" else 40
                if bh_pct is None:
                    bh_pct = 10 if bubble.type == "narration" else 16
                
                bx1 = int(img_w * bx_pct / 100)
                by1 = int(img_h * by_pct / 100)
                bx2 = int(img_w * (bx_pct + bw_pct) / 100)
                by2 = int(img_h * (by_pct + bh_pct) / 100)
                
                # 범위 보정
                bx2 = min(bx2, img_w - 2)
                by2 = min(by2, img_h - 2)
                
                # ── 폰트 결정: 개별 폰트 > 레이어 글로벌 > 시스템 기본 ──
                font_size_px = max(12, int(bubble.font_size * img_w / 480))
                bubble_font_family = getattr(bubble, 'font_family', '') or ''
                layer_font_family = getattr(layer, 'font_family', '') or ''
                
                # 폰트 이름 → Windows 시스템 폰트 경로 매핑
                _FONT_MAP = {
                    "Nanum Gothic": "C:/Windows/Fonts/NanumGothic.ttf",
                    "Do Hyeon": "C:/Windows/Fonts/DoHyeon-Regular.ttf",
                    "Jua": "C:/Windows/Fonts/Jua-Regular.ttf",
                    "Gaegu": "C:/Windows/Fonts/Gaegu-Regular.ttf",
                    "Black Han Sans": "C:/Windows/Fonts/BlackHanSans-Regular.ttf",
                    "Nanum Pen Script": "C:/Windows/Fonts/NanumPenScript-Regular.ttf",
                    "Nanum Brush Script": "C:/Windows/Fonts/NanumBrushScript-Regular.ttf",
                    "Nanum Myeongjo": "C:/Windows/Fonts/NanumMyeongjo.ttf",
                    "Gothic A1": "C:/Windows/Fonts/GothicA1-Regular.ttf",
                    "Gamja Flower": "C:/Windows/Fonts/GamjaFlower-Regular.ttf",
                    "Hi Melody": "C:/Windows/Fonts/HiMelody-Regular.ttf",
                    "Poor Story": "C:/Windows/Fonts/PoorStory-Regular.ttf",
                    "Sunflower": "C:/Windows/Fonts/Sunflower-Medium.ttf",
                }
                _DEFAULT_FONT = "C:/Windows/Fonts/malgun.ttf"
                
                chosen_font_name = bubble_font_family or layer_font_family
                font_path = _FONT_MAP.get(chosen_font_name, _DEFAULT_FONT)
                
                try:
                    font = ImageFont.truetype(font_path, font_size_px)
                except:
                    try:
                        font = ImageFont.truetype(_DEFAULT_FONT, font_size_px)
                    except:
                        font = ImageFont.load_default()
                
                padding_x = max(8, int((bx2 - bx1) * 0.08))
                padding_y = max(6, int((by2 - by1) * 0.08))
                
                # ── PillowService의 BUBBLE_STYLES 참조 ──
                from app.services.pillow_service import PillowService
                _pillow_styles = PillowService.BUBBLE_STYLES
                
                if bubble.type == "narration":
                    # ── 나레이션: 스타일별 배경 ──
                    narr_style = getattr(bubble, 'narration_style', 'classic') or 'classic'
                    _NARR_STYLES_PILLOW = {
                        "classic":   {"bg": (0, 0, 0, 180), "text": "white"},
                        "light":     {"bg": (255, 255, 255, 216), "text": "#333333"},
                        "gradient":  {"bg": (20, 20, 60, 200), "text": "white"},
                        "minimal":   {"bg": (0, 0, 0, 0), "text": "white"},
                        "cinematic": {"bg": (0, 0, 0, 216), "text": "#e0e0e0"},
                        "parchment": {"bg": (245, 235, 220, 230), "text": "#4a3728"},
                    }
                    ns = _NARR_STYLES_PILLOW.get(narr_style, _NARR_STYLES_PILLOW["classic"])
                    
                    if narr_style == 'minimal':
                        # 미니멀: 테두리만
                        draw.rectangle([bx1, by1, bx2, by2], fill=None, outline="white", width=1)
                    else:
                        draw.rectangle([bx1, by1, bx2, by2], fill=ns["bg"])
                    
                    _draw_wrapped_text(draw, bubble.text, font,
                                       bx1 + padding_x, by1 + padding_y,
                                       bx2 - bx1 - padding_x * 2,
                                       fill=ns["text"], align="center")
                else:
                    # ── 스타일별 렌더링 ──
                    shape = getattr(bubble, 'shape', 'round') or 'round'
                    style_def = _pillow_styles.get(shape, _pillow_styles.get('round'))
                    
                    # 배경색 결정: 스타일 기본 > 개별 설정
                    if shape == 'dark':
                        fill_color = style_def["bg_color"]
                    else:
                        bg_hex = bubble.bg_color or "#FFFFFF"
                        try:
                            r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
                            fill_color = (r, g, b, int((bubble.opacity or 0.95) * 255))
                        except:
                            fill_color = style_def["bg_color"]
                    
                    radius = style_def.get("border_radius", 15)
                    border_w = style_def.get("border_width", 2)
                    border_outline = bubble.border_color or "#333333"
                    
                    # soft 스타일은 테두리 없음
                    if shape == 'soft':
                        border_w = 0
                        border_outline = None
                    
                    bw = bx2 - bx1
                    bh = by2 - by1
                    
                    # ── 모양별 Pillow 렌더링 분기 ──
                    import math
                    
                    # clip-path 기반 모양: 다각형으로 렌더링
                    _CLIP_PATH_SHAPES = {
                        "starburst": [
                            (0.50,0.00),(0.61,0.15),(0.75,0.02),(0.77,0.20),(0.95,0.10),(0.85,0.28),
                            (1.00,0.40),(0.88,0.50),(1.00,0.62),(0.85,0.68),(0.93,0.88),(0.75,0.78),
                            (0.65,0.98),(0.55,0.80),(0.45,0.98),(0.35,0.80),(0.22,0.95),(0.22,0.72),
                            (0.05,0.82),(0.15,0.62),(0.00,0.50),(0.12,0.40),(0.00,0.25),(0.15,0.22),
                            (0.08,0.05),(0.25,0.15),(0.38,0.00)
                        ],
                        "spike": [
                            (0.50,0.00),(0.58,0.20),(0.72,0.03),(0.68,0.25),(0.90,0.12),(0.80,0.32),
                            (1.00,0.28),(0.88,0.45),(1.00,0.55),(0.88,0.58),(1.00,0.72),(0.82,0.70),
                            (0.92,0.90),(0.72,0.75),(0.62,1.00),(0.52,0.78),(0.40,1.00),(0.35,0.78),
                            (0.18,0.92),(0.22,0.70),(0.00,0.75),(0.14,0.58),(0.00,0.48),(0.12,0.40),
                            (0.00,0.25),(0.18,0.30),(0.08,0.12),(0.28,0.25),(0.35,0.02),(0.42,0.22)
                        ],
                        "explosion": [
                            (0.50,0.00),(0.55,0.18),(0.68,0.02),(0.65,0.22),(0.85,0.08),(0.78,0.28),
                            (0.98,0.22),(0.85,0.38),(1.00,0.45),(0.88,0.52),(1.00,0.62),(0.82,0.62),
                            (0.95,0.80),(0.72,0.72),(0.78,0.98),(0.58,0.78),(0.48,1.00),(0.42,0.78),
                            (0.25,0.95),(0.30,0.70),(0.08,0.82),(0.18,0.62),(0.00,0.55),(0.15,0.48),
                            (0.00,0.35),(0.18,0.35),(0.05,0.18),(0.22,0.28),(0.28,0.05),(0.38,0.22)
                        ],
                        "scallop": [
                            (0.08,0.00),(0.18,0.06),(0.28,0.00),(0.38,0.06),(0.50,0.00),(0.62,0.06),
                            (0.72,0.00),(0.82,0.06),(0.92,0.00),(1.00,0.08),(0.95,0.18),(1.00,0.28),
                            (0.95,0.40),(1.00,0.52),(0.95,0.62),(1.00,0.72),(0.95,0.82),(1.00,0.92),
                            (0.92,1.00),(0.82,0.94),(0.72,1.00),(0.62,0.94),(0.50,1.00),(0.38,0.94),
                            (0.28,1.00),(0.18,0.94),(0.08,1.00),(0.00,0.92),(0.05,0.82),(0.00,0.72),
                            (0.05,0.62),(0.00,0.52),(0.05,0.40),(0.00,0.28),(0.05,0.18),(0.00,0.08)
                        ],
                        "wavy": [
                            (0.05,0.00),(0.15,0.05),(0.25,0.00),(0.35,0.05),(0.45,0.00),(0.55,0.05),
                            (0.65,0.00),(0.75,0.05),(0.85,0.00),(0.95,0.05),(1.00,0.12),(0.98,0.25),
                            (1.00,0.38),(0.98,0.50),(1.00,0.62),(0.98,0.75),(1.00,0.88),(0.95,0.95),
                            (0.85,1.00),(0.75,0.95),(0.65,1.00),(0.55,0.95),(0.45,1.00),(0.35,0.95),
                            (0.25,1.00),(0.15,0.95),(0.05,1.00),(0.00,0.88),(0.02,0.75),(0.00,0.62),
                            (0.02,0.50),(0.00,0.38),(0.02,0.25),(0.00,0.12)
                        ],
                        "fluffy": [
                            (0.10,0.05),(0.20,0.00),(0.30,0.08),(0.42,0.00),(0.55,0.05),(0.65,0.00),
                            (0.75,0.08),(0.88,0.00),(0.95,0.10),(1.00,0.22),(0.95,0.35),(1.00,0.48),
                            (0.95,0.60),(1.00,0.72),(0.95,0.85),(0.88,0.95),(0.78,1.00),(0.65,0.95),
                            (0.55,1.00),(0.42,0.95),(0.30,1.00),(0.20,0.95),(0.10,1.00),(0.02,0.88),
                            (0.00,0.75),(0.05,0.62),(0.00,0.50),(0.05,0.38),(0.00,0.25),(0.05,0.12)
                        ],
                        "jagged": [
                            (0.03,0.05),(0.12,0.00),(0.22,0.08),(0.30,0.00),(0.42,0.05),(0.55,0.00),
                            (0.62,0.08),(0.75,0.00),(0.82,0.05),(0.95,0.00),(1.00,0.10),(0.95,0.22),
                            (1.00,0.32),(0.98,0.45),(1.00,0.58),(0.95,0.68),(1.00,0.78),(0.98,0.88),
                            (0.95,1.00),(0.82,0.95),(0.72,1.00),(0.62,0.92),(0.50,1.00),(0.40,0.95),
                            (0.28,1.00),(0.18,0.92),(0.08,1.00),(0.00,0.90),(0.05,0.78),(0.00,0.65),
                            (0.05,0.52),(0.00,0.42),(0.03,0.30),(0.00,0.18)
                        ],
                    }
                    
                    if shape == 'ellipse':
                        # 타원형 — draw.ellipse 사용
                        draw.ellipse([bx1, by1, bx2, by2], fill=fill_color, outline=border_outline, width=border_w)
                    elif shape == 'cloud':
                        # 구름 — 겹치는 원으로 구름 느낌
                        cx_c, cy_c = (bx1 + bx2) // 2, (by1 + by2) // 2
                        rw, rh = bw // 2, bh // 2
                        # 메인 타원
                        draw.ellipse([bx1, by1, bx2, by2], fill=fill_color, outline=None)
                        # 상단 볼록한 원들
                        bump_r = int(min(bw, bh) * 0.18)
                        for offset_x in [-rw * 0.4, -rw * 0.1, rw * 0.2, rw * 0.45]:
                            bx = int(cx_c + offset_x)
                            by_t = by1 - int(bump_r * 0.3)
                            draw.ellipse([bx - bump_r, by_t, bx + bump_r, by_t + bump_r * 2], fill=fill_color, outline=None)
                        # 테두리 (전체 외곽)
                        draw.ellipse([bx1, by1, bx2, by2], fill=None, outline=border_outline, width=border_w)
                    elif shape == 'thought':
                        # 생각 — 점선은 Pillow로 어렵기 때문에 타원 + 작은 원들로 표현
                        draw.ellipse([bx1, by1, bx2, by2], fill=fill_color, outline=border_outline, width=border_w)
                        # 아래에 작은 생각 동그라미 3개
                        dot_r = max(4, int(min(bw, bh) * 0.04))
                        for i, (dr, doff) in enumerate([(dot_r * 3, 1), (dot_r * 2, 2), (dot_r, 3)]):
                            dx = bx1 + int(bw * 0.25) - i * int(bw * 0.05)
                            dy = by2 + dot_r * (i + 1) * 2
                            draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=fill_color, outline=border_outline, width=max(1, border_w - 1))
                    elif shape in _CLIP_PATH_SHAPES:
                        # clip-path 다각형 기반 모양 렌더링
                        points = _CLIP_PATH_SHAPES[shape]
                        polygon_pts = [(int(bx1 + p[0] * bw), int(by1 + p[1] * bh)) for p in points]
                        draw.polygon(polygon_pts, fill=fill_color)
                        # 테두리를 다각형 외곽선으로
                        if border_outline and border_w > 0:
                            pts_closed = polygon_pts + [polygon_pts[0]]
                            draw.line(pts_closed, fill=border_outline, width=max(1, border_w), joint="curve")
                    else:
                        # 기본: rounded_rectangle (round, square, shout, emphasis, soft, dark, system 등)
                        draw.rounded_rectangle(
                            [bx1, by1, bx2, by2],
                            radius=radius,
                            fill=fill_color,
                            outline=border_outline,
                            width=border_w
                        )
                    
                    # 텍스트 색상: dark 스타일은 흰색
                    txt_fill = bubble.text_color or "#000000"
                    if shape == 'dark':
                        txt_fill = "#FFFFFF"
                    
                    _draw_wrapped_text(draw, bubble.text, font,
                                       bx1 + padding_x, by1 + padding_y,
                                       bx2 - bx1 - padding_x * 2,
                                       fill=txt_fill)
                    
                    # ── 꼬리(tail) 그리기 — 8방향 지원 (clip-path 모양은 꼬리 생략) ──
                    tail_dir = bubble.tail or bubble.tail_direction or 'none'
                    if tail_dir != 'none' and shape not in _CLIP_PATH_SHAPES:
                        tail_size = max(8, int(min(bw, bh) * 0.12))
                        cx = (bx1 + bx2) // 2  # 말풍선 중앙 X
                        cy = (by1 + by2) // 2  # 말풍선 중앙 Y
                        off = int(bw * 0.2)
                        
                        tp = None
                        if tail_dir == 'bottom-left':
                            tp = [(bx1 + off, by2), (bx1 + off + tail_size, by2), (bx1 + off, by2 + tail_size)]
                        elif tail_dir == 'bottom-center':
                            tp = [(cx - tail_size//2, by2), (cx + tail_size//2, by2), (cx, by2 + tail_size)]
                        elif tail_dir == 'bottom-right':
                            tp = [(bx2 - off - tail_size, by2), (bx2 - off, by2), (bx2 - off, by2 + tail_size)]
                        elif tail_dir == 'top-left':
                            tp = [(bx1 + off, by1 - tail_size), (bx1 + off, by1), (bx1 + off + tail_size, by1)]
                        elif tail_dir == 'top-center':
                            tp = [(cx - tail_size//2, by1), (cx + tail_size//2, by1), (cx, by1 - tail_size)]
                        elif tail_dir == 'top-right':
                            tp = [(bx2 - off - tail_size, by1), (bx2 - off, by1), (bx2 - off, by1 - tail_size)]
                        elif tail_dir == 'left':
                            tp = [(bx1 - tail_size, cy), (bx1, cy - tail_size//2), (bx1, cy + tail_size//2)]
                        elif tail_dir == 'right':
                            tp = [(bx2 + tail_size, cy), (bx2, cy - tail_size//2), (bx2, cy + tail_size//2)]
                        
                        if tp:
                            draw.polygon(tp, fill=fill_color)
                            if border_outline:
                                draw.line([tp[0], tp[1]], fill=border_outline, width=max(1, border_w))
                                draw.line([tp[0], tp[2]], fill=border_outline, width=max(1, border_w))
            
            img = Image.alpha_composite(img, overlay)
        
        # 별도 파일로 저장 (원본 보존!)
        export_path = os.path.join(export_dir, f"scene_{scene_num}_final.png")
        img.convert("RGB").save(export_path, "PNG")
        
        exported.append({
            "scene_number": scene_num,
            "export_path": export_path,
            "original_path": img_path  # 원본은 그대로
        })
    
    # final_images 업데이트
    session.final_images = [e["export_path"] for e in exported]
    
    return {
        "success": True,
        "exported_count": len(exported),
        "images": exported
    }


# ── html2canvas 캡처 이미지 업로드 (프론트엔드 캡처 방식) ──

@router.post("/bubble-layers/{session_id}/upload-export")
async def upload_export_image(session_id: str, image: UploadFile = File(...), scene_number: int = Form(...)):
    """프론트엔드 html2canvas에서 캡처한 최종 이미지 업로드"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    export_dir = os.path.join("output", "export")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, f"scene_{scene_number}_final.png")
    
    content = await image.read()
    with open(export_path, "wb") as f:
        f.write(content)
    
    return {"success": True, "export_path": export_path, "scene_number": scene_number}


class FinalizeExportRequest(BaseModel):
    export_paths: List[str]

@router.post("/bubble-layers/{session_id}/finalize-export")
async def finalize_export(session_id: str, request: FinalizeExportRequest):
    """내보내기 완료 후 final_images 목록 갱신"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    session.final_images = request.export_paths
    return {"success": True, "count": len(request.export_paths)}


# ============================================
# 시리즈 분할 설정 API
# ============================================

class SeriesConfigRequest(BaseModel):
    session_id: str
    total_series: int = 1
    scenes_per_series: List[int] = []  # 예: [5, 5, 5]

@router.post("/session/{session_id}/series-config")
async def save_series_config(session_id: str, request: SeriesConfigRequest):
    """시리즈 분할 설정 저장"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    if not session.story:
        raise HTTPException(status_code=400, detail="스토리가 아직 생성되지 않았습니다")
    
    total_scenes = len(session.story.scenes)
    
    # 유효성 검증
    if request.total_series < 1:
        raise HTTPException(status_code=400, detail="시리즈 수는 1 이상이어야 합니다")
    
    if request.total_series == 1:
        # 분할 안 함
        session.story.total_series = 1
        session.story.scenes_per_series = [total_scenes]
        session.story.series_info = SeriesInfo(
            total=1,
            episodes=[SeriesEpisode(
                episode_number=1,
                scene_count=total_scenes,
                scene_start=0,
                scene_end=total_scenes
            )]
        )
    else:
        # 분할
        if len(request.scenes_per_series) != request.total_series:
            raise HTTPException(
                status_code=400, 
                detail=f"시리즈 수({request.total_series})와 편별 씬 수 배열 길이({len(request.scenes_per_series)})가 일치하지 않습니다"
            )
        
        scene_sum = sum(request.scenes_per_series)
        if scene_sum != total_scenes:
            raise HTTPException(
                status_code=400, 
                detail=f"편별 씬 수 합계({scene_sum})가 전체 씬 수({total_scenes})와 일치하지 않습니다"
            )
        
        # 에피소드 목록 생성
        episodes = []
        offset = 0
        for i, count in enumerate(request.scenes_per_series):
            episodes.append(SeriesEpisode(
                episode_number=i + 1,
                scene_count=count,
                scene_start=offset,
                scene_end=offset + count
            ))
            offset += count
        
        session.story.total_series = request.total_series
        session.story.scenes_per_series = request.scenes_per_series
        session.story.series_info = SeriesInfo(
            total=request.total_series,
            episodes=episodes
        )
    
    logger.info(f"시리즈 설정 저장: {request.total_series}편, 씬 배분={session.story.scenes_per_series}")
    
    return {
        "success": True,
        "total_series": session.story.total_series,
        "scenes_per_series": session.story.scenes_per_series,
        "episodes": [ep.model_dump() for ep in session.story.series_info.episodes]
    }


@router.get("/session/{session_id}/series-config")
async def get_series_config(session_id: str):
    """시리즈 분할 설정 조회"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    if not session.story:
        return {"total_series": 1, "scenes_per_series": [], "episodes": [], "total_scenes": 0}
    
    total_scenes = len(session.story.scenes)
    series_info = session.story.series_info
    
    return {
        "total_series": session.story.total_series,
        "scenes_per_series": session.story.scenes_per_series,
        "episodes": [ep.model_dump() for ep in series_info.episodes] if series_info else [],
        "total_scenes": total_scenes
    }


# ============================================
# 10. 프로젝트 저장/불러오기 API
# ============================================

import shutil

class ProjectSaveRequest(BaseModel):
    session_id: str
    project_name: str
    caption: Optional[dict] = None  # 프론트에서 편집한 캡션 직접 전달


@router.post("/project/save")
async def save_project(request: ProjectSaveRequest):
    """현재 세션을 프로젝트로 저장 (스토리+이미지+시리즈+말풍선 전부)"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    # 프로젝트 디렉토리 생성
    safe_name = "".join(c for c in request.project_name if c.isalnum() or c in (' ', '_', '-')).strip() or 'project'
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join("output", "projects", f"{safe_name}_{timestamp}")
    os.makedirs(project_dir, exist_ok=True)
    images_dir = os.path.join(project_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 이미지 파일 복사 (현재 이미지 + 히스토리 이미지)
    image_files = []
    if session.images:
        for img in session.images:
            src = img.local_path if hasattr(img, 'local_path') else (img.get('local_path') if isinstance(img, dict) else None)
            if src and os.path.exists(src):
                fname = os.path.basename(src)
                dst = os.path.join(images_dir, fname)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                image_files.append(fname)
            # 히스토리 이미지도 복사
            hist_list = img.image_history if hasattr(img, 'image_history') else []
            for hist_path in hist_list:
                if hist_path and os.path.exists(hist_path):
                    hfname = os.path.basename(hist_path)
                    hdst = os.path.join(images_dir, hfname)
                    if not os.path.exists(hdst):
                        shutil.copy2(hist_path, hdst)

    # 프론트에서 캡션 직접 전달 시 세션 갱신
    if request.caption:
        try:
            session.caption = InstagramCaption(**request.caption)
        except Exception as e:
            logger.warning(f"[프로젝트] 프론트 캡션 반영 실패: {e}")

    # 메타데이터 구성
    project_data = {
        "project_name": request.project_name,
        "session_id": request.session_id,
        "saved_at": datetime.now().isoformat(),
        "keyword": session.keyword if hasattr(session, 'keyword') else "",
        "story": session.story.model_dump() if session.story else None,
        "characters": [c.model_dump() if hasattr(c, 'model_dump') else c for c in (session.story.characters if session.story else [])],
        "series_config": session.story.series_info.model_dump() if (session.story and session.story.series_info) else None,
        "bubble_layers": [bl.model_dump() if hasattr(bl, 'model_dump') else bl for bl in (session.bubble_layers or [])],
        "images": [img.model_dump() if hasattr(img, 'model_dump') else img for img in (session.images or [])],
        "image_files": image_files,
        "preset_name": getattr(session, 'preset_name', None),
        "collected_data": session.collected_data if hasattr(session, 'collected_data') else None,
        "caption": session.caption.model_dump() if session.caption else None,
        "final_images": session.final_images if hasattr(session, 'final_images') else [],
        "state": session.state.value if session.state else "idle",
        "last_tab": getattr(session, 'last_tab', None),
    }

    project_path = os.path.join(project_dir, "project.json")
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, ensure_ascii=False, indent=2)

    logger.info(f"[프로젝트] 저장 완료: {project_dir} (이미지 {len(image_files)}개)")

    return {
        "success": True,
        "project_dir": project_dir,
        "project_name": request.project_name,
        "image_count": len(image_files),
        "saved_at": project_data["saved_at"]
    }


@router.get("/project/list")
async def list_projects():
    """저장된 프로젝트 목록 조회"""
    try:
        projects_dir = os.path.join("output", "projects")
        if not os.path.exists(projects_dir):
            return {"projects": []}

        projects = []
        for dirname in sorted(os.listdir(projects_dir), reverse=True):
            project_json = os.path.join(projects_dir, dirname, "project.json")
            if os.path.exists(project_json):
                try:
                    with open(project_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    scene_count = len(data.get("story", {}).get("scenes", [])) if data.get("story") else 0
                    series_count = data.get("story", {}).get("total_series", 1) if data.get("story") else 1
                    projects.append({
                        "dirname": dirname,
                        "project_name": data.get("project_name", dirname),
                        "saved_at": data.get("saved_at", ""),
                        "scene_count": scene_count,
                        "series_count": series_count,
                        "image_count": len(data.get("image_files", [])),
                        "state": data.get("state", ""),
                    })
                except Exception as e:
                    logger.warning(f"[프로젝트] 메타 파싱 실패 ({dirname}): {e}")

        # saved_at 기준 최신순 정렬 (datetime 파싱으로 확실한 시간순 보장)
        def _sort_key(p):
            s = p.get("saved_at")
            if not s:
                return datetime.min
            try:
                return datetime.fromisoformat(s)
            except (ValueError, TypeError):
                return datetime.min
        projects.sort(key=_sort_key, reverse=True)

        return {"projects": projects}
    except Exception as e:
        logger.error(f"[list_projects] 디렉토리 읽기 실패: {e}")
        raise HTTPException(status_code=500, detail=f"프로젝트 목록 조회 실패: {str(e)}")


@router.post("/project/load")
async def load_project(request: dict):
    """프로젝트 불러오기 - 세션 복원"""
    dirname = request.get("dirname")
    if not dirname:
        raise HTTPException(status_code=400, detail="dirname이 필요합니다")

    project_json = os.path.join("output", "projects", dirname, "project.json")
    if not os.path.exists(project_json):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    with open(project_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 새 세션 생성 또는 기존 세션 재사용
    sid = data.get("session_id", str(uuid.uuid4()))
    session = WorkflowSession(session_id=sid)
    session.keyword = data.get("keyword", "")

    # 스토리 복원
    if data.get("story"):
        session.story = Story(**data["story"])

    # 이미지 복원 (경로를 프로젝트 디렉토리 기준으로 업데이트)
    project_images_dir = os.path.join("output", "projects", dirname, "images")
    if data.get("images"):
        session.images = []
        for img_data in data["images"]:
            try:
                if isinstance(img_data, dict):
                    # local_path를 프로젝트 images 폴더 기준으로 업데이트
                    if img_data.get("local_path"):
                        fname = os.path.basename(img_data["local_path"])
                        proj_img = os.path.join(project_images_dir, fname)
                        if os.path.exists(proj_img):
                            img_data["local_path"] = proj_img
                    # original_path도 동일하게 처리
                    if img_data.get("original_path"):
                        orig_fname = os.path.basename(img_data["original_path"])
                        orig_proj = os.path.join(project_images_dir, orig_fname)
                        if os.path.exists(orig_proj):
                            img_data["original_path"] = orig_proj
                    # image_history 경로도 업데이트
                    if img_data.get("image_history"):
                        updated_hist = []
                        for hp in img_data["image_history"]:
                            hfname = os.path.basename(hp)
                            hproj = os.path.join(project_images_dir, hfname)
                            updated_hist.append(hproj if os.path.exists(hproj) else hp)
                        img_data["image_history"] = updated_hist
                    session.images.append(GeneratedImage(**img_data))
                else:
                    session.images.append(img_data)
            except Exception:
                session.images.append(img_data)

    # 말풍선 복원
    if data.get("bubble_layers"):
        session.bubble_layers = []
        for bl_data in data["bubble_layers"]:
            try:
                session.bubble_layers.append(BubbleLayer(**bl_data) if isinstance(bl_data, dict) else bl_data)
            except Exception:
                session.bubble_layers.append(bl_data)

    # 수집 데이터 복원
    if data.get("collected_data"):
        session.collected_data = data["collected_data"]

    # 캡션 복원
    if data.get("caption"):
        try:
            session.caption = InstagramCaption(**data["caption"])
        except Exception as e:
            logger.warning(f"[프로젝트] 캡션 복원 실패: {e}")

    # final_images 복원
    if data.get("final_images"):
        session.final_images = data["final_images"]

    # 세션 등록
    sessions[sid] = session
    logger.info(f"[프로젝트] 불러오기 완료: {dirname} → 세션 {sid}")

    return {
        "success": True,
        "session_id": sid,
        "project_name": data.get("project_name", ""),
        "story": session.story.model_dump() if session.story else None,
        "images": [img.model_dump() if hasattr(img, 'model_dump') else img for img in (session.images or [])],
        "bubble_layers": [bl.model_dump() if hasattr(bl, 'model_dump') else bl for bl in (session.bubble_layers or [])],
        "series_config": data.get("series_config"),
        "caption": session.caption.model_dump() if session.caption else None,
        "collected_data": session.collected_data if session.collected_data else None,
        "state": data.get("state", "idle"),
    }


@router.delete("/project/delete/{dirname}")
async def delete_project(dirname: str):
    """프로젝트 삭제"""
    project_dir = os.path.join("output", "projects", dirname)
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    try:
        shutil.rmtree(project_dir)
        logger.info(f"[프로젝트] 삭제: {dirname}")
        return {"success": True, "deleted": dirname}
    except Exception as e:
        logger.error(f"[delete_project] 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail=f"프로젝트 삭제 실패: {str(e)}")
