# Auto-Webtoon 프로젝트 규칙

## 언어 규칙
- 모든 응답, 설명, 커밋 메시지, 작업 계획은 한국어로 작성할 것
- 코드 주석도 한국어로 작성
- 사용자에게 확인을 구할 때도 한국어로 질문할 것

## 기술 스택
- 백엔드: FastAPI + Python
- AI: Google Gemini API (`google.genai` SDK)
- 이미지 처리: Pillow, Playwright
- 발행: Instagram Graph API

## 구현 전 필수 검증 프로세스
모든 새로운 기능 구현이나 주요 변경 전에 반드시 아래 3단계를 수행할 것:

### 1단계: Context7으로 공식 문서 조회
- `resolve-library-id` → `query-docs` 순서로 사용하는 라이브러리의 최신 공식 문서를 확인
- 예: FastAPI, Pillow, google-genai, Playwright 등

### 2단계: WebSearch로 모범 사례 검색
- 구현하려는 기능의 best practice를 웹 검색으로 확인
- 검색 시 현재 연도(2026)를 포함하여 최신 정보 우선

### 3단계: 3개 소스 교차 검증
- 공식 문서 + 웹 검색 결과 + 기존 코드베이스 패턴을 교차 비교
- 3개 소스가 일치하는 방법을 채택
- 불일치 시 공식 문서를 최우선으로 따르되, 사용자에게 차이점 안내

## 템플릿 프리뷰 이미지 규칙

새 템플릿이나 템플릿 세트를 추가/수정할 때 반드시 아래 규칙을 따를 것:

### 프리뷰 이미지 생성 방식
1. 각 템플릿 세트의 **커버 슬라이드**를 샘플 데이터로 Playwright 렌더링하여 PNG 생성
2. 생성된 이미지를 `app/static/previews/{set_id}.png` 에 저장 (270x338px 썸네일)
3. 서버 재시작 시 API 호출 없이 **저장된 파일을 재사용** (매번 재생성 안 함)
4. 프론트엔드에서 `<img>` 태그로 해당 이미지를 갤러리에 표시

### 템플릿 추가 시 체크리스트
- [ ] `app/services/template_builders.py`에 빌더 함수 추가
- [ ] `app/services/theme_palettes.py`의 TEMPLATE_SETS에 세트 정보 추가
- [ ] `app/api/content_generator.py`의 `get_template_catalog()` individual_templates에 추가
- [ ] 프리뷰 이미지 생성 스크립트 실행하여 `app/static/previews/`에 새 PNG 저장
- [ ] 프론트엔드 갤러리가 자동으로 새 세트를 표시하는지 확인
