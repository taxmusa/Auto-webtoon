# 캐릭터 일관성 시스템 (CHARACTER_CONSISTENCY.md)

> **프로젝트**: Tax Webtoon Auto-Generator  
> **버전**: 1.0.0  
> **최종 수정일**: 2026-02-07  
> **목적**: PRD 보충 문서 — 캐릭터 일관성 유지 시스템 설계 + 코딩 AI 프롬프트

---

## 1. 현실적 구현 가능성 평가

### 1.1 AI 이미지 생성의 캐릭터 일관성 한계

**현실**: 2026년 2월 기준, 어떤 AI 이미지 생성 모델도 100% 캐릭터 일관성을 보장하지 못한다. 하지만 아래 기법들을 조합하면 **80~90% 수준의 일관성**을 달성할 수 있다.

| 기법 | 일관성 수준 | 난이도 | 비용 | 우리 시스템 적용 |
|------|------------|--------|------|----------------|
| 프롬프트 고정 (DNA Template) | 60~70% | 낮음 | 무료 | ✅ 기본 적용 |
| 레퍼런스 이미지 첨부 | 75~85% | 중간 | API 토큰 추가 | ✅ 핵심 적용 |
| 캐릭터 시트 생성 + 참조 | 80~90% | 중간 | 1회 생성 비용 | ✅ 핵심 적용 |
| LoRA 학습 (Stable Diffusion) | 90~95% | 높음 | 학습 비용 | ❌ Phase 2 검토 |
| 캐릭터 프리셋 저장/불러오기 | 시스템 기능 | 중간 | 무료 | ✅ 핵심 적용 |

**결론**: 프롬프트 DNA Template + 레퍼런스 이미지 첨부 + 캐릭터 시트 조합으로 **실용적 수준의 일관성** 확보 가능.

### 1.2 모델별 캐릭터 일관성 지원

| 모델 | 레퍼런스 이미지 입력 | 멀티 이미지 입력 | 일관성 수준 |
|------|-------------------|----------------|------------|
| GPT Image 1 / 1.5 | ✅ (이미지 편집 API) | ✅ (최대 4장) | 중~상 |
| DALL-E 3 | ❌ (텍스트만) | ❌ | 낮음 |
| Nano Banana (Gemini 2.5 Flash) | ✅ | ✅ (최대 10장) | 중 |
| Nano Banana Pro (Gemini 3 Pro) | ✅ | ✅ (최대 8장) | 중~상 |

---

## 2. 캐릭터 관리 시스템 설계

### 2.1 캐릭터 데이터 구조

```json
{
  "character_id": "char_001",
  "created_at": "2026-02-07T10:00:00Z",
  "updated_at": "2026-02-07T10:00:00Z",
  
  "meta": {
    "name": "김세무",
    "role": "expert",
    "role_type": "세무사",
    "description": "친근한 30대 여성 세무사"
  },
  
  "dna_template": {
    "physical": {
      "gender": "female",
      "age_range": "early 30s",
      "face_shape": "oval face with soft features",
      "hair": "shoulder-length straight black hair with side bangs",
      "eyes": "warm brown almond-shaped eyes",
      "skin_tone": "light warm skin tone",
      "height_build": "average height, slim build",
      "distinguishing_features": "small mole near left eye"
    },
    "clothing": {
      "default_outfit": "navy blue blazer over white blouse, silver-rimmed glasses on head",
      "color_palette": ["navy blue (#1B2A4A)", "white (#FFFFFF)", "silver (#C0C0C0)"],
      "accessories": "thin silver bracelet on right wrist"
    },
    "style": {
      "art_style": "Korean webtoon style, clean lines, soft colors",
      "proportion": "head-to-body ratio 1:5.5 (webtoon proportion)",
      "line_weight": "medium clean outlines with minimal hatching",
      "color_mood": "warm pastel tones"
    }
  },
  
  "reference_images": {
    "character_sheet": "characters/char_001/sheet.png",
    "front_view": "characters/char_001/front.png",
    "three_quarter_view": "characters/char_001/3q.png",
    "expressions": {
      "neutral": "characters/char_001/expr_neutral.png",
      "happy": "characters/char_001/expr_happy.png",
      "explaining": "characters/char_001/expr_explaining.png",
      "serious": "characters/char_001/expr_serious.png",
      "surprised": "characters/char_001/expr_surprised.png"
    }
  },
  
  "prompt_fragments": {
    "identity_block": "A Korean woman in her early 30s with shoulder-length straight black hair with side bangs, warm brown almond-shaped eyes, oval face with soft features, light warm skin tone, small mole near left eye, wearing a navy blue blazer over white blouse, silver-rimmed glasses pushed up on her head, thin silver bracelet on right wrist",
    "style_block": "Korean webtoon style, clean outlines, soft pastel colors, head-to-body ratio 1:5.5",
    "locked_attributes": ["shoulder-length straight black hair", "warm brown almond-shaped eyes", "small mole near left eye", "navy blue blazer", "silver-rimmed glasses"]
  },
  
  "usage_history": [
    {
      "post_id": "post_20260207_001",
      "date": "2026-02-07",
      "scenes_used": [1, 2, 3, 5, 7],
      "satisfaction_rating": 4
    }
  ]
}
```

### 2.2 캐릭터 프리셋 UI 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  캐릭터 관리                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [+ 새 캐릭터 만들기]  [📁 캐릭터 불러오기]  [📤 가져오기]     │
│                                                             │
│  ─── 저장된 캐릭터 ───                                       │
│                                                             │
│  ┌──────┐  ┌──────┐  ┌──────┐                               │
│  │ 😊   │  │ 🧑‍💼  │  │ 👩‍🔧  │                               │
│  │김세무 │  │박사장 │  │이직장│                               │
│  │세무사 │  │사업자 │  │직장인│                               │
│  │[선택] │  │[선택] │  │[선택]│                               │
│  │[편집] │  │[편집] │  │[편집]│                               │
│  │[삭제] │  │[삭제] │  │[삭제]│                               │
│  └──────┘  └──────┘  └──────┘                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 캐릭터 생성 워크플로우

#### A) 새 캐릭터 만들기

```
[1단계: 기본 정보 입력]
├── 이름, 역할 (질문자/전문가), 역할 유형
├── 성별, 나이대, 분위기 키워드
└── 스타일 선택 (웹툰/카드뉴스/심플)

        ↓

[2단계: AI가 DNA Template 자동 생성]
├── Gemini/GPT가 입력 기반으로 상세 외모 설명 생성
├── 사용자 검토 및 수정 가능
└── 프롬프트 조각(identity_block, style_block) 자동 구성

        ↓

[3단계: 캐릭터 시트 생성]
├── AI가 캐릭터 시트 이미지 생성 (정면/3/4/표정 5종)
├── 사용자 검토 → 불만족 시 재생성
└── 만족 시 레퍼런스 이미지로 저장

        ↓

[4단계: 저장]
├── 로컬 DB (SQLite)에 캐릭터 데이터 저장
├── 레퍼런스 이미지 파일 저장
└── 이후 모든 씬 생성 시 자동 참조
```

#### B) 발행된 인스타툰에서 캐릭터 가져오기

```
[1단계: 이미지 업로드]
├── 이전에 발행한 웹툰 이미지를 드래그&드롭 또는 파일 선택
├── 여러 장 업로드 가능 (같은 캐릭터가 나온 씬들)
└── 인스타에서 직접 다운로드 연동 (Phase 2)

        ↓

[2단계: AI가 캐릭터 분석]
├── 업로드된 이미지에서 캐릭터 외모 특징 자동 추출
│   (Gemini Vision / GPT-4o Vision 활용)
├── DNA Template 자동 생성
│   "이 캐릭터는 단발머리 여성, 네이비 블레이저, 갈색 눈..."
└── 사용자가 검토/수정

        ↓

[3단계: 레퍼런스 이미지 설정]
├── 업로드된 이미지 중 가장 잘 나온 것을 레퍼런스로 선택
├── 또는 AI가 업로드 이미지 기반으로 캐릭터 시트 재생성
└── 정면/3/4/표정 세트 구성

        ↓

[4단계: 저장 및 확인]
├── 테스트 이미지 생성 → 일관성 확인
├── 만족 시 캐릭터 프리셋으로 저장
└── 다음 웹툰 제작 시 불러오기 가능
```

### 2.4 씬 생성 시 캐릭터 일관성 적용 로직

```python
# 의사 코드 (실제 구현 참조용)

def generate_scene_image(scene, characters, model_config):
    """
    씬 이미지 생성 시 캐릭터 일관성 적용
    """
    
    # 1. 프롬프트 구성
    prompt = build_scene_prompt(scene)
    
    # 2. 캐릭터별 identity block 삽입
    for char in characters:
        prompt = inject_character_identity(prompt, char.dna_template)
    
    # 3. LOCKED 속성 명시
    prompt += "\n\nLOCKED ATTRIBUTES (must not change):\n"
    for char in characters:
        for attr in char.prompt_fragments["locked_attributes"]:
            prompt += f"- {char.meta['name']}: {attr}\n"
    
    # 4. 레퍼런스 이미지 첨부 (모델이 지원하는 경우)
    reference_images = []
    for char in characters:
        if char.reference_images.get("character_sheet"):
            reference_images.append(char.reference_images["character_sheet"])
        # 해당 씬의 감정에 맞는 표정 레퍼런스도 추가
        expression = scene.get("expression", "neutral")
        if char.reference_images["expressions"].get(expression):
            reference_images.append(
                char.reference_images["expressions"][expression]
            )
    
    # 5. 모델별 API 호출
    if model_config.model == "gpt-image-1":
        # GPT Image 1: 이미지 편집 API로 레퍼런스 전달
        result = openai_generate_with_reference(
            prompt=prompt,
            reference_images=reference_images,
            size="1024x1536"
        )
    elif model_config.model == "nano-banana":
        # Nano Banana: 멀티 이미지 입력으로 레퍼런스 전달
        result = gemini_generate_with_reference(
            prompt=prompt,
            reference_images=reference_images
        )
    
    return result
```

---

## 3. 캐릭터 일관성 확보 핵심 기법

### 3.1 DNA Template (프롬프트 고정)

모든 씬 생성 시 동일한 캐릭터 설명 블록을 프롬프트에 삽입한다.

```
[SYSTEM PROMPT FOR IMAGE GENERATION]

CHARACTER IDENTITY (DO NOT MODIFY):
Character 1 - "김세무" (Tax Expert):
- LOCKED: Korean woman, early 30s
- LOCKED: Shoulder-length straight black hair with side bangs
- LOCKED: Warm brown almond-shaped eyes
- LOCKED: Oval face with soft features, small mole near left eye
- LOCKED: Navy blue blazer over white blouse
- LOCKED: Silver-rimmed glasses pushed up on head
- LOCKED: Head-to-body ratio 1:5.5

Character 2 - "박사장" (Business Owner):
- LOCKED: Korean man, mid 40s
- LOCKED: Short neat black hair, slightly graying at temples
- LOCKED: Round face, warm smile lines
- LOCKED: Gray suit with loosened tie
- LOCKED: Slightly stocky build

STYLE CONSISTENCY:
- LOCKED: Korean webtoon style
- LOCKED: Clean outlines, soft pastel color palette
- LOCKED: Warm lighting throughout all scenes

SCENE: {scene_description}
EXPRESSIONS: {character_expressions}
```

### 3.2 레퍼런스 이미지 활용

#### GPT Image 1 / 1.5

```python
# 레퍼런스 이미지와 함께 새 씬 생성
from openai import OpenAI

client = OpenAI()

# 방법 1: 이미지 편집 API (가장 일관성 높음)
result = client.images.edit(
    model="gpt-image-1",
    image=open("character_sheet.png", "rb"),  # 레퍼런스
    prompt="""
    Using this exact character design, create a new scene:
    The tax expert character (exactly as shown in the reference) 
    is sitting at a desk explaining tax forms to a worried 
    business owner. Korean webtoon style, same art style as reference.
    
    CHARACTER CONSISTENCY:
    - Same facial features, hair style, and outfit as reference
    - Same art style and line weight
    - Same color palette
    """,
    size="1024x1536"
)

# 방법 2: Responses API (멀티 이미지 입력)
response = client.responses.create(
    model="gpt-4.1",
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": "character_sheet_base64_or_url"
                },
                {
                    "type": "input_text", 
                    "text": "Image 1 is the character reference sheet. "
                            "Generate a new scene maintaining EXACT same "
                            "character appearance: ..."
                }
            ]
        }
    ],
    tools=[{"type": "image_generation", "quality": "medium", "size": "1024x1536"}]
)
```

#### Nano Banana (Gemini API)

```python
from google import genai

client = genai.Client()

# 레퍼런스 이미지를 함께 전달
reference_image = genai.types.Part.from_image(
    open("character_sheet.png", "rb")
)

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[
        reference_image,
        """
        This is my character reference sheet. 
        Create a new scene with this EXACT same character:
        
        Scene: The character is standing in front of a whiteboard, 
        pointing at tax calculation formulas.
        
        CRITICAL: Maintain identical:
        - Facial features and hair style
        - Clothing and accessories  
        - Art style and color palette
        - Body proportions
        
        Korean webtoon style, 4:5 aspect ratio for Instagram.
        """
    ]
)
```

### 3.3 캐릭터 시트 자동 생성

캐릭터 등록 시 아래와 같은 캐릭터 시트를 자동 생성한다:

```
프롬프트 예시:

"Create a character reference sheet for a Korean webtoon character.
Layout: 2 rows x 3 columns grid on white background.

Character: Young Korean woman tax expert, early 30s, 
shoulder-length straight black hair with side bangs, 
warm brown almond-shaped eyes, oval face, 
navy blue blazer over white blouse, silver glasses on head.

Grid contents:
[Row 1] Front view (neutral) | Three-quarter view | Profile view
[Row 2] Happy expression | Explaining gesture | Surprised expression

Style: Clean Korean webtoon style, soft pastel colors, 
consistent proportions across all views.
Each cell clearly separated with thin gray borders.
White background, no text labels."
```

### 3.4 씬 간 일관성 체크 로직

```python
def check_consistency_between_scenes(scenes_images, character_ref):
    """
    생성된 씬 이미지들 간의 캐릭터 일관성을 AI로 검증
    """
    
    # Vision 모델로 일관성 평가 요청
    evaluation_prompt = f"""
    아래 이미지들은 같은 웹툰의 여러 씬입니다.
    캐릭터 레퍼런스 시트와 비교하여 일관성을 평가해주세요.
    
    평가 항목 (각 1~5점):
    1. 얼굴 특징 일관성
    2. 헤어스타일 일관성
    3. 의상 일관성
    4. 아트 스타일 일관성
    5. 체형/비율 일관성
    
    총점이 20점 미만이면 재생성을 권장합니다.
    
    JSON으로 응답:
    {{
      "scores": {{"face": N, "hair": N, "outfit": N, "style": N, "proportion": N}},
      "total": N,
      "issues": ["씬 3에서 머리카락 길이가 달라짐", ...],
      "recommendation": "pass" | "regenerate_scenes" | "regenerate_all"
    }}
    """
    
    # Gemini Vision 또는 GPT-4o Vision으로 평가
    result = evaluate_with_vision_model(
        images=[character_ref] + scenes_images,
        prompt=evaluation_prompt
    )
    
    return result
```

---

## 4. 로컬 저장소 설계

### 4.1 디렉토리 구조

```
/app_data/
├── /characters/
│   ├── /char_001/
│   │   ├── meta.json              # 캐릭터 메타데이터 + DNA Template
│   │   ├── sheet.png              # 캐릭터 시트 (6컷 그리드)
│   │   ├── front.png              # 정면 뷰 (크롭)
│   │   ├── 3q.png                 # 3/4 뷰 (크롭)
│   │   ├── expr_neutral.png       # 표정별 이미지
│   │   ├── expr_happy.png
│   │   ├── expr_explaining.png
│   │   ├── expr_serious.png
│   │   └── expr_surprised.png
│   └── /char_002/
│       └── ...
│
├── /projects/
│   ├── /proj_20260207_001/
│   │   ├── project.json           # 프로젝트 설정 (사용 캐릭터, 씬 등)
│   │   ├── /scenes/
│   │   │   ├── scene_01.png
│   │   │   ├── scene_01_overlay.png  # 텍스트 오버레이 후
│   │   │   └── ...
│   │   └── /published/
│   │       ├── final_01.png
│   │       └── ...
│   └── ...
│
└── /db/
    └── app.sqlite                 # 메타데이터, 히스토리
```

### 4.2 SQLite 스키마

```sql
CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,              -- 'expert' | 'questioner'
    role_type TEXT,                  -- '세무사', '사업자', '직장인' 등
    dna_template_json TEXT NOT NULL, -- JSON blob
    prompt_fragments_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    last_used_at DATETIME
);

CREATE TABLE character_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    image_type TEXT NOT NULL,        -- 'sheet', 'front', '3q', 'expr_happy' 등
    file_path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES characters(id)
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    title TEXT,
    keyword TEXT,
    status TEXT DEFAULT 'draft',     -- 'draft', 'scenes_ready', 'images_ready', 'published'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_characters (
    project_id TEXT,
    character_id TEXT,
    role_in_project TEXT,            -- 이 프로젝트에서의 역할
    PRIMARY KEY (project_id, character_id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (character_id) REFERENCES characters(id)
);
```

---

## 5. 일관성 향상 팁 (프롬프트 엔지니어링)

### 5.1 핵심 원칙

1. **Identity Block은 매 프롬프트에 100% 동일하게 복사-붙여넣기** — 단어 하나도 바꾸지 않는다
2. **LOCKED 키워드 사용** — AI 모델이 변경 불가 속성을 인식하도록 명시
3. **변경되는 것만 명시적으로 분리** — 포즈, 배경, 표정만 씬별로 변경
4. **색상은 hex 코드로 지정** — "파란색"이 아니라 "#1B2A4A 네이비 블루"
5. **비율을 숫자로 고정** — "1:5.5 head-to-body ratio" 명시
6. **레퍼런스 이미지는 항상 함께 전송** — 텍스트만으로는 한계가 크다
7. **이전 씬 결과물도 참조로 전달** — "maintain visual continuity with Image 1"

### 5.2 프롬프트 구조 템플릿

```
[CHARACTER IDENTITY - DO NOT MODIFY]
{identity_block 전문 복사}

[STYLE LOCK]
{style_block 전문 복사}

[THIS SCENE]
Scene number: {N}
Setting: {배경 설명}
Action: {캐릭터 행동}
Expression: {표정}
Camera angle: {앵글}

[CRITICAL RULES]
- Maintain EXACT same character appearance as the reference image
- DO NOT change: {locked_attributes 나열}
- Only change: pose, expression, background
- Keep identical art style, line weight, and color palette
```

### 5.3 흔한 문제와 해결법

| 문제 | 원인 | 해결 |
|------|------|------|
| 머리 색/길이 변함 | 프롬프트에서 hair 설명이 모호 | "shoulder-length"→"hair reaching exactly to shoulders, 25cm length" |
| 의상 색상 변함 | "blue"가 모호 | hex 코드 지정: "navy blue (#1B2A4A)" |
| 얼굴이 달라짐 | 레퍼런스 없이 텍스트만 사용 | 반드시 캐릭터 시트를 레퍼런스로 전달 |
| 스타일 변함 | 씬 설명이 스타일 설명을 압도 | style_block을 프롬프트 최상단에 배치 |
| 2인 캐릭터 뒤바뀜 | 누가 누구인지 불분명 | "LEFT: 김세무 (expert), RIGHT: 박사장 (questioner)" 위치 지정 |
| 체형이 달라짐 | proportion 미지정 | "head-to-body 1:5.5, shoulders 2.5x head width" |

---

## 6. 커서(Cursor) / 코딩 AI용 프롬프트

아래는 실제 개발 시 커서(Cursor), Windsurf, Claude Code 등 코딩 AI에게 제공할 프롬프트입니다.

---

### 6.1 시스템 프롬프트 (프로젝트 전체용)

```
## Project Context

You are building "Tax Webtoon Auto-Generator" — a Python FastAPI local web app (.exe) 
that auto-generates webtoon/card-news style Instagram content about tax/finance topics.

### Architecture
- Backend: Python FastAPI (async)
- Frontend: HTML/CSS/JS (served by FastAPI, localhost:8000)
- DB: SQLite (local storage)
- Image Gen: GPT Image 1 / Nano Banana (user's API key)
- Text Gen: Gemini 2.5 Flash (user's API key)
- Text Overlay: Python Pillow
- Image Hosting: Imgur API
- Publishing: Instagram Graph API
- Packaging: PyInstaller → .exe

### Key Design Principles
1. All AI API keys are provided by the user (no server costs)
2. Multiple AI model support (user selects their preferred model)
3. Character consistency is critical — see CHARACTER_CONSISTENCY.md
4. All UI is web-based (HTML served from FastAPI)
5. Offline-first (works without internet after initial setup, except API calls)

### Character Consistency System (CRITICAL)
- Every character has a DNA Template (fixed prompt text) + Reference Images
- Characters are saved to local SQLite DB + file system
- When generating scene images, ALWAYS:
  1. Include the character's identity_block in the prompt (verbatim, never modified)
  2. Attach character reference images to the API call
  3. Add LOCKED attributes list
  4. Use the scene-specific changes (pose, expression, background) separately
- Support character CRUD: Create, Read, Update, Delete
- Support importing characters from previously published webtoon images
- Character sheet generation: 6-view grid (front, 3/4, profile, 3 expressions)
```

### 6.2 캐릭터 관리 모듈 구현 프롬프트

```
## Task: Implement Character Management Module

### File: app/services/character_service.py

Implement a CharacterService class with these methods:

1. create_character(name, role, role_type, appearance_keywords) -> Character
   - Use Gemini/GPT to generate detailed DNA Template from keywords
   - Generate character sheet image (6-view grid)
   - Save to SQLite + file system
   - Return Character object with all data

2. import_from_images(images: List[UploadFile]) -> Character
   - Use Vision AI to analyze uploaded webtoon images
   - Extract character features automatically
   - Generate DNA Template from analysis
   - Optionally regenerate character sheet for cleaner reference
   - Save and return Character

3. get_character(character_id) -> Character
4. list_characters() -> List[Character]
5. update_character(character_id, updates) -> Character
6. delete_character(character_id) -> None

7. generate_character_sheet(character: Character) -> str (file_path)
   - Generate 2x3 grid: front, 3/4, profile, happy, explaining, surprised
   - Use the character's DNA Template as prompt
   - Save as single PNG file

8. build_scene_prompt(scene, characters: List[Character]) -> dict
   - Returns {"prompt": str, "reference_images": List[str]}
   - Assembles the full prompt with:
     a) Style lock block
     b) Each character's identity_block (VERBATIM - never modify)
     c) LOCKED attributes list
     d) Scene-specific description
     e) List of reference image paths to attach

### Data Models (Pydantic):

class CharacterDNA(BaseModel):
    physical: dict  # gender, age_range, face_shape, hair, eyes, etc.
    clothing: dict  # default_outfit, color_palette, accessories
    style: dict     # art_style, proportion, line_weight, color_mood

class Character(BaseModel):
    id: str
    name: str
    role: str  # 'expert' | 'questioner'
    role_type: str
    dna_template: CharacterDNA
    prompt_fragments: dict  # identity_block, style_block, locked_attributes
    reference_images: dict  # paths to character sheet and expression images

### Critical Implementation Notes:
- identity_block must be stored as a FROZEN string that is NEVER modified
  after creation — it is always inserted verbatim into prompts
- Reference images must be loaded as base64 and sent with API calls
- Character sheet generation prompt must produce a GRID layout,
  not separate images (saves API calls and ensures style consistency)
- When 2+ characters appear in a scene, specify LEFT/RIGHT positioning
- Add a consistency_check method that uses Vision AI to compare
  generated scene images against the character sheet
```

### 6.3 이미지 생성 모듈 프롬프트

```
## Task: Implement Image Generation Module with Character Consistency

### File: app/services/image_generator.py

Implement an ImageGenerator class that supports multiple AI models
and enforces character consistency.

### Interface:

class ImageGenerator:
    def __init__(self, model_config: ModelConfig):
        """
        model_config contains:
        - model_name: "gpt-image-1" | "gpt-image-1-mini" | "dall-e-3" 
                     | "nano-banana" | "nano-banana-pro"
        - api_key: user's API key
        - quality: "low" | "medium" | "high"
        - size: "1024x1536" (4:5 for Instagram)
        """
    
    async def generate_scene(
        self,
        prompt: str,
        reference_images: List[str] = None,  # file paths
        style: str = "webtoon"
    ) -> GeneratedImage:
        """
        Routes to the appropriate model-specific method.
        ALWAYS attaches reference_images if the model supports it.
        """
    
    async def _generate_gpt_image(self, prompt, refs) -> GeneratedImage:
        """
        GPT Image 1/1.5: Use images.edit() for ref-based generation
        or images.generate() with prompt-only fallback
        """
    
    async def _generate_nano_banana(self, prompt, refs) -> GeneratedImage:
        """
        Nano Banana: Use multi-image input with genai client
        """
    
    async def _generate_dalle3(self, prompt, refs) -> GeneratedImage:
        """
        DALL-E 3: Text-only (no reference support)
        Relies heavily on DNA Template in prompt
        """
    
    async def check_consistency(
        self,
        generated_images: List[str],
        character_ref: str
    ) -> ConsistencyReport:
        """
        Uses Vision AI to compare generated images against reference.
        Returns scores and recommendations.
        """

### Prompt Assembly Rules (MUST FOLLOW):
1. Start with STYLE LOCK block
2. Add CHARACTER IDENTITY blocks (verbatim from DNA Template)
3. Add LOCKED ATTRIBUTES list
4. Add scene-specific description LAST
5. Never modify identity_block text — always copy exactly as stored
6. For 2+ characters, specify spatial positions (LEFT/RIGHT/CENTER)
7. Include "maintain visual continuity with reference images" instruction

### Model-specific Reference Image Handling:
- GPT Image 1/1.5: Send as image parameter in images.edit()
  or as input_image in Responses API
- Nano Banana: Send as Part.from_image() in contents list
- Nano Banana Pro: Same as Nano Banana, supports up to 8 images
- DALL-E 3: NO reference support — prompt-only
  (warn user about lower consistency)
```

### 6.4 프론트엔드 캐릭터 관리 UI 프롬프트

```
## Task: Build Character Management UI

### Files:
- app/templates/characters.html
- app/static/js/characters.js
- app/static/css/characters.css

### Requirements:

1. Character List View
   - Grid of saved characters (thumbnail + name + role)
   - [New Character] [Import from Image] buttons
   - Click to select for current project
   - Edit / Delete options per character

2. Character Creation Modal
   - Step 1: Basic info form (name, role, role_type, keywords)
   - Step 2: AI generates DNA Template → user reviews/edits
   - Step 3: AI generates character sheet → user approves or regenerates
   - Step 4: Save confirmation

3. Character Import Modal
   - Drag & drop zone for images
   - AI analysis progress indicator
   - Generated DNA Template review
   - Character sheet generation option

4. Character Detail / Edit View
   - Character sheet image display
   - DNA Template text (editable)
   - Expression gallery
   - Usage history (which posts used this character)
   - [Regenerate Sheet] [Test Generation] buttons

5. Character Selection for Project
   - When creating a new webtoon, show character picker
   - Select 1 expert + 1 questioner (or custom roles)
   - Selected characters shown as pills/tags in the workflow

### UX Notes:
- Character sheet should be prominently displayed
- Show a "consistency score" after test generations
- Allow quick expression preview (click expression → see example)
- Mobile-responsive (web UI used on desktop primarily but be clean)
```

---

## 7. Phase 2 고려사항

### 7.1 LoRA 학습 통합 (추후)
- Stable Diffusion 기반 LoRA 학습으로 캐릭터 모델 생성
- 학습 데이터: 캐릭터 시트 + 다양한 포즈 10~20장
- 일관성 90%+ 달성 가능하나 학습 시간/비용 필요

### 7.2 캐릭터 마켓플레이스 (추후)
- 사용자 간 캐릭터 프리셋 공유/판매
- DNA Template + 캐릭터 시트 패키지

### 7.3 인스타그램 연동 캐릭터 추출 (추후)
- Instagram Graph API로 기발행 게시물 이미지 자동 다운로드
- AI가 캐릭터 자동 추출 및 등록 제안

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-07 | 1.0.0 | 초기 작성 — 캐릭터 일관성 시스템 설계, 구현 가이드, 코딩 AI 프롬프트 |
