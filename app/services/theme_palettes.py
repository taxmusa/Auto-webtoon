"""
카드뉴스/캐러셀 테마 팔레트 시스템

card-news-templates 디자인 시스템 기반.
5가지 테마(dark/light/blue/warm/teal) + 타이포그래피 + 레이아웃 상수.
"""

# ============================================
# 테마 팔레트 (5가지)
# ============================================

THEME_PALETTES = {
    "dark": {
        "bg": "#1A1A1A",
        "bg_alt": "#2D2D2D",
        "surface": "#333333",
        "divider": "#444444",
        "text_primary": "#FFFFFF",
        "text_secondary": "#AAAAAA",
        "accent": "#FF6B6B",
        "number_color": "#FFD700",
        "card_bg": "#2D2D2D",
        "card_border": "#444444",
        "good_color": "#4CAF50",
        "bad_color": "#FF6B6B",
        "tag_border": "#555555",
        "badge_bg": "#2A2A2A",
    },
    "light": {
        "bg": "#FFFFFF",
        "bg_alt": "#F5F5F5",
        "surface": "#F5F5F5",
        "divider": "#E0E0E0",
        "text_primary": "#1A1A1A",
        "text_secondary": "#666666",
        "accent": "#4A7FB5",
        "number_color": "#1565C0",
        "card_bg": "#F5F5F5",
        "card_border": "#E0E0E0",
        "good_color": "#2E7D32",
        "bad_color": "#D32F2F",
        "tag_border": "#CCCCCC",
        "badge_bg": "#F0F0F0",
    },
    "blue": {
        "bg": "#E8EEF4",
        "bg_alt": "#D6E4F0",
        "surface": "#FFFFFF",
        "divider": "#B0C4DE",
        "text_primary": "#1A1A1A",
        "text_secondary": "#555555",
        "accent": "#4A7FB5",
        "number_color": "#2B5EA7",
        "card_bg": "#FFFFFF",
        "card_border": "#B0C4DE",
        "good_color": "#2E7D32",
        "bad_color": "#D32F2F",
        "tag_border": "#B0C4DE",
        "badge_bg": "#1A1A1A",
    },
    "warm": {
        "bg": "#F5F0EB",
        "bg_alt": "#EDE5DA",
        "surface": "#FFFFFF",
        "divider": "#D4C5B0",
        "text_primary": "#1A1A1A",
        "text_secondary": "#666666",
        "accent": "#8B6914",
        "number_color": "#8B6914",
        "card_bg": "#FFFFFF",
        "card_border": "#D4C5B0",
        "good_color": "#2E7D32",
        "bad_color": "#D32F2F",
        "tag_border": "#C8B89A",
        "badge_bg": "#F0E8DD",
        "cta_bg": "#D4A574",
        "cta_text": "#FFFFFF",
    },
    "teal": {
        "bg": "#1A3A3A",
        "bg_alt": "#244A4A",
        "surface": "#2A5A5A",
        "divider": "#3A6A6A",
        "text_primary": "#FFFFFF",
        "text_secondary": "#A8D5D5",
        "accent": "#A8D5D5",
        "number_color": "#A8D5D5",
        "card_bg": "#2A5A5A",
        "card_border": "#3A6A6A",
        "good_color": "#81C784",
        "bad_color": "#FF8A80",
        "tag_border": "#4A7A7A",
        "badge_bg": "#2A5A5A",
        "btn_bg": "#2A5A5A",
    },
}

# ============================================
# 시맨틱 컬러 (세무사 전용)
# ============================================

SEMANTIC_COLORS = {
    "tax_green": "#2E7D32",    # 절세/이득
    "tax_red": "#D32F2F",      # 추가납부/손해
    "tax_blue": "#1565C0",     # 중립 정보
    "highlight_bg": "#FFF9C4", # 강조 박스 배경
    "coral": "#FF6B6B",
    "yellow": "#FFD700",
    "gold": "#C8A96E",
}

# ============================================
# 타이포그래피 (Pretendard 기반, px 단위)
# ============================================

TYPOGRAPHY = {
    "title_xl": {"size": 72, "weight": 800, "line_height": 1.2},
    "title_en": {"size": 88, "weight": 900, "line_height": 1.05},
    "subtitle": {"size": 32, "weight": 600, "line_height": 1.4},
    "category": {"size": 24, "weight": 700, "line_height": 1.0, "transform": "uppercase", "letter_spacing": 3},
    "body": {"size": 28, "weight": 400, "line_height": 1.6},
    "body_bold": {"size": 28, "weight": 700, "line_height": 1.6},
    "number_xl": {"size": 64, "weight": 900, "line_height": 1.1},
    "tag": {"size": 20, "weight": 500},
    "handle": {"size": 20, "weight": 400},
    "caption": {"size": 22, "weight": 400, "line_height": 1.5},
}

# ============================================
# 레이아웃 상수 (1080px 기준)
# ============================================

LAYOUT = {
    "padding": 60,
    "padding_top": 80,
    "padding_bottom": 80,
    "card_radius": 24,
    "card_padding": 40,
    "tag_radius": 20,
    "tag_padding_h": 24,
    "tag_padding_v": 10,
    "badge_radius": 8,
    "badge_padding_h": 16,
    "badge_padding_v": 8,
    "divider_thickness": 2,
    "element_gap": 24,
    "section_gap": 48,
}

# ============================================
# 커버 → 본문 테마 자동 매칭
# ============================================

COVER_TO_BODY_THEME = {
    "COVER-A": "dark",
    "COVER-B": "dark",
    "COVER-C": "blue",
    "COVER-D": "light",
    "COVER-E": "warm",
    "COVER-F": "teal",
}

# ============================================
# 템플릿 세트 (사전 조합)
# ============================================

TEMPLATE_SETS = {
    "dark_best": {
        "cover": "COVER-A",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "dark",
        "label": "다크 BEST 리스트",
        "description": "강렬한 다크 배경 + 넘버링 리스트 + 요약 CTA",
    },
    "blue_report": {
        "cover": "COVER-C",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "blue",
        "label": "블루 리포트",
        "description": "공신력 있는 블루 배경 + 넘버링 리스트 + 요약 CTA",
    },
    "minimal_card": {
        "cover": "COVER-D",
        "body": "BODY-A",
        "closing": "CLOSING-B",
        "theme": "light",
        "label": "미니멀 카드",
        "description": "깔끔한 흰색 카드 + 넘버링 리스트 + 브랜드 카드",
    },
    "warm_friendly": {
        "cover": "COVER-E",
        "body": "BODY-B",
        "closing": "CLOSING-A",
        "theme": "warm",
        "label": "웜톤 친근형",
        "description": "따뜻한 웜톤 + 비교형 본문 + 요약 CTA",
    },
    "teal_modern": {
        "cover": "COVER-F",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "teal",
        "label": "틸 모던",
        "description": "세련된 틸 배경 + 넘버링 리스트 + 요약 CTA",
    },
}

# ============================================
# 유틸리티 함수
# ============================================

def get_theme(name: str) -> dict:
    """테마 이름으로 팔레트 딕셔너리 반환 (없으면 light 기본)"""
    return THEME_PALETTES.get(name, THEME_PALETTES["light"])


def get_template_set(name: str) -> dict:
    """템플릿 세트 이름으로 설정 반환 (없으면 None)"""
    return TEMPLATE_SETS.get(name)


def theme_to_css_vars(theme_name: str) -> str:
    """테마 팔레트를 CSS 변수 선언 문자열로 변환

    Returns:
        ":root { --bg: #1A1A1A; --text-primary: #FFFFFF; ... }" 형태 문자열
    """
    palette = get_theme(theme_name)
    lines = []
    for key, value in palette.items():
        css_key = key.replace("_", "-")
        lines.append(f"    --{css_key}: {value};")
    return ":root {\n" + "\n".join(lines) + "\n}"


def get_available_themes() -> list:
    """사용 가능한 테마 이름 목록 반환"""
    return list(THEME_PALETTES.keys())


def get_available_template_sets() -> list:
    """사용 가능한 템플릿 세트 목록 반환 (라벨 포함)"""
    return [
        {"id": k, "label": v["label"], "description": v["description"]}
        for k, v in TEMPLATE_SETS.items()
    ]
