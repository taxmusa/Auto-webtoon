"""
카드뉴스 API 라우터 (thin wrapper → content_generator)

기존 URL `/api/cardnews/*`을 100% 유지하면서
content_generator 공통 엔진에 위임한다. (R4 대응)
프론트엔드 파라미터명(card_count, cards 등)도 그대로 유지.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.api.content_generator import (
    CARDNEWS_CONFIG,
    ContentCreateRequest,
    ContentRenderRequest,
    ItemEditRequest,
    SingleRenderRequest,
    generate_content,
    get_session,
    edit_item,
    render_content,
    render_single_item,
)

router = APIRouter(prefix="/api/cardnews", tags=["cardnews"])
logger = logging.getLogger(__name__)


# ============================================
# 기존 호환 모델 (프론트엔드 파라미터명 유지)
# ============================================

class CardNewsCreateRequest(BaseModel):
    """카드뉴스 생성 요청 (기존 호환)"""
    topic: str
    collected_data: str = ""
    card_count: int = Field(default=5, ge=1, le=10)
    bg_color: str = "#1a1a2e"
    text_color: str = "#FFFFFF"
    accent_color: str = "#e94560"
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    ai_model: str = "gemini"
    # Phase 1+
    last_page_type: str = "cta"
    aspect_ratio: str = "default"
    # Phase 2+
    title_size: str = "medium"
    spacing: str = "normal"
    title_accent: str = "none"
    # Phase 3+
    bg_gradient: Optional[str] = None


class CardEditRequest(BaseModel):
    """카드 수정 요청 (기존 호환)"""
    card_index: int
    title: Optional[str] = None
    body: Optional[str] = None


class CardNewsRenderRequest(BaseModel):
    """렌더링 옵션 변경 (기존 호환)"""
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    template: Optional[str] = None
    title_size: Optional[str] = None
    spacing: Optional[str] = None
    title_accent: Optional[str] = None
    bg_gradient: Optional[str] = None


# ============================================
# API 엔드포인트 (기존 URL 100% 유지)
# ============================================

@router.post("/generate-cards")
async def generate_cards(req: CardNewsCreateRequest):
    """AI로 카드뉴스 텍스트 생성"""
    common_req = ContentCreateRequest(
        topic=req.topic,
        collected_data=req.collected_data,
        item_count=req.card_count,
        bg_color=req.bg_color,
        text_color=req.text_color,
        accent_color=req.accent_color,
        font_family=req.font_family,
        template=req.template,
        ai_model=req.ai_model,
        last_page_type=req.last_page_type,
        aspect_ratio=req.aspect_ratio,
        title_size=req.title_size,
        spacing=req.spacing,
        title_accent=req.title_accent,
        bg_gradient=req.bg_gradient,
    )
    result = await generate_content(CARDNEWS_CONFIG, common_req)
    # 프론트엔드 호환: "items" → "cards"
    result["cards"] = result.pop("items")
    return result


@router.get("/{session_id}")
async def get_cardnews_session(session_id: str):
    """카드뉴스 세션 조회"""
    session = await get_session(session_id)
    data = session.dict()
    # 프론트엔드 호환: "items" → "cards"
    data["cards"] = data.pop("items")
    return data


@router.post("/{session_id}/edit-card")
async def edit_card(session_id: str, req: CardEditRequest):
    """카드 텍스트 수정"""
    result = await edit_item(session_id, ItemEditRequest(
        item_index=req.card_index,
        title=req.title,
        body=req.body,
    ))
    # 프론트엔드 호환: "item" → "card"
    result["card"] = result.pop("item")
    return result


@router.post("/{session_id}/render")
async def render_cardnews(session_id: str, req: Optional[CardNewsRenderRequest] = None):
    """모든 카드를 이미지로 렌더링"""
    common_req = None
    if req:
        common_req = ContentRenderRequest(
            bg_color=req.bg_color,
            text_color=req.text_color,
            accent_color=req.accent_color,
            font_family=req.font_family,
            template=req.template,
            title_size=req.title_size,
            spacing=req.spacing,
            title_accent=req.title_accent,
            bg_gradient=req.bg_gradient,
        )
    return await render_content(CARDNEWS_CONFIG, session_id, common_req)


@router.post("/{session_id}/render-single")
async def render_single_card(session_id: str, req: SingleRenderRequest):
    """개별 카드 재렌더링"""
    return await render_single_item(CARDNEWS_CONFIG, session_id, req)
