# IMAGE_GENERATION.md - 이미지 생성 로직

> 이 문서는 AI 이미지 생성 관련 로직을 정의합니다.

---

## 1. 지원 모델

| 모델 | 장점 | 단점 | 비용 |
|------|------|------|------|
| **DALL-E 3** (기본) | 웹툰 스타일 지원, 품질 좋음 | 비용 높음 | ~$0.04/이미지 |
| **Imagen 3** | 무료 티어 있음 | 만화 스타일 제한 | 무료~유료 |

---

## 2. 프롬프트 구조

### 2.1 기본 구조

```
[스타일 지시] + [장면 설명] + [캐릭터 설명] + [제외 사항]
```

### 2.2 스타일별 프롬프트

**웹툰 스타일**:
```
korean webtoon style, clean lines, vibrant colors, 
anime-inspired, expressive characters
```

**카드뉴스 스타일**:
```
modern infographic style, clean design, professional,
flat design, corporate colors
```

**심플 스타일**:
```
minimalist design, solid color background, 
simple and clean, modern
```

### 2.3 필수 제외 사항

```
DO NOT include any text, speech bubbles, letters, 
words, or typography in the image.
```

**이유**: AI가 한글을 제대로 렌더링하지 못함 → Pillow로 후처리

---

## 3. 캐릭터 일관성

### 3.1 캐릭터 설명 고정

```python
CHARACTER_DESCRIPTIONS = {
    "민지": "young korean woman in her 20s, short black hair, 
             casual office attire, friendly expression",
    "세무사": "middle-aged korean man, glasses, neat suit, 
              professional and kind appearance"
}
```

### 3.2 일관성 유지 전략

1. 동일한 캐릭터 설명 프롬프트 사용
2. 시드값 고정 (가능한 경우)
3. 마음에 안 들면 개별 재생성

---

## 4. 이미지 규격

| 용도 | 권장 크기 | 비율 |
|------|----------|------|
| 인스타 캐러셀 (기본) | 1080x1350px | 4:5 |
| 인스타 정사각형 | 1080x1080px | 1:1 |
| 스토리/릴스 | 1080x1920px | 9:16 |

---

## 5. 에러 처리

| 에러 | 대응 |
|------|------|
| Rate Limit | 2초 대기 후 재시도 (최대 3회) |
| Content Policy | 프롬프트 수정 안내 |
| Timeout | 재시도 또는 다른 모델 시도 |

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-06 | 1.0.0 | 초기 작성 |
