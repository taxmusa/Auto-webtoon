# TEXT_OVERLAY.md - Pillow 텍스트 오버레이

> 이 문서는 한글 텍스트 오버레이 처리를 정의합니다.

---

## 1. 왜 Pillow인가?

- AI 이미지 생성 모델은 한글 렌더링 불가
- Pillow로 후처리하여 텍스트 합성
- 폰트, 위치, 스타일 완벽 제어 가능

---

## 1.5 핵심 원리: 스토리 대사가 말풍선이 되기까지

### 전체 데이터 흐름

```
③ 스토리 생성 단계
   │
   │  씬별로 정해지는 것:
   │  - scene_description: "거실 배경, 두 캐릭터가 대화"
   │  - dialogues: [
   │      { character: "남편", text: "나 개발자가 될 거야!" },
   │      { character: "아내", text: "뭐?!" }
   │    ]
   │  - narration: "1년 전 남편이 선언했죠"
   │
   ↓
⑤ 이미지 생성 단계
   │
   │  AI에게 보내는 프롬프트:
   │  "거실 배경, 두 캐릭터가 대화하는 장면...
   │   DO NOT include any text, speech bubbles..."
   │   ← 대사/나레이션은 프롬프트에 포함하지 않음!
   │   ← AI는 글자 없는 깨끗한 그림만 생성
   │
   ↓
⑥ 이미지 편집 단계
   │
   │  사용자가 그림 자체를 확인/수정/확정
   │  (아직 글자 없는 상태)
   │
   ↓
⑦ 텍스트 오버레이 단계 ← ★ 여기서 대사가 말풍선으로 변환 ★
   │
   │  입력 1: 확정된 이미지 (글자 없음)
   │  입력 2: 스토리 데이터 (대사, 나레이션, 캐릭터명)
   │
   │  Pillow가 하는 일:
   │  1. 이미지를 열고
   │  2. 대사 → 말풍선 그리기 + 한글 텍스트 렌더링
   │  3. 나레이션 → 상단/하단 바에 렌더링
   │  4. 페이지 번호, 시리즈 배지 등 추가
   │  5. 최종 이미지 저장
   │
   ↓
   결과: 말풍선 + 한글 대사가 포함된 최종 이미지
```

### 입력 데이터 구조

텍스트 오버레이에 전달되는 데이터:

```python
@dataclass
class TextOverlayInput:
    """텍스트 오버레이 단계의 입력 데이터"""
    
    # 이미지 편집 단계에서 확정된 깨끗한 이미지
    confirmed_image_path: str
    
    # 스토리 단계에서 생성된 씬 데이터
    scene_number: int
    scene_title: str
    
    # 대사 목록 (말풍선으로 변환될 데이터)
    dialogues: list[DialogueItem]
    
    # 나레이션 (상단/하단 바로 변환)
    narration: Optional[str]
    
    # 전체 시리즈 정보 (페이지 번호용)
    total_scenes: int
    series_number: Optional[int]
    total_series: Optional[int]


@dataclass
class DialogueItem:
    """개별 대사 데이터"""
    character_name: str       # "남편", "세무사" 등
    text: str                 # "나 개발자가 될 거야!"
    character_position: str   # "LEFT" or "RIGHT" (캐릭터 위치)
    expression: str           # "happy", "surprised" 등 (참고용)
    
    # 말풍선 설정 (기본값 있음, 사용자 수정 가능)
    bubble_style: str = "round"        # round / square / thought
    bubble_position: str = "auto"      # auto / top_left / top_right / ...
    font_size: int = 24
```

### 처리 순서 (전체 씬 배치 생성)

```python
async def process_text_overlay_batch(
    story: Story,
    confirmed_images: dict,    # {scene_number: image_path}
    overlay_settings: OverlaySettings
) -> list[str]:
    """전체 씬에 텍스트 오버레이 일괄 처리"""
    
    final_images = []
    
    for scene in story.scenes:
        # 1. 확정된 이미지 열기
        image_path = confirmed_images[scene.scene_number]
        base_image = Image.open(image_path)
        
        # 2. 대사 → 말풍선 합성
        for dialogue in scene.dialogues:
            base_image = add_speech_bubble(
                image=base_image,
                text=dialogue.text,
                character_name=dialogue.character_name,
                character_position=dialogue.character_position,
                bubble_style=overlay_settings.bubble_style,
                font_path=overlay_settings.font_path,
                font_size=overlay_settings.font_size
            )
        
        # 3. 나레이션 합성 (있으면)
        if scene.narration:
            base_image = add_narration_bar(
                image=base_image,
                text=scene.narration,
                position=overlay_settings.narration_position,  # "top" or "bottom"
                font_path=overlay_settings.narration_font_path,
                font_size=overlay_settings.narration_font_size
            )
        
        # 4. 페이지 번호
        base_image = add_page_number(
            image=base_image,
            page_num=scene.scene_number,
            total=len(story.scenes),
            position="bottom_right"
        )
        
        # 5. 시리즈 배지 (시리즈물이면)
        if story.series_info:
            base_image = add_series_badge(
                image=base_image,
                series_num=story.series_info.current,
                total_series=story.series_info.total,
                position="top_left"
            )
        
        # 6. 최종 이미지 저장
        output_path = save_final_image(base_image, scene.scene_number)
        final_images.append(output_path)
    
    return final_images
```

### 말풍선 위치 자동 계산

캐릭터 위치(LEFT/RIGHT)에 따라 말풍선 위치를 자동 결정:

```python
def calculate_bubble_position(
    image_size: tuple,           # (width, height)
    character_position: str,     # "LEFT" or "RIGHT"
    dialogue_index: int,         # 0번째 대사, 1번째 대사
    total_dialogues: int         # 이 씬의 총 대사 수
) -> BubblePosition:
    """캐릭터 위치 기반 말풍선 자동 배치"""
    
    width, height = image_size
    margin = 30  # 여백
    
    if character_position == "LEFT":
        # 왼쪽 캐릭터 → 말풍선은 왼쪽 상단
        x = margin
        bubble_tail_direction = "bottom_left"
    else:
        # 오른쪽 캐릭터 → 말풍선은 오른쪽 상단
        x = width // 2 + margin
        bubble_tail_direction = "bottom_right"
    
    # 여러 대사가 있으면 세로로 배치
    y_offset = dialogue_index * 80
    y = margin + y_offset
    
    return BubblePosition(
        x=x, y=y,
        max_width=width // 2 - margin * 2,
        tail_direction=bubble_tail_direction
    )
```

### 텍스트 줄바꿈 처리

한글은 글자 단위로 줄바꿈 (영어처럼 단어 단위 아님):

```python
def wrap_korean_text(text: str, font: ImageFont, max_width: int) -> list[str]:
    """한글 텍스트를 말풍선 너비에 맞게 줄바꿈"""
    
    lines = []
    current_line = ""
    
    for char in text:
        test_line = current_line + char
        # 현재 줄의 너비 계산
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]
        
        if line_width > max_width:
            # 말풍선 너비 초과 → 줄바꿈
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    
    if current_line:
        lines.append(current_line)
    
    return lines
```

### 대사 수정 시 비용 0원인 이유

텍스트 오버레이는 **Pillow(Python 라이브러리)**가 처리하므로:
- AI API 호출 없음 → **비용 0원**
- 대사 오타 수정 → 텍스트만 다시 렌더링 (이미지 재생성 불필요)
- 말풍선 스타일 변경 → 즉시 적용
- 폰트/크기 변경 → 즉시 적용

```python
async def update_dialogue_text(
    scene_number: int,
    dialogue_index: int,
    new_text: str,
    project: Project
) -> str:
    """대사 텍스트만 수정 (이미지 재생성 없이)"""
    
    # 1. 원본 깨끗한 이미지 (글자 없는 버전) 로드
    clean_image_path = project.get_confirmed_image(scene_number)
    base_image = Image.open(clean_image_path)
    
    # 2. 스토리 데이터에서 대사 업데이트
    project.story.scenes[scene_number].dialogues[dialogue_index].text = new_text
    
    # 3. 텍스트 오버레이 다시 적용 (무료!)
    final_image = await apply_text_overlay(
        base_image=base_image,
        scene=project.story.scenes[scene_number],
        settings=project.overlay_settings
    )
    
    # 4. 최종 이미지 저장
    output_path = save_final_image(final_image, scene_number)
    return output_path
```

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
| 2026-02-09 | 2.0.0 | 스토리→이미지→텍스트 데이터 흐름 추가, 입력 데이터 구조, 말풍선 자동 배치 로직, 한글 줄바꿈, 대사 수정 로직 |
