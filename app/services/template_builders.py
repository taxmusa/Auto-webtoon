"""
카드뉴스 전용 템플릿 빌더 (card-news-templates 기반)

커버 6종 (COVER-A~F) + 본문 4종 (BODY-A~D) + 마무리 2종 (CLOSING-A~B)
= 총 12종 HTML 빌더. 기존 build_slide_html()과 별개로 동작.
template_set이 지정된 경우에만 이 빌더를 사용하고, 아니면 기존 빌더 사용.
"""
import html as html_mod
import logging

from app.services.theme_palettes import (
    get_theme,
    get_template_set,
    TYPOGRAPHY,
    LAYOUT,
    SEMANTIC_COLORS,
)

logger = logging.getLogger(__name__)

# 공통 폰트 CDN (render_service.py의 KOREAN_FONT_CSS와 동일)
_FONT_CSS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
"""


def _base_html(width: int, height: int, body_content: str, theme_name: str = "light") -> str:
    """공통 HTML 래퍼 — 폰트 로드 + 테마 CSS 변수 주입"""
    palette = get_theme(theme_name)

    # CSS 변수 생성
    css_vars = "\n".join(
        f"    --{k.replace('_', '-')}: {v};"
        for k, v in palette.items()
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{_FONT_CSS}
:root {{
{css_vars}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px;
    height: {height}px;
    background: var(--bg);
    font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
    position: relative;
    overflow: hidden;
    color: var(--text-primary);
}}
</style>
</head>
<body>
{body_content}
</body>
</html>"""


def _escape(text: str) -> str:
    """HTML 이스케이프 + 줄바꿈 → <br>"""
    return html_mod.escape(text or "").replace("\n", "<br>")


# ============================================
# 커버 슬라이드 빌더
# ============================================

def build_cover_a(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-A: 다크 BEST 리스트형 — 강렬, SNS 바이럴"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body에서 해시태그 추출 (있으면)
    tags_html = ""
    body_text = body or ""
    if "#" in body_text:
        parts = body_text.split("#")
        body_text = parts[0].strip()
        tags = [f"#{p.strip().split()[0]}" for p in parts[1:] if p.strip()][:3]
        if tags:
            tags_html = '<div style="display:flex; gap:12px; flex-wrap:wrap; margin-top:24px;">'
            for tag in tags:
                tags_html += f'<span style="border:1px solid {palette["tag_border"]}; border-radius:{LAYOUT["tag_radius"]}px; padding:{LAYOUT["tag_padding_v"]}px {LAYOUT["tag_padding_h"]}px; font-size:{TYPOGRAPHY["tag"]["size"]}px; color:var(--text-secondary);">{_escape(tag)}</span>'
            tags_html += '</div>'

    subtitle_html = f'<div style="color:{palette["accent"]}; font-size:{TYPOGRAPHY["subtitle"]["size"]}px; font-weight:{TYPOGRAPHY["subtitle"]["weight"]}; margin-bottom:16px;">{_escape(body_text)}</div>' if body_text else ""

    content = f"""
<div style="display:flex; flex-direction:column; justify-content:flex-end; height:100%; padding:{pad}px; padding-bottom:{pad + 40}px;">
    {subtitle_html}
    <div style="font-size:{TYPOGRAPHY["title_xl"]["size"]}px; font-weight:{TYPOGRAPHY["title_xl"]["weight"]}; line-height:{TYPOGRAPHY["title_xl"]["line_height"]}; color:var(--text-primary);">{_escape(title)}</div>
    {tags_html}
    <div style="margin-top:16px; font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_cover_c(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-C: 블루 리포트형 — 공신력, 전문가"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # 카테고리 레이블 (body 첫 줄 또는 기본값)
    lines = (body or "").split("\n")
    category = lines[0].strip() if lines[0].strip() else "REPORT"
    desc = "<br>".join(_escape(l) for l in lines[1:] if l.strip()) if len(lines) > 1 else ""

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 카테고리 레이블 -->
    <div style="display:flex; align-items:center; gap:16px; margin-top:20px;">
        <div style="flex:1; height:1px; background:{palette.get('divider', '#B0C4DE')};"></div>
        <div style="font-size:{TYPOGRAPHY["category"]["size"]}px; font-weight:{TYPOGRAPHY["category"]["weight"]}; color:{palette["accent"]}; text-transform:uppercase; letter-spacing:3px;">{_escape(category)}</div>
        <div style="flex:1; height:1px; background:{palette.get('divider', '#B0C4DE')};"></div>
    </div>

    <!-- 메인 제목 -->
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center;">
        <div style="font-size:{TYPOGRAPHY["title_xl"]["size"]}px; font-weight:{TYPOGRAPHY["title_xl"]["weight"]}; line-height:{TYPOGRAPHY["title_xl"]["line_height"]}; color:var(--text-primary);">{_escape(title)}</div>
    </div>

    <!-- 설명 텍스트 -->
    {"<div style='text-align:center; font-size:" + str(TYPOGRAPHY["caption"]["size"]) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY["caption"]["line_height"]) + "; margin-bottom:24px;'>" + desc + "</div>" if desc else ""}

    <!-- 핸들 -->
    <div style="text-align:center; font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary); padding-bottom:20px;">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_cover_d(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-D: 미니멀 카드형 — 깔끔, 모던"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]
    card_r = LAYOUT["card_radius"]

    # 영문 대형 제목 + 한글 부제 분리
    lines = (title or "").split("\n")
    main_title = lines[0] if lines else title
    sub_title = "<br>".join(_escape(l) for l in lines[1:]) if len(lines) > 1 else ""

    content = f"""
<div style="display:flex; justify-content:center; align-items:center; height:100%; padding:40px; background:{palette.get('surface', '#F5F5F5')};">
    <div style="background:#FFFFFF; border-radius:{card_r}px; box-shadow:0 4px 20px rgba(0,0,0,0.1); width:100%; height:100%; display:flex; flex-direction:column; justify-content:center; align-items:center; padding:{pad}px; text-align:center;">
        <!-- 메인 제목 -->
        <div style="font-size:{TYPOGRAPHY["title_en"]["size"]}px; font-weight:{TYPOGRAPHY["title_en"]["weight"]}; line-height:{TYPOGRAPHY["title_en"]["line_height"]}; color:var(--text-primary); margin-bottom:24px;">{_escape(main_title)}</div>

        <!-- 한글 부제 -->
        {"<div style='font-size:" + str(TYPOGRAPHY["subtitle"]["size"]) + "px; font-weight:" + str(TYPOGRAPHY["subtitle"]["weight"]) + "; color:var(--text-primary); margin-bottom:20px;'>" + sub_title + "</div>" if sub_title else ""}

        <!-- 설명 -->
        {"<div style='font-size:" + str(TYPOGRAPHY["caption"]["size"]) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY["caption"]["line_height"]) + ";'>" + _escape(body) + "</div>" if body else ""}

        <!-- 구분선 + 핸들 -->
        <div style="margin-top:auto; width:60%; border-top:1px solid {palette.get('divider', '#E0E0E0')}; padding-top:16px;">
            <div style="font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">@handle</div>
        </div>
    </div>
</div>"""

    return _base_html(width, height, content, theme)


def build_cover_b(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-B: 다크 카테고리형 — 전문적, 긴급성, 카테고리 배지"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body 첫 줄 = 카테고리 배지, 나머지 = 부제 설명
    lines = (body or "").split("\n")
    category = lines[0].strip() if lines and lines[0].strip() else "세무 상식 필수 정보"
    desc = "<br>".join(_escape(l) for l in lines[1:] if l.strip()) if len(lines) > 1 else ""

    # 제목에서 **키워드** 패턴을 노란색으로 강조
    import re
    title_html = _escape(title)
    # **text** → 노란색 강조
    title_html = re.sub(
        r'\*\*(.+?)\*\*',
        f'<span style="color:{SEMANTIC_COLORS["yellow"]};">\\1</span>',
        title_html,
    )

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 카테고리 배지 -->
    <div style="margin-top:60px;">
        <div style="display:inline-block; background:{palette.get('badge_bg', '#2A2A2A')}; padding:{LAYOUT['badge_padding_v']}px {LAYOUT['badge_padding_h']}px; border-radius:{LAYOUT['badge_radius']}px;">
            <span style="font-size:{TYPOGRAPHY['category']['size']}px; font-weight:{TYPOGRAPHY['category']['weight']}; color:{SEMANTIC_COLORS['yellow']}; letter-spacing:2px;">{_escape(category)}</span>
        </div>
        <div style="width:60px; height:2px; background:{palette.get('divider', '#444')}; margin-top:16px;"></div>
    </div>

    <!-- 메인 제목 -->
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center;">
        <div style="font-size:{TYPOGRAPHY['title_xl']['size']}px; font-weight:{TYPOGRAPHY['title_xl']['weight']}; line-height:{TYPOGRAPHY['title_xl']['line_height']}; color:var(--text-primary);">{title_html}</div>
    </div>

    <!-- 부제 설명 -->
    {"<div style='font-size:" + str(TYPOGRAPHY['caption']['size']) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY['caption']['line_height']) + "; margin-bottom:24px;'>" + desc + "</div>" if desc else ""}

    <!-- 핸들 -->
    <div style="font-size:{TYPOGRAPHY['handle']['size']}px; color:var(--text-secondary); padding-bottom:20px;">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_cover_e(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-E: 웜톤 질문형 — 친근, 질문형 제목, CTA 버튼"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body = 부가 설명
    desc = _escape(body) if body else ""

    # CTA 버튼 색상
    cta_bg = palette.get("cta_bg", palette["accent"])
    cta_text = palette.get("cta_text", "#FFFFFF")

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 질문형 메인 제목 -->
    <div style="margin-top:60px; font-size:{TYPOGRAPHY['title_xl']['size']}px; font-weight:{TYPOGRAPHY['title_xl']['weight']}; line-height:{TYPOGRAPHY['title_xl']['line_height']}; color:{palette['accent']};">{_escape(title)}</div>

    <!-- 부가 설명 -->
    {"<div style='font-size:" + str(TYPOGRAPHY['caption']['size']) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY['caption']['line_height']) + "; margin-top:24px;'>" + desc + "</div>" if desc else ""}

    <!-- 이미지 영역 (단색 플레이스홀더) -->
    <div style="flex:1; display:flex; align-items:center; justify-content:center; margin:32px 0;">
        <div style="width:80%; height:60%; background:{palette.get('surface', '#FFFFFF')}; border-radius:{LAYOUT['card_radius']}px; display:flex; align-items:center; justify-content:center;">
            <div style="font-size:48px; opacity:0.3;">📊</div>
        </div>
    </div>

    <!-- 하단: 브랜드 + CTA -->
    <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:20px;">
        <div>
            <div style="font-size:{TYPOGRAPHY['caption']['size']}px; color:var(--text-secondary); font-weight:600;">@handle</div>
        </div>
        <div style="background:{cta_bg}; color:{cta_text}; padding:10px 24px; border-radius:20px; font-size:{TYPOGRAPHY['tag']['size']}px; font-weight:600;">넘겨보기 →</div>
    </div>
</div>"""

    return _base_html(width, height, content, theme)


def build_cover_f(title: str, body: str, width: int, height: int, theme: str) -> str:
    """COVER-F: 틸 리포트형 — 세련, 트렌디, 영문 대형 제목"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body = 한글 서브 설명
    desc = _escape(body) if body else ""

    content = f"""
<div style="display:flex; flex-direction:column; justify-content:center; height:100%; padding:{pad}px;">
    <!-- 영문 대형 제목 -->
    <div style="font-size:{TYPOGRAPHY['title_en']['size']}px; font-weight:{TYPOGRAPHY['title_en']['weight']}; line-height:{TYPOGRAPHY['title_en']['line_height']}; color:var(--text-primary);">{_escape(title)}</div>

    <!-- 한글 서브 설명 -->
    {"<div style='font-size:" + str(TYPOGRAPHY['caption']['size']) + "px; color:" + palette['accent'] + "; line-height:" + str(TYPOGRAPHY['caption']['line_height']) + "; margin-top:32px;'>" + desc + "</div>" if desc else ""}

    <!-- 우측 하단 버튼 -->
    <div style="position:absolute; bottom:{pad}px; right:{pad}px;">
        <div style="width:56px; height:56px; border-radius:50%; background:{palette.get('btn_bg', palette.get('surface', '#2A5A5A'))}; display:flex; align-items:center; justify-content:center; font-size:24px; color:var(--text-primary);">▶</div>
    </div>
</div>"""

    return _base_html(width, height, content, theme)


# ============================================
# 본문 슬라이드 빌더
# ============================================

def build_body_a(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """BODY-A: 넘버링 리스트형 — 포인트별 정보 나열"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body를 줄바꿈으로 분리하여 항목 추출
    items = []
    if body:
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            # "1. 제목: 설명" 또는 "- 제목: 설명" 패턴
            clean = line.lstrip("0123456789.-) ·•▪▸►★☆✓✔ ")
            if ":" in clean:
                parts = clean.split(":", 1)
                items.append({"title": parts[0].strip(), "desc": parts[1].strip()})
            else:
                items.append({"title": clean, "desc": ""})

    items_html = ""
    for i, item in enumerate(items[:5]):  # 최대 5개
        num = f"{i + 1:02d}"
        items_html += f"""
        <div style="display:flex; gap:20px; align-items:flex-start; margin-bottom:{LAYOUT["element_gap"]}px;">
            <div style="min-width:48px; height:48px; border-radius:50%; background:{palette["accent"]}; color:{palette["bg"]}; display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:800;">{num}</div>
            <div style="flex:1;">
                <div style="font-size:{TYPOGRAPHY["body_bold"]["size"]}px; font-weight:{TYPOGRAPHY["body_bold"]["weight"]}; color:var(--text-primary); margin-bottom:4px;">{_escape(item["title"])}</div>
                {"<div style='font-size:" + str(TYPOGRAPHY["body"]["size"]) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY["body"]["line_height"]) + ";'>" + _escape(item["desc"]) + "</div>" if item["desc"] else ""}
            </div>
        </div>"""

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 헤더 -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div style="font-size:{TYPOGRAPHY["subtitle"]["size"]}px; font-weight:{TYPOGRAPHY["subtitle"]["weight"]}; color:var(--text-primary);">{_escape(title)}</div>
        <div style="font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">{page_num}</div>
    </div>
    <div style="height:{LAYOUT["divider_thickness"]}px; background:var(--divider); margin-bottom:{LAYOUT["section_gap"]}px;"></div>

    <!-- 항목 리스트 -->
    <div style="flex:1;">
        {items_html}
    </div>

    <!-- 하단 핸들 -->
    <div style="font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_body_b(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """BODY-B: 비교형 (O/X, Before/After)"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]
    card_r = LAYOUT["card_radius"]

    # body에서 비교 항목 추출: "X: ..." / "O: ..." 또는 "전: ..." / "후: ..."
    bad_items = []
    good_items = []
    key_point = ""

    if body:
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith(("x:", "x ", "✕", "❌", "전:")):
                bad_items.append(line.split(":", 1)[-1].strip() if ":" in line else line[1:].strip())
            elif lower.startswith(("o:", "o ", "✓", "✔", "⭕", "후:")):
                good_items.append(line.split(":", 1)[-1].strip() if ":" in line else line[1:].strip())
            elif lower.startswith(("💡", "포인트:", "핵심:")):
                key_point = line.split(":", 1)[-1].strip() if ":" in line else line[2:].strip()
            else:
                # 기본: 짝수는 bad, 홀수는 good으로 분배
                if len(bad_items) <= len(good_items):
                    bad_items.append(line)
                else:
                    good_items.append(line)

    bad_html = "".join(f'<div style="font-size:{TYPOGRAPHY["body"]["size"]}px; color:var(--text-primary); margin-bottom:8px; text-decoration:line-through; opacity:0.7;">{_escape(item)}</div>' for item in bad_items[:4])
    good_html = "".join(f'<div style="font-size:{TYPOGRAPHY["body"]["size"]}px; color:var(--text-primary); margin-bottom:8px;">{_escape(item)}</div>' for item in good_items[:4])

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 헤더 -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div style="font-size:{TYPOGRAPHY["subtitle"]["size"]}px; font-weight:{TYPOGRAPHY["subtitle"]["weight"]}; color:var(--text-primary);">{_escape(title)}</div>
        <div style="font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">{page_num}</div>
    </div>
    <div style="height:{LAYOUT["divider_thickness"]}px; background:var(--divider); margin-bottom:{LAYOUT["section_gap"]}px;"></div>

    <!-- 비교 카드 -->
    <div style="flex:1; display:flex; gap:24px;">
        <!-- BAD -->
        <div style="flex:1; background:{palette["card_bg"]}; border:1px solid {palette.get("bad_color", "#FF6B6B")}30; border-radius:{card_r}px; padding:{LAYOUT["card_padding"]}px;">
            <div style="font-size:20px; font-weight:800; color:{palette.get("bad_color", "#FF6B6B")}; margin-bottom:16px; text-align:center;">✕ BEFORE</div>
            <div style="border-top:2px solid {palette.get("bad_color", "#FF6B6B")}30; padding-top:16px;">
                {bad_html}
            </div>
        </div>
        <!-- GOOD -->
        <div style="flex:1; background:{palette["card_bg"]}; border:1px solid {palette.get("good_color", "#4CAF50")}30; border-radius:{card_r}px; padding:{LAYOUT["card_padding"]}px;">
            <div style="font-size:20px; font-weight:800; color:{palette.get("good_color", "#4CAF50")}; margin-bottom:16px; text-align:center;">✓ AFTER</div>
            <div style="border-top:2px solid {palette.get("good_color", "#4CAF50")}30; padding-top:16px;">
                {good_html}
            </div>
        </div>
    </div>

    <!-- 핵심 포인트 -->
    {"<div style='margin-top:24px; font-size:" + str(TYPOGRAPHY["body_bold"]["size"]) + "px; font-weight:" + str(TYPOGRAPHY["body_bold"]["weight"]) + "; color:" + palette["accent"] + "; text-align:center;'>💡 " + _escape(key_point) + "</div>" if key_point else ""}

    <!-- 하단 핸들 -->
    <div style="margin-top:16px; font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_body_c(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """BODY-C: 하이라이트 박스형 — 큰 숫자/금액 강조"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body 파싱: 첫 줄 = 큰 숫자, 둘째 줄 = 라벨, 나머지 = 계산 세부
    lines = [l.strip() for l in (body or "").split("\n") if l.strip()]
    big_number = lines[0] if lines else "0"
    label = lines[1] if len(lines) > 1 else ""
    detail_lines = lines[2:] if len(lines) > 2 else []

    # 계산 세부 HTML
    detail_html = ""
    if detail_lines:
        items = ""
        for dl in detail_lines:
            if dl.startswith(("합계", "총", "---", "===")):
                items += f'<div style="border-top:1px solid var(--divider); margin-top:8px; padding-top:8px; font-weight:700; font-size:{TYPOGRAPHY["body_bold"]["size"]}px; color:var(--text-primary);">{_escape(dl)}</div>'
            else:
                items += f'<div style="font-size:{TYPOGRAPHY["body"]["size"]}px; color:var(--text-secondary); line-height:1.8;">{_escape(dl)}</div>'
        detail_html = f"""
        <div style="background:{palette['card_bg']}; border:1px solid {palette.get('card_border', '#E0E0E0')}; border-radius:{LAYOUT['card_radius']}px; padding:{LAYOUT['card_padding']}px; margin-top:24px;">
            {items}
        </div>"""

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 헤더 -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div style="font-size:{TYPOGRAPHY['subtitle']['size']}px; font-weight:{TYPOGRAPHY['subtitle']['weight']}; color:var(--text-primary);">{_escape(title)}</div>
        <div style="font-size:{TYPOGRAPHY['handle']['size']}px; color:var(--text-secondary);">{page_num}</div>
    </div>
    <div style="height:{LAYOUT['divider_thickness']}px; background:var(--divider); margin-bottom:{LAYOUT['section_gap']}px;"></div>

    <!-- 하이라이트 박스 -->
    <div style="background:{palette['card_bg']}; border:1px solid {palette.get('card_border', '#E0E0E0')}; border-radius:{LAYOUT['card_radius']}px; padding:{LAYOUT['card_padding'] + 16}px; text-align:center;">
        <div style="font-size:{TYPOGRAPHY['number_xl']['size']}px; font-weight:{TYPOGRAPHY['number_xl']['weight']}; line-height:{TYPOGRAPHY['number_xl']['line_height']}; color:{palette['number_color']};">{_escape(big_number)}</div>
        {"<div style='font-size:" + str(TYPOGRAPHY['caption']['size']) + "px; color:var(--text-secondary); margin-top:8px;'>" + _escape(label) + "</div>" if label else ""}
    </div>

    <!-- 계산 세부 -->
    {detail_html}

    <!-- 하단 핸들 -->
    <div style="margin-top:auto; font-size:{TYPOGRAPHY['handle']['size']}px; color:var(--text-secondary);">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


def build_body_d(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """BODY-D: 스텝/프로세스형 — STEP 1→2→3→4 연결선"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body 파싱: "STEP 1: 제목\n설명" 또는 "1. 제목: 설명"
    steps = []
    if body:
        current_title = ""
        current_desc = ""
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            # STEP N 또는 숫자. 패턴 감지
            import re
            step_match = re.match(r'^(?:STEP\s*)?(\d+)[.:\s]+(.+)', line, re.IGNORECASE)
            if step_match:
                if current_title:
                    steps.append({"title": current_title, "desc": current_desc.strip()})
                current_title = step_match.group(2).strip()
                # 콜론으로 제목:설명 분리
                if ":" in current_title:
                    parts = current_title.split(":", 1)
                    current_title = parts[0].strip()
                    current_desc = parts[1].strip()
                else:
                    current_desc = ""
            elif current_title:
                current_desc += " " + line if current_desc else line
            else:
                steps.append({"title": line, "desc": ""})
        if current_title:
            steps.append({"title": current_title, "desc": current_desc.strip()})

    steps_html = ""
    for i, step in enumerate(steps[:6]):
        is_last_step = (i == len(steps[:6]) - 1)
        connector = ""
        if not is_last_step:
            connector = f'<div style="margin-left:18px; height:24px; border-left:2px dashed {palette["accent"]}; opacity:0.5;"></div>'

        steps_html += f"""
        <div>
            <div style="display:flex; align-items:center; gap:16px; margin-bottom:4px;">
                <div style="font-size:16px; font-weight:800; color:{palette['accent']}; min-width:60px;">STEP {i + 1}</div>
                <div style="flex:1; height:1px; background:{palette.get('divider', '#444')};"></div>
            </div>
            <div style="padding-left:12px;">
                <div style="font-size:{TYPOGRAPHY['body_bold']['size']}px; font-weight:{TYPOGRAPHY['body_bold']['weight']}; color:var(--text-primary); margin-bottom:2px;">{_escape(step['title'])}</div>
                {"<div style='font-size:" + str(TYPOGRAPHY['body']['size']) + "px; color:var(--text-secondary); line-height:" + str(TYPOGRAPHY['body']['line_height']) + ";'>" + _escape(step['desc']) + "</div>" if step['desc'] else ""}
            </div>
            {connector}
        </div>"""

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 헤더 -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div style="font-size:{TYPOGRAPHY['subtitle']['size']}px; font-weight:{TYPOGRAPHY['subtitle']['weight']}; color:var(--text-primary);">{_escape(title)}</div>
        <div style="font-size:{TYPOGRAPHY['handle']['size']}px; color:var(--text-secondary);">{page_num}</div>
    </div>
    <div style="height:{LAYOUT['divider_thickness']}px; background:var(--divider); margin-bottom:{LAYOUT['section_gap']}px;"></div>

    <!-- 스텝 리스트 -->
    <div style="flex:1;">
        {steps_html}
    </div>

    <!-- 하단 핸들 -->
    <div style="font-size:{TYPOGRAPHY['handle']['size']}px; color:var(--text-secondary);">@handle</div>
</div>"""

    return _base_html(width, height, content, theme)


# ============================================
# 마무리 슬라이드 빌더
# ============================================

def build_closing_a(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """CLOSING-A: 요약 + CTA형"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # body에서 요약 포인트 추출
    points = []
    cta_text = ""
    if body:
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(("📞", "CTA:", "cta:")):
                cta_text = line.split(":", 1)[-1].strip() if ":" in line else line[2:].strip()
            else:
                clean = line.lstrip("0123456789.-) ·•▪✓✔☑ ")
                if clean:
                    points.append(clean)

    points_html = ""
    for pt in points[:5]:
        points_html += f"""
        <div style="display:flex; gap:12px; align-items:flex-start; margin-bottom:16px;">
            <div style="color:{palette["accent"]}; font-size:24px; font-weight:700;">✓</div>
            <div style="font-size:{TYPOGRAPHY["body_bold"]["size"]}px; font-weight:{TYPOGRAPHY["body_bold"]["weight"]}; color:var(--text-primary);">{_escape(pt)}</div>
        </div>"""

    # CTA 버튼
    cta_html = ""
    if cta_text:
        cta_html = f"""
    <div style="margin-top:24px; text-align:center;">
        <div style="display:inline-block; background:{palette["accent"]}; color:#FFFFFF; padding:16px 48px; border-radius:12px; font-size:{TYPOGRAPHY["body_bold"]["size"]}px; font-weight:{TYPOGRAPHY["body_bold"]["weight"]};">📞 {_escape(cta_text)}</div>
    </div>"""

    content = f"""
<div style="display:flex; flex-direction:column; height:100%; padding:{pad}px;">
    <!-- 요약 타이틀 -->
    <div style="font-size:{TYPOGRAPHY["subtitle"]["size"]}px; font-weight:{TYPOGRAPHY["subtitle"]["weight"]}; color:{palette["accent"]}; margin-bottom:16px;">{_escape(title) if title else "오늘의 핵심 정리"}</div>
    <div style="height:{LAYOUT["divider_thickness"]}px; background:var(--divider); margin-bottom:{LAYOUT["section_gap"]}px;"></div>

    <!-- 요약 포인트 -->
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center;">
        {points_html}
    </div>

    <div style="height:{LAYOUT["divider_thickness"]}px; background:var(--divider); margin-bottom:24px;"></div>

    {cta_html}

    <!-- 하단 핸들 -->
    <div style="display:flex; align-items:center; gap:16px; margin-top:auto; justify-content:center;">
        <div style="flex:1; height:1px; background:var(--divider);"></div>
        <div style="font-size:{TYPOGRAPHY["handle"]["size"]}px; color:var(--text-secondary);">@handle</div>
        <div style="flex:1; height:1px; background:var(--divider);"></div>
    </div>
</div>"""

    return _base_html(width, height, content, theme)


def build_closing_b(title: str, body: str, page_num: str, width: int, height: int, theme: str) -> str:
    """CLOSING-B: 브랜드 카드형 — 회사명, 슬로건, 연락처, 해시태그"""
    palette = get_theme(theme)
    pad = LAYOUT["padding"]

    # 파싱: title = 브랜드명, body 줄별로 슬로건/연락처/태그/하단메시지
    brand_name = _escape(title) if title else "브랜드명"
    slogan = ""
    contacts = []
    tags = []
    bottom_msg = ""

    if body:
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(("#")):
                # 해시태그
                for tag in line.split():
                    if tag.startswith("#"):
                        tags.append(tag)
            elif line.startswith(("📞", "📧", "📍", "☎", "✉")):
                contacts.append(line)
            elif line.startswith(("💾", "저장")):
                bottom_msg = line
            elif not slogan:
                slogan = line
            else:
                contacts.append(line)

    contacts_html = "".join(
        f'<div style="font-size:{TYPOGRAPHY["body"]["size"]}px; color:var(--text-secondary); margin-bottom:8px; text-align:center;">{_escape(c)}</div>'
        for c in contacts[:4]
    )

    tags_html = ""
    if tags:
        tag_items = "".join(
            f'<span style="border:1px solid {palette.get("tag_border", "#CCC")}; border-radius:{LAYOUT["tag_radius"]}px; padding:{LAYOUT["tag_padding_v"]}px {LAYOUT["tag_padding_h"]}px; font-size:{TYPOGRAPHY["tag"]["size"]}px; color:var(--text-secondary);">{_escape(t)}</span>'
            for t in tags[:5]
        )
        tags_html = f'<div style="display:flex; gap:10px; flex-wrap:wrap; justify-content:center; margin-top:24px;">{tag_items}</div>'

    content = f"""
<div style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:100%; padding:{pad}px; text-align:center;">
    <!-- 브랜드명 -->
    <div style="font-size:{TYPOGRAPHY['title_xl']['size']}px; font-weight:{TYPOGRAPHY['title_xl']['weight']}; line-height:{TYPOGRAPHY['title_xl']['line_height']}; color:var(--text-primary); margin-bottom:16px;">{brand_name}</div>

    <!-- 슬로건 -->
    {"<div style='font-size:" + str(TYPOGRAPHY['subtitle']['size']) + "px; font-weight:" + str(TYPOGRAPHY['subtitle']['weight']) + "; color:" + palette['accent'] + "; margin-bottom:32px;'>" + _escape(slogan) + "</div>" if slogan else ""}

    <div style="width:60%; height:1px; background:var(--divider); margin-bottom:32px;"></div>

    <!-- 연락처 -->
    {contacts_html}

    <div style="width:60%; height:1px; background:var(--divider); margin-top:24px;"></div>

    <!-- 해시태그 -->
    {tags_html}

    <!-- 하단 메시지 -->
    {"<div style='font-size:" + str(TYPOGRAPHY['caption']['size']) + "px; color:var(--text-secondary); margin-top:32px;'>" + _escape(bottom_msg) + "</div>" if bottom_msg else ""}
</div>"""

    return _base_html(width, height, content, theme)


# ============================================
# 라우팅 함수 — template_set에 따라 적절한 빌더 호출
# ============================================

# 빌더 매핑 (12종 전체)
_COVER_BUILDERS = {
    "COVER-A": build_cover_a,
    "COVER-B": build_cover_b,
    "COVER-C": build_cover_c,
    "COVER-D": build_cover_d,
    "COVER-E": build_cover_e,
    "COVER-F": build_cover_f,
}

_BODY_BUILDERS = {
    "BODY-A": build_body_a,
    "BODY-B": build_body_b,
    "BODY-C": build_body_c,
    "BODY-D": build_body_d,
}

_CLOSING_BUILDERS = {
    "CLOSING-A": build_closing_a,
    "CLOSING-B": build_closing_b,
}


def build_template_slide(
    template_set: str,
    slide_index: int,
    total_slides: int,
    title: str,
    body: str,
    width: int = 1080,
    height: int = 1350,
    template_type_override: str = None,
) -> str:
    """template_set에 따라 적절한 빌더를 선택하여 HTML 생성

    Args:
        template_set: 템플릿 세트 이름 (dark_best, blue_report 등)
        slide_index: 0부터 시작하는 슬라이드 인덱스
        total_slides: 전체 슬라이드 수
        title: 제목
        body: 본문
        width/height: 크기
        template_type_override: 슬라이드별 개별 템플릿 오버라이드 (COVER-A, BODY-C 등)

    Returns:
        HTML 문자열

    Raises:
        ValueError: 알 수 없는 template_set이면 에러
    """
    ts = get_template_set(template_set)
    if not ts:
        raise ValueError(f"알 수 없는 template_set: {template_set}")

    theme = ts["theme"]
    cover_type = ts["cover"]
    body_type = ts["body"]
    closing_type = ts["closing"]

    is_cover = (slide_index == 0)
    is_last = (slide_index == total_slides - 1) and total_slides > 1

    page_num = f"{slide_index + 1}/{total_slides}"

    # 오버라이드가 있으면 해당 빌더를 직접 사용
    if template_type_override:
        override = template_type_override
        all_builders = {**_COVER_BUILDERS, **_BODY_BUILDERS, **_CLOSING_BUILDERS}
        builder = all_builders.get(override)
        if builder:
            # 커버 빌더는 page_num 파라미터가 없음
            if override.startswith("COVER-"):
                return builder(title, body, width, height, theme)
            else:
                return builder(title, body, page_num, width, height, theme)
        else:
            logger.warning(f"오버라이드 빌더 없음: {override}, 기본 로직 사용")

    if is_cover:
        builder = _COVER_BUILDERS.get(cover_type)
        if not builder:
            logger.warning(f"커버 빌더 없음: {cover_type}, COVER-A로 대체")
            builder = build_cover_a
        return builder(title, body, width, height, theme)

    elif is_last:
        builder = _CLOSING_BUILDERS.get(closing_type)
        if not builder:
            logger.warning(f"마무리 빌더 없음: {closing_type}, CLOSING-A로 대체")
            builder = build_closing_a
        return builder(title, body, page_num, width, height, theme)

    else:
        builder = _BODY_BUILDERS.get(body_type)
        if not builder:
            logger.warning(f"본문 빌더 없음: {body_type}, BODY-A로 대체")
            builder = build_body_a
        return builder(title, body, page_num, width, height, theme)
