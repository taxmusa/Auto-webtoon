# IMAGE_GENERATION.md - 이미지 생성 로직

> 이 문서는 AI 이미지 생성 관련 모든 로직을 정의합니다.  
> **v2.0.0** — 5개 모델 지원, 캐릭터 일관성 프롬프트 통합

---

## 1. 지원 모델 (5개)

### 1.1 OpenAI 계열 (API 키 1개로 모두 사용)

| 모델 | 모델 ID | 가격/장 | 최대 해상도 | 레퍼런스 이미지 |
|------|---------|---------|-----------|---------------|
| **GPT Image 1 Mini** | `gpt-image-1-mini` | $0.005~0.052 | 1536px | ✅ |
| **GPT Image 1** | `gpt-image-1` | $0.02~0.19 | 1536px | ✅ (최대 4장) |
| **GPT Image 1.5** | `gpt-image-1.5` | $0.04~0.08 | 1536px | ✅ 멀티 이미지 |

**품질 옵션 (Low / Medium / High)**: 가격과 품질에 영향

### 1.2 Google 계열 (Gemini 텍스트와 동일 API 키)

| 모델 | 모델 ID | 가격/장 | 최대 해상도 | 레퍼런스 이미지 |
|------|---------|---------|-----------|---------------|
| **Nano Banana** | `gemini-2.5-flash-preview-image-generation` | ~$0.02 | 2K | ✅ (최대 10장) |
| **Nano Banana Pro** | `gemini-3-pro-image-generation` | $0.134~0.24 | 4K | ✅ (최대 8장) |

---

## 2. 코드 구조 (추상화)

```python
from abc import ABC, abstractmethod

class ImageGeneratorBase(ABC):
    """모든 이미지 생성 모델의 공통 인터페이스"""
    
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        reference_images: list[bytes] = None,
        size: str = "1024x1536",
        quality: str = "medium"
    ) -> bytes:
        pass
    
    @abstractmethod
    async def edit_with_reference(
        self,
        prompt: str,
        reference_image: bytes,
        size: str = "1024x1536"
    ) -> bytes:
        pass


class OpenAIGenerator(ImageGeneratorBase):
    """GPT Image 1 Mini / 1 / 1.5"""
    
    def __init__(self, api_key: str, model: str = "gpt-image-1-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    async def generate(self, prompt, reference_images=None, size="1024x1536", quality="medium"):
        if reference_images:
            # 이미지 편집 API로 레퍼런스 이미지 활용
            result = self.client.images.edit(
                model=self.model,
                image=reference_images[0],
                prompt=prompt,
                size=size,
                quality=quality
            )
        else:
            result = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=size,
                quality=quality
            )
        return result


class GeminiGenerator(ImageGeneratorBase):
    """Nano Banana / Nano Banana Pro"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-preview-image-generation"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
    
    async def generate(self, prompt, reference_images=None, size="1024x1536", quality="medium"):
        contents = []
        
        # 레퍼런스 이미지 첨부
        if reference_images:
            for ref_img in reference_images:
                contents.append(genai.types.Part.from_image(ref_img))
        
        contents.append(prompt)
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )
        return response


# 팩토리
def get_generator(model_name: str, api_key: str) -> ImageGeneratorBase:
    MODEL_MAP = {
        "gpt-image-1-mini": (OpenAIGenerator, "gpt-image-1-mini"),
        "gpt-image-1": (OpenAIGenerator, "gpt-image-1"),
        "gpt-image-1.5": (OpenAIGenerator, "gpt-image-1.5"),
        "nano-banana": (GeminiGenerator, "gemini-2.5-flash-preview-image-generation"),
        "nano-banana-pro": (GeminiGenerator, "gemini-3-pro-image-generation"),
    }
    cls, model_id = MODEL_MAP[model_name]
    return cls(api_key=api_key, model=model_id)
```

---

## 3. 프롬프트 구조

### 3.1 기본 구조

```
[CHARACTER IDENTITY - DO NOT MODIFY] ← 캐릭터 DNA (FROZEN)
+
[STYLE CONSISTENCY] ← 아트 스타일 고정
+
[THIS SCENE] ← 이번 씬 설명 (변동)
+
[LOCKED ATTRIBUTES] ← 절대 변경 금지 속성
+
[EXCLUSION] ← 텍스트/글자 생성 금지
```

### 3.2 캐릭터 일관성 통합 프롬프트

```python
def build_scene_prompt(scene, characters, style_config):
    """씬 이미지 생성용 프롬프트 구성"""
    
    prompt_parts = []
    
    # 1. 캐릭터 Identity Block (FROZEN - 단어 하나도 변경 금지)
    for i, char in enumerate(characters):
        position = "LEFT" if i == 0 else "RIGHT"
        prompt_parts.append(f"""
[CHARACTER IDENTITY - DO NOT MODIFY]
Character {i+1} - "{char.meta['name']}" ({char.meta['role_type']}):
Position: {position}
{char.prompt_fragments['identity_block']}
""")
    
    # 2. 스타일 블록
    prompt_parts.append(f"""
[STYLE CONSISTENCY]
{style_config.style_block}
""")
    
    # 3. 이번 씬 설명
    prompt_parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {scene.expression or 'auto'}
Composition: {scene.composition or 'two characters talking'}
""")
    
    # 4. LOCKED 속성 명시
    locked_section = "\n[LOCKED ATTRIBUTES (must not change)]:\n"
    for char in characters:
        for attr in char.prompt_fragments['locked_attributes']:
            locked_section += f"- {char.meta['name']}: {attr}\n"
    prompt_parts.append(locked_section)
    
    # 5. 필수 제외 사항
    prompt_parts.append("""
[EXCLUSION]
DO NOT include any text, speech bubbles, letters, words, 
numbers, or typography in the image. The image must be 
completely free of any written content. Text will be added 
separately via post-processing.
""")
    
    return "\n".join(prompt_parts)
```

### 3.3 스타일별 프롬프트

**웹툰 스타일**:
```
Korean webtoon style, clean lines, vibrant colors, 
anime-inspired, expressive characters, soft pastel colors,
warm lighting, head-to-body ratio 1:5.5
```

**카드뉴스 스타일**:
```
Modern infographic style, clean design, professional,
flat design, corporate colors, structured layout
```

**심플 스타일**:
```
Minimalist design, solid color background, 
simple and clean, modern, single focal point
```

---

## 4. 씬 이미지 생성 로직

### 4.1 전체 생성 흐름

```python
async def generate_scene_image(scene, characters, model_config):
    """캐릭터 일관성이 적용된 씬 이미지 생성"""
    
    # 1. 프롬프트 구성
    prompt = build_scene_prompt(scene, characters, model_config.style)
    
    # 2. 레퍼런스 이미지 수집
    reference_images = []
    for char in characters:
        # 캐릭터 시트 (필수)
        reference_images.append(load_image(char.reference_images['character_sheet']))
        # 해당 표정 이미지 (있으면)
        expression = scene.get('expression', 'neutral')
        if expression in char.reference_images.get('expressions', {}):
            reference_images.append(
                load_image(char.reference_images['expressions'][expression])
            )
    
    # 3. 이전 씬 이미지도 참조 (연속성)
    if scene.scene_number > 1 and scene.previous_image:
        reference_images.append(load_image(scene.previous_image))
    
    # 4. 모델별 API 호출
    generator = get_generator(model_config.model, model_config.api_key)
    result = await generator.generate(
        prompt=prompt,
        reference_images=reference_images,
        size=model_config.size,
        quality=model_config.quality
    )
    
    return result
```

### 4.2 배치 생성 (전체 씬)

```python
async def generate_all_scenes(story, characters, model_config):
    """전체 씬 이미지 순차 생성"""
    
    results = []
    for scene in story.scenes:
        # 씬에 등장하는 캐릭터만 필터
        scene_characters = [c for c in characters if c.id in scene.character_ids]
        
        image = await generate_scene_image(scene, scene_characters, model_config)
        results.append({
            'scene_number': scene.scene_number,
            'image': image,
            'status': 'generated'
        })
        
        # Rate Limit 방지
        await asyncio.sleep(1)
    
    return results
```

---

## 5. 캐릭터 시트 생성

### 5.1 캐릭터 시트 프롬프트

```python
CHARACTER_SHEET_PROMPT = """
Create a character reference sheet for a Korean webtoon character.
Layout: 2 rows x 3 columns grid on white background.

Character: {character_description}

Grid contents:
[Row 1] Front view (neutral) | Three-quarter view | Profile view
[Row 2] Happy expression | Explaining gesture | Surprised expression

Style: {style_description}
Each cell clearly separated with thin gray borders.
White background, no text labels.
Consistent proportions across all views.
"""
```

### 5.2 생성 후 분할

```python
async def create_character_sheet(character, model_config):
    """캐릭터 시트 생성 및 개별 이미지 분할"""
    
    prompt = CHARACTER_SHEET_PROMPT.format(
        character_description=character.dna_template_to_text(),
        style_description=character.style_block
    )
    
    # 1장으로 6개 뷰 생성 (API 호출 절약)
    sheet_image = await generator.generate(prompt=prompt, size="1536x1024")
    
    # PIL로 6등분 분할
    views = split_grid(sheet_image, rows=2, cols=3)
    
    # 저장
    save_image(views[0], f"characters/{character.id}/front.png")
    save_image(views[1], f"characters/{character.id}/3q.png")
    save_image(views[2], f"characters/{character.id}/profile.png")
    save_image(views[3], f"characters/{character.id}/expr_happy.png")
    save_image(views[4], f"characters/{character.id}/expr_explaining.png")
    save_image(views[5], f"characters/{character.id}/expr_surprised.png")
    save_image(sheet_image, f"characters/{character.id}/sheet.png")
    
    return sheet_image
```

---

## 6. 이미지 규격

| 용도 | 권장 크기 | 비율 |
|------|----------|------|
| 인스타 캐러셀 (기본) | 1080x1350px | 4:5 |
| 인스타 정사각형 | 1080x1080px | 1:1 |
| 스토리/릴스 | 1080x1920px | 9:16 |

---

## 7. 에러 처리

| 에러 | 대응 |
|------|------|
| Rate Limit | 2초 대기 후 재시도 (최대 3회) |
| Content Policy | 프롬프트 수정 안내 |
| Timeout | 재시도 또는 다른 모델 시도 |
| API Key Invalid | 설정 화면으로 이동 안내 |
| Insufficient Quota | 잔액 부족 알림 |

```python
@retry(max_attempts=3, delay=2)
async def generate_image_with_retry(prompt, reference_images, settings):
    """재시도 로직이 포함된 이미지 생성"""
    try:
        return await generator.generate(prompt, reference_images, settings)
    except RateLimitError:
        await asyncio.sleep(5)
        raise
    except ContentPolicyError as e:
        # 프롬프트 자동 수정 시도
        sanitized_prompt = sanitize_prompt(prompt)
        return await generator.generate(sanitized_prompt, reference_images, settings)
```

---

## 8. 일관성 향상 팁 (프롬프트 엔지니어링)

### 8.1 핵심 원칙

1. Identity Block은 매 프롬프트에 **100% 동일**하게 복사
2. LOCKED 키워드로 변경 불가 속성 명시
3. 변경되는 것만 분리 (포즈, 배경, 표정)
4. 색상은 hex 코드: "파란색" → `#1B2A4A navy blue`
5. 비율을 숫자로: "1:5.5 head-to-body ratio"
6. 레퍼런스 이미지 항상 첨부
7. 2인 이상 등장 시 `LEFT: 김세무, RIGHT: 박사장` 위치 지정

### 8.2 흔한 문제와 해결

| 문제 | 해결 |
|------|------|
| 머리 색/길이 변함 | "hair reaching exactly to shoulders, 25cm length" |
| 의상 색상 변함 | hex 코드: "navy blue (#1B2A4A)" |
| 얼굴이 달라짐 | 캐릭터 시트를 레퍼런스로 반드시 전달 |
| 스타일 변함 | style_block을 프롬프트 최상단에 배치 |
| 2인 캐릭터 뒤바뀜 | LEFT/RIGHT 위치 명시 |
| 체형이 달라짐 | "head-to-body 1:5.5, shoulders 2.5x head width" |

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-06 | 1.0.0 | 초기 작성 (DALL-E 3 + Imagen) |
| 2026-02-09 | 2.0.0 | 5개 모델 지원으로 전면 개편, 캐릭터 일관성 프롬프트 통합, 코드 추상화 구조, 캐릭터 시트 생성 로직 추가 |
