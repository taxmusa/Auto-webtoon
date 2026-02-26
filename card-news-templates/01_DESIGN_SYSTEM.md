# 01. 디자인 시스템 (Design Tokens)

> 모든 템플릿이 공유하는 컬러, 폰트, 레이아웃 규칙.
> 이 파일의 값을 Python dict/config로 구현할 것.

---

## 프로젝트 개요

- **목적**: 세무사 전문 블로그용 카드뉴스 이미지 자동 생성 Python 모듈
- **입력**: 주제, 본문 내용 (Claude API가 생성한 텍스트)
- **출력**: PNG 이미지 세트 (커버 + 본문 N장 + 마무리)
- **기술**: Python 3.11+ / Pillow(PIL)
- **폰트**: Pretendard (1순위) 또는 Noto Sans KR (2순위)

---

## 출력 사이즈

| 비율 | 픽셀 | 용도 |
|------|------|------|
| 1:1 | 1080 x 1080 | 네이버 블로그, 인스타 정사각 |
| 4:5 | 1080 x 1350 | 인스타 세로, 블로그 세로형 |

---

## 브랜드 기본값 (config로 변경 가능)

```python
BRAND = {
    "name": "세무회계 지광",
    "handle": "@taxlab_jikwang",
    "slogan": "쉽고 정확한 세금 가이드",
    "phone": "02-XXX-XXXX",
}
```

---

## 컬러 팔레트

```python
COLORS = {
    # ── 다크 테마 (ref01, 04, 05, 06, 07, 09) ──
    "dark_bg":           "#1A1A1A",
    "dark_bg_alt":       "#2D2D2D",
    "dark_surface":      "#333333",
    "dark_divider":      "#444444",

    # ── 라이트 테마 (ref02, 03, 08, 10, 12) ──
    "light_bg":          "#FFFFFF",
    "light_bg_warm":     "#FAF8F5",
    "light_surface":     "#F5F5F5",
    "light_border":      "#E0E0E0",
    "light_divider":     "#D0D0D0",

    # ── 블루 리포트 테마 (ref11, 14) ──
    "blue_bg":           "#E8EEF4",
    "blue_accent":       "#4A7FB5",
    "blue_label_bg":     "#D6E4F0",
    "blue_line":         "#B0C4DE",

    # ── 웜 테마 (ref13, 15, 17) ──
    "warm_bg":           "#F5F0EB",
    "warm_accent":       "#8B6914",
    "warm_cta_bg":       "#D4A574",
    "warm_cta_text":     "#FFFFFF",

    # ── 틸 테마 (ref16) ──
    "teal_bg":           "#1A3A3A",
    "teal_accent":       "#A8D5D5",
    "teal_btn_bg":       "#2A5A5A",

    # ── 강조색 ──
    "coral":             "#FF6B6B",
    "yellow":            "#FFD700",
    "gold":              "#C8A96E",

    # ── 텍스트 ──
    "text_white":        "#FFFFFF",
    "text_black":        "#1A1A1A",
    "text_gray":         "#888888",
    "text_light_gray":   "#AAAAAA",
    "text_dark_gray":    "#555555",

    # ── 태그/배지 ──
    "badge_dark_bg":     "#2A2A2A",
    "tag_border_dark":   "#555555",
    "tag_border_light":  "#CCCCCC",

    # ── 세무사 전용 시맨틱 컬러 ──
    "tax_green":         "#2E7D32",   # 절세/이득
    "tax_red":           "#D32F2F",   # 추가납부/손해
    "tax_blue":          "#1565C0",   # 중립 정보
    "highlight_bg":      "#FFF9C4",   # 강조 박스 배경
}
```

---

## 타이포그래피

```python
FONTS = {
    # 메인 제목 (커버 슬라이드 큰 글씨)
    "title_xl": {
        "family": "Pretendard-ExtraBold",
        "size": 72,
        "line_height": 1.2,
    },
    # 영문 대형 타이틀 (ref08, 10, 12 스타일)
    "title_en": {
        "family": "Pretendard-Black",
        "size": 88,
        "line_height": 1.05,
    },
    # 서브 타이틀
    "subtitle": {
        "family": "Pretendard-SemiBold",
        "size": 32,
        "line_height": 1.4,
    },
    # 카테고리 레이블 (영문 대문자)
    "category": {
        "family": "Pretendard-Bold",
        "size": 24,
        "line_height": 1.0,
        "transform": "uppercase",
        "letter_spacing": 3,
    },
    # 본문 텍스트
    "body": {
        "family": "Pretendard-Regular",
        "size": 28,
        "line_height": 1.6,
    },
    # 본문 강조
    "body_bold": {
        "family": "Pretendard-Bold",
        "size": 28,
        "line_height": 1.6,
    },
    # 큰 숫자/금액 (본문 하이라이트)
    "number_xl": {
        "family": "Pretendard-Black",
        "size": 64,
        "line_height": 1.1,
    },
    # 해시태그
    "tag": {
        "family": "Pretendard-Medium",
        "size": 20,
    },
    # 계정 핸들
    "handle": {
        "family": "Pretendard-Regular",
        "size": 20,
        "color": "text_gray",
    },
    # 설명 텍스트 (작은 글씨)
    "caption": {
        "family": "Pretendard-Regular",
        "size": 22,
        "line_height": 1.5,
    },
}
```

---

## 공통 레이아웃 규칙

```python
LAYOUT = {
    "padding": 60,              # 좌우 패딩 (1080px 기준)
    "padding_top": 80,          # 상단 패딩
    "padding_bottom": 80,       # 하단 패딩
    "card_radius": 24,          # 카드 모서리 둥글기
    "card_padding": 40,         # 카드 내부 패딩
    "tag_radius": 20,           # 태그 버튼 둥글기
    "tag_padding_h": 24,        # 태그 좌우 패딩
    "tag_padding_v": 10,        # 태그 상하 패딩
    "badge_radius": 8,          # 배지 둥글기
    "badge_padding_h": 16,      # 배지 좌우 패딩
    "badge_padding_v": 8,       # 배지 상하 패딩
    "divider_thickness": 2,     # 구분선 두께
    "element_gap": 24,          # 요소 간 기본 간격
    "section_gap": 48,          # 섹션 간 간격
}
```

---

## 폰트 설치 방법

```bash
# Pretendard 다운로드 (추천)
wget https://github.com/orioncactus/pretendard/releases/latest/download/Pretendard-1.3.9.zip
unzip Pretendard-1.3.9.zip -d fonts/

# 또는 Noto Sans KR
pip install fonts-noto-sans-kr --break-system-packages
```

---

## 다음 파일
- `02_COVER_TEMPLATES.md` → 커버 슬라이드 6종 상세 스펙
- `03_BODY_TEMPLATES.md` → 본문 슬라이드 4종 상세 스펙
- `04_CLOSING_TEMPLATES.md` → 마무리 슬라이드 2종 상세 스펙
- `05_TEMPLATE_PREVIEW_REQUEST.md` → 미리보기 HTML 생성 요구사항
