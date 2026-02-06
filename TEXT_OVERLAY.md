# TEXT_OVERLAY.md - Pillow 텍스트 오버레이

> 이 문서는 한글 텍스트 오버레이 처리를 정의합니다.

---

## 1. 왜 Pillow인가?

- AI 이미지 생성 모델은 한글 렌더링 불가
- Pillow로 후처리하여 텍스트 합성
- 폰트, 위치, 스타일 완벽 제어 가능

---

## 2. 필요 폰트

### 2.1 기본 제공 폰트

| 폰트명 | 용도 | 라이선스 |
|--------|------|----------|
| 나눔고딕 | 기본 대사 | OFL |
| 나눔바른고딕 | 나레이션 | OFL |
| 배민 도현체 | 강조/제목 | 무료 |

### 2.2 폰트 설치 경로

```
/app/fonts/
├── NanumGothic.ttf
├── NanumGothicBold.ttf
├── NanumBarunGothic.ttf
└── BMDOHYEON.ttf
```

---

## 3. 말풍선 처리

### 3.1 말풍선 스타일

```python
BUBBLE_STYLES = {
    "round": {  # 둥근 말풍선
        "border_radius": 20,
        "padding": 15,
        "bg_color": (255, 255, 255, 230),
        "border_color": (0, 0, 0),
        "border_width": 2
    },
    "square": {  # 각진 말풍선
        "border_radius": 5,
        "padding": 12,
        "bg_color": (255, 255, 255, 230),
        "border_color": (0, 0, 0),
        "border_width": 2
    },
    "thought": {  # 생각 풍선
        "style": "cloud",
        "bg_color": (255, 255, 255, 200)
    }
}
```

### 3.2 말풍선 꼬리

- 캐릭터 위치 기반 자동 배치
- 좌/우/상/하 방향 지정 가능

---

## 4. 텍스트 배치 옵션

### 4.1 말풍선 스타일 (기본)

```
┌─────────────────────────────┐
│  ┌───────────────────┐      │
│  │ "대사 텍스트"      │◀────│  말풍선
│  └───────────────────┘      │
│                             │
│      [캐릭터 이미지]        │
│                             │
└─────────────────────────────┘
```

### 4.2 하단 자막 스타일

```
┌─────────────────────────────┐
│                             │
│      [캐릭터 이미지]        │
│                             │
├─────────────────────────────┤
│ 민지: "대사 텍스트"         │  자막 영역
└─────────────────────────────┘
```

---

## 5. 기타 오버레이 요소

### 5.1 페이지 번호

```python
def add_page_number(image, page_num, total, position="bottom_right"):
    text = f"{page_num}/{total}"
    # 위치: top_left, top_right, bottom_left, bottom_right
```

### 5.2 시리즈 배지

```python
def add_series_badge(image, series_num, total_series, position="top_left"):
    text = f"시리즈 {series_num}/{total_series}"
    # 배지 스타일 적용
```

### 5.3 워터마크

```python
def add_watermark(image, text_or_logo, opacity=0.3, position="bottom_right"):
    # 텍스트 또는 로고 이미지 지원
```

---

## 6. 코드 예시

```python
from PIL import Image, ImageDraw, ImageFont

def overlay_dialogue(image_path, dialogues, settings):
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    
    font = ImageFont.truetype(settings.font_path, settings.font_size)
    
    for dialogue in dialogues:
        # 말풍선 그리기
        bubble = create_speech_bubble(
            text=dialogue.text,
            style=settings.bubble_style,
            position=dialogue.position
        )
        img.paste(bubble, dialogue.position, bubble)
    
    return img
```

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-06 | 1.0.0 | 초기 작성 |
