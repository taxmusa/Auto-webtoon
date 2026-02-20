"""
Playwright 렌더링 서비스
- HTML/CSS → 이미지 변환 (말풍선, 캐러셀, 카드뉴스)
- 한글 웹폰트 지원 (Google Fonts 11종)
- 고품질 스크린샷 (2x 해상도)
- document.fonts.ready 대기로 폰트 로딩 보장 (R1)
- sync API + 전용 단일 스레드 Executor로 greenlet 호환 (R3)
"""
import asyncio
import os
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# Cursor 샌드박스가 설정하는 임시 경로 제거 (기본 경로 사용)
_pw_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
if "cursor-sandbox" in _pw_path or "Temp" in _pw_path:
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    logger.info(f"[Playwright] 샌드박스 브라우저 경로 제거: {_pw_path}")

# Playwright는 greenlet 기반이므로 반드시 동일 스레드에서 실행해야 함
# max_workers=1 → 모든 Playwright 호출이 단일 전용 스레드에서 순차 실행
_playwright_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")

# Playwright sync 브라우저 인스턴스 (싱글톤, 스레드 안전)
_sync_browser = None
_sync_playwright = None
_browser_thread_id = None  # 브라우저를 생성한 스레드 ID
_browser_lock = threading.Lock()
_render_semaphore = asyncio.Semaphore(3)


def _get_sync_browser():
    """Playwright sync 브라우저 싱글톤 (스레드에서 호출)

    greenlet 호환을 위해 현재 스레드가 브라우저 생성 스레드와 다르면
    자동으로 기존 인스턴스를 폐기하고 재생성한다.
    """
    global _sync_browser, _sync_playwright, _browser_thread_id

    current_thread = threading.current_thread().ident

    # 브라우저가 다른 스레드에서 생성되었거나, 생성 스레드를 알 수 없는 경우 → 강제 재생성
    need_recreate = (
        _sync_browser is not None
        and (_browser_thread_id is None or _browser_thread_id != current_thread)
    )

    if not need_recreate and _sync_browser and _sync_browser.is_connected():
        return _sync_browser

    with _browser_lock:
        # 더블 체크: 락 획득 사이에 다른 호출이 이미 재생성했을 수 있음
        if _sync_browser and _sync_browser.is_connected() and _browser_thread_id == current_thread:
            return _sync_browser

        if _sync_browser is not None:
            logger.warning(
                "[Playwright] 스레드 불일치 감지 (생성=%s, 현재=%s) → 브라우저 재생성",
                _browser_thread_id, current_thread
            )

        if _sync_browser:
            try:
                _sync_browser.close()
            except Exception:
                pass
            _sync_browser = None
        if _sync_playwright:
            try:
                _sync_playwright.stop()
            except Exception:
                pass
            _sync_playwright = None
        _browser_thread_id = None

        from playwright.sync_api import sync_playwright

        for attempt in range(3):
            try:
                _sync_playwright = sync_playwright().start()
                _sync_browser = _sync_playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                _browser_thread_id = current_thread
                logger.info("[Playwright] 브라우저 시작됨 (sync mode, thread=%s)", current_thread)
                return _sync_browser
            except Exception as e:
                logger.warning(f"[Playwright] 브라우저 시작 실패 (시도 {attempt+1}/3): {e}")
                if attempt < 2:
                    import time
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Playwright 브라우저를 시작할 수 없습니다: {e}")


async def shutdown_browser():
    """앱 종료 시 브라우저 정리"""
    global _sync_browser, _sync_playwright
    def _shutdown():
        global _sync_browser, _sync_playwright
        if _sync_browser:
            try:
                _sync_browser.close()
            except Exception:
                pass
            _sync_browser = None
        if _sync_playwright:
            try:
                _sync_playwright.stop()
            except Exception:
                pass
            _sync_playwright = None
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_playwright_executor, _shutdown)


# ────────────────────────────────────────────
# 핵심 렌더링 함수
# ────────────────────────────────────────────

def _render_sync(
    html_content: str,
    width: int,
    height: int,
    output_path: Optional[str],
    device_scale_factor: float,
    omit_background: bool = False,
) -> bytes:
    """스레드에서 실행되는 sync 렌더링 (Playwright sync API)"""
    browser = _get_sync_browser()
    page = browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )
    try:
        page.set_content(html_content, wait_until="networkidle")
        try:
            page.wait_for_function(
                "() => document.fonts.ready.then(() => true)",
                timeout=5000,
            )
        except Exception:
            page.wait_for_timeout(500)
        page.wait_for_timeout(100)

        screenshot_bytes = page.screenshot(
            type="png",
            full_page=False,
            omit_background=omit_background,
        )

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(screenshot_bytes)
            logger.info(f"[Playwright] 이미지 저장: {output_path}")

        return screenshot_bytes
    finally:
        page.close()


async def render_html_to_image(
    html_content: str,
    width: int = 1080,
    height: int = 1350,
    output_path: Optional[str] = None,
    device_scale_factor: float = 2.0,
) -> bytes:
    """HTML 문자열을 이미지(PNG bytes)로 변환

    Args:
        html_content: 완전한 HTML 문서 (<!DOCTYPE html>...</html>)
        width: 뷰포트 너비 (px)
        height: 뷰포트 높이 (px)
        output_path: 파일 저장 경로 (None이면 bytes만 반환)
        device_scale_factor: 해상도 배율 (2.0 = 레티나급)

    Returns:
        PNG 이미지 bytes
    """
    async with _render_semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _playwright_executor,
            _render_sync, html_content, width, height,
            output_path, device_scale_factor, False,
        )


async def render_html_to_transparent_image(
    html_content: str,
    width: int = 1080,
    height: int = 1350,
    output_path: Optional[str] = None,
    device_scale_factor: float = 2.0,
) -> bytes:
    """HTML을 투명 배경 PNG로 렌더링 (오버레이용)

    배경이 transparent인 HTML → 투명 PNG로 변환.
    기존 AI 이미지 위에 말풍선을 합성할 때 사용.
    """
    async with _render_semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _playwright_executor,
            _render_sync, html_content, width, height,
            output_path, device_scale_factor, True,
        )


# ────────────────────────────────────────────
# 한글 웹폰트 CSS (Google Fonts CDN)
# ────────────────────────────────────────────

KOREAN_FONT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&family=Nanum+Pen+Script&family=Do+Hyeon&family=Jua&family=Black+Han+Sans&family=Gaegu:wght@400;700&family=Noto+Sans+KR:wght@400;700&family=Nanum+Myeongjo:wght@400;700&family=Gothic+A1:wght@400;700&family=Sunflower:wght@300;500&family=Poor+Story&display=swap');

:root {
    --font-gothic: 'Nanum Gothic', sans-serif;
    --font-pen: 'Nanum Pen Script', cursive;
    --font-dohyeon: 'Do Hyeon', sans-serif;
    --font-jua: 'Jua', sans-serif;
    --font-blackhan: 'Black Han Sans', sans-serif;
    --font-gaegu: 'Gaegu', cursive;
    --font-notosans: 'Noto Sans KR', sans-serif;
    --font-myeongjo: 'Nanum Myeongjo', serif;
    --font-gothica1: 'Gothic A1', sans-serif;
    --font-sunflower: 'Sunflower', sans-serif;
    --font-poorstory: 'Poor Story', cursive;
}
"""


# ────────────────────────────────────────────
# 말풍선 오버레이 HTML 빌더 (웹툰용)
# ────────────────────────────────────────────

def build_bubble_overlay_html(
    dialogues: list,
    narration: str = "",
    width: int = 1080,
    height: int = 1350,
    font_family: str = "Nanum Gothic",
    style: str = "round",
) -> str:
    """말풍선 + 나레이션 오버레이 HTML 생성

    Args:
        dialogues: [{"character": "민지", "text": "안녕!", "position": "top-left"}, ...]
        narration: 상단 나레이션 텍스트
        width: 이미지 너비
        height: 이미지 높이
        font_family: 한글 폰트 이름
        style: round | square | shout | thought

    Returns:
        투명 배경 HTML 문자열
    """
    bubble_styles = {
        "round":    "border-radius: 20px; background: rgba(255,255,255,0.95);",
        "square":   "border-radius: 6px; background: rgba(255,255,255,0.95);",
        "shout":    "border-radius: 4px; background: #fff; border: 3px solid #000; font-weight: 800;",
        "thought":  "border-radius: 50% / 40%; background: rgba(255,255,255,0.9); border: 2px dashed #888; font-style: italic;",
        "whisper":  "border-radius: 14px; background: rgba(255,255,255,0.7); border: 1px solid #aaa; font-style: italic; opacity: 0.7;",
        "scream":   "border-radius: 2px; background: #fff; border: 4px solid #000; font-weight: 900;",
        "cloud":    "border-radius: 30px 30px 30px 5px; background: rgba(255,255,255,0.95); border: 2px solid #555;",
        "dark":     "border-radius: 4px; background: rgba(30,30,30,0.92); color: #fff; border: 2px solid #555;",
        "emphasis": "border-radius: 12px; background: rgba(255,255,255,0.95); border: 2px solid #000; font-weight: 700;",
        "system":   "border-radius: 0px; background: rgba(240,240,240,0.9); border: 1px solid #999; font-family: 'Nanum Gothic', sans-serif;",
        "soft":     "border-radius: 22px; background: rgba(255,255,255,0.95); border: none; box-shadow: 0 4px 16px rgba(0,0,0,0.12);",
    }

    bubble_css = bubble_styles.get(style, bubble_styles["round"])

    # 위치 매핑 (상단 여백 25% 기준)
    position_map = {
        "top-left":     "top: 5%; left: 5%;",
        "top-center":   "top: 5%; left: 50%; transform: translateX(-50%);",
        "top-right":    "top: 5%; right: 5%;",
        "mid-left":     "top: 30%; left: 5%;",
        "mid-center":   "top: 30%; left: 50%; transform: translateX(-50%);",
        "mid-right":    "top: 30%; right: 5%;",
        "bottom-left":  "bottom: 15%; left: 5%;",
        "bottom-center": "bottom: 15%; left: 50%; transform: translateX(-50%);",
        "bottom-right": "bottom: 15%; right: 5%;",
    }

    # 대사 HTML
    bubbles_html = ""
    for i, d in enumerate(dialogues[:3]):  # 최대 3개
        pos = d.get("position", "top-left" if i == 0 else "top-right" if i == 1 else "mid-left")
        pos_css = position_map.get(pos, position_map["top-left"])
        text = d.get("text", "")
        char_name = d.get("character", "")

        bubbles_html += f"""
        <div class="bubble" style="position: absolute; {pos_css} {bubble_css}
            padding: 12px 18px; max-width: 45%; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            font-size: 18px; line-height: 1.5; color: #111; z-index: 10;">
            {f'<div style="font-size:12px; color:#666; margin-bottom:4px; font-weight:700;">{char_name}</div>' if char_name else ''}
            <div>{text}</div>
        </div>
        """

    # 나레이션 HTML (상단 중앙)
    narration_html = ""
    if narration:
        narration_html = f"""
        <div class="narration" style="position: absolute; top: 2%; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.7); color: #fff; padding: 8px 20px; border-radius: 4px;
            font-size: 15px; max-width: 80%; text-align: center; z-index: 10; line-height: 1.4;">
            {narration}
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{KOREAN_FONT_CSS}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px;
    height: {height}px;
    background: transparent;
    font-family: '{font_family}', 'Nanum Gothic', sans-serif;
    position: relative;
    overflow: hidden;
}}
</style>
</head>
<body>
{narration_html}
{bubbles_html}
</body>
</html>"""

    return html


# ────────────────────────────────────────────
# 캐러셀/카드뉴스 슬라이드 HTML 빌더
# ────────────────────────────────────────────

def build_slide_html(
    title: str = "",
    body: str = "",
    page_number: str = "",
    bg_color: str = "#FFFFFF",
    text_color: str = "#111111",
    accent_color: str = "#6366f1",
    font_family: str = "Nanum Gothic",
    width: int = 1080,
    height: int = 1080,
    template: str = "centered",
    # Phase 1 파라미터 (모두 기본값 → 하위 호환)
    is_cover: bool = False,
    is_last: bool = False,
    last_type: str = None,
    # Phase 2 파라미터
    title_size: str = "medium",
    spacing: str = "normal",
    title_accent: str = "none",
    bg_gradient: str = None,
    logo_base64: str = None,
) -> str:
    """캐러셀/카드뉴스 슬라이드 HTML 생성

    Args:
        title: 제목
        body: 본문
        page_number: 페이지 번호 (예: "1/5")
        bg_color: 배경색
        text_color: 텍스트 색상
        accent_color: 강조색
        font_family: 폰트
        width/height: 슬라이드 크기
        template: centered | left-aligned | highlight
        is_cover: 첫 슬라이드(커버) 여부
        is_last: 마지막 슬라이드 여부
        last_type: 마지막 페이지 타입 (summary | cta | branding)
        title_size: 제목 크기 (large | medium | small)
        spacing: 여백 (compact | normal | spacious)
        title_accent: 제목 강조 (none | underline | highlight | box)
        bg_gradient: CSS 그래디언트 문자열
        logo_base64: 로고 base64 데이터

    Returns:
        HTML 문자열
    """
    # --- 제목 크기 배율 ---
    size_scale = {"large": 1.3, "medium": 1.0, "small": 0.8}.get(title_size, 1.0)

    # --- 여백/줄간격 ---
    spacing_map = {
        "compact": ("40px", "1.2"),
        "normal": ("60px", "1.5"),
        "spacious": ("80px", "1.8"),
    }
    pad, lh = spacing_map.get(spacing, ("60px", "1.5"))

    # --- 템플릿별 기본 제목 크기 ---
    base_sizes = {
        "centered": 44,
        "left-aligned": 42,
        "highlight": 48,
    }
    base_title_size = base_sizes.get(template, 44)
    final_title_size = int(base_title_size * size_scale)

    # --- 커버 슬라이드 오버라이드 ---
    if is_cover:
        final_title_size = int(60 * size_scale)

    # --- 마지막 슬라이드(브랜딩) 오버라이드 ---
    if is_last and last_type == "branding":
        final_title_size = int(52 * size_scale)

    # --- 템플릿별 레이아웃 ---
    if template == "left-aligned":
        layout_css = f"text-align: left; padding: {pad};"
        title_color = text_color
        body_opacity = "opacity: 0.85;"
        text_align_title = ""
        text_align_body = ""
        max_width_body = ""
    elif template == "highlight":
        layout_css = f"display: flex; flex-direction: column; justify-content: center; align-items: center; padding: {pad};"
        title_color = accent_color
        body_opacity = ""
        text_align_title = "text-align: center;"
        text_align_body = "text-align: center;"
        max_width_body = "max-width: 85%;"
    else:  # centered
        layout_css = f"display: flex; flex-direction: column; justify-content: center; align-items: center; padding: {pad};"
        title_color = text_color
        body_opacity = "opacity: 0.85;"
        text_align_title = "text-align: center;"
        text_align_body = "text-align: center;"
        max_width_body = "max-width: 85%;"

    # --- 제목 강조 스타일 ---
    accent_styles = {
        "none": "",
        "underline": f"border-bottom: 4px solid {accent_color}; display: inline-block; padding-bottom: 4px;",
        "highlight": f"background: linear-gradient(transparent 60%, {accent_color}40 60%); display: inline;",
        "box": f"border: 3px solid {accent_color}; padding: 8px 16px; display: inline-block;",
    }
    title_accent_css = accent_styles.get(title_accent, "")

    # --- 배경 CSS ---
    if bg_gradient:
        background_css = f"background: {bg_gradient};"
    else:
        background_css = f"background: {bg_color};"

    # --- 커버 슬라이드 특별 처리 ---
    body_html = f'<div class="slide-body">{body}</div>' if body else ""
    if is_cover:
        # 커버: 본문을 부제 스타일로
        body_html = f'<div class="slide-body" style="font-size: 20px; opacity: 0.6; margin-top: 16px;">{body}</div>' if body else ""

    # --- 마지막 슬라이드(브랜딩) 특별 처리 ---
    if is_last and last_type == "branding":
        body_html = f'<div class="slide-body" style="font-size: 18px; opacity: 0.5; margin-top: 20px;">{body}</div>' if body else ""

    # --- 페이지 번호 (커버에서는 숨김) ---
    page_html = ""
    if page_number and not is_cover:
        page_html = f'<div style="position:absolute; bottom:30px; right:40px; font-size:16px; color:{text_color}; opacity:0.4;">{page_number}</div>'

    # --- 로고/워터마크 ---
    logo_html = ""
    if logo_base64:
        if is_last and last_type == "branding":
            # 브랜딩 페이지: 중앙 큰 로고
            logo_html = f'<div style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); opacity:0.15;"><img src="data:image/png;base64,{logo_base64}" style="width:120px; height:120px; object-fit:contain;" /></div>'
        else:
            # 일반 워터마크: 우하단
            logo_html = f'<div style="position:absolute; bottom:25px; left:40px; opacity:0.5;"><img src="data:image/png;base64,{logo_base64}" style="width:60px; height:60px; object-fit:contain;" /></div>'

    # --- 커버 배경 악센트 ---
    cover_accent_html = ""
    if is_cover:
        cover_accent_html = f'<div style="position:absolute; bottom:0; left:0; right:0; height:6px; background:{accent_color};"></div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{KOREAN_FONT_CSS}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px;
    height: {height}px;
    {background_css}
    font-family: '{font_family}', 'Nanum Gothic', sans-serif;
    position: relative;
    overflow: hidden;
    {layout_css}
}}
.slide-title {{
    font-size: {final_title_size}px;
    font-weight: 800;
    color: {title_color};
    margin-bottom: 24px;
    line-height: 1.3;
    {text_align_title}
    {title_accent_css}
}}
.slide-body {{
    font-size: 22px;
    color: {text_color};
    {body_opacity}
    line-height: {lh};
    {text_align_body}
    {max_width_body}
}}
</style>
</head>
<body>
    <div class="slide-title">{title}</div>
    {body_html}
    {page_html}
    {logo_html}
    {cover_accent_html}
</body>
</html>"""

    return html


# ────────────────────────────────────────────
# 이미지 합성 (AI 이미지 + 말풍선 오버레이)
# ────────────────────────────────────────────

async def composite_bubble_on_image(
    base_image_path: str,
    dialogues: list,
    narration: str = "",
    output_path: Optional[str] = None,
    font_family: str = "Nanum Gothic",
    bubble_style: str = "round",
) -> bytes:
    """AI 생성 이미지 위에 말풍선 오버레이를 합성

    1. base_image_path에서 원본 이미지 로드 (크기 측정)
    2. 같은 크기로 투명 말풍선 오버레이 렌더링
    3. Pillow로 합성

    Returns:
        최종 합성 이미지 PNG bytes
    """
    from PIL import Image
    from io import BytesIO

    # 1. 원본 이미지 크기 확인
    base_img = Image.open(base_image_path).convert("RGBA")
    w, h = base_img.size

    # 2. 말풍선 오버레이 HTML 생성 + 렌더링
    overlay_html = build_bubble_overlay_html(
        dialogues=dialogues,
        narration=narration,
        width=w,
        height=h,
        font_family=font_family,
        style=bubble_style,
    )

    overlay_bytes = await render_html_to_transparent_image(
        html_content=overlay_html,
        width=w,
        height=h,
        device_scale_factor=1.0,  # 원본과 동일 크기
    )

    # 3. Pillow로 합성
    overlay_img = Image.open(BytesIO(overlay_bytes)).convert("RGBA")

    # 크기 맞춤 (안전)
    if overlay_img.size != base_img.size:
        overlay_img = overlay_img.resize(base_img.size, Image.LANCZOS)

    result = Image.alpha_composite(base_img, overlay_img)
    result_rgb = result.convert("RGB")

    # 저장
    buf = BytesIO()
    result_rgb.save(buf, format="PNG")
    result_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(result_bytes)
        logger.info(f"[Playwright] 합성 이미지 저장: {output_path}")

    return result_bytes


def build_summary_slide_html(
    summary_text: str,
    style: str = "text_card",
    story_title: str = "",
    width: int = 1080,
    height: int = 1350,
    bg_color: str = "#1a1a2e",
    text_color: str = "#FFFFFF",
    accent_color: str = "#e94560",
    font_family: str = "Nanum Gothic",
) -> str:
    """요약 슬라이드용 HTML 생성 — 전문 디자인 v3 (밝고 깔끔한 톤)"""
    import html as html_mod
    import re as _re

    safe_title = html_mod.escape(story_title) if story_title else ""
    safe_text = summary_text or ""

    # ── 스타일별 색상 팔레트 (밝고 세련된 톤) ──
    palettes = {
        "table":     {"bg": "#f8fafc", "card": "#ffffff", "accent": "#2563eb", "text": "#1e293b", "muted": "#64748b", "accent_light": "#dbeafe", "border": "#e2e8f0"},
        "checklist": {"bg": "#f9fafb", "card": "#ffffff", "accent": "#059669", "text": "#1c1917", "muted": "#6b7280", "accent_light": "#d1fae5", "border": "#e5e7eb"},
        "qa":        {"bg": "#faf5ff", "card": "#ffffff", "accent": "#7c3aed", "text": "#1e1b4b", "muted": "#6b7280", "accent_light": "#ede9fe", "border": "#e9e5f5"},
        "steps":     {"bg": "#fff7ed", "card": "#ffffff", "accent": "#ea580c", "text": "#1c1917", "muted": "#78716c", "accent_light": "#ffedd5", "border": "#fed7aa"},
        "highlight": {"bg": "#fffbeb", "card": "#ffffff", "accent": "#d97706", "text": "#1c1917", "muted": "#78716c", "accent_light": "#fef3c7", "border": "#fde68a"},
        "text_card": {"bg": "#f0fdf4", "card": "#ffffff", "accent": "#059669", "text": "#1c1917", "muted": "#6b7280", "accent_light": "#d1fae5", "border": "#a7f3d0"},
    }
    p = palettes.get(style, palettes["text_card"])

    # ── 공통 헤더/배지 ──
    badge_html = f"""<div class="badge">\u2728 \uc694\uc57d \uc815\ub9ac</div>"""
    title_html = f"""<div class="title">{safe_title}</div>""" if safe_title else ""

    # ── 스타일별 본문 HTML ──
    body_html = ""
    extra_css = ""

    if style == "table":
        rows = []
        for line in safe_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells:
                rows.append(cells)
        if rows:
            header = rows[0]
            data_rows = rows[1:] if len(rows) > 1 else []
            th_html = "".join(f"<th>{html_mod.escape(c)}</th>" for c in header)
            tr_html = ""
            for ri, row in enumerate(data_rows):
                cls = ' class="alt"' if ri % 2 == 1 else ""
                td_html = "".join(f"<td>{html_mod.escape(c)}</td>" for c in row)
                tr_html += f"<tr{cls}>{td_html}</tr>"
            body_html = f"""<div class="table-wrap"><table><thead><tr>{th_html}</tr></thead><tbody>{tr_html}</tbody></table></div>"""
        extra_css = f"""
.table-wrap {{ flex:1; display:flex; align-items:flex-start; overflow:hidden; margin-top:28px; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; border-radius:16px; overflow:hidden; border:1px solid {p['border']}; }}
thead th {{ background:{p['accent']}; color:#fff; padding:22px 28px; font-size:26px; font-weight:800; text-align:left; letter-spacing:0.01em; }}
thead th:not(:last-child) {{ border-right:1px solid rgba(255,255,255,0.2); }}
tbody td {{ padding:20px 28px; font-size:24px; color:{p['text']}; border-bottom:1px solid {p['border']}; line-height:1.6; background:{p['card']}; }}
tbody td:not(:last-child) {{ border-right:1px solid {p['border']}; }}
tbody tr.alt td {{ background:{p['accent_light']}40; }}
tbody tr:last-child td {{ border-bottom:none; }}
"""

    elif style == "checklist":
        items = []
        for line in safe_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            line = _re.sub(r'^[-\u2022]\s*', '', line)
            line = _re.sub(r'^\[[ x]?\]\s*', '', line)
            items.append(f"""<div class="check-item">
<div class="check-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="{p['accent_light']}"/><path d="M8 12l3 3 5-5" stroke="{p['accent']}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
<div class="check-text">{html_mod.escape(line)}</div>
</div>""")
        body_html = f"""<div class="check-list">{"".join(items)}</div>"""
        extra_css = f"""
.check-list {{ flex:1; display:flex; flex-direction:column; gap:14px; margin-top:28px; }}
.check-item {{ display:flex; align-items:flex-start; gap:18px; background:{p['card']}; border-radius:14px; padding:22px 28px; border:1px solid {p['border']}; border-left:4px solid {p['accent']}; }}
.check-icon {{ flex-shrink:0; margin-top:2px; }}
.check-text {{ font-size:25px; line-height:1.6; color:{p['text']}; font-weight:500; }}
"""

    elif style == "qa":
        blocks = []
        lines = safe_text.strip().split("\n")

        # 테이블 형식(| col |) 감지 → 자동 변환
        has_pipe = any("|" in l for l in lines)
        if has_pipe:
            clean_lines = []
            header_row = None
            for line in lines:
                line = line.strip()
                if not line or line.startswith("---") or _re.match(r'^[\s\-|]+$', line):
                    continue
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if not cells:
                    continue
                if header_row is None:
                    header_row = cells
                else:
                    if len(cells) >= 2:
                        clean_lines.append((cells[0], " / ".join(cells[1:])))
                    else:
                        clean_lines.append((cells[0], ""))
            for qi, (q_val, a_val) in enumerate(clean_lines, 1):
                blocks.append(f"""<div class="qa-block">
<div class="qa-q"><span class="qa-badge">Q{qi}</span><span class="qa-q-text">{html_mod.escape(q_val)}</span></div>
<div class="qa-a"><span class="qa-badge qa-badge-a">A</span><span class="qa-a-text">{html_mod.escape(a_val)}</span></div>
</div>""")
        else:
            i = 0
            qa_num = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                is_q = (
                    line.upper().startswith("Q:") or line.upper().startswith("Q.")
                    or line.upper().startswith("Q ") or _re.match(r'^Q\d', line.upper())
                )
                if is_q:
                    qa_num += 1
                    q_text = _re.sub(r'^[Qq][\.:)]\s*', '', line).strip()
                    q_text = _re.sub(r'^[Qq]\d+[\.:)]\s*', '', q_text).strip()
                    q = html_mod.escape(q_text) if q_text else html_mod.escape(line)
                    a = ""
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        is_a = (
                            next_line.upper().startswith("A:") or next_line.upper().startswith("A.")
                            or next_line.upper().startswith("A ") or _re.match(r'^A\d', next_line.upper())
                        )
                        if is_a:
                            a_text = _re.sub(r'^[Aa][\.:)]\s*', '', next_line).strip()
                            a_text = _re.sub(r'^[Aa]\d+[\.:)]\s*', '', a_text).strip()
                            a = html_mod.escape(a_text) if a_text else html_mod.escape(next_line)
                            i += 1
                        elif not next_line.upper().startswith("Q"):
                            a = html_mod.escape(next_line)
                            i += 1
                    blocks.append(f"""<div class="qa-block">
<div class="qa-q"><span class="qa-badge">Q{qa_num}</span><span class="qa-q-text">{q}</span></div>
<div class="qa-a"><span class="qa-badge qa-badge-a">A</span><span class="qa-a-text">{a}</span></div>
</div>""")
                else:
                    qa_num += 1
                    blocks.append(f"""<div class="qa-block">
<div class="qa-q"><span class="qa-badge">Q{qa_num}</span><span class="qa-q-text">{html_mod.escape(line)}</span></div>
<div class="qa-a"><span class="qa-badge qa-badge-a">A</span><span class="qa-a-text"></span></div>
</div>""")
                i += 1
        body_html = f"""<div class="qa-list">{"".join(blocks)}</div>"""
        extra_css = f"""
.qa-list {{ flex:1; display:flex; flex-direction:column; gap:18px; margin-top:28px; }}
.qa-block {{ background:{p['card']}; border-radius:16px; padding:28px 32px; border:1px solid {p['border']}; }}
.qa-q {{ display:flex; align-items:flex-start; gap:16px; margin-bottom:18px; }}
.qa-a {{ display:flex; align-items:flex-start; gap:16px; padding-top:18px; border-top:1px dashed {p['border']}; }}
.qa-badge {{ display:inline-flex; align-items:center; justify-content:center; min-width:42px; height:42px; border-radius:12px; background:{p['accent']}; color:#fff; font-weight:900; font-size:20px; flex-shrink:0; }}
.qa-badge-a {{ background:{p['accent_light']}; color:{p['accent']}; }}
.qa-q-text {{ font-size:26px; font-weight:700; color:{p['text']}; line-height:1.5; padding-top:6px; }}
.qa-a-text {{ font-size:24px; color:{p['muted']}; line-height:1.7; padding-top:8px; }}
"""

    elif style == "steps":
        steps = []
        for idx_s, line in enumerate(safe_text.strip().split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            line = _re.sub(r'^\d+[\.\)\-\ub2e8\uacc4:]+\s*', '', line)
            steps.append(f"""<div class="step-item">
<div class="step-left">
    <div class="step-num">{idx_s}</div>
    <div class="step-line"></div>
</div>
<div class="step-card">{html_mod.escape(line)}</div>
</div>""")
        body_html = f"""<div class="step-list">{"".join(steps)}</div>"""
        extra_css = f"""
.step-list {{ flex:1; display:flex; flex-direction:column; margin-top:28px; }}
.step-item {{ display:flex; gap:20px; }}
.step-left {{ display:flex; flex-direction:column; align-items:center; }}
.step-num {{ width:52px; height:52px; border-radius:50%; background:{p['accent']}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:24px; flex-shrink:0; }}
.step-line {{ width:2px; flex:1; background:{p['border']}; min-height:14px; }}
.step-item:last-child .step-line {{ display:none; }}
.step-card {{ flex:1; background:{p['card']}; border-radius:14px; padding:22px 28px; margin-bottom:14px; border:1px solid {p['border']}; border-left:3px solid {p['accent']}; font-size:25px; line-height:1.6; color:{p['text']}; font-weight:500; }}
"""

    elif style == "highlight":
        lines_hl = [l.strip() for l in safe_text.strip().split("\n") if l.strip()]
        main_text = lines_hl[0] if lines_hl else ""
        sub_text = " ".join(lines_hl[1:]) if len(lines_hl) > 1 else ""
        body_html = f"""<div class="hl-wrap">
<div class="hl-deco-line"></div>
<div class="hl-main">{html_mod.escape(main_text)}</div>
{f'<div class="hl-sub">{html_mod.escape(sub_text)}</div>' if sub_text else ''}
<div class="hl-deco-line"></div>
</div>"""
        extra_css = f"""
.hl-wrap {{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:48px; gap:28px; }}
.hl-deco-line {{ width:80px; height:4px; background:{p['accent']}; border-radius:2px; }}
.hl-main {{ font-size:52px; font-weight:900; color:{p['accent']}; line-height:1.35; letter-spacing:-0.02em; max-width:90%; }}
.hl-sub {{ font-size:26px; color:{p['muted']}; line-height:1.7; max-width:85%; font-weight:400; }}
"""

    else:  # text_card
        paragraphs = []
        for line in safe_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            paragraphs.append(f"<p>{html_mod.escape(line)}</p>")
        body_html = f"""<div class="tc-wrap">{"".join(paragraphs)}</div>"""
        extra_css = f"""
.tc-wrap {{ flex:1; background:{p['card']}; border-radius:20px; padding:44px 48px; margin-top:24px; border:1px solid {p['border']}; overflow:hidden; }}
.tc-wrap p {{ font-size:26px; line-height:1.8; color:{p['text']}; margin:0 0 18px 0; }}
.tc-wrap p:last-child {{ margin-bottom:0; }}
.tc-wrap p:first-child {{ font-size:28px; font-weight:700; color:{p['accent']}; margin-bottom:24px; padding-bottom:18px; border-bottom:2px solid {p['border']}; }}
"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{width}px; height:{height}px;
    background:{p['bg']};
    color:{p['text']};
    font-family:'Noto Sans KR', '{font_family}', sans-serif;
    padding:0; margin:0;
    overflow:visible;
}}
#wrap {{
    display:flex; flex-direction:column;
    padding:64px 56px 56px;
}}
.badge {{
    display:inline-flex; align-items:center; gap:8px;
    background:{p['accent']};
    color:#fff; padding:10px 24px; border-radius:40px;
    font-size:20px; font-weight:700; letter-spacing:0.03em;
    align-self:flex-start; margin-bottom:20px;
}}
.title {{
    font-size:36px; font-weight:900; color:{p['text']};
    line-height:1.3; margin-bottom:4px; letter-spacing:-0.02em;
    padding-bottom:20px;
    border-bottom:2px solid {p['border']};
}}
{extra_css}
</style></head>
<body>
<div id="wrap">
{badge_html}
{title_html}
{body_html}
</div>
<script>
(function(){{
    var w=document.getElementById('wrap');
    var body=document.body;
    var maxH=body.clientHeight;
    var realH=w.scrollHeight;
    if(realH>maxH){{
        var s=maxH/realH;
        if(s<0.55) s=0.55;
        w.style.transform='scale('+s+')';
        w.style.transformOrigin='top left';
        w.style.width=(100/s)+'%';
    }}
}})();
</script>
</body></html>"""
