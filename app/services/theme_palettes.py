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
    "navy": {
        "bg": "#0D1B2A",
        "bg_alt": "#1B2D45",
        "surface": "#1B2D45",
        "divider": "#2A4060",
        "text_primary": "#FFFFFF",
        "text_secondary": "#8DA4BF",
        "accent": "#C9A96E",
        "number_color": "#C9A96E",
        "card_bg": "#1B2D45",
        "card_border": "#2A4060",
        "good_color": "#4CAF50",
        "bad_color": "#FF6B6B",
        "tag_border": "#2A4060",
        "badge_bg": "#162438",
    },
    "sage": {
        "bg": "#F0EDE8",
        "bg_alt": "#E5E0D8",
        "surface": "#FFFFFF",
        "divider": "#C8C0B4",
        "text_primary": "#2C3E2D",
        "text_secondary": "#6B7B6C",
        "accent": "#6B7F5E",
        "number_color": "#4A6741",
        "card_bg": "#FFFFFF",
        "card_border": "#C8C0B4",
        "good_color": "#4A6741",
        "bad_color": "#C75B5B",
        "tag_border": "#B8B0A4",
        "badge_bg": "#E8E4DD",
        "cta_bg": "#6B7F5E",
        "cta_text": "#FFFFFF",
    },
    "rose": {
        "bg": "#FDF2F4",
        "bg_alt": "#F5E1E6",
        "surface": "#FFFFFF",
        "divider": "#E8C8D0",
        "text_primary": "#3A2A2E",
        "text_secondary": "#8A7078",
        "accent": "#C75B7A",
        "number_color": "#B84A68",
        "card_bg": "#FFFFFF",
        "card_border": "#E8C8D0",
        "good_color": "#5A8A5E",
        "bad_color": "#C75B5B",
        "tag_border": "#DDB8C2",
        "badge_bg": "#F5E8EC",
        "cta_bg": "#C75B7A",
        "cta_text": "#FFFFFF",
    },
    "slate": {
        "bg": "#F8F9FA",
        "bg_alt": "#E9ECEF",
        "surface": "#FFFFFF",
        "divider": "#CED4DA",
        "text_primary": "#212529",
        "text_secondary": "#6C757D",
        "accent": "#495057",
        "number_color": "#343A40",
        "card_bg": "#FFFFFF",
        "card_border": "#CED4DA",
        "good_color": "#2E7D32",
        "bad_color": "#D32F2F",
        "tag_border": "#ADB5BD",
        "badge_bg": "#E9ECEF",
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
    "title_xl": {"size": 80, "weight": 800, "line_height": 1.2},
    "title_en": {"size": 96, "weight": 900, "line_height": 1.05},
    "subtitle": {"size": 38, "weight": 600, "line_height": 1.4},
    "category": {"size": 28, "weight": 700, "line_height": 1.0, "transform": "uppercase", "letter_spacing": 3},
    "body": {"size": 32, "weight": 400, "line_height": 1.6},
    "body_bold": {"size": 32, "weight": 700, "line_height": 1.6},
    "number_xl": {"size": 80, "weight": 900, "line_height": 1.1},
    "tag": {"size": 22, "weight": 500},
    "handle": {"size": 22, "weight": 400},
    "caption": {"size": 24, "weight": 400, "line_height": 1.5},
}

# 텍스트 양에 따른 적응형 타이포그래피 프리셋
TEXT_TIERS = {
    "spacious": {"title": 44, "body": 36, "line_height": 1.7, "gap": 32},  # 39자 이하
    "normal":   {"title": 38, "body": 32, "line_height": 1.6, "gap": 24},  # 40~79자
    "compact":  {"title": 32, "body": 26, "line_height": 1.5, "gap": 16},  # 80자 이상
}

def get_text_tier(body_text: str) -> dict:
    """본문 텍스트 양에 따른 타이포그래피 등급 반환"""
    char_count = len((body_text or "").replace("\n", "").replace(" ", ""))
    if char_count >= 80:
        return TEXT_TIERS["compact"]
    elif char_count >= 40:
        return TEXT_TIERS["normal"]
    else:
        return TEXT_TIERS["spacious"]

# ============================================
# 레이아웃 상수 (1080px 기준)
# ============================================

LAYOUT = {
    "padding": 64,
    "padding_top": 80,
    "padding_bottom": 72,
    "card_radius": 24,
    "card_padding": 44,
    "tag_radius": 20,
    "tag_padding_h": 24,
    "tag_padding_v": 10,
    "badge_radius": 8,
    "badge_padding_h": 16,
    "badge_padding_v": 8,
    "divider_thickness": 2,
    "element_gap": 28,
    "section_gap": 40,
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
        "preview_colors": ["#1A1A1A", "#FF6B6B", "#FFFFFF"],
    },
    "dark_category": {
        "cover": "COVER-B",
        "body": "BODY-C",
        "closing": "CLOSING-A",
        "theme": "dark",
        "label": "다크 카테고리",
        "description": "전문적 카테고리 배지 + 금액 하이라이트 + CTA",
        "preview_colors": ["#1A1A1A", "#FFD700", "#FFFFFF"],
    },
    "blue_report": {
        "cover": "COVER-C",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "blue",
        "label": "블루 리포트",
        "description": "공신력 있는 블루 배경 + 넘버링 리스트 + 요약 CTA",
        "preview_colors": ["#E8EEF4", "#4A7FB5", "#1A1A1A"],
    },
    "minimal_card": {
        "cover": "COVER-D",
        "body": "BODY-A",
        "closing": "CLOSING-B",
        "theme": "light",
        "label": "미니멀 카드",
        "description": "깔끔한 흰색 카드 + 넘버링 리스트 + 브랜드 카드",
        "preview_colors": ["#FFFFFF", "#4A7FB5", "#1A1A1A"],
    },
    "warm_friendly": {
        "cover": "COVER-E",
        "body": "BODY-B",
        "closing": "CLOSING-A",
        "theme": "warm",
        "label": "웜톤 친근형",
        "description": "따뜻한 웜톤 + 비교형 본문 + 요약 CTA",
        "preview_colors": ["#F5F0EB", "#8B6914", "#1A1A1A"],
    },
    "teal_modern": {
        "cover": "COVER-F",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "teal",
        "label": "틸 모던",
        "description": "세련된 틸 배경 + 넘버링 리스트 + 요약 CTA",
        "preview_colors": ["#1A3A3A", "#A8D5D5", "#FFFFFF"],
    },
    "dark_process": {
        "cover": "COVER-B",
        "body": "BODY-D",
        "closing": "CLOSING-B",
        "theme": "dark",
        "label": "다크 프로세스",
        "description": "카테고리 배지 + 단계별 프로세스 + 브랜드 카드",
        "preview_colors": ["#1A1A1A", "#FFD700", "#FFFFFF"],
    },
    "warm_highlight": {
        "cover": "COVER-E",
        "body": "BODY-C",
        "closing": "CLOSING-B",
        "theme": "warm",
        "label": "웜톤 하이라이트",
        "description": "질문형 커버 + 금액/숫자 강조 + 브랜드 카드",
        "preview_colors": ["#F5F0EB", "#8B6914", "#1A1A1A"],
    },
    # --- 신규 세트 (v2) ---
    "navy_premium": {
        "cover": "COVER-A",
        "body": "BODY-A",
        "closing": "CLOSING-B",
        "theme": "navy",
        "label": "네이비 프리미엄",
        "description": "금융 전문가 느낌 + 골드 악센트 + 넘버링 리스트",
        "preview_colors": ["#0D1B2A", "#C9A96E", "#FFFFFF"],
    },
    "navy_step": {
        "cover": "COVER-B",
        "body": "BODY-D",
        "closing": "CLOSING-A",
        "theme": "navy",
        "label": "네이비 단계형",
        "description": "카테고리 배지 + 단계별 프로세스 + 골드 악센트",
        "preview_colors": ["#0D1B2A", "#C9A96E", "#8DA4BF"],
    },
    "sage_natural": {
        "cover": "COVER-C",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "sage",
        "label": "세이지 내추럴",
        "description": "자연스러운 올리브톤 + 넘버링 리스트 + CTA",
        "preview_colors": ["#F0EDE8", "#6B7F5E", "#2C3E2D"],
    },
    "sage_compare": {
        "cover": "COVER-E",
        "body": "BODY-B",
        "closing": "CLOSING-B",
        "theme": "sage",
        "label": "세이지 비교형",
        "description": "친근한 질문형 커버 + O/X 비교 + 자연 톤",
        "preview_colors": ["#F0EDE8", "#6B7F5E", "#4A6741"],
    },
    "rose_soft": {
        "cover": "COVER-E",
        "body": "BODY-A",
        "closing": "CLOSING-A",
        "theme": "rose",
        "label": "로제 소프트",
        "description": "부드러운 파스텔 + 넘버링 리스트 + 인스타 감성",
        "preview_colors": ["#FDF2F4", "#C75B7A", "#3A2A2E"],
    },
    "rose_highlight": {
        "cover": "COVER-D",
        "body": "BODY-C",
        "closing": "CLOSING-B",
        "theme": "rose",
        "label": "로제 하이라이트",
        "description": "미니멀 카드 + 금액/숫자 강조 + 로제 톤",
        "preview_colors": ["#FDF2F4", "#C75B7A", "#B84A68"],
    },
    "slate_editorial": {
        "cover": "COVER-C",
        "body": "BODY-A",
        "closing": "CLOSING-B",
        "theme": "slate",
        "label": "슬레이트 에디토리얼",
        "description": "모노톤 에디토리얼 + 넘버링 리스트 + 미니멀",
        "preview_colors": ["#F8F9FA", "#495057", "#212529"],
    },
    "slate_process": {
        "cover": "COVER-F",
        "body": "BODY-D",
        "closing": "CLOSING-A",
        "theme": "slate",
        "label": "슬레이트 프로세스",
        "description": "세련된 모던 커버 + 단계별 프로세스 + 차콜",
        "preview_colors": ["#F8F9FA", "#495057", "#6C757D"],
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
