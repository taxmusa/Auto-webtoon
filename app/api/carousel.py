"""
캐러셀(슬라이드형 콘텐츠) API 라우터
- AI 텍스트 생성 → Playwright 렌더링 → 이미지 슬라이드
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import logging

router = APIRouter(prefix="/api/carousel", tags=["carousel"])
logger = logging.getLogger(__name__)

# 캐러셀 세션 저장소
carousel_sessions = {}


# ============================================
# Request/Response 모델
# ============================================

class CarouselCreateRequest(BaseModel):
    """캐러셀 생성 요청"""
    topic: str                          # 주제/키워드
    collected_data: str = ""            # Tab 2에서 수집한 자료
    slide_count: int = 5                # 슬라이드 수 (3~10)
    bg_color: str = "#FFFFFF"           # 배경색
    text_color: str = "#111111"         # 텍스트 색상
    accent_color: str = "#6366f1"       # 강조색
    font_family: str = "Nanum Gothic"   # 폰트
    template: str = "centered"          # centered | left-aligned | highlight
    ai_model: str = "gemini"            # 텍스트 생성 모델


class CarouselSlide(BaseModel):
    title: str = ""
    body: str = ""
    page_number: str = ""


class CarouselSession(BaseModel):
    id: str
    topic: str
    slides: List[CarouselSlide] = []
    rendered_images: List[str] = []     # 렌더링된 이미지 경로
    bg_color: str = "#FFFFFF"
    text_color: str = "#111111"
    accent_color: str = "#6366f1"
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    status: str = "created"             # created | generating | rendered | published


class SlideEditRequest(BaseModel):
    """슬라이드 수정 요청"""
    slide_index: int
    title: Optional[str] = None
    body: Optional[str] = None


class CarouselRenderRequest(BaseModel):
    """렌더링 요청 (선택 옵션 변경 시)"""
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    template: Optional[str] = None


# ============================================
# API 엔드포인트
# ============================================

@router.post("/generate-slides")
async def generate_slides(req: CarouselCreateRequest):
    """AI로 캐러셀 슬라이드 텍스트 생성"""
    session_id = str(uuid.uuid4())[:8]

    # AI 텍스트 생성
    try:
        slides = await _generate_slide_texts(
            topic=req.topic,
            collected_data=req.collected_data,
            slide_count=req.slide_count,
            ai_model=req.ai_model,
        )
    except Exception as e:
        logger.error(f"[캐러셀] 슬라이드 텍스트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"텍스트 생성 실패: {str(e)}")

    session = CarouselSession(
        id=session_id,
        topic=req.topic,
        slides=slides,
        bg_color=req.bg_color,
        text_color=req.text_color,
        accent_color=req.accent_color,
        font_family=req.font_family,
        template=req.template,
        status="generating",
    )
    carousel_sessions[session_id] = session

    logger.info(f"[캐러셀] 세션 {session_id}: {len(slides)}개 슬라이드 생성")
    return {
        "session_id": session_id,
        "slides": [s.dict() for s in slides],
        "total": len(slides),
    }


@router.get("/{session_id}")
async def get_carousel_session(session_id: str):
    """캐러셀 세션 조회"""
    session = carousel_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="캐러셀 세션을 찾을 수 없습니다.")
    return session.dict()


@router.post("/{session_id}/edit-slide")
async def edit_slide(session_id: str, req: SlideEditRequest):
    """슬라이드 텍스트 수정"""
    session = carousel_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")

    if req.slide_index < 0 or req.slide_index >= len(session.slides):
        raise HTTPException(status_code=400, detail="유효하지 않은 슬라이드 인덱스")

    slide = session.slides[req.slide_index]
    if req.title is not None:
        slide.title = req.title
    if req.body is not None:
        slide.body = req.body

    return {"success": True, "slide": slide.dict()}


@router.post("/{session_id}/render")
async def render_carousel(session_id: str, req: Optional[CarouselRenderRequest] = None):
    """Playwright로 모든 슬라이드를 이미지로 렌더링"""
    session = carousel_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")

    # 옵션 업데이트
    if req:
        if req.bg_color: session.bg_color = req.bg_color
        if req.text_color: session.text_color = req.text_color
        if req.accent_color: session.accent_color = req.accent_color
        if req.font_family: session.font_family = req.font_family
        if req.template: session.template = req.template

    from app.services.render_service import render_html_to_image, build_slide_html

    output_dir = os.path.join("output", f"carousel_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    rendered = []
    for i, slide in enumerate(session.slides):
        html = build_slide_html(
            title=slide.title,
            body=slide.body,
            page_number=f"{i + 1}/{len(session.slides)}",
            bg_color=session.bg_color,
            text_color=session.text_color,
            accent_color=session.accent_color,
            font_family=session.font_family,
            width=1080,
            height=1080,
            template=session.template,
        )

        img_path = os.path.join(output_dir, f"slide_{i + 1:02d}.png")
        await render_html_to_image(
            html_content=html,
            width=1080,
            height=1080,
            output_path=img_path,
        )
        rendered.append(f"/output/carousel_{session_id}/slide_{i + 1:02d}.png")

    session.rendered_images = rendered
    session.status = "rendered"

    logger.info(f"[캐러셀] 세션 {session_id}: {len(rendered)}개 슬라이드 렌더링 완료")
    return {
        "success": True,
        "images": rendered,
        "total": len(rendered),
    }


# ============================================
# AI 텍스트 생성 헬퍼
# ============================================

async def _generate_slide_texts(
    topic: str,
    collected_data: str,
    slide_count: int,
    ai_model: str,
) -> List[CarouselSlide]:
    """Gemini AI로 슬라이드 텍스트 생성"""
    import json

    prompt = f"""당신은 인스타그램 캐러셀 콘텐츠 전문가입니다.

주제: {topic}

참고 자료:
{collected_data[:3000] if collected_data else "(없음)"}

위 주제로 인스타그램 캐러셀 슬라이드 {slide_count}장의 텍스트를 생성해주세요.

규칙:
1. 첫 슬라이드는 강렬한 제목 (호기심 유발)
2. 중간 슬라이드는 핵심 정보 전달
3. 마지막 슬라이드는 CTA (행동 유도) 또는 요약
4. 제목은 20자 이내, 본문은 80자 이내
5. 전문 용어는 쉬운 표현으로
6. 이모지를 적절히 활용

반드시 아래 JSON 형식으로만 응답:
[
  {{"title": "제목1", "body": "본문1"}},
  {{"title": "제목2", "body": "본문2"}}
]
"""

    try:
        import google.generativeai as genai

        from app.core.config import get_settings
        api_key = get_settings().gemini_api_key or ""
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        response = model.generate_content(prompt)
        text = response.text.strip()

        # JSON 파싱
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        slides_data = json.loads(text)

        slides = []
        for i, s in enumerate(slides_data[:slide_count]):
            slides.append(CarouselSlide(
                title=s.get("title", f"슬라이드 {i+1}"),
                body=s.get("body", ""),
                page_number=f"{i+1}/{len(slides_data)}",
            ))

        return slides

    except Exception as e:
        logger.error(f"[캐러셀] AI 텍스트 생성 오류: {e}")
        # 폴백: 기본 슬라이드
        return [
            CarouselSlide(title=f"{topic}", body="자세한 내용을 확인해보세요.", page_number=f"1/{slide_count}"),
            *[CarouselSlide(title=f"포인트 {i}", body="내용을 입력해주세요.", page_number=f"{i+1}/{slide_count}") for i in range(1, slide_count)],
        ]
