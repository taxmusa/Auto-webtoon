"""
Playwright 렌더링 서비스
- HTML/CSS → 이미지 변환 (말풍선, 캐러셀, 카드뉴스)
- 한글 웹폰트 지원
- 고품질 스크린샷 (2x 해상도)
"""
import asyncio
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Playwright 브라우저 인스턴스 (싱글톤)
_browser = None
_playwright = None


async def _get_browser():
    """Playwright 브라우저 싱글톤 반환 (재시도 포함)"""
    global _browser, _playwright

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
    browser = await _get_browser()
    page = await browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )

    try:
        await page.set_content(html_content, wait_until="networkidle")
        # 폰트 로딩 대기 (최대 3초)
        await page.wait_for_timeout(500)

        screenshot_bytes = await page.screenshot(
            type="png",
            full_page=False,  # 뷰포트 크기 그대로
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
    browser = await _get_browser()
    page = await browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )

    try:
        await page.set_content(html_content, wait_until="networkidle")
        await page.wait_for_timeout(500)

        screenshot_bytes = await page.screenshot(
            type="png",
            full_page=False,
            omit_background=True,  # 투명 배경
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
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&family=Nanum+Pen+Script&family=Do+Hyeon&family=Jua&family=Black+Han+Sans&family=Gaegu:wght@400;700&display=swap');

:root {
    --font-gothic: 'Nanum Gothic', sans-serif;
    --font-pen: 'Nanum Pen Script', cursive;
    --font-dohyeon: 'Do Hyeon', sans-serif;
    --font-jua: 'Jua', sans-serif;
    --font-blackhan: 'Black Han Sans', sans-serif;
    --font-gaegu: 'Gaegu', cursive;
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
) -> str:
    """캐러셀/카드뉴스 슬라이드 HTML 생성

    Args:
        title: 제목
        body: 본문
        page_number: 페이지 번호 표시 (예: "1/5")
        bg_color: 배경색
        text_color: 텍스트 색상
        accent_color: 강조색
        font_family: 폰트
        width/height: 슬라이드 크기
        template: centered | left-aligned | two-column | highlight

    Returns:
        HTML 문자열
    """
    # 템플릿별 레이아웃
    if template == "left-aligned":
        layout_css = "text-align: left; padding: 80px 60px;"
        title_css = f"font-size: 42px; font-weight: 800; color: {text_color}; margin-bottom: 24px; line-height: 1.3;"
        body_css = f"font-size: 22px; color: {text_color}; opacity: 0.85; line-height: 1.7;"
    elif template == "highlight":
        layout_css = "display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px;"
        title_css = f"font-size: 48px; font-weight: 800; color: {accent_color}; margin-bottom: 30px; text-align: center; line-height: 1.3;"
        body_css = f"font-size: 24px; color: {text_color}; text-align: center; line-height: 1.7; max-width: 85%;"
    else:  # centered (기본)
        layout_css = "display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px;"
        title_css = f"font-size: 44px; font-weight: 800; color: {text_color}; margin-bottom: 24px; text-align: center; line-height: 1.3;"
        body_css = f"font-size: 22px; color: {text_color}; opacity: 0.85; text-align: center; line-height: 1.7; max-width: 85%;"

    page_html = ""
    if page_number:
        page_html = f'<div style="position:absolute; bottom:30px; right:40px; font-size:16px; color:{text_color}; opacity:0.4;">{page_number}</div>'

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
    background: {bg_color};
    font-family: '{font_family}', 'Nanum Gothic', sans-serif;
    position: relative;
    overflow: hidden;
    {layout_css}
}}
</style>
</head>
<body>
    <div style="{title_css}">{title}</div>
    <div style="{body_css}">{body}</div>
    {page_html}
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
