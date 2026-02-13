"""
워크플로우 API 라우터
세무 웹툰 생성 전체 흐름 관리
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.models.models import (
    WorkflowSession, WorkflowState, WorkflowMode,
    Story, Scene, InstagramCaption, ProjectSettings,
    CharacterSettings, ImageStyle, SubStyle, SpecializedField,
    ManualPromptOverrides, ThumbnailData, ThumbnailSource, ThumbnailPosition,
    SeriesInfo, ToBeContinuedStyle, GeneratedImage,
    BubbleLayer, BubbleOverlay, BubblePosition, BubbleShape, CHARACTER_COLORS
)
from app.services.gemini_service import get_gemini_service
from app.services.openai_service import get_openai_service
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


def _resolve_api_key(model_name: str) -> str:
    """모델명에 따라 적절한 API 키를 반환하는 헬퍼"""
    if "flux" in model_name:
        return os.getenv("FAL_KEY", "")
    elif "gpt" in model_name or "dall-e" in model_name:
        return os.getenv("OPENAI_API_KEY", "")
    else:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")


async def _translate_scenes_to_english(scenes):
    """Flux 모델용: 모든 씬의 한국어 설명을 영어로 일괄 번역.
    
    SmartTranslator를 사용하여 캐시/사전/AI 3단계로 번역.
    캐시 누적으로 같은 표현은 다시 AI를 호출하지 않음.
    """
    import re

    # 한국어 포함 씬만 수집
    korean_scenes = []
    for s in scenes:
        if re.search(r'[\uac00-\ud7af]', s.scene_description or ''):
            korean_scenes.append(s)
    
    if not korean_scenes:
        return  # 이미 전부 영어

    try:
        from app.services.smart_translator import translate_prompts_batch
        
        texts = [s.scene_description for s in korean_scenes]
        translated = translate_prompts_batch(texts)
        
        for s, t in zip(korean_scenes, translated):
            if t and len(t) > 5:
                s.scene_description = t
        
        logger.info(f"[번역] {len(korean_scenes)}개 씬 설명 한→영 번역 완료 (SmartTranslator)")

    except Exception as e:
        logger.warning(f"[번역] 씬 일괄 번역 실패 (개별 번역으로 폴백): {e}")


# ============================================
# Request/Response 모델
# ============================================

class StartWorkflowRequest(BaseModel):
    mode: str = "auto"  # auto | manual
    keyword: Optional[str] = None
    model: str = "gemini-3.0-flash"


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
    model: str = "gemini-2.0-flash"
    character_names: str = ""  # 쉼표 구분 등장인물 이름 (빈 문자열이면 AI 자동 생성)


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


@router.post("/generate-story")
async def generate_story(request: GenerateStoryRequest):
    """스토리 생성"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.keyword:
         raise HTTPException(status_code=400, detail="Keyword is required")
         
    session.state = WorkflowState.GENERATING_STORY
    
    gemini = get_gemini_service()
    
    field_info = session.field_info or await gemini.detect_field(session.keyword)
    
    # 세션에 저장된 수집 데이터 가져오기 ( Step 2에서 수집함)
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
    
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[generate_story] 스토리 생성 시작 - keyword: {session.keyword}, scene_count: {request.scene_count}, model: {request.model}")
        
        story = await gemini.generate_story(
            keyword=session.keyword,
            field_info=field_info,
            collected_data=collected_data,
            scene_count=request.scene_count,
            character_settings=character_settings,
            rule_settings=rule_settings,
            model=request.model,
            character_names=request.character_names
        )
        
        if not story:
            raise ValueError("스토리 생성 결과가 없습니다")
        
        logger.info(f"[generate_story] 스토리 생성 완료 - 씬 수: {len(story.scenes) if story.scenes else 0}")
        
        session.story = story
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
        import logging
        import traceback
        logger = logging.getLogger(__name__)
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


class RegenerateImagePromptRequest(BaseModel):
    session_id: str
    scene_number: int
    model: str = "gemini-2.0-flash"


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

        import google.generativeai as genai
        api_key = gemini.api_key
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(request.model)
        response = model.generate_content(regen_prompt)
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
    
    for scene in session.story.scenes:
        scene.status = "approved"
    
    session.state = WorkflowState.GENERATING_IMAGES
    
    return {"success": True, "state": session.state.value}


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
        
        # ★ Flux 모델 선택 시 프롬프트 최적화 적용
        is_flux = "flux" in (request.model or "").lower()
        if is_flux:
            from app.services.prompt_builder import optimize_for_flux_kontext
            # image_prompt가 있으면 우선 사용 (시각 묘사 전용)
            _scene_desc_for_flux = target_scene.image_prompt or target_scene.scene_description
            prompt = optimize_for_flux_kontext(
                prompt,
                scene_description=_scene_desc_for_flux,
                is_reference=False,
                characters=characters
            )
            logger.info(f"[PREVIEW] Flux 최적화 적용됨 → {len(prompt)}자")
        
        api_key = _resolve_api_key(request.model)
        generator = get_generator(request.model, api_key)

        print(f"[PREVIEW] model={request.model}, prompt_len={len(prompt)}자, api_key={'SET' if api_key else 'MISSING'}")
        logger.info(f"미리보기 생성 시작 (model={request.model}, prompt_len={len(prompt)}자)")
        
        seed = None
        if is_flux:
            import random
            seed = random.randint(1, 2**31 - 1)
        
        image_data = await asyncio.wait_for(
            generator.generate(prompt, size="1024x1024", quality="standard", seed=seed),
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


@router.post("/generate-images")
async def generate_images(request: GenerateImagesRequest):
    """이미지 일괄 생성 (Style System 2.0)"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    session.state = WorkflowState.GENERATING_IMAGES
    
    # Settings storage
    session.settings.image.model = request.model
    session.settings.image.character_style_id = request.character_style_id
    session.settings.image.background_style_id = request.background_style_id
    session.settings.image.sub_style = request.sub_style
    if request.manual_overrides:
        session.settings.image.manual_overrides = ManualPromptOverrides(**request.manual_overrides)

    import asyncio
    import random
        
    # Load styles
    char_style = get_character_style(request.character_style_id) if request.character_style_id else None
    bg_style = get_background_style(request.background_style_id) if request.background_style_id else None
    overrides = session.settings.image.manual_overrides
    sub_style = request.sub_style

    # Select generator — 모델별 API 키 자동 선택
    api_key = _resolve_api_key(request.model)
    generator = get_generator(request.model, api_key)
    
    # Flux Kontext 여부 판별 (참조 이미지 기반 일관성)
    is_flux_kontext = "flux-kontext" in request.model
    
    generated_images = []
    
    # Flux 모델: 세션당 기본 seed 생성 (캐릭터 일관성 + 씬별 변형)
    is_flux = "flux" in request.model
    if is_flux:
        # 기존 세션에 seed가 있으면 재사용, 없으면 새로 생성
        if session.settings.image.flux_seed:
            base_seed = session.settings.image.flux_seed
            logger.info(f"[Flux] 기존 세션 base_seed 재사용: {base_seed}")
        else:
            base_seed = random.randint(1, 2**31 - 100000)  # 씬 오프셋 여유
            session.settings.image.flux_seed = base_seed
            logger.info(f"[Flux] 새 세션 base_seed 생성: {base_seed}")
    else:
        base_seed = None
    
    # Flux 모델이면 씬 설명을 미리 영어로 번역 (한 번만)
    if is_flux and session.story and session.story.scenes:
        await _translate_scenes_to_english(session.story.scenes)
    
    # ★★★ 씬 설명 전처리: 숫자/인포그래픽 → 시각적 비유 변환 ★★★
    # "1.5억 증여" 같은 텍스트를 AI가 깨진 글자로 그리지 않도록
    # Gemini로 시각적 비유로 변환한다.
    if session.story and session.story.scenes:
        try:
            from app.services.scene_preprocessor import preprocess_scenes_for_image_gen
            session.story.scenes = await preprocess_scenes_for_image_gen(
                session.story.scenes
            )
            logger.info("[전처리] 씬 설명 전처리 완료 (숫자/인포그래픽 → 시각적 비유)")
        except Exception as pp_err:
            logger.warning(f"[전처리] 씬 설명 전처리 실패, 원본 유지: {pp_err}")

    # ★★★ 3종 레퍼런스 이미지 로드 + CRS 폴백 ★★★
    # 1. 사용자가 설정한 Character/Method/Style 레퍼런스를 로드
    # 2. Character.jpg가 없으면 기존 CRS 자동 생성으로 폴백
    from app.services.reference_service import ReferenceService
    from app.services.prompt_builder import build_scene_chaining_context
    
    ref_service = ReferenceService(request.session_id)
    ref_data = ref_service.load_for_model(request.model) if request.use_reference_images else {}
    
    character_ref_bytes = ref_data.get("character")  # Character.jpg
    method_ref_bytes = ref_data.get("method")        # Method.jpg
    style_ref_bytes = ref_data.get("style")          # Style.jpg
    
    # Gemini 모델 판별
    model_lower = request.model.lower() if request.model else ""
    is_gemini = any(k in model_lower for k in ["gemini", "nano-banana"])
    
    # Character.jpg 없으면 기존 CRS 자동 생성 (Flux 계열만)
    if not character_ref_bytes and (is_flux or is_flux_kontext):
        try:
            from app.services.prompt_builder import build_character_reference_prompt
            
            ref_prompt = build_character_reference_prompt(
                characters=session.story.characters,
                character_style=char_style,
                sub_style_name=sub_style
            )
            
            ref_seed = base_seed if base_seed else None
            size = "1024x1536" if request.aspect_ratio in ("4:5", "9:16") else "1024x1024"
            
            logger.info("[레퍼런스] Character.jpg 없음 → CRS 자동 생성으로 폴백...")
            character_ref_bytes = await generator.generate(
                ref_prompt, reference_images=None, size=size, seed=ref_seed
            )
            
            if isinstance(character_ref_bytes, bytes):
                ref_path = os.path.join("output", f"character_ref_{session.session_id[:8]}.png")
                os.makedirs("output", exist_ok=True)
                with open(ref_path, "wb") as f:
                    f.write(character_ref_bytes)
                logger.info(f"[레퍼런스] CRS 자동 생성 저장: {ref_path}")
            else:
                character_ref_bytes = None
                logger.warning("[레퍼런스] CRS 자동 생성 실패 — text2img 폴백")
                
        except Exception as ref_err:
            logger.warning(f"[레퍼런스] CRS 자동 생성 실패, text2img 폴백: {ref_err}")
            character_ref_bytes = None

    # 레퍼런스 상태 로그
    ref_status = []
    if character_ref_bytes: ref_status.append("Character")
    if method_ref_bytes: ref_status.append("Method")
    if style_ref_bytes: ref_status.append("Style")
    logger.info(f"[레퍼런스] 사용 가능: {', '.join(ref_status) if ref_status else '없음'} (모델: {request.model})")

    async def generate_single_scene(scene, scene_seed=None, ref_image_bytes=None,
                                     method_bytes=None, style_bytes=None,
                                     prev_scene_image=None, prev_scene_summaries=None):
        """단일 씬 이미지 생성 — 3종 레퍼런스 + 씬 체이닝 지원
        
        모델별 레퍼런스 사용:
        - Gemini: 3종 레퍼런스 + 이전 씬 → contents에 모두 전달
        - Flux Kontext: Character.jpg → img2img CRS
        - DALL-E: 프롬프트만 (이미지 참조 불가)
        """
        try:
            from app.services.prompt_builder import optimize_for_flux_kontext
            
            prompt = build_styled_prompt(
                scene=scene,
                characters=session.story.characters,
                character_style=char_style,
                background_style=bg_style,
                manual_overrides=overrides,
                sub_style_name=sub_style
            )
            
            size = "1024x1536" if request.aspect_ratio in ("4:5", "9:16") else "1024x1024"
            
            # ★ 모델별 분기
            if is_gemini:
                # Gemini: 3종 레퍼런스 + 이전 씬 체이닝을 모두 활용
                # 일관성 체이닝: prev_scene_number 전달하여 라벨에 장면 번호 포함
                _prev_sn = scene.scene_number - 1 if prev_scene_image else None
                image_data = await generator.generate(
                    prompt,
                    reference_images=[ref_image_bytes] if ref_image_bytes else None,
                    size=size,
                    seed=scene_seed,
                    method_image=method_bytes,
                    style_image=style_bytes,
                    prev_scene_image=prev_scene_image,
                    prev_scene_summaries=prev_scene_summaries,
                    prev_scene_number=_prev_sn
                )
                ref_count = sum(1 for x in [ref_image_bytes, method_bytes, style_bytes] if x)
                logger.info(f"[Gemini] 씬 {scene.scene_number}: {ref_count}종 레퍼런스"
                            f"{' + 씬체이닝' if prev_scene_image else ''}")
            
            elif is_flux_kontext or is_flux:
                # Flux: 프롬프트 최적화 + Character CRS img2img
                # image_prompt가 있으면 우선 사용 (시각 묘사 전용)
                _scene_desc_flux = getattr(scene, 'image_prompt', None) or scene.scene_description
                prompt = optimize_for_flux_kontext(
                    prompt,
                    scene_description=_scene_desc_flux,
                    is_reference=(ref_image_bytes is not None),
                    characters=session.story.characters
                )
                
                if ref_image_bytes:
                    image_data = await generator.generate(
                        prompt,
                        reference_images=[ref_image_bytes],
                        size=size,
                        seed=scene_seed
                    )
                    logger.info(f"[Flux] 씬 {scene.scene_number}: img2img (Character 참조)")
                else:
                    image_data = await generator.generate(
                        prompt, reference_images=None, size=size, seed=scene_seed
                    )
                    logger.info(f"[Flux] 씬 {scene.scene_number}: text2img (독립 생성)")
            
            else:
                # DALL-E 등: 프롬프트만 사용
                image_data = await generator.generate(
                    prompt, reference_images=None, size=size, seed=scene_seed
                )
                logger.info(f"[기타] 씬 {scene.scene_number}: text2img")
            
            # 파일 저장
            filename = f"scene_{scene.scene_number}_{uuid.uuid4().hex[:6]}.png"
            filepath = os.path.join("output", filename)
            os.makedirs("output", exist_ok=True)
            
            if isinstance(image_data, bytes):
                with open(filepath, "wb") as f:
                    f.write(image_data)
                
                # Pillow 후처리: 상단 여백 확보
                try:
                    from app.services.pillow_service import get_pillow_service
                    from PIL import Image
                    from io import BytesIO
                    pillow = get_pillow_service()
                    img = Image.open(filepath)
                    img = pillow.ensure_top_margin(img, margin_ratio=0.25)
                    img.save(filepath, "PNG")
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    image_data = buf.getvalue()
                except Exception as margin_err:
                    logger.warning(f"여백 후처리 실패 (씬 {scene.scene_number}): {margin_err}")
            
            return {
                "scene_number": scene.scene_number,
                "prompt_used": prompt,
                "local_path": filepath,
                "status": "generated",
                "image_bytes": image_data if isinstance(image_data, bytes) else b""
            }
        except Exception as e:
            logger.error(f"Error generating scene {scene.scene_number}: {e}")
            return {
                "scene_number": scene.scene_number,
                "prompt_used": "Error",
                "status": "error",
                "error": str(e)
            }

    # ★★★ 레퍼런스 + 씬 체이닝 통합 생성 루프 ★★★
    #
    # [모델별 전략]
    #   Gemini: 3종 레퍼런스 + 이전 씬 이미지/요약 → 최고 일관성
    #   Flux Kontext: Character CRS → img2img → 캐릭터 일관성
    #   DALL-E: 프롬프트만 → 텍스트 기반 일관성
    #
    # [씬 체이닝]
    #   씬 2+부터 직전 씬 이미지 + 이전 씬 텍스트 요약 전달
    #   "현재 프롬프트 우선, 직전 씬은 캐릭터 외형 참고용"
    from app.models.models import GeneratedImage
    session.images = []
    stop_signals[request.session_id] = False
    
    # 생성된 씬 이미지 저장 (체이닝용)
    generated_scene_images = {}  # {scene_number: image_bytes}
    
    for scene in session.story.scenes:
        if stop_signals.get(request.session_id, False):
            logger.info(f"[STOP] 세션 {request.session_id} 이미지 생성 중단됨 "
                        f"({len(session.images)}/{len(session.story.scenes)} 완료)")
            break
        
        # 씬별 seed
        scene_seed = (base_seed + scene.scene_number * 1000) if base_seed else None
        
        # 씬 체이닝: 직전 씬 이미지 + 이전 씬 텍스트 요약
        prev_scene_image = None
        prev_scene_summaries = None
        
        if request.scene_chaining and scene.scene_number > 1:
            prev_summaries, prev_sn = build_scene_chaining_context(
                session.story.scenes, scene.scene_number
            )
            prev_scene_summaries = prev_summaries if prev_summaries else None
            
            # 직전 씬 이미지 로드
            if prev_sn and prev_sn in generated_scene_images:
                prev_scene_image = generated_scene_images[prev_sn]
        
        mode_parts = []
        if character_ref_bytes: mode_parts.append("Character")
        if method_ref_bytes: mode_parts.append("Method")
        if style_ref_bytes: mode_parts.append("Style")
        if prev_scene_image: mode_parts.append("체이닝")
        mode_str = f"레퍼런스({'+'.join(mode_parts)})" if mode_parts else "독립 생성"
        
        logger.info(f"[생성] 씬 {scene.scene_number}/{len(session.story.scenes)} — "
                     f"seed={scene_seed}, {mode_str}")
        
        res = await generate_single_scene(
            scene,
            scene_seed=scene_seed,
            ref_image_bytes=character_ref_bytes,
            method_bytes=method_ref_bytes if is_gemini else None,
            style_bytes=style_ref_bytes if is_gemini else None,
            prev_scene_image=prev_scene_image,
            prev_scene_summaries=prev_scene_summaries
        )
        
        # 체이닝용 이미지 저장
        if res.get("image_bytes"):
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
    
    # 중단 신호 정리
    stop_signals.pop(request.session_id, None)
    session.state = WorkflowState.REVIEWING_IMAGES
    
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "images": [img.model_dump() for img in session.images]
    }


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
    
    # 스토리 전체 요약 생성 (모든 씬 포함)
    story_summary = f"제목: {session.story.title}\n"
    story_summary += f"등장인물: {', '.join([c.name + '(' + c.role + ')' for c in session.story.characters])}\n"
    story_summary += "\n".join([
        f"씬{s.scene_number}: {s.scene_description}"
        for s in session.story.scenes  # ★ 전체 씬 사용 (기존: [:3])
    ])
    # 대사도 요약에 포함 (스토리 맥락 강화)
    dialogues_summary = []
    for s in session.story.scenes[:5]:
        for d in s.dialogues[:2]:
            dialogues_summary.append(f"  {d.character}: \"{d.line}\"")
    if dialogues_summary:
        story_summary += "\n주요 대사:\n" + "\n".join(dialogues_summary)
    
    field = session.field_info.field if session.field_info else SpecializedField.GENERAL
    
    caption = await gemini.generate_caption(
        keyword=session.keyword or session.story.title,
        field=field,
        story_summary=story_summary
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
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

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
        response = model.generate_content(prompt)
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
            "hashtags": "#세무 #절세 #정보",
        }


# ============================================
# 모델 테스트 API
# ============================================

class TestModelRequest(BaseModel):
    model: str = "gemini-2.0-flash"


@router.post("/test-model")
async def test_model(request: TestModelRequest):
    """특정 AI 모델의 동작 상태 확인"""
    import google.generativeai as genai
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[test-model] 테스트 시작: {request.model}")
    
    try:
        model = genai.GenerativeModel(request.model)
        response = await model.generate_content_async("Say 'Hello' in Korean")
        
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
    session_id: str
    keyword: str
    model: str = "gemini-2.0-flash"


@router.post("/collect-data")
async def collect_data(request: CollectDataRequest):
    """자료 수집"""
    import logging
    logger = logging.getLogger(__name__)
    
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    gemini = get_gemini_service()
    
    # AI를 사용해 상세 정보 수집
    try:
        logger.info(f"[collect_data] 모델: {request.model}, 키워드: {request.keyword}")
        
        # 사용자 선택 모델 전달
        field_info = session.field_info or await gemini.detect_field(request.keyword, request.model)
        logger.info(f"[collect_data] 분야 감지 완료: {field_info.field}")
        
        items = await gemini.collect_data(request.keyword, field_info, request.model)
        logger.info(f"[collect_data] 자료 수집 완료: {len(items)}개 항목")
        
        # 세션에 저장 (상세 내용 포함)
        session.collected_data = items
        
        return {
            "session_id": session.session_id,
            "items": items,
            "model_used": request.model
        }
    except Exception as e:
        logger.error(f"[collect_data] 오류 발생 - 모델: {request.model}, 에러: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"자료 수집 오류 ({request.model}): {str(e)}")


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
    model: str = "gemini-2.0-flash"


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
    model: str = "dall-e-3"


@router.post("/regenerate-image")
async def regenerate_image(request: RegenerateImageRequest):
    """이미지 재생성 — 메인 생성과 동일한 generator + prompt_builder 방식"""
    session = sessions.get(request.session_id)
    if not session or not session.story or not session.images:
        raise HTTPException(status_code=404, detail="Session, story, or images not found")
    
    if request.scene_index >= len(session.story.scenes):
        raise HTTPException(status_code=400, detail="Invalid scene index")
    
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
        size = "1024x1536"  # 웹툰 기본 세로
        
        # Flux Kontext 프롬프트 최적화
        is_flux_kontext = "flux-kontext" in model_name
        is_flux_regen = "flux" in model_name
        ref_images = None
        
        if is_flux_kontext:
            # ★ 재생성: 현재 씬의 기존 이미지를 참조로 전달 (캐릭터 외모 유지)
            if session.images and request.scene_index < len(session.images):
                current_img = session.images[request.scene_index]
                if current_img.local_path and os.path.exists(current_img.local_path):
                    with open(current_img.local_path, "rb") as rf:
                        ref_images = [rf.read()]
                    logger.info(f"[재생성] 씬 {scene.scene_number}: 기존 이미지를 참조로 사용 (캐릭터 외모 유지)")
            
            from app.services.prompt_builder import optimize_for_flux_kontext
            _regen_desc = getattr(scene, 'image_prompt', None) or scene.scene_description
            prompt = optimize_for_flux_kontext(
                prompt,
                scene_description=_regen_desc,
                is_reference=bool(ref_images),
                characters=session.story.characters
            )
        elif is_flux_regen:
            # flux-dev 등 일반 Flux: text2img 최적화
            from app.services.prompt_builder import optimize_for_flux_kontext
            _regen_desc2 = getattr(scene, 'image_prompt', None) or scene.scene_description
            prompt = optimize_for_flux_kontext(
                prompt,
                scene_description=_regen_desc2,
                is_reference=False,
                characters=session.story.characters
            )
        
        # ★ 재생성 시 씬별 seed 사용 (최초 생성과 동일 seed → 유사한 결과)
        base_seed = session.settings.image.flux_seed if is_flux_regen else None
        regen_seed = (base_seed + scene.scene_number * 1000) if base_seed else None
        image_data = await generator.generate(prompt, reference_images=ref_images, size=size, seed=regen_seed)
        
        # 파일 저장
        filename = f"scene_{scene.scene_number}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join("output", filename)
        os.makedirs("output", exist_ok=True)
        
        if isinstance(image_data, bytes):
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            # Pillow 후처리: 상단 25% 여백 강제 확보
            try:
                from app.services.pillow_service import get_pillow_service
                from PIL import Image as PILImage
                pillow = get_pillow_service()
                regen_img = PILImage.open(filepath)
                regen_img = pillow.ensure_top_margin(regen_img, margin_ratio=0.25)
                regen_img.save(filepath, "PNG")
            except Exception as margin_err:
                logger.warning(f"여백 후처리 실패 (재생성 씬 {scene.scene_number}): {margin_err}")
        
        new_img = GeneratedImage(
            scene_number=scene.scene_number,
            prompt_used=prompt,
            local_path=filepath,
            status="generated"
        )
        session.images[request.scene_index] = new_img
        return {"image": new_img.model_dump()}
    except Exception as e:
        print(f"[REGEN ERROR] scene {scene.scene_number}: {e}")
        raise HTTPException(status_code=500, detail=f"재생성 실패: {str(e)}")


# ============================================
# 발행 API
# ============================================

class PublishRequest(BaseModel):
    session_id: str
    caption: str
    images: List[str]


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
    """Instagram 발행. 로컬 이미지는 Cloudinary 있으면 자동 업로드 후 발행."""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        from app.services.instagram_service import get_instagram_service
        from app.services.cloudinary_service import get_cloudinary_service
        from app.models.models import PublishData
        
        image_urls = []
        cloudinary = get_cloudinary_service()
        
        # 1) 세션 이미지가 있으면 우선 사용 (로컬이면 Cloudinary 업로드)
        if session.images:
            for img in session.images:
                if getattr(img, "image_url", None) and str(img.image_url).startswith("http"):
                    image_urls.append(img.image_url)
                elif getattr(img, "local_path", None):
                    path = img.local_path
                    if cloudinary.cloud_name and path:
                        url = await cloudinary.upload_from_path(path)
                        if url:
                            image_urls.append(url)
                    else:
                        return {"success": False, "error": "로컬 이미지는 Cloudinary 설정이 필요합니다. .env에 CLOUDINARY_* 를 넣어주세요."}
                else:
                    return {"success": False, "error": "이미지에 공개 URL 또는 로컬 경로가 없습니다."}
        # 2) request.images 가 있으면 사용 (http 아니면 업로드 시도)
        if not image_urls and request.images:
            for raw in request.images:
                if raw.startswith("http"):
                    image_urls.append(raw)
                elif cloudinary.cloud_name:
                    url = await cloudinary.upload_from_path(raw)
                    if url:
                        image_urls.append(url)
                else:
                    return {"success": False, "error": "이미지는 공개 URL이어야 하거나, Cloudinary를 설정해주세요."}
        
        if not image_urls:
            return {"success": False, "error": "발행할 이미지가 없습니다."}
        
        instagram = get_instagram_service()
        publish_data = PublishData(images=image_urls, caption=request.caption)
        result = await instagram.publish_workflow(publish_data)
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "Unknown error")}
        session.state = WorkflowState.PUBLISHED
        return {"success": True, "post_id": result.get("media_id", "")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 9. 스토리 히스토리 API
# ============================================

@router.get("/history/stories")
async def list_story_history():
    """저장된 스토리 목록 조회 (최신순 5개)"""
    history_dir = "output/stories"
    if not os.path.exists(history_dir):
        return []
    
    files = glob.glob(os.path.join(history_dir, "*.json"))
    files.sort(key=os.path.getmtime, reverse=True)
    
    recent_files = files[:10]
    result = []
    
    for f in recent_files:
        try:
            filename = os.path.basename(f)
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                result.append({
                    "filename": filename,
                    "keyword": data.get("keyword", "Unknown"),
                    "timestamp": data.get("timestamp", ""),
                    "title": data.get("story", {}).get("title", "Untitled"),
                    "scene_count": len(data.get("story", {}).get("scenes", []))
                })
        except Exception as e:
            print(f"Error reading history file {f}: {e}")
            
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
            
        # 이미지 데이터 복원 (있다면)
        # 이전 저장 파일에는 이미지가 없을 수 있음 (UserRequest: "직전 내용으로 산출되게 해줘" implies loading state)
        
        return {
            "success": True,
            "session_id": session.session_id, # Return the (possibly new) session ID
            "story": session.story.model_dump(),
            "collected_data": session.collected_data
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
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "keyword": session.keyword,
        "story": session.story.model_dump(),
        "collected_data": session.collected_data,
        "character_settings": session.settings.character.model_dump()
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

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다")

        model_name = session.settings.image.model or "gpt-image-1"
        generator = get_generator(model_name, api_key)
        image_bytes = await generator.generate(cover_prompt, size="1024x1024", quality="medium")

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
    """시리즈 마지막 씬에 '다음편에 계속' 오버레이 적용"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if not session.story:
        raise HTTPException(status_code=400, detail="스토리가 없습니다")

    story = session.story

    # 시리즈 분할 안 됐거나 마지막 편이면 적용 불필요
    if not story.series_info:
        return {"success": False, "reason": "시리즈가 아닙니다"}
    if story.series_info.current >= story.series_info.total:
        return {"success": False, "reason": "마지막 편이므로 '다음편에 계속'이 불필요합니다"}
    if not request.enabled:
        story.to_be_continued_enabled = False
        return {"success": True, "enabled": False}

    # 마지막 씬 이미지에 오버레이 적용
    if not session.images:
        return {"success": False, "reason": "생성된 이미지가 없습니다"}

    last_img = session.images[-1]
    img_path = last_img.local_path
    if not img_path or not os.path.exists(img_path):
        return {"success": False, "reason": "마지막 씬 이미지를 찾을 수 없습니다"}

    from app.services.pillow_service import get_pillow_service
    from PIL import Image

    pillow = get_pillow_service()
    base_image = Image.open(img_path)
    result_image = pillow.add_to_be_continued(
        image=base_image,
        text=request.text,
        style=request.style
    )

    # 덮어쓰기 저장
    result_image.save(img_path, "PNG")

    story.to_be_continued_enabled = True
    story.to_be_continued_style = ToBeContinuedStyle(request.style)

    return {
        "success": True,
        "enabled": True,
        "style": request.style,
        "applied_to_scene": last_img.scene_number
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
            
            colors = char_color_map.get(dialogue.character, CHARACTER_COLORS[0])
            
            bubbles.append(BubbleOverlay(
                id=f"s{scene.scene_number}_d{j}",
                type="dialogue",
                character=dialogue.character,
                text=dialogue.text,
                position=pos,
                shape=BubbleShape.ROUND,
                tail_direction="bottom-left" if j % 2 == 0 else "bottom-right",
                bg_color=colors["bg"],
                text_color=colors["text"],
                border_color=colors["border"],
                font_size=15,
                visible=True
            ))
        
        # 나레이션 → BubbleOverlay
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
                font_size=13,
                visible=True,
                opacity=0.85
            ))
        
        layers.append(BubbleLayer(
            scene_number=scene.scene_number,
            bubbles=bubbles,
            show_all=True,
            font_family="Nanum Gothic"
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
                    
                    # ── 꼬리(tail) 그리기 ──
                    tail_dir = getattr(bubble, 'tail_direction', 'none') or 'none'
                    if tail_dir != 'none':
                        tail_size = max(8, int(min(bx2 - bx1, by2 - by1) * 0.12))
                        tail_offset = int((bx2 - bx1) * 0.2)
                        
                        if tail_dir == 'bottom-left':
                            tp = [(bx1 + tail_offset, by2), (bx1 + tail_offset + tail_size, by2), (bx1 + tail_offset, by2 + tail_size)]
                        elif tail_dir == 'bottom-right':
                            tp = [(bx2 - tail_offset - tail_size, by2), (bx2 - tail_offset, by2), (bx2 - tail_offset, by2 + tail_size)]
                        elif tail_dir == 'top-left':
                            tp = [(bx1 + tail_offset, by1 - tail_size), (bx1 + tail_offset, by1), (bx1 + tail_offset + tail_size, by1)]
                        elif tail_dir == 'top-right':
                            tp = [(bx2 - tail_offset, by1 - tail_size), (bx2 - tail_offset, by1), (bx2 - tail_offset - tail_size, by1)]
                        else:
                            tp = None
                        
                        if tp:
                            # 꼬리 배경
                            draw.polygon(tp, fill=fill_color)
                            # 꼬리 테두리
                            if border_outline:
                                draw.line([tp[0], tp[2]], fill=border_outline, width=max(1, border_w))
                                if tail_dir.startswith('bottom'):
                                    draw.line([tp[1], tp[2]], fill=border_outline, width=max(1, border_w))
                                else:
                                    draw.line([tp[0], tp[1]], fill=border_outline, width=max(1, border_w))
            
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
