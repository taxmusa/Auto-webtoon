# STYLE_SYSTEM.md - 스타일 관리 시스템

> **프로젝트**: Tax Webtoon Auto-Generator  
> **버전**: 1.0.0  
> **최종 수정일**: 2026-02-09  
> **목적**: 인물 스타일 / 배경 스타일 저장·관리·적용 시스템 + 샘플 미리보기 + 수동 프롬프트 편집

---

## 1. 개요 및 목적

### 1.1 왜 필요한가

- **브랜드 일관성**: 같은 계정에서 올리는 웹툰은 매번 다른 주제라도 동일한 그림체/분위기를 유지해야 팔로워가 인지함
- **기존 발행물 연속성**: 이미 올린 인스타툰이 있으면, 새 콘텐츠도 같은 스타일로 만들어야 함
- **비용 절약**: 본 생성 전에 샘플로 스타일을 확인하고 진행해야 재생성 횟수 감소
- **세밀한 제어**: 자동 프롬프트만으로 부족할 때 수동으로 기준 이미지를 바꿀 수 있어야 함

### 1.2 핵심 기능 요약

| 기능 | 설명 |
|------|------|
| **스타일 저장** | 인물 스타일 / 배경 스타일을 별도로 저장·관리 |
| **발행물에서 추출** | 기존 발행 이미지를 업로드하면 Vision AI가 스타일 자동 분석 |
| **직접 업로드 저장** | 사진/이미지를 올려서 인물 or 배경 스타일로 저장 |
| **스타일 조합 선택** | 저장된 인물 스타일 + 배경 스타일을 조합하여 이미지 생성 |
| **샘플 미리보기** | 실제 생성 전에 1장 샘플로 스타일 확인 (Low 품질로 비용 절약) |
| **수동 프롬프트 편집** | 샘플이 마음에 안 들면 기준 이미지 프롬프트를 직접 수정 |

---

## 2. 데이터 구조

### 2.1 스타일 프리셋 (Style Preset)

```json
{
  "style_id": "style_001",
  "created_at": "2026-02-09T10:00:00Z",
  "updated_at": "2026-02-09T10:00:00Z",
  
  "meta": {
    "name": "깔끔한 세무 웹툰",
    "description": "파스텔톤, 클린 라인, 따뜻한 조명의 한국 웹툰 스타일",
    "tags": ["웹툰", "파스텔", "깔끔"],
    "usage_count": 0
  },

  "character_style": {
    "style_id": "char_style_001",
    "name": "클린 웹툰 캐릭터",
    "prompt_block": "Korean webtoon style, clean outlines with medium line weight, soft pastel skin tones, expressive anime-inspired eyes, head-to-body ratio 1:5.5, warm natural lighting, soft shadow under chin",
    "reference_images": [
      "styles/char_style_001/ref_01.png",
      "styles/char_style_001/ref_02.png"
    ],
    "locked_attributes": [
      "clean outlines with medium line weight",
      "soft pastel skin tones",
      "head-to-body ratio 1:5.5",
      "warm natural lighting"
    ],
    "extracted_from": null,
    "source_type": "manual"
  },

  "background_style": {
    "style_id": "bg_style_001",
    "name": "사무실/도시 배경",
    "prompt_block": "modern Korean office interior, warm lighting, soft pastel wall colors (#F5E6D3), clean minimalist furniture, large window with city view, soft depth-of-field blur on background, consistent warm color palette",
    "reference_images": [
      "styles/bg_style_001/ref_01.png",
      "styles/bg_style_001/ref_02.png"
    ],
    "locked_attributes": [
      "warm lighting",
      "soft pastel wall colors (#F5E6D3)",
      "soft depth-of-field blur on background"
    ],
    "extracted_from": null,
    "source_type": "manual"
  }
}
```

### 2.2 인물 스타일 (Character Style) — 별도 저장

캐릭터 DNA Template과는 **별개**. DNA Template은 "이 사람이 누구인지"(얼굴, 머리, 의상)이고, Character Style은 "어떤 그림체로 그릴 것인지"(선 굵기, 색감, 비율, 조명).

```json
{
  "style_id": "char_style_001",
  "name": "클린 웹툰 캐릭터",
  "description": "깨끗한 선, 파스텔톤, 1:5.5 비율",
  
  "prompt_block": "Korean webtoon style, clean outlines with medium line weight, soft pastel skin tones, expressive anime-inspired eyes, head-to-body ratio 1:5.5, warm natural lighting, soft shadow under chin",
  
  "visual_attributes": {
    "line_style": "clean outlines, medium weight, no sketch marks",
    "color_palette": "soft pastel (#FFE4C9 skin, #F8D7DA blush, #FFB6C1 accents)",
    "proportion": "head-to-body ratio 1:5.5",
    "shading": "soft cel-shading with warm tones",
    "lighting": "warm natural lighting, soft shadow under chin",
    "expression_style": "expressive anime-inspired eyes, subtle mouth expressions"
  },
  
  "reference_images": ["styles/char_style_001/ref_01.png"],
  "locked_attributes": ["clean outlines", "head-to-body ratio 1:5.5", "warm natural lighting"],
  
  "source_type": "extracted",
  "extracted_from": {
    "image_paths": ["uploads/my_existing_webtoon_01.png"],
    "extraction_date": "2026-02-09",
    "ai_analysis_raw": "..."
  }
}
```

### 2.3 배경 스타일 (Background Style) — 별도 저장

```json
{
  "style_id": "bg_style_001",
  "name": "따뜻한 사무실",
  "description": "한국식 사무실, 따뜻한 조명, 도시 뷰",
  
  "prompt_block": "modern Korean office interior, warm lighting (#FFD4A0 ambient), soft pastel wall colors (#F5E6D3), clean minimalist furniture, large window with city view, soft depth-of-field blur, watercolor-like background texture",
  
  "visual_attributes": {
    "setting": "indoor office / urban",
    "color_palette": "warm tones (#FFD4A0 ambient, #F5E6D3 walls, #E8D5C4 floor)",
    "lighting": "warm natural window light, soft ambient fill",
    "detail_level": "medium - furniture outlines clean but not photorealistic",
    "depth": "soft depth-of-field blur on background elements",
    "texture": "watercolor-like soft gradients"
  },
  
  "reference_images": ["styles/bg_style_001/ref_01.png"],
  "locked_attributes": ["warm lighting (#FFD4A0 ambient)", "soft depth-of-field blur"],
  
  "source_type": "uploaded",
  "source_images": ["uploads/office_background_ref.png"]
}
```

### 2.4 비주얼 프리셋 (Visual Presets / Sub Styles) ⭐

전용 프롬프트 블록을 통해 이미지의 전체적인 렌더링 방식이나 분위기를 결정하는 **상위 레이어 스타일**입니다. 인물/배경 스타일과 조합하여 사용됩니다.

| ID | 이름 | 이모지 | 주요 특징 |
|---|---|---|---|
| `ghibli` | 지브리 | 🌿 | 지브리풍 부드러운 색감과 수채화 질감 |
| `romance` | 로맨스 | 💕 | 파스텔 톤, 따뜻하고 몽환적인 감성 |
| `business` | 비즈니스 | 💼 | 깔끔하고 전문적인 느낌의 오피스 일러스트 |
| `round_lineart` | 동글 라인 | ✏️ | 둥글둥글하고 귀여운 외곽선 강조 |
| `pastel_flat` | 파스텔 플랫 | 🎨 | 부드러운 파스텔 톤의 평면적 일러스트 |
| `bold_cartoon` | 볼드 카툰 | 💥 | 굵은 선과 원색 위주의 강렬한 카툰풍 |
| `pencil_sketch` | 연필 스케치 | 📝 | 손그림 느낌의 텍스처와 연필 질감 |
| `monoline` | 모노라인 | 〰️ | 일정한 선 두께의 미니멀한 라인 아트 |
| `watercolor_soft`| 수채화 | 💧 | 물조절이 느껴지는 번짐 효과와 투명감 |
| `neon_pop` | 네온 팝 | 🌙 | 어두운 배경과 대조되는 화려한 네온 컬러 |
| `emoji_icon` | 이모지 | 😊 | 극단적으로 단순화된 아이콘 스타일 |
| `retro_90s` | 90s 레트로 | 📼 | 90년대 애니메이션 특유의 빈티지 색감 |
| `cutout_collage` | 컷아웃 | ✂️ | 종이를 오려 붙인 듯한 콜라주 형태 |

**적용 로직**:
최종 프롬프트 구성 시 `[RENDERING STYLE / VISUAL PRESET]` 섹션에 해당 프리셋의 프롬프트가 삽입됩니다.

---

## 3. 스타일 저장 워크플로우

### 3.1 방법 A: 기존 발행물에서 추출 ⭐

사용자가 이미 올린 인스타툰 이미지를 업로드하면, Vision AI가 자동 분석.

```
[이미지 업로드 (여러 장 가능)]
        ↓
[Vision AI 분석]
  - 인물 스타일 추출 (선 스타일, 색감, 비율, 조명, 표정 스타일)
  - 배경 스타일 추출 (장소, 색상 팔레트, 조명, 디테일 수준, 텍스처)
        ↓
[사용자에게 분석 결과 표시]
  ┌──────────────────────────────────────────────┐
  │ 📸 분석 결과                                  │
  │                                              │
  │ 🧑 인물 스타일:                               │
  │ "클린 라인, 파스텔톤, 1:5.5 비율, 따뜻한 조명" │
  │ [인물 스타일로 저장] [수정 후 저장]             │
  │                                              │
  │ 🏙️ 배경 스타일:                               │
  │ "사무실, 따뜻한 조명, 도시 뷰, 소프트 블러"    │
  │ [배경 스타일로 저장] [수정 후 저장]             │
  │                                              │
  │ [둘 다 저장] [다시 분석]                       │
  └──────────────────────────────────────────────┘
        ↓
[저장 완료 → 스타일 관리에서 확인]
```

**Vision AI 분석 프롬프트**:

```python
STYLE_EXTRACTION_PROMPT = """
You are an expert visual style analyst for Korean webtoon/cartoon images.

Analyze the uploaded image(s) and extract two separate style profiles:

## CHARACTER STYLE (인물 스타일)
Describe the following visual attributes of how characters are drawn:
- line_style: outline thickness, sketch vs clean, ink quality
- color_palette: skin tones (with hex codes), hair colors, clothing color tendencies
- proportion: head-to-body ratio, eye size relative to face
- shading: cel-shading, gradient, flat color, shadow style
- lighting: direction, warmth, shadow intensity on characters
- expression_style: how eyes/mouth are drawn, level of expressiveness

## BACKGROUND STYLE (배경 스타일)  
Describe the following visual attributes of backgrounds:
- setting: type of location (office, outdoor, abstract, etc.)
- color_palette: dominant colors with hex codes
- lighting: ambient light color, direction, intensity
- detail_level: photorealistic, simplified, abstract
- depth: depth-of-field blur, flat, layered
- texture: smooth gradient, watercolor, flat vector, etc.

## OUTPUT FORMAT
Return JSON with these exact keys:
{
  "character_style": {
    "prompt_block": "<one paragraph prompt that captures all character style attributes>",
    "visual_attributes": { "line_style": "...", "color_palette": "...", "proportion": "...", "shading": "...", "lighting": "...", "expression_style": "..." },
    "locked_attributes": ["<top 3-4 most distinctive attributes>"]
  },
  "background_style": {
    "prompt_block": "<one paragraph prompt that captures all background style attributes>",
    "visual_attributes": { "setting": "...", "color_palette": "...", "lighting": "...", "detail_level": "...", "depth": "...", "texture": "..." },
    "locked_attributes": ["<top 3-4 most distinctive attributes>"]
  }
}
"""
```

### 3.2 방법 B: 사진/이미지 직접 업로드

사용자가 참고 이미지를 올려서 원하는 스타일 유형(인물 or 배경)을 선택하여 저장.

```
[이미지 업로드]
        ↓
[저장 유형 선택]
  ○ 인물 스타일로 저장
  ○ 배경 스타일로 저장
  ○ 둘 다 분석해서 저장
        ↓
[Vision AI 분석 → 프롬프트 자동 생성]
        ↓
[사용자 검토/수정]
        ↓
[이름 지정 → 저장]
```

### 3.3 방법 C: 수동 생성

프롬프트를 직접 작성하여 스타일 저장.

```
[스타일 유형 선택: 인물 / 배경]
        ↓
[프롬프트 직접 입력]
        ↓
[테스트 이미지 생성 (샘플)]
        ↓
[만족 → 저장 / 불만족 → 프롬프트 수정]
```

---

## 4. 스타일 조합 및 적용

### 4.1 프로젝트에서 스타일 선택

새 웹툰을 만들 때, 저장된 스타일 중에서 인물 스타일과 배경 스타일을 각각 선택.

```
┌─────────────────────────────────────────────────────────────────┐
│  🎨 스타일 선택                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🧑 인물 스타일                                        [관리]    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ [미리보기]│ │ [미리보기]│ │ [미리보기]│ │    +     │          │
│  │ 클린 웹툰 │ │ 지브리풍  │ │ 리얼리스틱│ │ 새로추가  │          │
│  │   ● 선택  │ │   ○      │ │   ○      │ │          │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                 │
│  🏙️ 배경 스타일                                       [관리]    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ [미리보기]│ │ [미리보기]│ │ [미리보기]│ │    +     │          │
│  │ 따뜻한    │ │ 심플 단색 │ │ 도시 야경 │ │ 새로추가  │          │
│  │ 사무실    │ │          │ │          │ │          │          │
│  │   ● 선택  │ │   ○      │ │   ○      │ │          │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                 │
│  ─── 선택된 조합 미리보기 ───                                    │
│  인물: "클린 웹툰" + 배경: "따뜻한 사무실"                       │
│                                                                 │
│  [🔍 샘플 미리보기 생성]                    [다음 단계 →]         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 프롬프트 결합 로직

```python
def build_styled_prompt(
    scene: Scene,
    characters: list[Character],
    character_style: CharacterStyle,
    background_style: BackgroundStyle,
    manual_override: str = None
) -> str:
    """스타일 프리셋이 적용된 최종 프롬프트 구성"""
    
    parts = []
    
    # 1. 글로벌 스타일 (인물 스타일에서)
    parts.append(f"""
[GLOBAL ART STYLE - DO NOT DEVIATE]
{character_style.prompt_block}
""")
    
    # 2. 배경 스타일
    parts.append(f"""
[BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]
{background_style.prompt_block}
""")
    
    # 3. 캐릭터 Identity (DNA Template에서 — 개별 인물 정체성)
    for i, char in enumerate(characters):
        position = "LEFT" if i == 0 else "RIGHT"
        parts.append(f"""
[CHARACTER {i+1} IDENTITY - DO NOT MODIFY]
Position: {position}
{char.prompt_fragments['identity_block']}
""")
    
    # 4. 이번 씬 설명
    parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {scene.expression or 'auto'}
""")
    
    # 5. LOCKED 속성 (스타일 + 캐릭터 모두)
    locked = "\n[LOCKED ATTRIBUTES]:\n"
    
    # 스타일 LOCKED
    for attr in character_style.locked_attributes:
        locked += f"- STYLE: {attr}\n"
    for attr in background_style.locked_attributes:
        locked += f"- BACKGROUND: {attr}\n"
    
    # 캐릭터 LOCKED
    for char in characters:
        for attr in char.prompt_fragments['locked_attributes']:
            locked += f"- {char.meta['name']}: {attr}\n"
    
    parts.append(locked)
    
    # 6. 텍스트 제외
    parts.append("""
[EXCLUSION]
DO NOT include any text, speech bubbles, letters, words, 
numbers, or typography in the image.
""")
    
    # 7. 수동 오버라이드 (사용자가 직접 수정한 경우)
    if manual_override:
        parts.append(f"""
[USER MANUAL OVERRIDE]
{manual_override}
""")
    
    return "\n".join(parts)
```

### 4.3 스타일과 캐릭터의 관계 정리

```
┌──────────────────────────────────────────────────────────┐
│                    최종 이미지 프롬프트                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐  ← "어떤 그림체로?" (스타일)       │
│  │ Character Style  │     선 굵기, 색감, 비율, 조명       │
│  │ (인물 스타일)     │                                    │
│  └─────────────────┘                                     │
│           +                                              │
│  ┌─────────────────┐  ← "어떤 배경으로?" (스타일)       │
│  │ Background Style │     장소, 색상, 조명, 텍스처        │
│  │ (배경 스타일)     │                                    │
│  └─────────────────┘                                     │
│           +                                              │
│  ┌─────────────────┐  ← "누가 등장?" (캐릭터)           │
│  │ Character DNA    │     얼굴, 머리, 의상, 체형          │
│  │ (캐릭터 정체성)   │     ※ CHARACTER_CONSISTENCY.md      │
│  └─────────────────┘                                     │
│           +                                              │
│  ┌─────────────────┐  ← "무슨 장면?" (씬)              │
│  │ Scene Description│     행동, 감정, 구도                │
│  │ (장면 설명)       │                                    │
│  └─────────────────┘                                     │
│           =                                              │
│  ┌─────────────────┐                                     │
│  │ 최종 이미지       │                                    │
│  └─────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

---

## 5. 샘플 미리보기 (Style Preview) ⭐

### 5.1 목적

실제 전체 씬 이미지를 생성하기 전에, 선택한 스타일 조합이 어떤 느낌인지 **1장 샘플**을 저비용으로 확인하는 기능.

### 5.2 워크플로우

```
[인물 스타일 선택] + [배경 스타일 선택] + [캐릭터 선택]
        ↓
[🔍 샘플 미리보기 생성] 버튼 클릭
        ↓
[Low 품질 + 저해상도로 1장 생성] ← API 비용 최소화
        ↓
[미리보기 표시]
  ┌────────────────────────────────────────────────┐
  │  🔍 스타일 샘플 미리보기                        │
  │                                                │
  │  ┌──────────────────────────────┐              │
  │  │                              │              │
  │  │    [샘플 이미지 표시]         │              │
  │  │    (512x640 Low 품질)         │              │
  │  │                              │              │
  │  └──────────────────────────────┘              │
  │                                                │
  │  적용된 스타일:                                  │
  │  🧑 인물: "클린 웹툰" + 🏙️ 배경: "따뜻한 사무실" │
  │  👤 캐릭터: 김세무 (세무사) + 박사장 (사업자)     │
  │                                                │
  │  [✅ 이 스타일로 진행]                           │
  │  [🔄 다시 생성]                                 │
  │  [✏️ 프롬프트 수정]  ← 수동 프롬프트 편집으로    │
  │  [🔙 스타일 변경]    ← 스타일 선택으로 돌아가기   │
  └────────────────────────────────────────────────┘
```

### 5.3 비용 최소화 전략

```python
async def generate_style_preview(
    character_style: CharacterStyle,
    background_style: BackgroundStyle,
    characters: list[Character],
    model_config: ModelConfig
) -> bytes:
    """스타일 미리보기 - 최소 비용으로 1장 생성"""
    
    # 대표 씬 (두 캐릭터가 대화하는 기본 장면)
    preview_scene = Scene(
        scene_description="Two characters having a friendly conversation in an office setting",
        expression="neutral"
    )
    
    # 프롬프트 구성 (실제와 동일한 구조)
    prompt = build_styled_prompt(
        scene=preview_scene,
        characters=characters,
        character_style=character_style,
        background_style=background_style
    )
    
    # 레퍼런스 이미지 수집
    reference_images = []
    # 스타일 레퍼런스
    for ref in character_style.reference_images:
        reference_images.append(load_image(ref))
    for ref in background_style.reference_images:
        reference_images.append(load_image(ref))
    # 캐릭터 시트
    for char in characters:
        if char.reference_images.get('character_sheet'):
            reference_images.append(load_image(char.reference_images['character_sheet']))
    
    # ⭐ 비용 절약: Low 품질 + 작은 사이즈
    preview_config = ModelConfig(
        model=model_config.model,
        api_key=model_config.api_key,
        quality="low",           # Low로 고정 (비용 최소)
        size="512x640"           # 절반 크기 (미리보기용)
    )
    
    generator = get_generator(preview_config.model, preview_config.api_key)
    result = await generator.generate(
        prompt=prompt,
        reference_images=reference_images,
        size=preview_config.size,
        quality=preview_config.quality
    )
    
    return result
```

### 5.4 미리보기 비용 예상

| 모델 | 미리보기 1장 비용 | 본 생성 대비 절약 |
|------|-----------------|-----------------|
| GPT Image 1 Mini (Low) | ~$0.003 | 본생성의 ~10% |
| GPT Image 1 (Low) | ~$0.01 | 본생성의 ~15% |
| Nano Banana | ~$0.01 | 본생성의 ~50% |

---

## 6. 수동 프롬프트 편집 ⭐

### 6.1 목적

샘플 미리보기가 마음에 안 들 때, AI가 자동 생성한 프롬프트를 사용자가 직접 수정하여 **기준 이미지(Base Image)**를 변경하는 기능.

### 6.2 UI

```
┌─────────────────────────────────────────────────────────────────┐
│  ✏️ 프롬프트 수동 편집                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ── 인물 스타일 프롬프트 ──                              [초기화] │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Korean webtoon style, clean outlines with medium line   │   │
│  │ weight, soft pastel skin tones, expressive anime-       │   │
│  │ inspired eyes, head-to-body ratio 1:5.5, warm natural   │   │
│  │ lighting, soft shadow under chin                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│  💡 팁: 선 굵기, 색감, 비율, 조명 등을 수정하세요               │
│                                                                 │
│  ── 배경 스타일 프롬프트 ──                              [초기화] │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ modern Korean office interior, warm lighting (#FFD4A0   │   │
│  │ ambient), soft pastel wall colors (#F5E6D3), clean      │   │
│  │ minimalist furniture, large window with city view,      │   │
│  │ soft depth-of-field blur on background                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  💡 팁: 장소, 색상(hex 권장), 조명, 디테일 수준 등을 수정하세요   │
│                                                                 │
│  ── 추가 지시사항 (선택) ──                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ (여기에 자유롭게 추가 요청을 입력할 수 있습니다)          │   │
│  │ 예: "좀 더 밝은 분위기로", "그림자를 더 강하게"           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [🔍 수정된 프롬프트로 샘플 재생성]                               │
│  [💾 수정 내용을 스타일에 저장]                                   │
│  [↩️ 원래대로 되돌리기]                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 수동 편집 데이터 흐름

```
[자동 생성된 프롬프트]
        ↓
[사용자가 텍스트 직접 수정]
        ↓
[수정된 프롬프트로 샘플 재생성]
        ↓
  ├─ 만족 → [이 스타일로 진행] (수정 프롬프트가 이후 모든 씬에 적용)
  ├─ 만족 + 저장 → [스타일 프리셋에 수정 내용 반영 저장]
  └─ 불만족 → [다시 수정] 반복
```

### 6.4 코드

```python
@dataclass
class ManualPromptEdit:
    """사용자의 수동 프롬프트 편집 데이터"""
    character_style_prompt: str    # 수정된 인물 스타일 프롬프트
    background_style_prompt: str   # 수정된 배경 스타일 프롬프트
    additional_instructions: str   # 추가 지시사항
    is_modified: bool = False      # 수정 여부
    
    def apply_to_styles(
        self, 
        char_style: CharacterStyle, 
        bg_style: BackgroundStyle
    ) -> tuple[CharacterStyle, BackgroundStyle]:
        """수정된 프롬프트를 스타일에 적용"""
        if self.is_modified:
            char_style = char_style.copy()
            char_style.prompt_block = self.character_style_prompt
            
            bg_style = bg_style.copy()
            bg_style.prompt_block = self.background_style_prompt
        
        return char_style, bg_style

    def save_to_preset(
        self, 
        char_style: CharacterStyle, 
        bg_style: BackgroundStyle
    ):
        """수정 내용을 원본 스타일 프리셋에 영구 저장"""
        char_style.prompt_block = self.character_style_prompt
        char_style.updated_at = datetime.now()
        
        bg_style.prompt_block = self.background_style_prompt
        bg_style.updated_at = datetime.now()
        
        db.save_character_style(char_style)
        db.save_background_style(bg_style)
```

---

## 7. 저장소 구조

```
/app_data/
├── /styles/
│   ├── /char_styles/
│   │   ├── /char_style_001/
│   │   │   ├── meta.json          # 스타일 메타 + 프롬프트
│   │   │   ├── ref_01.png         # 레퍼런스 이미지
│   │   │   └── ref_02.png
│   │   └── /char_style_002/...
│   │
│   ├── /bg_styles/
│   │   ├── /bg_style_001/
│   │   │   ├── meta.json
│   │   │   ├── ref_01.png
│   │   │   └── ref_02.png
│   │   └── /bg_style_002/...
│   │
│   └── /presets/
│       ├── preset_001.json        # 인물+배경 조합 프리셋
│       └── preset_002.json
│
├── /characters/                    # 기존 캐릭터 (CHARACTER_CONSISTENCY.md)
├── /projects/                      # 기존 프로젝트
└── /db/
    └── app.sqlite
```

### 7.1 SQLite 스키마 추가

```sql
-- 인물 스타일
CREATE TABLE character_styles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    prompt_block TEXT NOT NULL,
    visual_attributes_json TEXT NOT NULL,
    locked_attributes_json TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',  -- manual / extracted / uploaded
    extracted_from_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0
);

-- 배경 스타일
CREATE TABLE background_styles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    prompt_block TEXT NOT NULL,
    visual_attributes_json TEXT NOT NULL,
    locked_attributes_json TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_images_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0
);

-- 스타일 레퍼런스 이미지
CREATE TABLE style_reference_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    style_id TEXT NOT NULL,
    style_type TEXT NOT NULL,  -- 'character' or 'background'
    file_path TEXT NOT NULL
);

-- 스타일 조합 프리셋
CREATE TABLE style_presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    character_style_id TEXT NOT NULL,
    background_style_id TEXT NOT NULL,
    tags_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    FOREIGN KEY (character_style_id) REFERENCES character_styles(id),
    FOREIGN KEY (background_style_id) REFERENCES background_styles(id)
);

-- 프로젝트에 스타일 연결
ALTER TABLE projects ADD COLUMN style_preset_id TEXT REFERENCES style_presets(id);
ALTER TABLE projects ADD COLUMN manual_prompt_override_json TEXT;
```

---

## 8. 전체 워크플로우 통합

### 8.1 기존 워크플로우에 스타일 단계 삽입

```
[키워드 입력] → [분야 감지] → [정보 수집] → [스토리 생성]
      ↓
[씬 검토 UI] ← 1차 체크포인트
      ↓
[캐릭터 선택]     ← 기존 CHARACTER_CONSISTENCY.md
      ↓
[스타일 선택] ⭐ NEW
  - 인물 스타일 선택 (저장된 목록에서)
  - 배경 스타일 선택 (저장된 목록에서)
      ↓
[샘플 미리보기] ⭐ NEW
  - 1장 저비용 샘플 생성
  - 만족 → 진행 / 불만족 → 프롬프트 수정 또는 스타일 변경
      ↓
[이미지 생성] (전체 씬, 선택한 스타일 적용)
      ↓
[이미지 검토] ← 2차 체크포인트
      ↓
[텍스트 오버레이] → [캡션 생성] → [발행]
```

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-09 | 1.0.0 | 초기 작성 — 스타일 관리 시스템 전체 설계 |
