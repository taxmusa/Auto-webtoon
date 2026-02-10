"""
워크플로우 API 라우터
세무 웹툰 생성 전체 흐름 관리
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.models.models import (
    WorkflowSession, WorkflowState, WorkflowMode,
    Story, Scene, InstagramCaption, ProjectSettings,
    CharacterSettings, ImageStyle, SubStyle, SpecializedField,
    ManualPromptOverrides
)
from app.services.gemini_service import get_gemini_service
from app.services.openai_service import get_openai_service
from app.services.image_generator import get_generator
from app.services.prompt_builder import build_styled_prompt
from app.api.styles import get_character_style, get_background_style
import os
import json
import glob
import glob
from datetime import datetime
import logging

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# 로거 설정
logger = logging.getLogger(__name__)

# 메모리 기반 세션 저장 (실제 서비스에서는 DB 사용)
sessions: dict[str, WorkflowSession] = {}


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


class UpdateSceneRequest(BaseModel):
    session_id: str
    scene_number: int
    scene_description: Optional[str] = None
    dialogues: Optional[List[dict]] = None
    narration: Optional[str] = None


class GenerateImagesRequest(BaseModel):
    session_id: str
    style: str = "webtoon"
    sub_style: str = "normal"
    aspect_ratio: str = "4:5"
    model: str = "gpt-image-1-mini"
    
    # Style System 2.0
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    manual_overrides: Optional[dict] = None


class GeneratePreviewRequest(BaseModel):
    session_id: str
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    manual_overrides: Optional[dict] = None # ManualPromptOverrides
    model: str = "gpt-image-1-mini"


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
        logger.info(f"[generate_story] 스토리 생성 시작 - keyword: {session.keyword}, scene_count: {request.scene_count}")
        
        story = await gemini.generate_story(
            keyword=session.keyword,
            field_info=field_info,
            collected_data=collected_data,
            scene_count=request.scene_count,
            character_settings=character_settings,
            rule_settings=rule_settings
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
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")

    # Load styles
    char_style = get_character_style(request.character_style_id) if request.character_style_id else None
    bg_style = get_background_style(request.background_style_id) if request.background_style_id else None
    
    # Manual overrides
    overrides = None
    if request.manual_overrides:
        overrides = ManualPromptOverrides(**request.manual_overrides)

    # Use first scene or placeholder
    target_scene = session.story.scenes[0] if session.story.scenes else Scene(scene_number=1, scene_description="A placeholder scene", dialogues=[])
    
    # Build Prompt
    prompt = build_styled_prompt(
        scene=target_scene,
        characters=session.story.characters,
        character_style=char_style,
        background_style=bg_style,
        manual_overrides=overrides
    )
    
    # Select generator
    api_key = os.getenv("OPENAI_API_KEY") if "gpt" in request.model or "dall-e" in request.model else os.getenv("GOOGLE_API_KEY")
    generator = get_generator(request.model, api_key)
    
    try:
        # Generate single image
        logger.info(f"Generating preview with model {request.model}")
        
        image_data = await generator.generate(prompt, size="1024x1024", quality="standard") # Standard/Low for preview
        
        # Save to temp
        import base64
        if isinstance(image_data, bytes):
            b64_img = base64.b64encode(image_data).decode('utf-8')
            return {"success": True, "image_b64": b64_img, "prompt_used": prompt}
        else:
             return {"success": True, "image_url": image_data, "prompt_used": prompt}
            
    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    if request.manual_overrides:
        session.settings.image.manual_overrides = ManualPromptOverrides(**request.manual_overrides)
        
    # Load styles
    char_style = get_character_style(request.character_style_id) if request.character_style_id else None
    bg_style = get_background_style(request.background_style_id) if request.background_style_id else None
    overrides = session.settings.image.manual_overrides

    # Select generator
    api_key = os.getenv("OPENAI_API_KEY") if "gpt" in request.model or "dall-e" in request.model else os.getenv("GOOGLE_API_KEY")
    generator = get_generator(request.model, api_key)
    
    generated_images = []
    import asyncio
    
    # Async batch generation (simplified loop for now, ideally parallel)
    # Using semaphore to limit concurrency if needed, but let's do sequential or chunks for stability first
    # or simple asyncio.gather
    
    async def generate_single_scene(scene):
        try:
            prompt = build_styled_prompt(
                scene=scene,
                characters=session.story.characters,
                character_style=char_style,
                background_style=bg_style,
                manual_overrides=overrides
            )
            
            # Using 1024x1792 for Webtoon (Vertical) if supported
            size = "1024x1792" if request.aspect_ratio == "4:5" or request.aspect_ratio == "9:16" else "1024x1024"
            # OpenAI supports 1024x1792. Gemini might vary.
            
            image_data = await generator.generate(prompt, size=size)
            
            # Save file
            filename = f"scene_{scene.scene_number}_{uuid.uuid4().hex[:6]}.png"
            filepath = os.path.join("output", filename)
            os.makedirs("output", exist_ok=True)
            
            import base64
            with open(filepath, "wb") as f:
                if isinstance(image_data, bytes):
                    f.write(image_data)
                else:
                    # If URL, need to download. For now assume bytes or b64
                    pass
            
            return {
                "scene_number": scene.scene_number,
                "prompt_used": prompt,
                "local_path": filepath,
                "status": "generated"
            }
        except Exception as e:
            print(f"Error generating scene {scene.scene_number}: {e}")
            return {
                "scene_number": scene.scene_number,
                "prompt_used": "Error",
                "status": "error",
                "error": str(e)
            }

    # Parallel execution
    tasks = [generate_single_scene(scene) for scene in session.story.scenes]
    results = await asyncio.gather(*tasks)
    
    # Map to GeneratedImage objects
    from app.models.models import GeneratedImage
    session.images = []
    for res in results:
        if res.get("local_path"):
            img = GeneratedImage(
                scene_number=res["scene_number"],
                prompt_used=res["prompt_used"],
                local_path=res["local_path"],
                status="generated"
            )
            session.images.append(img)
            
    session.state = WorkflowState.REVIEWING_IMAGES
    
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "images": [img.model_dump() for img in session.images]
    }


@router.post("/generate-caption")
async def generate_caption(request: GenerateCaptionRequest):
    """캡션 생성"""
    session = sessions.get(request.session_id)
    if not session or not session.story:
        raise HTTPException(status_code=404, detail="Session or story not found")
    
    session.state = WorkflowState.GENERATING_CAPTION
    
    gemini = get_gemini_service()
    
    # 스토리 요약 생성
    story_summary = f"제목: {session.story.title}\n"
    story_summary += "\n".join([
        f"씬{s.scene_number}: {s.scene_description}"
        for s in session.story.scenes[:3]
    ])
    
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
    """이미지 재생성"""
    session = sessions.get(request.session_id)
    if not session or not session.story or not session.images:
        raise HTTPException(status_code=404, detail="Session, story, or images not found")
    
    if request.scene_index >= len(session.story.scenes):
        raise HTTPException(status_code=400, detail="Invalid scene index")
    
    openai_service = get_openai_service()
    scene = session.story.scenes[request.scene_index]
    
    # 세션 설정 사용
    style = session.settings.image_style or ImageStyle.WEBTOON
    sub_style = session.settings.sub_style or SubStyle.NORMAL
    
    # 단일 이미지 재생성
    images = await openai_service.generate_images_batch(
        scenes=[scene],
        style=style,
        sub_style=sub_style
    )
    
    if images:
        session.images[request.scene_index] = images[0]
        return {"image": images[0].model_dump()}
    
    raise HTTPException(status_code=500, detail="Failed to regenerate image")


# ============================================
# 발행 API
# ============================================

class PublishRequest(BaseModel):
    session_id: str
    caption: str
    images: List[str]


@router.post("/publish")
async def publish(request: PublishRequest):
    """Instagram 발행"""
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 실제 Instagram 발행 로직은 instagram_service 사용
    # 여기서는 시뮬레이션
    try:
        from app.services.instagram_service import get_instagram_service
        instagram = get_instagram_service()
        
        result = await instagram.publish_carousel(
            image_urls=request.images,
            caption=request.caption
        )
        
        session.state = WorkflowState.PUBLISHED
        
        return {
            "success": True,
            "post_id": result.get("id", "simulated_" + session.session_id[:8])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


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
    
    recent_files = files[:5]
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
