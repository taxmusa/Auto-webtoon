# Auto Webtoon - 전체 빌드 계획서
> 작성일: 2025-02-11
> 최종 수정: 2026-02-15
> 상태: Phase 4 완료 (UX 강화 + 발행 고도화)

---

## 프로젝트 개요

세무/법률/노무 전문 분야 **웹툰 + 캐러셀 + 카드뉴스** 자동 생성 프로그램

### 콘텐츠 타입 3종
| 타입 | 설명 | AI 이미지 | 복잡도 |
|------|------|----------|--------|
| 🎨 웹툰 | 캐릭터+대사+스토리 기반 인스타툰 | 필요 (Flux/OpenAI/Gemini) | 높음 |
| 📱 캐러셀 | 슬라이드형 정보 콘텐츠 | 불필요 (배경색+텍스트) | 낮음 |
| 📋 카드뉴스 | 카드형 정보 콘텐츠 | 불필요 (배경색+텍스트) | 낮음 |

---

## 전체 아키텍처

### 공통 경로
```
Tab 1: 키워드/분야 선택 (공통)
Tab 2: 자료 수집 (공통) → 콘텐츠 타입 선택
  ├── [🎨 웹툰 만들기] → 웹툰 경로
  ├── [📱 캐러셀 만들기] → 캐러셀 경로
  └── [📋 카드뉴스 만들기] → 카드뉴스 경로
```

### 웹툰 경로 (풀 파이프라인)
```
Tab 3: 스토리 생성 (씬/대사/캐릭터)
Tab 4: 상세 설정
  ├── 이미지 생성 모델 (Flux Kontext/LoRA/OpenAI/Gemini)
  ├── 🧑 인물 스타일 (기본/커스텀/학습캐릭터🎓)
  ├── 🏙️ 배경 스타일
  └── 🎓 학습 스타일 (LoRA 학습 관리)
Tab 5: 이미지 생성 + Pillow 여백 후처리
Tab 6: 텍스트 오버레이 (Playwright 말풍선 + 한글)
Tab 7: 편집/확인
Tab 8: 캡션 생성
Tab 9: 발행
```

### 캐러셀 경로 (간소화)
```
Tab C1: 설정 (AI 텍스트 구성 + 배경색 + 폰트 + 템플릿)
Tab C2: 미리보기 + 편집
Tab C3: 캡션 + 발행
```

### 카드뉴스 경로 (간소화)
```
Tab N1: 설정 (AI 텍스트 구성 + 배경색 + 폰트 + 템플릿)
Tab N2: 미리보기 + 편집
Tab N3: 캡션 + 발행
```

---

## 이미지 생성 파이프라인 (웹툰용)

```
Step 1: AI 이미지 생성 (말풍선 없는 순수 이미지)
  ├── Flux Kontext (참조 이미지 기반, 일관성 94.7%)
  ├── Flux LoRA (학습 캐릭터, 일관성 95%+)
  ├── OpenAI GPT Image / DALL-E (기존 유지)
  └── Gemini Nano Banana (기존 유지)

Step 2: Pillow 후처리
  └── 상단 25~30% 여백 강제 확보

Step 3: Playwright 텍스트 오버레이 (Tab 6)
  ├── HTML/CSS 말풍선 템플릿
  ├── 웹툰 전용 한글 폰트
  └── 스크린샷 → 최종 이미지
```

---

## 기술 스택

| 구분 | 기술 | 용도 |
|------|------|------|
| 이미지 생성 | fal.ai (Flux Kontext/LoRA) | 캐릭터 일관성 |
| 이미지 생성 | OpenAI API | GPT Image, DALL-E |
| 이미지 생성 | Google Gemini API | Nano Banana |
| 이미지 후처리 | Pillow | 여백, 톤 조절 |
| 텍스트 렌더링 | Playwright (Python) | 말풍선 + 한글 |
| 캐러셀/카드뉴스 | Playwright (Python) | 템플릿 → 이미지 |
| 텍스트 생성 | Gemini API | 스토리, 캡션 |
| 백엔드 | FastAPI | API 서버 |
| 프론트엔드 | Vanilla JS + HTML/CSS | 단일 페이지 |

---

## 빌드 순서

### Phase 1: 이미지 생성 강화 (Flux Kontext + LoRA) ✅ 완료
- [x] ① Flux Kontext 이미지 생성기 추가 (image_generator.py)
- [x] ② fal_service.py - LoRA 학습/관리/추론 서비스
- [x] ③ models.py - TrainedCharacter, TrainingJob 모델
- [x] ④ training.py API 라우터 (학습 시작/상태/목록/추가학습/삭제)
- [x] ⑤ workflow.py - Flux Kontext 참조이미지 연동 + LoRA 트리거워드
- [x] ⑥ Tab 4 UI 개편 (학습 스타일 탭 + 학습캐릭터 배지 + 모델 선택)
- [x] ⑦ Pillow 여백 후처리 (pillow_service.py)
- [x] ⑧ Tab 2 콘텐츠 타입 선택 메뉴 (웹툰/캐러셀/카드뉴스 3개 버튼)

### Phase 2: 텍스트 오버레이 + 캐러셀/카드뉴스 ✅ 완료
- [x] ⑨ Playwright 설치 + 렌더링 엔진 (render_service.py)
- [x] ⑩ 말풍선 CSS 템플릿 시스템 (웹툰용)
- [x] ⑪ Tab 6 텍스트 오버레이 Playwright 연동
- [x] ⑫ 캐러셀 API + 템플릿 + UI (carousel.py)
- [x] ⑬ 카드뉴스 API + 템플릿 + UI (cardnews.py)

### Phase 3: 마무리 + 통합 ✅ 완료
- [x] ⑭ 전체 발행 흐름 통합 (3개 경로 → 공통 캡션/발행)
- [x] ⑮ 프롬프트 최적화 (Flux Kontext/LoRA 전용)
- [x] ⑯ 에러 처리 + 안정성 강화 (Playwright 재시도, Flux 재시도)
- [x] ⑰ 임포트 검증 + 통합 테스트

### Phase 4: UX 강화 + 발행 고도화 ✅ 완료
- [x] ⑱ 스토리 편집 UX 개선 (인라인 편집, 표지 씬, 저장/불러오기)
- [x] ⑲ 시리즈 분할 기능 (시리즈 수 설정, 편별 씬 배분, 시리즈별 발행)
- [x] ⑳ 프로젝트 저장/불러오기 (header 통합)
- [x] ㉑ Instagram Graph API 예약 발행 연동
- [x] ㉒ "다음편에 계속" 오버레이 UI 연동
- [x] ㉓ 씬 재생성 기능 활성화 (AI 스토리 재생성 API 연동)
- [x] ㉔ 코드 품질 개선 (예외 처리, 로깅, dead code 정리)

---

## API 구조

### 공통
```
POST /api/workflow/start                # 세션 시작
POST /api/workflow/collect-data         # 자료 수집
POST /api/workflow/parse-manual-content # 수동 입력 파싱
GET  /api/workflow/session/{id}         # 세션 상태
POST /api/workflow/generate-common-caption # 공통 캡션 생성
POST /api/workflow/test-model           # AI 모델 테스트
```

### 웹툰 전용
```
POST /api/workflow/generate-story       # 스토리 생성
POST /api/workflow/update-scene         # 씬 수정
POST /api/workflow/approve-scenes       # 씬 전체 승인
POST /api/workflow/regenerate-scene     # 씬 재생성
POST /api/workflow/regenerate-image-prompt # 이미지 프롬프트 재생성
POST /api/workflow/generate-preview     # 미리보기 1장
POST /api/workflow/generate-images      # 이미지 일괄 생성
POST /api/workflow/regenerate-image     # 이미지 재생성
POST /api/workflow/stop-generation      # 생성 중단
POST /api/workflow/generate-caption     # 캡션 생성
POST /api/workflow/publish              # Instagram 발행
GET  /api/workflow/instagram-check      # Instagram 연결 확인
POST /api/workflow/instagram-test       # Instagram 테스트 발행
```

### 썸네일/시리즈/프로젝트
```
POST /api/workflow/thumbnail/generate   # 썸네일 생성
POST /api/workflow/thumbnail/toggle     # 썸네일 ON/OFF
GET  /api/workflow/thumbnail/{id}       # 썸네일 조회
POST /api/workflow/to-be-continued/apply # 다음편에 계속 적용
POST /api/workflow/session/{id}/series-config # 시리즈 설정
GET  /api/workflow/session/{id}/series-config # 시리즈 조회
POST /api/workflow/project/save         # 프로젝트 저장
GET  /api/workflow/project/list         # 프로젝트 목록
POST /api/workflow/project/load         # 프로젝트 불러오기
DELETE /api/workflow/project/delete/{dir} # 프로젝트 삭제
```

### 말풍선 레이어
```
POST /api/workflow/bubble-layers/{id}/init   # 말풍선 초기화
GET  /api/workflow/bubble-layers/{id}        # 말풍선 조회
PUT  /api/workflow/bubble-layers/{id}/{num}  # 말풍선 수정
POST /api/workflow/bubble-layers/{id}/export # 말풍선 합성 내보내기
DELETE /api/workflow/session/{id}/delete-scene/{num} # 씬 삭제
```

### SNS 인증/설정
```
GET  /api/sns/status                    # 전체 연결 상태
POST /api/sns/facebook/save-app         # Facebook App 정보 저장
POST /api/sns/facebook/exchange-token   # 토큰 교환 (영구 토큰)
POST /api/sns/instagram/save-token      # Instagram 토큰 직접 저장
GET  /api/sns/instagram/verify          # Instagram 토큰 검증
POST /api/sns/cloudinary/save           # Cloudinary 설정 저장
GET  /api/sns/cloudinary/verify         # Cloudinary 연결 확인
GET  /api/sns/apikey/status             # API 키 상태 확인
POST /api/sns/apikey/save               # API 키 저장
```

### 캐러셀 전용
```
POST /api/carousel/generate-slides      # 슬라이드 텍스트 생성
POST /api/carousel/render               # Playwright 렌더링
```

### 카드뉴스 전용
```
POST /api/cardnews/generate-cards       # 카드 텍스트 생성
POST /api/cardnews/render               # Playwright 렌더링
```

### 스타일 관리
```
GET  /api/styles/characters             # 캐릭터 스타일 목록
POST /api/styles/character              # 캐릭터 스타일 저장
GET  /api/styles/backgrounds            # 배경 스타일 목록
POST /api/styles/background             # 배경 스타일 저장
```

---

## 파일 구조 (최종 예상)

```
Auto Webtoon/
├── app/
│   ├── api/
│   │   ├── workflow.py        # 웹툰 워크플로우 (발행/시리즈/프로젝트 포함)
│   │   ├── carousel.py        # 캐러셀 API
│   │   ├── cardnews.py        # 카드뉴스 API
│   │   ├── styles.py          # 스타일 관리
│   │   ├── edit_stage.py      # 이미지 편집
│   │   └── sns_auth.py        # SNS 인증/연결 관리
│   ├── services/
│   │   ├── image_generator.py # 이미지 생성기 (Flux/OpenAI/Gemini)
│   │   ├── gemini_service.py  # Gemini AI (텍스트+이미지)
│   │   ├── openai_service.py  # OpenAI (이미지)
│   │   ├── fal_service.py     # fal.ai API (Flux)
│   │   ├── instagram_service.py # Instagram Graph API
│   │   ├── cloudinary_service.py # 이미지 호스팅
│   │   ├── pillow_service.py  # Pillow 후처리 (여백/오버레이)
│   │   ├── render_service.py  # Playwright 렌더링 (캐러셀/카드뉴스)
│   │   ├── prompt_builder.py  # 프롬프트 빌더 (Flux 최적화)
│   │   ├── reference_service.py # 3종 레퍼런스 관리
│   │   ├── smart_translator.py # 한영 번역 (캐시/사전/AI)
│   │   └── scene_preprocessor.py # 씬 전처리 (숫자→시각화)
│   ├── models/
│   │   └── models.py          # 데이터 모델
│   ├── templates/
│   │   ├── index.html         # 메인 UI
│   │   └── settings.html      # 설정 페이지
│   ├── core/
│   │   └── config.py          # 환경변수 설정
│   └── main.py                # FastAPI 앱
├── app_data/                  # 사용자 데이터 (git 제외)
│   ├── reference/sessions/    # 레퍼런스 이미지 세션
│   └── reference_presets/     # 레퍼런스 프리셋
├── requirements.txt
├── .env                       # 환경변수 (git 제외)
├── BUILD_PLAN.md              # 이 문서
├── WORKFLOW.md                # 워크플로우 명세
└── run.py
```

---

## 환경 변수 (.env)

```
# AI
GEMINI_API_KEY=...          # Google Gemini (텍스트+이미지, 핵심)
OPENAI_API_KEY=...          # OpenAI (이미지 대체)
FAL_KEY=...                 # fal.ai (Flux Kontext + LoRA)

# SNS 발행
INSTAGRAM_ACCESS_TOKEN=...  # 인스타 발행 (영구 페이지 토큰)
INSTAGRAM_USER_ID=...       # 인스타 비즈니스 계정 ID
# 이미지 호스팅
CLOUDINARY_CLOUD_NAME=...   # Cloudinary
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...

# Facebook OAuth (토큰 교환용)
FACEBOOK_APP_ID=...
FACEBOOK_APP_SECRET=...
```
