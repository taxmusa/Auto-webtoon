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
