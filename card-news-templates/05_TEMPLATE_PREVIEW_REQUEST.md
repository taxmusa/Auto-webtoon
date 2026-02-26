# 05. 템플릿 미리보기 생성 요구사항

> 이 파일은 Claude Code에게 "모든 템플릿을 한눈에 볼 수 있는 미리보기"를 만들어달라고 할 때 사용.
> MD 파일 제목만으로는 어떤 디자인인지 알 수 없으므로, 실제 이미지로 미리보기를 생성해야 한다.

---

## 요청 사항

### 1. 미리보기 이미지 생성 (Python + Pillow)

**모든 12종 템플릿을 실제 세무사 예시 데이터로 채워서 PNG 이미지로 생성해라.**

생성할 파일 목록:

```
preview/
├── cover_a_dark_best.png          # 커버A: 다크 BEST 리스트
├── cover_b_dark_category.png      # 커버B: 다크 카테고리
├── cover_c_blue_report.png        # 커버C: 블루 리포트
├── cover_d_minimal_card.png       # 커버D: 미니멀 카드
├── cover_e_warm_question.png      # 커버E: 웜톤 질문형
├── cover_f_teal_report.png        # 커버F: 틸 리포트
├── body_a_numbered_list.png       # 본문A: 넘버링 리스트
├── body_b_comparison.png          # 본문B: 비교형
├── body_c_highlight.png           # 본문C: 하이라이트 박스
├── body_d_steps.png               # 본문D: 스텝/프로세스
├── closing_a_summary_cta.png      # 마무리A: 요약+CTA
├── closing_b_brand_card.png       # 마무리B: 브랜드 카드
└── all_templates_grid.png         # 전체 12종 한 장 그리드
```

---

### 2. 미리보기용 세무사 예시 데이터

각 템플릿에 채워넣을 샘플 데이터:

#### 커버 A (다크 BEST)
```python
{
    "subtitle": "2025년 반드시 알아야 할",
    "title": "종합소득세\n절세 방법\nBEST 5",
    "tags": ["#종합소득세", "#절세팁", "#세무사"],
    "handle": "@taxlab_jikwang",
}
```

#### 커버 B (다크 카테고리)
```python
{
    "category": "💰 세무 상식 필수 정보",
    "title": "부동산 취득세\n이것 모르면\n수백만원 손해!",
    "highlight_word": "수백만원 손해!",  # yellow로 강조
    "description": "2025년 개정된 취득세율과\n감면 혜택을 한눈에 정리합니다.",
    "handle": "@taxlab_jikwang",
}
```

#### 커버 C (블루 리포트)
```python
{
    "category": "2025 TAX REPORT",
    "title": "연말정산\n환급 많이 받는\n핵심 전략",
    "badge": "핵심 체크리스트",
    "description": "놓치기 쉬운 공제항목과\n최적의 신고 전략을 안내합니다.",
    "handle": "@taxlab_jikwang",
}
```

#### 커버 D (미니멀 카드)
```python
{
    "title_en": "TAX\nGUIDE",
    "subtitle_kr": "사업자 필수 세금 상식",
    "description": "매출부터 신고까지\n사업자가 알아야 할 핵심 포인트.",
    "handle": "@taxlab_jikwang",
}
```

#### 커버 E (웜톤 질문)
```python
{
    "title": "매년 내는 재산세,\n제대로 알고\n있나요?",
    "description": "재산세 계산부터 납부 시기까지\n한 번에 정리해드립니다.",
    "brand": "세무회계 지광",
    "handle": "@taxlab_jikwang",
}
```

#### 커버 F (틸 리포트)
```python
{
    "title_en": "2025\nTax\nReport",
    "subtitle_kr": "올해 달라진 5가지 세법 핵심 포인트",
}
```

#### 본문 A (넘버링 리스트) — 다크 테마
```python
{
    "page": "2/7",
    "items": [
        {"title": "인적공제 꼼꼼히 챙기기", "desc": "부양가족 기본공제(150만원)와\n추가공제를 빠짐없이 확인하세요."},
        {"title": "신용카드 공제 최적화", "desc": "총급여의 25% 초과 사용분부터\n공제가 시작됩니다."},
        {"title": "연금저축 한도 채우기", "desc": "연 900만원 한도 IRP 포함,\n최대 148.5만원 세액공제."},
    ],
    "handle": "@taxlab_jikwang",
}
```

#### 본문 B (비교형) — 라이트 테마
```python
{
    "page": "3/7",
    "title": "사업용 경비 처리 O/X",
    "bad": {
        "label": "✕ 이렇게 하면 안 돼요",
        "text": "개인 식비를 사업 경비로 처리\n적격증빙 없이 비용 인정 요청",
    },
    "good": {
        "label": "✓ 이렇게 해야 해요",
        "text": "거래처 접대비로 적격증빙 갖춰 처리\n건당 1만원 이하는 간이영수증 가능",
    },
    "point": "💡 핵심은 '업무 관련성' + '적격증빙'입니다",
    "handle": "@taxlab_jikwang",
}
```

#### 본문 C (하이라이트 박스) — 블루 테마
```python
{
    "page": "4/7",
    "category": "CASE STUDY",
    "title": "연봉 5천만원 직장인 절세 효과",
    "highlight_number": "1,485,000",
    "highlight_prefix": "₩",
    "highlight_suffix": "원",
    "highlight_label": "연간 예상 절세 금액",
    "breakdown": [
        ("연금저축 (400만원 × 16.5%)", "660,000원"),
        ("IRP (300만원 × 16.5%)", "495,000원"),
        ("월세 세액공제 (연600만원 × 17%)", "330,000원"),
    ],
    "total": ("합계", "1,485,000원"),
    "handle": "@taxlab_jikwang",
}
```

#### 본문 D (스텝) — 다크 테마
```python
{
    "page": "5/7",
    "category": "PROCESS",
    "title": "종합소득세 신고 절차",
    "steps": [
        {"step": 1, "title": "홈택스 접속 및 로그인", "desc": "공동인증서 또는 간편인증으로 로그인"},
        {"step": 2, "title": "소득·공제 내역 확인", "desc": "근로/사업/기타소득과 공제항목 확인"},
        {"step": 3, "title": "세액 계산 및 신고서 작성", "desc": "자동계산된 세액 확인 후 신고서 제출"},
        {"step": 4, "title": "납부 또는 환급", "desc": "추가납부세액은 납부, 환급은 계좌 입금"},
    ],
    "handle": "@taxlab_jikwang",
}
```

#### 마무리 A (요약+CTA)
```python
{
    "page": "6/7",
    "summary_title": "오늘의 핵심 정리",
    "points": [
        "인적공제·연금저축을 빠짐없이 챙기세요",
        "신용카드 vs 체크카드 비율을 최적화하세요",
        "연말정산 간소화 서비스는 1월 15일 오픈",
    ],
    "cta_message": "맞춤 절세 전략이\n필요하신가요?",
    "cta_button": "📞 무료 세무 상담 신청",
    "handle": "@taxlab_jikwang",
}
```

#### 마무리 B (브랜드 카드)
```python
{
    "page": "7/7",
    "brand": "세무회계 지광",
    "slogan": "쉽고 정확한 세금 가이드",
    "contacts": [
        "📞 02-XXX-XXXX",
        "📧 tax@jikwang.com",
        "📍 서울 강남구 XX로 XX",
    ],
    "tags": ["#세무사", "#절세", "#종합소득세", "#세무상담"],
    "footer": "💾 저장하고 필요할 때 꺼내보세요!",
}
```

---

### 3. 전체 그리드 이미지 (all_templates_grid.png)

12종을 4열 × 3행으로 배치한 한 장짜리 총정리 이미지:

```
┌──────┬──────┬──────┬──────┐
│ 커버A │ 커버B │ 커버C │ 커버D │
├──────┼──────┼──────┼──────┤
│ 커버E │ 커버F │ 본문A │ 본문B │
├──────┼──────┼──────┼──────┤
│ 본문C │ 본문D │마무리A│마무리B│
└──────┴──────┴──────┴──────┘
```

- 각 셀 크기: 540x540 (축소)
- 셀 하단에 템플릿 ID 라벨 표시
- 전체 이미지: 2160 x 1620 (또는 여백 포함 더 크게)

---

### 4. HTML 카탈로그 (선택사항)

`preview/catalog.html` 파일로 브라우저에서 볼 수 있는 카탈로그도 생성하면 좋음:
- 각 템플릿 이미지 + 이름 + 설명
- 클릭하면 원본 크기로 보기
- 반응형 그리드

---

### 5. 구현 우선순위

Claude Code에서 작업할 때 이 순서로:

1. **폰트 설치** (Pretendard 또는 Noto Sans KR)
2. **공통 유틸 함수** (텍스트 렌더링, 둥근 사각형, 태그 버튼 등)
3. **커버 6종 구현** → 미리보기 이미지 생성
4. **본문 4종 구현** → 미리보기 이미지 생성
5. **마무리 2종 구현** → 미리보기 이미지 생성
6. **전체 그리드** 생성
7. **메인 API** — `generate_card_news(topic, template_set, content)` 함수

---

### 6. Claude Code에 주는 프롬프트 예시

```
이 프로젝트의 모든 md 파일을 읽고, reference-images/ 폴더의 레퍼런스 이미지를 참고하여
Python + Pillow로 12종 카드뉴스 템플릿을 구현해줘.

먼저 05_TEMPLATE_PREVIEW_REQUEST.md의 샘플 데이터로 
각 템플릿의 미리보기 이미지를 preview/ 폴더에 생성해줘.

폰트는 Pretendard를 먼저 시도하고, 없으면 Noto Sans KR을 사용해.
```

---

## 파일 구조 최종 정리

```
card-news-templates/
├── 01_DESIGN_SYSTEM.md              # 컬러, 폰트, 공통 레이아웃
├── 02_COVER_TEMPLATES.md            # 커버 슬라이드 6종 상세
├── 03_BODY_TEMPLATES.md             # 본문 슬라이드 4종 상세
├── 04_CLOSING_TEMPLATES.md          # 마무리 슬라이드 2종 상세
├── 05_TEMPLATE_PREVIEW_REQUEST.md   # 미리보기 생성 요구사항 (이 파일)
├── reference-images/                # 원본 레퍼런스 이미지 17장
│   ├── ref01_dark_best.png
│   ├── ref02_browser.png
│   ├── ref03_minimal_serif.png
│   ├── ...
│   └── ref17_warm_brown.png
└── preview/                         # (생성될) 미리보기 이미지
    ├── cover_a_dark_best.png
    ├── ...
    └── all_templates_grid.png
```
