# STYLE_SYSTEM.md - 스타일 관리 시스템 (v2.0)

> **프로젝트**: Tax Webtoon Auto-Generator  
> **버전**: 2.0.0 (Style System 2.0)  
> **최종 수정일**: 2026-02-10  
> **목적**: 통합 스타일 프롬프트, 프리셋 시스템, 커스텀 스타일 관리 및 UI 워크플로우 정의

---

## 1. 개요 (Style System 2.0)

### 1.1 주요 변경 사항
- **통합 스타일 프롬프트**: 기존의 인물/배경 스타일을 개별적으로 관리하던 방식에서, **`[VISUAL STYLE & ART DIRECTION]`** 섹션을 통해 하나의 통합된 스타일 프롬프트로 제어하는 방식으로 진화했습니다.
- **프리셋 시스템 도입**: "지브리", "로맨스", "비즈니스" 등 13종 이상의 검증된 스타일 프리셋을 제공하여 사용자가 쉽게 고품질 이미지를 생성할 수 있습니다.
- **커스텀 스타일 관리**: 사용자가 이미지에서 스타일을 추출하거나 직접 프롬프트를 작성하여 나만의 스타일을 저장하고 재사용할 수 있습니다.
- **UI 직관성 개선**: 카드형 그리드 UI를 통해 스타일을 시각적으로 선택하고 미리볼 수 있습니다.

---

## 2. 데이터 구조 및 프리셋

### 2.1 통합 스타일 데이터
Style System 2.0은 단일 스타일 객체(또는 프리셋)를 선택하면 해당 스타일의 `prompt`가 전체 이미지 생성에 적용되는 구조입니다.

```json
{
  "id": "ghibli",
  "name": "지브리",
  "emoji": "🌿",
  "desc": "지브리풍 부드러운 색감",
  "prompt": "studio ghibli inspired, soft colors, dreamy atmosphere, watercolor-like backgrounds, gentle lighting, whimsical characters",
  "is_preset": true
}
```

### 2.2 제공되는 프리셋 (Presets)
| ID | 이름 | 특징 |
|---|---|---|
| `ghibli` | 지브리 🌿 | 부드러운 색감, 몽환적 분위기, 수채화 배경 |
| `romance` | 로맨스 💕 | 파스텔 톤, 따뜻한 조명, 순정만화 감성 |
| `business` | 비즈니스 💼 | 깔끔한 오피스룩, 신뢰감 주는 선화 |
| `round_lineart` | 동글 라인 ✏️ | 둥글고 귀여운 선화, 인스타툰 최적화 |
| `pastel_flat` | 파스텔 플랫 🎨 | 그림자 없는 플랫한 파스텔 일러스트 |
| `bold_cartoon` | 볼드 카툰 💥 | 굵은 선, 강렬한 색채, 팝아트 느낌 |
| (외 7종) | ... | 다양한 아트 스타일 제공 |

---

## 3. 프롬프트 구성 로직 (Backend)

`app/services/prompt_builder.py`에서 스타일 프롬프트는 다음과 같은 우선순위로 적용됩니다:

1.  **통합 스타일 프롬프트 (`manual_overrides.style_prompt`)** [최우선]
    - UI에서 프리셋/커스텀 스타일 선택 시 이 필드에 프롬프트 전체가 입력됩니다.
    - 적용 시: `[VISUAL STYLE & ART DIRECTION]` 섹션에 삽입.
2.  **레거시 개별 스타일 (Character + Background)** [Fallback]
    - 통합 스타일이 없을 경우, 기존의 `character_style` 및 `background_style` 객체의 프롬프트를 각각 적용.

```python
# prompt_builder.py (Simplified)
if manual_overrides and manual_overrides.style_prompt:
    parts.append(f"[VISUAL STYLE & ART DIRECTION]\n{manual_overrides.style_prompt}")
else:
    if character_style: parts.append(f"[CHARACTER STYLE]\n{character_style.prompt_block}")
    if background_style: parts.append(f"[BACKGROUND STYLE]\n{background_style.prompt_block}")
```

---

## 4. 커스텀 스타일 관리 (User Workflow)

### 4.1 스타일 추출 (Vision AI)
사용자가 이미지를 업로드하면 Google Gemini Vision AI(`gemini-3-pro-preview` 등)가 해당 이미지의 화풍(선화, 색감, 채색 방식 등)을 분석하여 텍스트 프롬프트로 변환합니다.

- **API**: `/api/styles/extract`
- **Output**: JSON (Character Style attributes + Background Style attributes) -> 통합 프롬프트로 병합 가능

### 4.2 스타일 저장
추출된 프롬프트나 사용자가 직접 작성한 프롬프트를 "나만의 스타일"로 저장합니다.
- **저장 위치**: `app_data/styles/character/` 또는 `app_data/styles/background/` (통합 관리 인터페이스 사용)
- **메타데이터**: 이름, 프롬프트, 레퍼런스 이미지 경로 등

---

## 5. UI 워크플로우

1.  **스타일 탭 진입**: "그림 스타일" 탭에서 프리셋 카드 그리드 확인.
2.  **스타일 선택**: 원하는 스타일 카드(예: "동글 라인") 클릭.
3.  **자동 입력**: 하단 "프롬프트 수동 편집" 영역에 해당 스타일의 프롬프트가 자동 입력됨.
4.  **수동 수정 (옵션)**: 필요 시 사용자가 프롬프트를 직접 수정하거나 추가 지시사항(Negative Prompt 등) 입력.
5.  **미리보기 생성**: "샘플 미리보기 생성" 버튼을 눌러 스타일 적용 결과 1장 확인.
6.  **이미지 생성 시작**: 최종 확정 시 전체 씬 이미지 생성.

---

## 6. 향후 계획
- **스타일 믹싱**: 두 가지 스타일의 가중치를 조절하여 섞는 기능.
- **LoRA 학습 연동**: (SD 사용 시) 스타일 이미지를 기반으로 LoRA를 즉시 학습하여 적용.
