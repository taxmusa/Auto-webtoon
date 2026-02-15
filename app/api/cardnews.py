"""
카드뉴스 API 라우터
- AI 텍스트 생성 → Playwright 렌더링 → 카드 이미지
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import logging

router = APIRouter(prefix="/api/cardnews", tags=["cardnews"])
logger = logging.getLogger(__name__)

# 카드뉴스 세션 저장소
cardnews_sessions = {}


# ============================================
# Request/Response 모델
# ============================================

class CardNewsCreateRequest(BaseModel):
    """카드뉴스 생성 요청"""
    topic: str
    collected_data: str = ""
    card_count: int = 5
    bg_color: str = "#1a1a2e"
    text_color: str = "#FFFFFF"
    accent_color: str = "#e94560"
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    ai_model: str = "gemini"


class CardItem(BaseModel):
    title: str = ""
    body: str = ""
    page_number: str = ""


class CardNewsSession(BaseModel):
    id: str
    topic: str
    cards: List[CardItem] = []
    rendered_images: List[str] = []
    bg_color: str = "#1a1a2e"
    text_color: str = "#FFFFFF"
    accent_color: str = "#e94560"
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    status: str = "created"


class CardEditRequest(BaseModel):
    card_index: int
    title: Optional[str] = None
    body: Optional[str] = None


class CardNewsRenderRequest(BaseModel):
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    template: Optional[str] = None


# ============================================
# API 엔드포인트
# ============================================

@router.post("/generate-cards")
async def generate_cards(req: CardNewsCreateRequest):
    """AI로 카드뉴스 텍스트 생성"""
    session_id = str(uuid.uuid4())[:8]

    try:
        cards = await _generate_card_texts(
            topic=req.topic,
            collected_data=req.collected_data,
            card_count=req.card_count,
            ai_model=req.ai_model,
        )
    except Exception as e:
        logger.error(f"[카드뉴스] 텍스트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"텍스트 생성 실패: {str(e)}")

    session = CardNewsSession(
        id=session_id,
        topic=req.topic,
        cards=cards,
        bg_color=req.bg_color,
        text_color=req.text_color,
        accent_color=req.accent_color,
        font_family=req.font_family,
        template=req.template,
        status="generating",
    )
    cardnews_sessions[session_id] = session

    logger.info(f"[카드뉴스] 세션 {session_id}: {len(cards)}장 생성")
    return {
        "session_id": session_id,
        "cards": [c.dict() for c in cards],
        "total": len(cards),
    }


@router.get("/{session_id}")
async def get_cardnews_session(session_id: str):
    """카드뉴스 세션 조회"""
    session = cardnews_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="카드뉴스 세션 없음")
    return session.dict()


@router.post("/{session_id}/edit-card")
async def edit_card(session_id: str, req: CardEditRequest):
    """카드 텍스트 수정"""
    session = cardnews_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")

    if req.card_index < 0 or req.card_index >= len(session.cards):
        raise HTTPException(status_code=400, detail="유효하지 않은 카드 인덱스")

    card = session.cards[req.card_index]
    if req.title is not None:
        card.title = req.title
    if req.body is not None:
        card.body = req.body

    return {"success": True, "card": card.dict()}


@router.post("/{session_id}/render")
async def render_cardnews(session_id: str, req: Optional[CardNewsRenderRequest] = None):
    """Playwright로 모든 카드를 이미지로 렌더링"""
    session = cardnews_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")

    if req:
        if req.bg_color: session.bg_color = req.bg_color
        if req.text_color: session.text_color = req.text_color
        if req.accent_color: session.accent_color = req.accent_color
        if req.font_family: session.font_family = req.font_family
        if req.template: session.template = req.template

    from app.services.render_service import render_html_to_image, build_slide_html

    output_dir = os.path.join("output", f"cardnews_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    rendered = []
    for i, card in enumerate(session.cards):
        html = build_slide_html(
            title=card.title,
            body=card.body,
            page_number=f"{i + 1}/{len(session.cards)}",
            bg_color=session.bg_color,
            text_color=session.text_color,
            accent_color=session.accent_color,
            font_family=session.font_family,
            width=1080,
            height=1350,  # 카드뉴스는 4:5 비율
            template=session.template,
        )

        img_path = os.path.join(output_dir, f"card_{i + 1:02d}.png")
        await render_html_to_image(
            html_content=html,
            width=1080,
            height=1350,
            output_path=img_path,
        )
        rendered.append(f"/output/cardnews_{session_id}/card_{i + 1:02d}.png")

    session.rendered_images = rendered
    session.status = "rendered"

    logger.info(f"[카드뉴스] 세션 {session_id}: {len(rendered)}장 렌더링 완료")
    return {
        "success": True,
        "images": rendered,
        "total": len(rendered),
    }


# ============================================
# AI 텍스트 생성 헬퍼
# ============================================

async def _generate_card_texts(
    topic: str,
    collected_data: str,
    card_count: int,
    ai_model: str,
) -> List[CardItem]:
    """Gemini AI로 카드뉴스 텍스트 생성"""
    import json

    prompt = f"""당신은 인스타그램 카드뉴스 전문가입니다.

주제: {topic}

참고 자료:
{collected_data[:3000] if collected_data else "(없음)"}

위 주제로 인스타그램 카드뉴스 {card_count}장의 텍스트를 생성해주세요.

규칙:
1. 첫 카드: 강렬한 표지 (주제를 한 문장으로)
2. 중간 카드: 핵심 정보를 하나씩 전달
3. 마지막 카드: 핵심 요약 + CTA
4. 제목은 15자 이내 (굵은 폰트용)
5. 본문은 100자 이내 (가독성 우선)
6. 전문 용어 대신 쉬운 한국어 사용
7. 이모지 적절히 활용

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

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        cards_data = json.loads(text)

        cards = []
        for i, c in enumerate(cards_data[:card_count]):
            cards.append(CardItem(
                title=c.get("title", f"카드 {i+1}"),
                body=c.get("body", ""),
                page_number=f"{i+1}/{len(cards_data)}",
            ))

        return cards

    except Exception as e:
        logger.error(f"[카드뉴스] AI 텍스트 생성 오류: {e}")
        return [
            CardItem(title=f"{topic}", body="자세한 내용을 확인해보세요.", page_number=f"1/{card_count}"),
            *[CardItem(title=f"핵심 {i}", body="내용을 입력해주세요.", page_number=f"{i+1}/{card_count}") for i in range(1, card_count)],
        ]
