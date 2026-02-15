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
import base64
import zipfile
from io import BytesIO

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
    default_bg_color="#1a1a2e",
    default_text_color="#FFFFFF",
    default_accent_color="#e94560",
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


class ContentCreateRequest(BaseModel):
    """콘텐츠 생성 요청 (모든 Phase 파라미터 포함, 기본값으로 하위 호환)"""
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


class ItemEditRequest(BaseModel):
    """아이템 텍스트 수정 요청"""
    item_index: int
    title: Optional[str] = None
    body: Optional[str] = None


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

    from app.services.render_service import render_html_to_image, build_slide_html

    output_dir = os.path.join("output", f"{config.output_prefix}_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    logo_b64 = _load_logo_base64(session.logo_path)
    rendered = []
    total = len(session.items)

    for i, item in enumerate(session.items):
        is_cover = (i == 0)
        is_last = (i == total - 1) and total > 1

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

    from app.services.render_service import render_html_to_image, build_slide_html

    total = len(session.items)
    is_cover = (idx == 0)
    is_last = (idx == total - 1) and total > 1
    logo_b64 = _load_logo_base64(session.logo_path)

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
    )

    output_dir = os.path.join("output", f"{config.output_prefix}_{session_id}")
    os.makedirs(output_dir, exist_ok=True)

    img_path = os.path.join(output_dir, f"{config.file_prefix}_{idx + 1:02d}.png")
    await render_html_to_image(
        html_content=html,
        width=session.width,
        height=session.height,
        output_path=img_path,
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
) -> List[ContentItem]:
    """Gemini AI로 텍스트 생성"""

    last_instruction = {
        "summary": f"마지막 {config.item_label}: 핵심 3줄 요약",
        "cta": f"마지막 {config.item_label}: CTA (행동 유도) + 팔로우/저장 유도",
        "branding": f"마지막 {config.item_label}: 계정명/슬로건 (텍스트 최소화, 브랜드 강조)",
    }.get(last_page_type, f"마지막 {config.item_label}: CTA (행동 유도)")

    prompt = f"""당신은 {config.ai_role}입니다.

주제: {topic}

참고 자료:
{collected_data[:3000] if collected_data else "(없음)"}

위 주제로 인스타그램 {config.label} {item_count}장의 텍스트를 생성해주세요.

규칙:
1. 첫 {config.item_label}: 강렬한 표지 (주제를 한 문장으로, 호기심 유발)
2. 중간 {config.item_label}: 핵심 정보를 하나씩 전달
3. {last_instruction}
4. 제목은 {config.title_limit}자 이내
5. 본문은 {config.body_limit}자 이내
6. 전문 용어 대신 쉬운 한국어 사용
7. 이모지를 적절히 활용

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
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Gemini API 키가 설정되지 않았습니다. 설정 → AI API 키에서 입력하세요.",
            )

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")

        response = model.generate_content(prompt)
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
