"""
Playwright 렌더링 서비스
- HTML/CSS → 이미지 변환 (말풍선, 캐러셀, 카드뉴스)
- 한글 웹폰트 지원 (Google Fonts 11종)
- 고품질 스크린샷 (2x 해상도)
- document.fonts.ready 대기로 폰트 로딩 보장 (R1)
- asyncio.Lock 으로 브라우저 초기화 경합 방지 (R2 준비)
"""
import asyncio
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Playwright 브라우저 인스턴스 (싱글톤)
_browser = None
_playwright = None
_browser_lock = asyncio.Lock()  # R2: 브라우저 초기화 경합 방지
_render_semaphore = asyncio.Semaphore(3)  # R2: 동시 렌더링 3개 제한


async def _get_browser():
    """Playwright 브라우저 싱글톤 반환 (재시도 포함, Lock으로 경합 방지)"""
    global _browser, _playwright

    if _browser and _browser.is_connected():
        return _browser

    async with _browser_lock:
        # 더블체크 (Lock 대기 중 다른 코루틴이 이미 생성했을 수 있음)
        if _browser and _browser.is_connected():
            return _browser

        # 기존 인스턴스 정리
        if _browser:
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None
        if _playwright:
            try:
                await _playwright.stop()
            except Exception:
                pass
            _playwright = None

        from playwright.async_api import async_playwright

        for attempt in range(3):
            try:
                _playwright = await async_playwright().start()
                _browser = await _playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                logger.info("[Playwright] 브라우저 시작됨")
                return _browser
            except Exception as e:
                logger.warning(f"[Playwright] 브라우저 시작 실패 (시도 {attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"Playwright 브라우저를 시작할 수 없습니다: {e}")


async def shutdown_browser():
    """앱 종료 시 브라우저 정리"""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


# ────────────────────────────────────────────
# 핵심 렌더링 함수
# ────────────────────────────────────────────

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
    async with _render_semaphore:  # R2: 동시 렌더링 3개 제한
        browser = await _get_browser()
        page = await browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=device_scale_factor,
        )

        try:
            await page.set_content(html_content, wait_until="networkidle")
            # R1: document.fonts.ready로 폰트 로딩 완료 대기 (최대 5초)
            try:
                await page.wait_for_function(
                    "() => document.fonts.ready.then(() => true)",
                    timeout=5000,
                )
            except Exception:
                # 폴백: 고정 대기
                await page.wait_for_timeout(500)

            screenshot_bytes = await page.screenshot(
                type="png",
                full_page=False,
            )

            if output_path:
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(screenshot_bytes)
                logger.info(f"[Playwright] 이미지 저장: {output_path}")

            return screenshot_bytes

        finally:
            await page.close()


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
        browser = await _get_browser()
        page = await browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=device_scale_factor,
        )

        try:
            await page.set_content(html_content, wait_until="networkidle")
            try:
                await page.wait_for_function(
                    "() => document.fonts.ready.then(() => true)",
                    timeout=5000,
                )
            except Exception:
                await page.wait_for_timeout(500)

            screenshot_bytes = await page.screenshot(
                type="png",
                full_page=False,
                omit_background=True,
            )

            if output_path:
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(screenshot_bytes)

            return screenshot_bytes

        finally:
            await page.close()


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
