# Auto-Webtoon (세무 웹툰 자동화 시스템)

세무/회계/법률 등 전문 분야의 정보를 **웹툰, 캐러셀, 카드뉴스** 형태로 자동 생성하고 인스타그램에 발행하는 시스템입니다.

## 주요 기능

- **웹툰 자동 생성**: 키워드 입력 → AI 스토리 생성 → AI 이미지 생성 → 말풍선/대사 합성
- **캐러셀/카드뉴스**: 슬라이드형 정보 콘텐츠 자동 제작
- **인스타그램 발행**: 생성된 콘텐츠를 Instagram Graph API로 직접 발행
- **캐릭터 일관성**: 레퍼런스 이미지 기반 캐릭터 외형 유지
- **이미지 프롬프트 편집**: 이미지 생성 프롬프트를 직접 확인하고 편집 가능

---

## 요구사항

- **Python 3.10 이상**
- Windows / macOS / Linux
- Node.js 불필요 (순수 Python 백엔드)

---

## 설치 방법

### 1. 프로젝트 클론

```bash
git clone https://github.com/taxmusa/Auto-webtoon.git
cd Auto-webtoon
```

### 2. 가상환경 생성 및 활성화

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. Playwright 브라우저 설치 (텍스트 렌더링용)

```bash
playwright install chromium
```

---

## 환경 설정

`.env.example` 파일을 복사하여 `.env`로 저장한 뒤, 각 API 키를 입력합니다.

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

### 필수 API 키

#### Google Gemini API (필수)

스토리 생성 + 이미지 생성에 사용됩니다.

1. [Google AI Studio](https://aistudio.google.com/) 접속
2. 좌측 메뉴에서 "API keys" 클릭
3. "Create API Key" 클릭하여 키 발급
4. `.env` 파일에 입력:

```
GEMINI_API_KEY=발급받은_키
```

### 선택 API 키

#### Cloudinary (인스타그램 발행 시 필수)

인스타그램 발행 시 이미지를 클라우드에 업로드하는 데 사용됩니다.

1. [Cloudinary](https://cloudinary.com/) 에서 무료 가입
2. Dashboard에서 Cloud Name, API Key, API Secret 확인
3. `.env` 파일에 입력:

```
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

#### Instagram Graph API (인스타그램 발행 시 필수)

인스타그램 발행을 위해서는 아래 4가지가 모두 필요합니다.

**사전 준비:**

- Instagram **비즈니스 계정** (개인 계정 X, 프로필 설정에서 전환 가능)
- 비즈니스 계정과 연결된 **Facebook 페이지**
- Facebook **개발자 계정**

**Step 1: Facebook 앱 생성**

1. [Facebook 개발자](https://developers.facebook.com/) 에서 로그인
2. 우측 상단 "내 앱" → "앱 만들기" 클릭
3. 앱 유형: "비즈니스" 선택
4. 앱 이름 입력 후 생성
5. 앱 대시보드 → "설정" → "기본" 에서 **App ID**와 **App Secret** 확인 (나중에 필요)

**Step 2: 필수 권한이 포함된 단기 토큰 발급**

1. [Graph API Explorer](https://developers.facebook.com/tools/explorer/) 접속
2. 우측 상단에서 방금 만든 앱 선택
3. "권한 추가" 버튼을 클릭하여 아래 **5개 권한 반드시 체크**:
   - `pages_show_list`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
   - `business_management`
4. "Generate Access Token" 클릭
5. Facebook 로그인 팝업에서 **인스타그램이 연결된 페이지를 반드시 선택**
6. 모든 권한 허용 후 토큰 발급 완료

이 토큰은 **약 1시간**만 유효한 단기 토큰입니다.

**Step 3: 영구 토큰으로 교환 (중요!)**

단기 토큰을 영구 페이지 토큰으로 교환해야 합니다. 두 가지 방법 중 택 1:

*방법 A: 프로그램 내 설정 탭 (권장)*

1. 프로그램 실행 후 설정 탭으로 이동
2. Facebook App ID, App Secret 입력 후 저장
3. 단기 토큰 붙여넣기 → "토큰 교환" 클릭
4. 자동으로 **영구 페이지 토큰** 교환 + `.env` 저장 완료

*방법 B: 커맨드라인 도구*

```bash
.\venv\Scripts\python _token_exchange.py
```

안내에 따라 App ID, App Secret, 단기 토큰을 입력하면 자동으로 교환됩니다.

**토큰 종류 비교:**

| 토큰 종류 | 유효 기간 | 설명 |
|-----------|-----------|------|
| 단기 사용자 토큰 | ~1시간 | Graph API Explorer에서 발급 |
| 장기 사용자 토큰 | ~60일 | 단기 토큰을 교환한 것 |
| **페이지 토큰** | **영구 (만료 없음)** | 장기 사용자 토큰에서 자동 파생, 비밀번호 변경/앱 삭제 시에만 무효화 |

교환 완료 후 `.env` 파일에 자동 저장되며, **이후 갱신 작업은 필요 없습니다.**
비밀번호를 변경하거나 앱을 삭제하지 않는 한 영구적으로 사용 가능합니다.

#### OpenAI API (선택)

DALL-E 이미지 생성 시 사용됩니다. Gemini만으로도 사용 가능합니다.

```
OPENAI_API_KEY=your_openai_key
```

---

## 실행

```bash
python run.py
```

실행 후 브라우저가 자동으로 `http://127.0.0.1:8000`에 열립니다.

---

## 다른 PC로 이동 시 필수 설정

프로젝트 폴더를 다른 컴퓨터로 복사하거나 `git clone`으로 받은 경우, 아래 순서대로 진행합니다.

### 주의사항

- `venv` 폴더는 복사하지 마세요 (경로가 달라서 작동하지 않습니다)
- `.env` 파일은 그대로 복사하면 API 키 재입력 불필요

### 1. Python 설치 (최초 1회)

[python.org](https://www.python.org/downloads/) 에서 Python 3.10 이상 다운로드 후 설치합니다. 설치 시 반드시 **"Add Python to PATH"** 체크합니다.

### 2. 환경 구성 (최초 1회)

PowerShell 또는 명령 프롬프트에서 프로젝트 폴더로 이동 후 실행합니다.

```powershell
cd C:\경로\Auto-webtoon

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 텍스트 렌더링용 브라우저 설치
playwright install chromium
```

### 3. 실행

```powershell
python run.py
```

이후부터는 **3번만 반복**하면 됩니다. 1~2번은 최초 1회만 실행합니다.

---

## 기본 사용 흐름

1. **키워드 입력**: 만들고 싶은 콘텐츠 주제 입력 (예: "종합소득세 신고 방법")
2. **자료 수집**: AI가 관련 정보를 수집
3. **콘텐츠 타입 선택**: 웹툰 / 캐러셀 / 카드뉴스 중 선택
4. **스토리 생성**: AI가 씬별 스토리 자동 생성
5. **씬 편집**: 씬 설명, 대사, 이미지 프롬프트를 직접 수정 가능
6. **이미지 생성**: 각 씬에 대한 AI 이미지 생성
7. **말풍선 편집**: 대사 위치, 크기, 스타일 조정
8. **캡션/태그**: AI 캡션 자동 생성 또는 직접 작성
9. **발행**: 인스타그램에 캐러셀 형태로 발행

---

## 프로젝트 구조

```
Auto-webtoon/
├── run.py                  # 서버 실행 진입점
├── requirements.txt        # Python 패키지 목록
├── .env.example            # 환경 변수 예시
├── app/
│   ├── main.py             # FastAPI 앱 초기화
│   ├── api/
│   │   └── workflow.py     # API 엔드포인트 (스토리, 이미지, 발행)
│   ├── models/
│   │   └── models.py       # 데이터 모델 (Scene, Character 등)
│   ├── services/
│   │   ├── gemini_service.py      # Gemini AI 연동
│   │   ├── image_generator.py     # 이미지 생성 엔진
│   │   ├── prompt_builder.py      # 프롬프트 조립
│   │   ├── prompt_rules.py        # 프롬프트 정제 규칙
│   │   ├── reference_service.py   # 레퍼런스 이미지 관리
│   │   └── scene_preprocessor.py  # 씬 전처리
│   └── templates/
│       └── index.html      # 프론트엔드 (단일 파일 SPA)
└── output/                 # 생성된 이미지 저장 디렉토리
```

---

## 라이선스

이 프로젝트는 개인/상업 프로그램 판매용으로 제작되었습니다.
