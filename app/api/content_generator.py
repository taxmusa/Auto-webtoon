"""
캐러셀/카드뉴스 공통 엔진 — 코드 통합 모듈

carousel.py와 cardnews.py의 95% 중복 코드를 하나의 공통 엔진으로 통합.
차이점(색상, 크기, 프롬프트 등)은 ContentConfig 상수로 분리.
기존 URL은 각 wrapper 파일에서 100% 유지(R4 대응).
"""
from dataclasses import dataclass
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import os
import uuid
import json
import logging
import asyncio
import base64
import zipfile
from io import BytesIO

from app.core.config import DEFAULT_TEXT_MODEL

logger = logging.getLogger(__name__)

# /api/content/* 공유 엔드포인트 (프리셋, 세션, 로고, ZIP 등)
router = APIRouter(prefix="/api/content", tags=["content"])


# ============================================
# 콘텐츠 타입별 설정 (차이점만 정의)
# ============================================

@dataclass
class ContentConfig:
    """캐러셀/카드뉴스 간 차이점을 정의하는 설정 객체"""
    content_type: str          # "carousel" | "cardnews"
    label: str                 # "캐러셀" | "카드뉴스"
    item_label: str            # "슬라이드" | "카드"
    default_bg_color: str
    default_text_color: str
    default_accent_color: str
    default_width: int
    default_height: int
    title_limit: int
    body_limit: int
    ai_role: str               # AI 프롬프트 역할 설명
    output_prefix: str         # 출력 폴더명 접두사
    file_prefix: str           # 파일명 접두사


CAROUSEL_CONFIG = ContentConfig(
    content_type="carousel",
    label="캐러셀",
    item_label="슬라이드",
    default_bg_color="#FFFFFF",
    default_text_color="#111111",
    default_accent_color="#6366f1",
    default_width=1080,
    default_height=1080,
    title_limit=20,
    body_limit=80,
    ai_role="인스타그램 캐러셀 콘텐츠 전문가",
    output_prefix="carousel",
    file_prefix="slide",
)

CARDNEWS_CONFIG = ContentConfig(
    content_type="cardnews",
    label="카드뉴스",
    item_label="카드",
    default_bg_color="#F8F9FA",
    default_text_color="#1A1A1A",
    default_accent_color="#4A7FB5",
    default_width=1080,
    default_height=1350,
    title_limit=15,
    body_limit=100,
    ai_role="인스타그램 카드뉴스 전문가",
    output_prefix="cardnews",
    file_prefix="card",
)


# ============================================
# 공통 Pydantic 모델
# ============================================

class ContentItem(BaseModel):
    """슬라이드/카드 아이템"""
    title: str = ""
    body: str = ""
    page_number: str = ""
    template_type: Optional[str] = None  # 슬라이드별 개별 템플릿 (COVER-A, BODY-B 등)


class ContentCreateRequest(BaseModel):
    """콘텐츠 생성 요청 (모든 Phase 파라미터 포함, 기본값으로 하위 호환)"""
    content_type: str = "cardnews"     # "carousel" | "cardnews" (통합 엔드포인트용)
    topic: str
    collected_data: str = ""
    item_count: int = Field(default=5, ge=1, le=10)
    bg_color: Optional[str] = None       # None이면 config 기본값 사용
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    ai_model: str = "gemini"
    # Phase 1
    last_page_type: str = "cta"          # summary | cta | branding
    aspect_ratio: str = "default"        # default | 1:1 | 4:5 | 9:16
    # Phase 2
    title_size: str = "medium"           # large | medium | small
    spacing: str = "normal"              # compact | normal | spacious
    title_accent: str = "none"           # none | underline | highlight | box
    # Phase 3
    bg_gradient: Optional[str] = None    # CSS gradient 문자열
    # Phase B: 테마 팔레트
    theme: Optional[str] = None          # dark | light | blue | warm | teal (None이면 개별 색상 사용)
    # Phase C: 템플릿 세트
    template_set: Optional[str] = None   # dark_best | blue_report | minimal_card | warm_friendly | teal_modern


class ContentSession(BaseModel):
    """세션 데이터 (모든 Phase 필드 포함, 기본값으로 하위 호환)"""
    id: str
    content_type: str = "carousel"
    topic: str
    items: List[ContentItem] = []
    rendered_images: List[str] = []
    bg_color: str = "#FFFFFF"
    text_color: str = "#111111"
    accent_color: str = "#6366f1"
    font_family: str = "Nanum Gothic"
    template: str = "centered"
    status: str = "created"
    width: int = 1080
    height: int = 1080
    # Phase 1
    last_page_type: str = "cta"
    aspect_ratio: str = "default"
    # Phase 2
    title_size: str = "medium"
    spacing: str = "normal"
    title_accent: str = "none"
    logo_path: Optional[str] = None
    # Phase 3
    bg_gradient: Optional[str] = None
    # Phase B: 테마 팔레트
    theme: Optional[str] = None
    # Phase C: 템플릿 세트
    template_set: Optional[str] = None


class ItemEditRequest(BaseModel):
    """아이템 텍스트 수정 요청"""
    item_index: int
    title: Optional[str] = None
    body: Optional[str] = None
    template_type: Optional[str] = None  # 슬라이드별 개별 템플릿 변경


class ContentRenderRequest(BaseModel):
    """렌더링 옵션 변경 요청"""
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    template: Optional[str] = None
    title_size: Optional[str] = None
    spacing: Optional[str] = None
    title_accent: Optional[str] = None
    bg_gradient: Optional[str] = None
    last_page_type: Optional[str] = None
    aspect_ratio: Optional[str] = None
    theme: Optional[str] = None
    template_set: Optional[str] = None


class SingleRenderRequest(BaseModel):
    """개별 아이템 재렌더링 요청"""
    item_index: int
    title: Optional[str] = None
    body: Optional[str] = None


class ReorderRequest(BaseModel):
    """아이템 순서 변경 요청"""
    order: List[int]


# ============================================
# 세션 저장소 (in-memory + 디스크 영구 저장)
# ============================================

content_sessions: Dict[str, ContentSession] = {}


# ============================================
# 디렉토리 자동 생성
# ============================================

PRESETS_FILE = os.path.join("app_data", "content_presets.json")
SESSIONS_DIR = os.path.join("app_data", "content_sessions")
LOGOS_DIR = os.path.join("app_data", "logos")


def _ensure_dirs():
    """필요한 디렉토리 자동 생성"""
    for d in ["app_data", SESSIONS_DIR, LOGOS_DIR]:
        os.makedirs(d, exist_ok=True)


_ensure_dirs()


# ============================================
# Config 조회 헬퍼
# ============================================

def _get_config(content_type: str) -> ContentConfig:
    """content_type 문자열로 Config 객체 반환"""
    configs = {
        "carousel": CAROUSEL_CONFIG,
        "cardnews": CARDNEWS_CONFIG,
    }
    return configs.get(content_type, CARDNEWS_CONFIG)


# ============================================
# 핵심 공통 함수
# ============================================

def _resolve_dimensions(config: ContentConfig, aspect_ratio: str) -> tuple:
    """비율에 따른 (width, height) 결정"""
    ratios = {
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
        "9:16": (1080, 1920),
    }
    if aspect_ratio in ratios:
        return ratios[aspect_ratio]
    return config.default_width, config.default_height


async def generate_content(config: ContentConfig, req: ContentCreateRequest) -> dict:
    """AI로 콘텐츠 텍스트 생성 (공통 엔진)"""
    session_id = str(uuid.uuid4())[:8]

    # 테마/템플릿 세트 지정 시 팔레트에서 색상 자동 적용
    theme_name = req.theme
    template_set_name = req.template_set
    if template_set_name:
        from app.services.theme_palettes import get_template_set
        ts = get_template_set(template_set_name)
        if ts:
            theme_name = ts["theme"]

    if theme_name:
        from app.services.theme_palettes import get_theme
        palette = get_theme(theme_name)
        bg_color = req.bg_color or palette["bg"]
        text_color = req.text_color or palette["text_primary"]
        accent_color = req.accent_color or palette["accent"]
    else:
        bg_color = req.bg_color or config.default_bg_color
        text_color = req.text_color or config.default_text_color
        accent_color = req.accent_color or config.default_accent_color

    width, height = _resolve_dimensions(config, req.aspect_ratio)

    try:
        items = await _generate_texts(
            config=config,
            topic=req.topic,
            collected_data=req.collected_data,
            item_count=req.item_count,
            last_page_type=req.last_page_type,
            template_set=template_set_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        from app.core.error_classifier import classify_gemini_error
        diag = classify_gemini_error(e)
        logger.error(f"[{config.label}] 텍스트 생성 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"텍스트 생성 실패: {diag.message} — {diag.action}",
        )

    # template_set이 있으면 각 아이템에 template_type 자동 배정
    if template_set_name:
        from app.services.theme_palettes import get_template_set
        ts = get_template_set(template_set_name)
        if ts:
            for i, item in enumerate(items):
                if i == 0:
                    item.template_type = ts.get("cover", "COVER-A")
                elif i == len(items) - 1 and len(items) > 1:
                    item.template_type = ts.get("closing", "CLOSING-A")
                else:
                    item.template_type = ts.get("body", "BODY-A")

    session = ContentSession(
        id=session_id,
        content_type=config.content_type,
        topic=req.topic,
        items=items,
        bg_color=bg_color,
        text_color=text_color,
        accent_color=accent_color,
        font_family=req.font_family,
        template=req.template,
        status="generating",
        width=width,
        height=height,
        last_page_type=req.last_page_type,
        aspect_ratio=req.aspect_ratio,
        title_size=req.title_size,
        spacing=req.spacing,
        title_accent=req.title_accent,
        bg_gradient=req.bg_gradient,
        theme=theme_name,
        template_set=template_set_name,
    )
    content_sessions[session_id] = session
    save_session_to_disk(session)

    logger.info(f"[{config.label}] 세션 {session_id}: {len(items)}개 {config.item_label} 생성")
    return {
        "session_id": session_id,
        "items": [item.dict() for item in items],
        "total": len(items),
    }


async def get_session(session_id: str) -> ContentSession:
    """세션 조회 (메모리 → 디스크 순서 탐색)"""
    session = content_sessions.get(session_id)
    if session:
        return session
    # 디스크에서 로드 시도
    fpath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            session = ContentSession(**data)
            content_sessions[session_id] = session
            return session
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")


async def edit_item(session_id: str, req: ItemEditRequest) -> dict:
    """아이템 텍스트 수정"""
    session = await get_session(session_id)

    if req.item_index < 0 or req.item_index >= len(session.items):
        raise HTTPException(status_code=400, detail="유효하지 않은 인덱스")

    item = session.items[req.item_index]
    if req.title is not None:
        item.title = req.title
    if req.body is not None:
        item.body = req.body
    if req.template_type is not None:
        item.template_type = req.template_type

    return {"success": True, "item": item.dict()}


async def render_content(
    config: ContentConfig,
    session_id: str,
    req: Optional[ContentRenderRequest] = None,
) -> dict:
    """모든 아이템을 Playwright로 이미지 렌더링"""
    session = await get_session(session_id)

    # 옵션 업데이트
    if req:
        # 테마 변경 시 팔레트 색상 자동 적용
        if req.theme:
            from app.services.theme_palettes import get_theme
            session.theme = req.theme
            palette = get_theme(req.theme)
            if not req.bg_color:
                session.bg_color = palette["bg"]
            if not req.text_color:
                session.text_color = palette["text_primary"]
            if not req.accent_color:
                session.accent_color = palette["accent"]
        if req.template_set:
            session.template_set = req.template_set
        if req.bg_color:
            session.bg_color = req.bg_color
        if req.text_color:
            session.text_color = req.text_color
        if req.accent_color:
            session.accent_color = req.accent_color
        if req.font_family:
            session.font_family = req.font_family
        if req.template:
            session.template = req.template
        if req.title_size:
            session.title_size = req.title_size
        if req.spacing:
            session.spacing = req.spacing
        if req.title_accent:
            session.title_accent = req.title_accent
        if req.bg_gradient is not None:
            session.bg_gradient = req.bg_gradient
        if req.last_page_type:
            session.last_page_type = req.last_page_type
        if req.aspect_ratio:
            session.aspect_ratio = req.aspect_ratio
            w, h = _resolve_dimensions(config, req.aspect_ratio)
            session.width = w
            session.height = h

    try:
        from app.services.render_service import render_html_to_image, build_slide_html
    except ImportError as e:
        logger.error(f"[{config.label}] Playwright 임포트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail="렌더링 엔진(Playwright)이 설치되지 않았습니다. 'pip install playwright && playwright install chromium'을 실행하세요.",
        )

    output_dir = os.path.join("output", f"{config.output_prefix}_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    logo_b64 = _load_logo_base64(session.logo_path)
    rendered = []
    total = len(session.items)

    try:
        for i, item in enumerate(session.items):
            is_cover = (i == 0)
            is_last = (i == total - 1) and total > 1

            # template_set이 있으면 새 템플릿 빌더 사용
            use_new_builder = session.template_set is not None
            if use_new_builder:
                try:
                    from app.services.template_builders import build_template_slide
                    html = build_template_slide(
                        template_set=session.template_set,
                        slide_index=i,
                        total_slides=total,
                        title=item.title,
                        body=item.body,
                        width=session.width,
                        height=session.height,
                        template_type_override=item.template_type,
                    )
                except Exception as e:
                    logger.warning(f"[{config.label}] 새 템플릿 빌더 실패, 기존 빌더 사용: {e}")
                    use_new_builder = False

            if not use_new_builder:
                html = build_slide_html(
                    title=item.title,
                    body=item.body,
                    page_number=f"{i + 1}/{total}",
                    bg_color=session.bg_color,
                    text_color=session.text_color,
                    accent_color=session.accent_color,
                    font_family=session.font_family,
                    width=session.width,
                    height=session.height,
                    template=session.template,
                    is_cover=is_cover,
                    is_last=is_last,
                    last_type=session.last_page_type if is_last else None,
                    title_size=session.title_size,
                    spacing=session.spacing,
                    title_accent=session.title_accent,
                    bg_gradient=session.bg_gradient,
                    logo_base64=logo_b64,
                    theme=session.theme,
                )

            img_path = os.path.join(output_dir, f"{config.file_prefix}_{i + 1:02d}.png")
            await render_html_to_image(
                html_content=html,
                width=session.width,
                height=session.height,
                output_path=img_path,
            )
            rendered.append(
                f"/output/{config.output_prefix}_{session_id}/{config.file_prefix}_{i + 1:02d}.png"
            )
    except RuntimeError as e:
        logger.error(f"[{config.label}] Playwright 브라우저 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Playwright 브라우저 시작 실패: {e}. 'playwright install chromium'을 실행하세요.",
        )
    except Exception as e:
        logger.error(f"[{config.label}] 렌더링 중 오류 ({len(rendered)}/{total}): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"렌더링 실패 ({len(rendered)}/{total}번째): {str(e)[:200]}",
        )

    session.rendered_images = rendered
    session.status = "rendered"
    save_session_to_disk(session)

    logger.info(f"[{config.label}] 세션 {session_id}: {len(rendered)}개 렌더링 완료")
    return {
        "success": True,
        "images": rendered,
        "total": len(rendered),
    }


async def render_single_item(
    config: ContentConfig,
    session_id: str,
    req: SingleRenderRequest,
) -> dict:
    """개별 아이템 재렌더링"""
    session = await get_session(session_id)

    idx = req.item_index
    if idx < 0 or idx >= len(session.items):
        raise HTTPException(status_code=400, detail="유효하지 않은 인덱스")

    item = session.items[idx]
    if req.title is not None:
        item.title = req.title
    if req.body is not None:
        item.body = req.body

    try:
        from app.services.render_service import render_html_to_image, build_slide_html
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="렌더링 엔진(Playwright)이 설치되지 않았습니다. 'pip install playwright && playwright install chromium'을 실행하세요.",
        )

    total = len(session.items)
    is_cover = (idx == 0)
    is_last = (idx == total - 1) and total > 1
    logo_b64 = _load_logo_base64(session.logo_path)

    # template_set이 있으면 새 템플릿 빌더 사용
    use_new_builder = session.template_set is not None
    if use_new_builder:
        try:
            from app.services.template_builders import build_template_slide
            html = build_template_slide(
                template_set=session.template_set,
                slide_index=idx,
                total_slides=total,
                title=item.title,
                body=item.body,
                width=session.width,
                height=session.height,
                template_type_override=item.template_type,
            )
        except Exception as e:
            logger.warning(f"[{config.label}] 새 템플릿 빌더 실패, 기존 빌더 사용: {e}")
            use_new_builder = False

    if not use_new_builder:
        html = build_slide_html(
            title=item.title,
            body=item.body,
            page_number=f"{idx + 1}/{total}",
            bg_color=session.bg_color,
            text_color=session.text_color,
            accent_color=session.accent_color,
            font_family=session.font_family,
            width=session.width,
            height=session.height,
            template=session.template,
            is_cover=is_cover,
            is_last=is_last,
            last_type=session.last_page_type if is_last else None,
            title_size=session.title_size,
            spacing=session.spacing,
            title_accent=session.title_accent,
            bg_gradient=session.bg_gradient,
            logo_base64=logo_b64,
            theme=session.theme,
        )

    output_dir = os.path.join("output", f"{config.output_prefix}_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        img_path = os.path.join(output_dir, f"{config.file_prefix}_{idx + 1:02d}.png")
        await render_html_to_image(
            html_content=html,
            width=session.width,
            height=session.height,
            output_path=img_path,
        )
    except RuntimeError as e:
        logger.error(f"[{config.label}] Playwright 브라우저 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Playwright 브라우저 시작 실패: {e}. 'playwright install chromium'을 실행하세요.",
        )
    except Exception as e:
        logger.error(f"[{config.label}] {config.item_label} {idx+1} 렌더링 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"{config.item_label} {idx+1} 렌더링 실패: {str(e)[:200]}",
        )

    url = f"/output/{config.output_prefix}_{session_id}/{config.file_prefix}_{idx + 1:02d}.png"

    # 렌더링 목록 업데이트
    while len(session.rendered_images) <= idx:
        session.rendered_images.append("")
    session.rendered_images[idx] = url
    save_session_to_disk(session)

    logger.info(f"[{config.label}] 세션 {session_id}: {config.item_label} {idx + 1} 재렌더링 완료")
    return {
        "success": True,
        "image": url,
        "item_index": idx,
    }


# ============================================
# AI 텍스트 생성 (에러 진단 R7 연동)
# ============================================

async def _generate_texts(
    config: ContentConfig,
    topic: str,
    collected_data: str,
    item_count: int,
    last_page_type: str = "cta",
    template_set: str = None,
) -> List[ContentItem]:
    """Gemini AI로 텍스트 생성 — 디자인 최적화 프롬프트"""

    last_instruction = {
        "summary": f"마지막 {config.item_label}: 핵심 3줄 요약",
        "cta": f"마지막 {config.item_label}: CTA (행동 유도) + 팔로우/저장 유도",
        "branding": f"마지막 {config.item_label}: 계정명/슬로건 (텍스트 최소화, 브랜드 강조)",
    }.get(last_page_type, f"마지막 {config.item_label}: CTA (행동 유도)")

    # 템플릿 세트별 본문 포맷 가이드
    body_format_guide = ""
    if template_set:
        from app.services.theme_palettes import get_template_set
        ts = get_template_set(template_set)
        if ts:
            body_type = ts.get("body", "BODY-A")
            format_guides = {
                "BODY-A": """[본문 리스트형 포맷]
각 중간 슬라이드의 body는 넘버링 리스트 형식으로 작성:
- 각 항목을 줄바꿈(\\n)으로 구분
- 형식: "항목 제목: 설명" (콜론으로 제목과 설명 분리)
- 항목당 설명은 15~30자
- 3~5개 항목이 적정
예시: "1. 기본공제: 본인·배우자·부양가족 1인당 150만원\\n2. 추가공제: 장애인·경로우대 추가 공제 가능"
""",
                "BODY-B": """[본문 비교형 포맷]
각 중간 슬라이드의 body는 비교(Before/After) 형식:
- X: 로 시작하면 잘못된 사례 (BEFORE)
- O: 로 시작하면 올바른 사례 (AFTER)
- 💡 로 시작하면 핵심 포인트
- 각 항목은 15~25자
예시: "X: 무조건 경비처리하면 된다\\nX: 영수증 안 챙겨도 괜찮다\\nO: 적격증빙 꼭 보관\\nO: 업무 관련성 증명 필수\\n💡 적격증빙이 핵심"
""",
                "BODY-C": """[본문 숫자 강조형 포맷]
각 중간 슬라이드의 body 첫 줄은 큰 숫자/금액:
- 1줄: 강조할 숫자 (예: "150만원", "3.3%", "5년")
- 2줄: 해당 숫자의 설명 라벨
- 3줄~: 세부 계산 내역 (선택)
예시: "최대 700만원\\n연금저축 세액공제 한도\\n총급여 5,500만원 이하: 16.5%\\n총급여 5,500만원 초과: 13.2%"
""",
                "BODY-D": """[본문 단계형 포맷]
각 중간 슬라이드의 body는 STEP 순서로 작성:
- 형식: "STEP 1: 제목: 설명"  또는  "1. 제목: 설명"
- 3~5단계가 적정
- 각 단계 설명은 15~25자
예시: "STEP 1: 서류 준비: 소득금액증명원, 사업자등록증 준비\\nSTEP 2: 홈택스 접속: 종합소득세 신고 메뉴 선택\\nSTEP 3: 신고서 작성: 수입금액과 경비 입력"
""",
            }
            body_format_guide = format_guides.get(body_type, "")

    prompt = f"""당신은 {config.ai_role}입니다. 1080px 인스타그램 이미지에 최적화된 텍스트를 생성합니다.

주제: {topic}

참고 자료:
{collected_data[:3000] if collected_data else "(없음)"}

위 주제로 인스타그램 {config.label} {item_count}장의 텍스트를 생성해주세요.

=== 콘텐츠 구성 규칙 ===
1. 첫 {config.item_label}: 강렬한 표지 (주제를 한 문장으로, 호기심/위기감 유발)
2. 중간 {config.item_label}: 핵심 정보를 하나씩 전달
3. {last_instruction}

=== 디자인 최적화 규칙 (필수) ===
- 제목: {config.title_limit}자 이내, 한 줄에 12~16자가 이상적
- 본문: {config.body_limit}자 이내
- 각 항목의 설명은 한 줄에 14~20자가 적정 (1080px 기준)
- 숫자/금액은 "150만원", "3.3%" 등 짧고 임팩트 있게
- 줄바꿈(\\n)을 활용하여 항목을 명확히 구분
- 한 문장이 30자를 넘지 않도록 끊어 작성
- 전문 용어 → 쉬운 한국어로 변환
- 이모지는 제목에 1~2개만 적절히 사용

{body_format_guide}
반드시 아래 JSON 형식으로만 응답:
[
  {{"title": "제목1", "body": "본문1"}},
  {{"title": "제목2", "body": "본문2"}}
]
"""

    try:
        from app.services.gemini_service import get_gemini_client

        client = get_gemini_client()
        if not client:
            raise HTTPException(
                status_code=400,
                detail="Gemini API 키가 설정되지 않았습니다. 설정 → AI API 키에서 입력하세요.",
            )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=DEFAULT_TEXT_MODEL,
            contents=prompt
        )
        text = response.text.strip()

        # JSON 파싱 (마크다운 코드 블록 제거)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        items_data = json.loads(text)

        items = []
        for i, d in enumerate(items_data[:item_count]):
            items.append(ContentItem(
                title=d.get("title", f"{config.item_label} {i + 1}"),
                body=d.get("body", ""),
                page_number=f"{i + 1}/{item_count}",
            ))

        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{config.label}] AI 텍스트 생성 오류: {e}")
        # 폴백: 기본 아이템 반환 (서비스 중단 방지)
        return [
            ContentItem(
                title=f"{topic}",
                body="자세한 내용을 확인해보세요.",
                page_number=f"1/{item_count}",
            ),
            *[
                ContentItem(
                    title=f"핵심 {i}",
                    body="내용을 입력해주세요.",
                    page_number=f"{i + 1}/{item_count}",
                )
                for i in range(1, item_count)
            ],
        ]


# ============================================
# 헬퍼 함수
# ============================================

def _load_logo_base64(logo_path: Optional[str]) -> Optional[str]:
    """로고 파일을 base64 문자열로 로드"""
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        with open(logo_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except Exception:
        return None


def _update_page_numbers(session: ContentSession):
    """페이지 번호 재계산"""
    total = len(session.items)
    for i, item in enumerate(session.items):
        item.page_number = f"{i + 1}/{total}"


def save_session_to_disk(session: ContentSession):
    """세션을 디스크에 영구 저장"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    fpath = os.path.join(SESSIONS_DIR, f"{session.id}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(session.dict(), f, ensure_ascii=False, indent=2)


# ============================================
# /api/content/* 공유 엔드포인트
# ============================================

# --- 프리셋 ---

@router.get("/presets")
async def get_presets():
    """스타일 프리셋 목록"""
    if not os.path.exists(PRESETS_FILE):
        return {"presets": []}
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            return {"presets": json.load(f)}
    except Exception:
        return {"presets": []}


@router.post("/presets")
async def save_preset(preset: dict):
    """스타일 프리셋 저장"""
    presets = []
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
        except Exception:
            presets = []

    # 같은 이름 덮어쓰기
    presets = [p for p in presets if p.get("name") != preset.get("name")]
    presets.append(preset)

    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)

    return {"success": True, "total": len(presets)}


@router.delete("/presets/{name}")
async def delete_preset(name: str):
    """스타일 프리셋 삭제"""
    if not os.path.exists(PRESETS_FILE):
        return {"success": True}
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            presets = json.load(f)
        presets = [p for p in presets if p.get("name") != name]
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"success": True}


# --- 세션 ---

@router.get("/sessions")
async def list_sessions():
    """저장된 세션 목록 (최근 20개)"""
    sessions_list = []
    if os.path.exists(SESSIONS_DIR):
        files = sorted(os.listdir(SESSIONS_DIR), reverse=True)
        for fname in files[:20]:
            if not fname.endswith(".json"):
                continue
            try:
                fpath = os.path.join(SESSIONS_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions_list.append({
                    "session_id": data.get("id", ""),
                    "topic": data.get("topic", ""),
                    "content_type": data.get("content_type", ""),
                    "item_count": len(data.get("items", [])),
                    "status": data.get("status", ""),
                })
            except Exception:
                pass
    return {"sessions": sessions_list}


@router.get("/sessions/{session_id}")
async def load_session(session_id: str):
    """저장된 세션 로드"""
    session = await get_session(session_id)
    return session.dict()


# --- 로고 업로드 ---

@router.post("/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    """로고/워터마크 이미지 업로드 (최대 500KB)"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    data = await file.read()
    if len(data) > 500 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 500KB 이하여야 합니다.")

    os.makedirs(LOGOS_DIR, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    logo_path = os.path.join(LOGOS_DIR, f"logo_{uuid.uuid4().hex[:8]}.{ext}")
    with open(logo_path, "wb") as f:
        f.write(data)

    return {"success": True, "logo_path": logo_path}


# --- ZIP 다운로드 ---

@router.get("/{session_id}/download")
async def download_zip(session_id: str):
    """렌더링된 이미지를 ZIP으로 다운로드"""
    from fastapi.responses import StreamingResponse

    session = content_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")
    if not session.rendered_images:
        raise HTTPException(status_code=400, detail="렌더링된 이미지가 없습니다.")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_url in session.rendered_images:
            local_path = img_url.lstrip("/")
            if os.path.exists(local_path):
                zf.write(local_path, os.path.basename(local_path))

    buf.seek(0)
    safe_topic = "".join(c for c in session.topic[:20] if c.isalnum() or c in " _-")
    filename = f"{session.content_type}_{safe_topic}_{session_id}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- 아이템 추가/삭제/복제/순서변경 ---

@router.post("/{session_id}/add-item")
async def add_item(session_id: str):
    """빈 아이템 추가"""
    session = await get_session(session_id)
    if len(session.items) >= 10:
        raise HTTPException(status_code=400, detail="최대 10개까지 가능합니다.")
    new_item = ContentItem(title="새 슬라이드", body="내용을 입력하세요.")
    session.items.append(new_item)
    _update_page_numbers(session)
    save_session_to_disk(session)
    return {"success": True, "item": new_item.dict(), "total": len(session.items)}


@router.delete("/{session_id}/item/{item_index}")
async def delete_item(session_id: str, item_index: int):
    """아이템 삭제"""
    session = await get_session(session_id)
    if item_index < 0 or item_index >= len(session.items):
        raise HTTPException(status_code=400, detail="유효하지 않은 인덱스")
    if len(session.items) <= 1:
        raise HTTPException(status_code=400, detail="최소 1개 아이템이 필요합니다.")
    session.items.pop(item_index)
    _update_page_numbers(session)
    save_session_to_disk(session)
    return {"success": True, "total": len(session.items)}


@router.post("/{session_id}/duplicate/{item_index}")
async def duplicate_item(session_id: str, item_index: int):
    """아이템 복제"""
    session = await get_session(session_id)
    if item_index < 0 or item_index >= len(session.items):
        raise HTTPException(status_code=400, detail="유효하지 않은 인덱스")
    if len(session.items) >= 10:
        raise HTTPException(status_code=400, detail="최대 10개까지 가능합니다.")
    original = session.items[item_index]
    dup = ContentItem(title=original.title, body=original.body)
    session.items.insert(item_index + 1, dup)
    _update_page_numbers(session)
    save_session_to_disk(session)
    return {"success": True, "total": len(session.items)}


@router.post("/{session_id}/reorder")
async def reorder_items(session_id: str, req: ReorderRequest):
    """아이템 순서 변경"""
    session = await get_session(session_id)
    if sorted(req.order) != list(range(len(session.items))):
        raise HTTPException(status_code=400, detail="유효하지 않은 순서")
    session.items = [session.items[i] for i in req.order]
    _update_page_numbers(session)
    save_session_to_disk(session)
    return {"success": True}


# --- 테마/템플릿 세트 조회 ---

@router.get("/themes")
async def list_themes():
    """사용 가능한 테마 팔레트 목록"""
    from app.services.theme_palettes import THEME_PALETTES
    themes = []
    for name, palette in THEME_PALETTES.items():
        themes.append({
            "id": name,
            "bg": palette["bg"],
            "text_primary": palette["text_primary"],
            "accent": palette["accent"],
        })
    return {"themes": themes}


@router.get("/template-sets")
async def list_template_sets():
    """사용 가능한 템플릿 세트 목록"""
    from app.services.theme_palettes import get_available_template_sets
    return {"template_sets": get_available_template_sets()}


# ============================================
# 통합 엔드포인트 (캐러셀/카드뉴스 공용)
# ============================================

@router.post("/generate")
async def unified_generate(req: ContentCreateRequest):
    """통합 콘텐츠 생성 — content_type으로 캐러셀/카드뉴스 구분"""
    config = _get_config(req.content_type)
    result = await generate_content(config, req)
    return result


@router.get("/{session_id}/detail")
async def unified_get_session(session_id: str):
    """통합 세션 조회"""
    session = await get_session(session_id)
    return session.dict()


@router.post("/{session_id}/edit")
async def unified_edit_item(session_id: str, req: ItemEditRequest):
    """통합 아이템 수정"""
    result = await edit_item(session_id, req)
    return result


@router.post("/{session_id}/render")
async def unified_render(session_id: str, req: Optional[ContentRenderRequest] = None):
    """통합 렌더링 — 세션의 content_type에서 config 자동 결정"""
    session = await get_session(session_id)
    config = _get_config(session.content_type)
    return await render_content(config, session_id, req)


@router.post("/{session_id}/render-single")
async def unified_render_single(session_id: str, req: SingleRenderRequest):
    """통합 개별 재렌더링"""
    session = await get_session(session_id)
    config = _get_config(session.content_type)
    return await render_single_item(config, session_id, req)


class HtmlPreviewRequest(BaseModel):
    """HTML 미리보기 요청 (Playwright 렌더링 없이 HTML만 반환)"""
    item_index: int
    title: Optional[str] = None
    body: Optional[str] = None
    template_type: Optional[str] = None


@router.post("/{session_id}/preview-html")
async def get_preview_html(session_id: str, req: HtmlPreviewRequest):
    """개별 슬라이드 HTML 반환 (실시간 미리보기용, Playwright 미사용)"""
    session = await get_session(session_id)

    idx = req.item_index
    if idx < 0 or idx >= len(session.items):
        raise HTTPException(status_code=400, detail="유효하지 않은 인덱스")

    item = session.items[idx]
    title = req.title if req.title is not None else item.title
    body = req.body if req.body is not None else item.body
    template_type = req.template_type or item.template_type

    total = len(session.items)

    # template_set이 있으면 새 템플릿 빌더 사용
    if session.template_set:
        try:
            from app.services.template_builders import build_template_slide
            html = build_template_slide(
                template_set=session.template_set,
                slide_index=idx,
                total_slides=total,
                title=title,
                body=body,
                width=session.width,
                height=session.height,
                template_type_override=template_type,
            )
            return {"html": html}
        except Exception as e:
            logger.warning(f"새 템플릿 빌더 실패, 기존 빌더 사용: {e}")

    # 기존 빌더 폴백
    from app.services.render_service import build_slide_html
    is_cover = (idx == 0)
    is_last = (idx == total - 1) and total > 1
    logo_b64 = _load_logo_base64(session.logo_path)

    html = build_slide_html(
        title=title,
        body=body,
        page_number=f"{idx + 1}/{total}",
        bg_color=session.bg_color,
        text_color=session.text_color,
        accent_color=session.accent_color,
        font_family=session.font_family,
        width=session.width,
        height=session.height,
        template=session.template,
        is_cover=is_cover,
        is_last=is_last,
        last_type=session.last_page_type if is_last else None,
        title_size=session.title_size,
        spacing=session.spacing,
        title_accent=session.title_accent,
        bg_gradient=session.bg_gradient,
        logo_base64=logo_b64,
        theme=session.theme,
    )
    return {"html": html}


class AiRewriteRequest(BaseModel):
    """AI 텍스트 다시쓰기 요청"""
    item_index: int
    title: str = ""
    body: str = ""
    mode: str = "rewrite"  # rewrite(다시쓰기), shorter(짧게), professional(전문적), friendly(친근하게)
    topic: str = ""  # 원래 주제 (컨텍스트)


@router.post("/{session_id}/ai-rewrite")
async def ai_rewrite_item(session_id: str, req: AiRewriteRequest):
    """개별 슬라이드 텍스트 AI 다시쓰기"""
    session = await get_session(session_id)
    config = _get_config(session.content_type)

    mode_instructions = {
        "rewrite": "동일한 핵심 정보를 유지하면서 더 매력적이고 읽기 쉽게 다시 작성",
        "shorter": "핵심만 남기고 최대한 간결하게 줄이기 (제목 10자, 본문 40자 이내 목표)",
        "professional": "전문적이고 신뢰감 있는 톤으로 변환 (존댓말, 정확한 용어)",
        "friendly": "친근하고 편안한 톤으로 변환 (반말OK, 이모지 활용, 대화체)",
    }
    instruction = mode_instructions.get(req.mode, mode_instructions["rewrite"])

    # 슬라이드 위치 파악
    total = len(session.items)
    idx = req.item_index
    position = "표지(첫 슬라이드)" if idx == 0 else ("마무리(마지막 슬라이드)" if idx == total - 1 and total > 1 else "본문 슬라이드")

    prompt = f"""인스타그램 {config.label}의 {position}입니다.
주제: {req.topic or session.topic or '(미지정)'}

현재 텍스트:
- 제목: {req.title}
- 본문: {req.body}

요청: {instruction}

규칙:
- 한 줄에 14~20자 적정 (1080px 이미지 기준)
- 줄바꿈(\\n)으로 항목 구분
- 제목은 {config.title_limit}자 이내
- 본문은 {config.body_limit}자 이내

반드시 JSON으로만 응답:
{{"title": "새 제목", "body": "새 본문"}}
"""

    try:
        from app.services.gemini_service import get_gemini_client
        client = get_gemini_client()
        if not client:
            raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=DEFAULT_TEXT_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        return {
            "success": True,
            "title": result.get("title", req.title),
            "body": result.get("body", req.body),
            "mode": req.mode,
        }
    except Exception as e:
        logger.error(f"AI 다시쓰기 오류: {e}")
        raise HTTPException(status_code=500, detail=f"AI 다시쓰기 실패: {str(e)}")


# --- 템플릿 카탈로그 ---

@router.get("/templates")
async def get_template_catalog():
    """전체 템플릿 카탈로그 (세트 + 개별 템플릿 목록)"""
    from app.services.theme_palettes import TEMPLATE_SETS, THEME_PALETTES

    # 템플릿 세트 목록
    template_sets = []
    for set_id, ts in TEMPLATE_SETS.items():
        theme = THEME_PALETTES.get(ts["theme"], {})
        # 프리뷰 이미지 파일 존재 여부 확인
        import os
        preview_path = os.path.join("app", "static", "previews", f"{set_id}.png")
        preview_image = f"/static/previews/{set_id}.png" if os.path.exists(preview_path) else None
        template_sets.append({
            "id": set_id,
            "name": ts.get("label", set_id),
            "description": ts.get("description", ""),
            "theme": ts["theme"],
            "cover": ts["cover"],
            "body": ts["body"],
            "closing": ts.get("closing", "CLOSING-A"),
            "preview_image": preview_image,
            "preview_colors": [
                theme.get("bg", "#FFFFFF"),
                theme.get("accent", "#4A7FB5"),
                theme.get("text_primary", "#1A1A1A"),
            ],
        })

    # 개별 템플릿 목록
    individual_templates = [
        # 커버
        {"id": "COVER-A", "type": "cover", "name": "다크 BEST 리스트형", "theme": "dark", "description": "강렬한 SNS 바이럴"},
        {"id": "COVER-B", "type": "cover", "name": "다크 카테고리형", "theme": "dark", "description": "전문적, 긴급성 강조"},
        {"id": "COVER-C", "type": "cover", "name": "블루 리포트형", "theme": "blue", "description": "공신력, 전문가"},
        {"id": "COVER-D", "type": "cover", "name": "미니멀 카드형", "theme": "light", "description": "깔끔, 모던"},
        {"id": "COVER-E", "type": "cover", "name": "웜톤 질문형", "theme": "warm", "description": "친근, 질문형 제목"},
        {"id": "COVER-F", "type": "cover", "name": "틸 리포트형", "theme": "teal", "description": "세련, 트렌디"},
        # 본문
        {"id": "BODY-A", "type": "body", "name": "넘버링 리스트형", "description": "포인트별 정보 전달"},
        {"id": "BODY-B", "type": "body", "name": "비교형 (Good/Bad)", "description": "O/X, Before/After 비교"},
        {"id": "BODY-C", "type": "body", "name": "하이라이트 박스형", "description": "큰 숫자/금액 강조"},
        {"id": "BODY-D", "type": "body", "name": "스텝/프로세스형", "description": "단계별 진행 흐름"},
        # 마무리
        {"id": "CLOSING-A", "type": "closing", "name": "요약 + CTA형", "description": "핵심 요약 + 행동 유도"},
        {"id": "CLOSING-B", "type": "closing", "name": "브랜드 카드형", "description": "회사명, 슬로건, 연락처"},
    ]

    return {
        "template_sets": template_sets,
        "individual_templates": individual_templates,
    }
