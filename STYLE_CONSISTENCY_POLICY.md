# STYLE_CONSISTENCY_POLICY.md - 스타일 일관성 정책

> **프로젝트**: Tax Webtoon Auto-Generator  
> **버전**: 1.1.0  
> **목적**: 이미지 생성 프롬프트의 섹션 순서·고정 규칙을 정의하고, `prompt_builder.py` 및 관련 코드가 이를 준수하도록 함.

---

## 1. 적용 범위

- **구현 파일**: `app/services/prompt_builder.py`  
- **참조 문서**: `docs/STYLE_SYSTEM.md`, `IMAGE_GENERATION.md`, `CHARACTER_CONSISTENCY.md`

이 정책에 정의된 **섹션 순서**와 **FROZEN/LOCKED 규칙**은 모든 씬에 동일하게 적용되어, 시리즈 내 시각적 일관성을 유지한다.

---

## 2. 프롬프트 섹션 순서 (필수)

최종 프롬프트는 **아래 순서를 반드시 준수**해야 한다. 순서 변경 시 AI 모델의 해석이 달라져 일관성이 깨질 수 있다.

| 순서 | 섹션 라벨 | 설명 | 씬별 변동 |
|------|-----------|------|-----------|
| 0 | `[HIGHEST PRIORITY — USER OVERRIDE INSTRUCTION]` (선택) | 사용자 추가 지시 — **맨 앞에 삽입, 최우선 적용** | 선택 |
| 1 | `[GLOBAL ART STYLE - DO NOT DEVIATE]` | 인물/캐릭터 전역 아트 스타일 (선, 색감, 비율, 조명) | 고정 |
| 2 | `[RENDERING STYLE / VISUAL PRESET]` | 서브스타일(지브리, 로맨스, 볼드 카툰 등) | 고정 |
| 3 | `[BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]` | 배경 스타일 (장소, 색상, 조명, 텍스처). 오버라이드에 배경 관련 지시가 있으면 기본값 대신 반영 | 고정 |
| 4 | `[CHARACTER N IDENTITY - DO NOT MODIFY]` | 캐릭터별 정체성 (이름, 역할, 외모, 위치) | 고정 |
| 5 | `[THIS SCENE]` | 이번 씬 설명, 표정, 나레이션 | **변동** |
| 6 | `[LOCKED ATTRIBUTES]` | 스타일/배경에서 절대 변경 금지 속성 | 고정 |
| 7 | `[EXCLUSION]` | 텍스트/말풍선/글자 생성 금지 | 고정 |
| 8 | `[REMINDER — APPLY USER OVERRIDE ABOVE ALL ELSE]` (선택) | 맨 끝에서 오버라이드 재강조 | 선택 |

- **고정**: 동일 세션·동일 스타일 선택 시 모든 씬에서 동일한 문구 유지.  
- **변동**: 씬마다 `scene_description`, `dialogues`, `narration` 등만 변경.
- **오버라이드**: 사용자 `additional_instructions`가 있으면 프롬프트 **맨 앞(0번)**과 **맨 끝(8번)** 양쪽에 삽입. 배경 관련 키워드가 포함되면 [BACKGROUND STYLE] 섹션도 직접 수정.

---

## 3. FROZEN 규칙

- **Character Identity**: 한 번 정해진 캐릭터 identity 블록은 **동일 에피소드 내 모든 씬에서 동일 문자열**로 유지한다. (이름, 역할, 외모, Position LEFT/RIGHT 등)
- **Locked Attributes**: `character_style.locked_attributes`, `background_style.locked_attributes`에 들어 있는 항목은 프롬프트에서 **삭제하거나 완화하지 않는다**.
- **Exclusion**: "DO NOT include any text, speech bubbles, letters..." 문구는 **항상 마지막에 가깝게** 포함하며, 생략하지 않는다.

---

## 4. LOCKED 속성 포맷

- 인물 스타일 locked: `- STYLE: {attr}`
- 배경 스타일 locked: `- BACKGROUND: {attr}`

`prompt_builder.py`에서 Locked Attributes 섹션을 조립할 때 위 접두어를 사용해 구분한다.

---

## 5. 서브스타일(SUB_STYLES) 정책

- 서브스타일 키는 `prompt_builder.SUB_STYLES`에 정의된 것만 사용한다.
- 정의되지 않은 `sub_style_name`이 전달되면 **해당 섹션은 생략**한다 (기본 스타일만 적용).
- 서브스타일 문구는 **한 번 선택되면 에피소드 전체에서 동일**하게 적용한다.

---

## 6. 수동 오버라이드 우선순위

`ManualPromptOverrides`가 있을 때:

1. `character_style_prompt` → GLOBAL ART STYLE을 대체  
2. `style_prompt` → GLOBAL ART STYLE을 대체 (character_style_prompt 미지정 시)
3. `background_style_prompt` → BACKGROUND STYLE을 대체  
4. `additional_instructions` → **최우선 지시**: 프롬프트 맨 앞(0번 섹션)과 맨 끝(8번 리마인더)에 삽입. 배경 관련 키워드("배경", "흰", "white", "없" 등) 포함 시 BACKGROUND STYLE 섹션도 직접 수정.

오버라이드는 **저장된 스타일보다 우선**하되, LOCKED 속성과 EXCLUSION은 그대로 유지한다.

---

## 7. prompt_builder.py 준수 사항

- 이 정책 문서를 **주석 또는 docstring**으로 참조한다.
- `build_styled_prompt()` 반환 문자열의 **섹션 순서**는 위 2번 테이블과 동일하게 유지한다.
- 새 섹션을 추가할 경우 이 정책 문서를 먼저 수정·버전 관리한 뒤 코드를 반영한다.

---

## 8. GUARD 블록 정책

GUARD 블록은 AI 모델이 씬 변동(섹션 5) 때문에 고정 섹션(1~4)을 무시하는 것을 방지하기 위한 **능동적 재강조 마커**이다.

### 8.1 GUARD vs LOCKED 차이

| 구분 | LOCKED | GUARD |
|------|--------|-------|
| 위치 | 섹션 6 (후방) | 각 고정 섹션 직후 |
| 역할 | "이 속성은 변경 금지" 목록 | "위 섹션을 반드시 유지하라" 재강조 |
| 대상 | 개별 속성 (line-weight, palette 등) | 섹션 전체 (아트스타일, 캐릭터 등) |

### 8.2 GUARD 블록 삽입 위치

| 삽입 위치 | GUARD 문구 |
|-----------|-----------|
| 섹션 1 직후 | `[GUARD] Maintain this exact art style consistently. Any deviation breaks visual coherence.` |
| 섹션 4 직후 | `[GUARD] These character appearances are FROZEN. Do not alter hair, eyes, clothes, or proportions.` |

### 8.3 GUARD 적용 조건

- GUARD는 **항상 삽입**한다 (ON/OFF 없음).
- GUARD 문구는 짧고 명령형으로 유지한다 (모델 토큰 절약).
- 사용자 오버라이드(섹션 0)가 스타일/캐릭터를 직접 변경하는 경우에도 GUARD는 유지하되, 오버라이드가 우선한다는 점은 섹션 0·8에서 이미 명시되어 있으므로 충돌하지 않는다.

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-11 | 1.0.0 | 초기 정책 작성, prompt_builder 반영 기준 정의 |
| 2026-02-11 | 1.1.0 | §8 GUARD 블록 정책 추가 (능동적 일관성 재강조) |
