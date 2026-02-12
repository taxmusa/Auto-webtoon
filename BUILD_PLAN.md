# Auto Webtoon - 전체 빌드 계획서
> 작성일: 2025-02-11
> 상태: Phase 3 완료 (전체 빌드 완료)

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

---

## API 구조

### 공통
```
POST /api/workflow/start           # 세션 시작
POST /api/workflow/collect-data    # 자료 수집
GET  /api/workflow/session/{id}    # 세션 상태
```

### 웹툰 전용
```
POST /api/workflow/generate-story    # 스토리 생성
POST /api/workflow/generate-images   # 이미지 생성
POST /api/workflow/regenerate-image  # 이미지 재생성
POST /api/workflow/stop-generation   # 생성 중단
POST /api/workflow/publish           # 발행
```

### LoRA 학습
```
POST /api/training/start             # 학습 시작
GET  /api/training/status/{job_id}   # 학습 상태
GET  /api/training/characters        # 학습 캐릭터 목록
POST /api/training/retrain/{id}      # 추가 학습
DELETE /api/training/character/{id}   # 캐릭터 삭제
POST /api/training/upload-images     # 학습 이미지 업로드
```

### 캐러셀 전용
```
POST /api/carousel/generate-slides   # 슬라이드 텍스트 생성
POST /api/carousel/render            # Playwright 렌더링
POST /api/carousel/publish           # 발행
```

### 카드뉴스 전용
```
POST /api/cardnews/generate-cards    # 카드 텍스트 생성
POST /api/cardnews/render            # Playwright 렌더링
POST /api/cardnews/publish           # 발행
```

---

## 파일 구조 (최종 예상)

```
Auto Webtoon/
├── app/
│   ├── api/
│   │   ├── workflow.py        # 웹툰 워크플로우 (기존 + Flux 연동)
│   │   ├── training.py        # LoRA 학습 API (신규)
│   │   ├── carousel.py        # 캐러셀 API (신규)
│   │   ├── cardnews.py        # 카드뉴스 API (신규)
│   │   ├── styles.py          # 스타일 관리 (기존)
│   │   └── edit_stage.py      # 이미지 편집 (기존)
│   ├── services/
│   │   ├── image_generator.py # 이미지 생성기 (기존 + FluxKontextGenerator)
│   │   ├── fal_service.py     # fal.ai API 서비스 (신규)
│   │   ├── image_postprocess.py # Pillow 후처리 (신규)
│   │   ├── render_service.py  # Playwright 렌더링 (신규)
│   │   ├── prompt_builder.py  # 프롬프트 빌더 (기존 + Flux 최적화)
│   │   └── gemini_service.py  # Gemini AI (기존)
│   ├── models/
│   │   └── models.py          # 데이터 모델 (기존 + Training 모델)
│   ├── templates/
│   │   ├── index.html         # 메인 UI (기존 + 개편)
│   │   └── bubbles/           # 말풍선 CSS 템플릿 (신규)
│   ├── core/
│   │   └── config.py          # 설정 (기존 + fal_key)
│   └── main.py                # FastAPI 앱 (기존 + 라우터 추가)
├── trained_characters/        # 학습 캐릭터 데이터 저장 (신규)
├── assets/
│   └── fonts/                 # 웹툰 한글 폰트
├── requirements.txt
├── .env
├── BUILD_PLAN.md              # 이 문서
└── run.py
```

---

## 환경 변수 (.env)

```
GEMINI_API_KEY=...          # Google Gemini (텍스트+이미지)
OPENAI_API_KEY=...          # OpenAI (이미지)
FAL_KEY=...                 # fal.ai (Flux Kontext + LoRA) ← 신규
INSTAGRAM_ACCESS_TOKEN=...  # 인스타 발행
INSTAGRAM_USER_ID=...
CLOUDINARY_CLOUD_NAME=...   # 이미지 호스팅
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```
