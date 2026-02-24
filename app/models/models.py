"""
데이터 모델 정의 - Pydantic 기반
웹툰 자동 생성 시스템의 핵심 데이터 구조
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


# ============================================
# 1. 워크플로우 모드
# ============================================

class WorkflowMode(str, Enum):
    AUTO = "auto"       # 키워드 기반 자동 생성
    MANUAL = "manual"   # 직접 입력


class WorkflowState(str, Enum):
    INITIALIZED = "initialized"
    COLLECTING_INFO = "collecting_info"
    GENERATING_STORY = "generating_story"
    REVIEWING_SCENES = "reviewing_scenes"
    GENERATING_IMAGES = "generating_images"
    EDITING_IMAGES = "editing_images"       # ★ 이미지 편집 단계 (NEW)
    REVIEWING_IMAGES = "reviewing_images"
    OVERLAYING_TEXT = "overlaying_text"
    EDITING_THUMBNAIL = "editing_thumbnail"   # ★ 썸네일 편집 단계
    GENERATING_CAPTION = "generating_caption"
    REVIEWING_CAPTION = "reviewing_caption"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    ERROR = "error"


# ============================================
# 2. 분야 정보
# ============================================

class SpecializedField(str, Enum):
    TAX = "세무"
    LAW = "법률"
    LABOR = "노무"
    ACCOUNTING = "회계"
    REAL_ESTATE = "부동산정책"
    GENERAL = "일반"


class FieldInfo(BaseModel):
    """분야 감지 결과"""
    field: SpecializedField = SpecializedField.GENERAL
    target_year: Optional[str] = "2025"      # 기준 년도
    requires_legal_verification: bool = False # 법령 검증 필요성
    confidence_score: float = 1.0
    reason: Optional[str] = None             # 판단 근거


# ============================================
# 3. 스토리 관련 모델
# ============================================

class VisualIdentity(BaseModel):
    """캐릭터 시각적 고정 속성 — 모든 씬에서 불변"""
    gender: str = ""                    # male / female
    age_range: str = ""                 # e.g. "early 30s"
    hair_style: str = ""                # e.g. "short black hair, side parted"
    hair_color: str = ""                # e.g. "#1a1a1a jet black"
    skin_tone: str = ""                 # e.g. "warm beige, light tan"
    eye_shape: str = ""                 # e.g. "almond-shaped, medium size"
    glasses: str = "none"               # 기본값: 안경 없음. "none" 또는 구체적 안경 설명
    outfit: str = ""                    # e.g. "navy suit, white shirt, blue tie"
    outfit_color: str = ""              # e.g. "navy #1B2A4A jacket, white #FFFFFF shirt"
    accessories: str = "none"           # e.g. "silver watch on left wrist" or "none"
    body_type: str = ""                 # e.g. "average build, 175cm"
    distinguishing_features: str = "none"  # e.g. "small mole on right cheek"


class CharacterProfile(BaseModel):
    """등장인물 프로필"""
    name: str
    role: str                   # 전문가, 일반인, 조력자 등
    appearance: Optional[str] = None # 외모 묘사 (Gemini용)
    personality: Optional[str] = None # 성격
    visual_identity: Optional[VisualIdentity] = None  # 구체적 시각 속성 (이미지 일관성용)


class Dialogue(BaseModel):
    """캐릭터 대사"""
    character: str              # 캐릭터 이름 (예: "민지", "세무사")
    text: str                   # 대사 내용 (최대 20자 권장)
    emotion: Optional[str] = "neutral"  # 표정 (기쁨/걱정/설명/놀람/진지/화남)


class Scene(BaseModel):
    """개별 씬"""
    scene_number: int
    scene_description: str      # 장면 설명 (배경, 상황) — 스토리용
    scene_description_original: Optional[str] = None  # 전처리 전 원본 (백업용)
    image_prompt: Optional[str] = None  # 이미지 생성용 상세 프롬프트 (시각 묘사 전용)
    dialogues: List[Dialogue] = Field(default_factory=list)
    narration: Optional[str] = None  # 나레이션 (최대 30자 권장)
    status: str = "pending"     # pending | approved | needs_edit
    warnings: List[str] = Field(default_factory=list) # 규칙 위반 경고
    layout_meta: Optional[dict] = Field(default_factory=dict) # 씬별 개별 레이아웃 설정

    # 요약 슬라이드 / 업로드 이미지 지원
    scene_type: str = "normal"               # "normal" | "summary" | "uploaded"
    summary_style: Optional[str] = None      # "table" | "text_card" | "checklist" | "qa" | "steps" | "highlight"
    summary_text: Optional[str] = None       # 요약 슬라이드용 텍스트
    rendered_image_path: Optional[str] = None # Playwright 렌더링 결과 PNG 경로


class SeriesPublishStatus(str, Enum):
    """시리즈별 발행 상태"""
    NOT_PUBLISHED = "not_published"   # 미발행
    PUBLISHED = "published"           # 발행완료
    SCHEDULED = "scheduled"           # 예약중

class SeriesEpisode(BaseModel):
    """시리즈 개별 편 정보"""
    episode_number: int = 1                          # 편 번호 (1-based)
    scene_count: int = 0                             # 이 편의 씬 수
    scene_start: int = 0                             # 시작 씬 인덱스 (0-based, 전체 씬 목록 기준)
    scene_end: int = 0                               # 끝 씬 인덱스 (exclusive)
    publish_status: SeriesPublishStatus = SeriesPublishStatus.NOT_PUBLISHED
    published_at: Optional[str] = None               # 발행 일시
    scheduled_at: Optional[str] = None               # 예약 발행 일시
    caption_hook: Optional[str] = None               # 훅 문장
    caption_body: Optional[str] = None               # 본문 캡션
    caption_tip: Optional[str] = None                # 전문가 Tip
    caption_hashtags: Optional[str] = None           # 해시태그

class SeriesInfo(BaseModel):
    """시리즈 분할 정보"""
    total: int = 1                # 전체 편 수
    episodes: List[SeriesEpisode] = Field(default_factory=list)  # 편별 상세 정보
    prev_episode_url: Optional[str] = None   # 이전편 URL (발행 후 채워짐)
    prev_summary: Optional[str] = None       # 이전편 한줄 요약


class ToBeContinuedStyle(str, Enum):
    """'다음편에 계속' 디자인 옵션"""
    FADE_OVERLAY = "fade_overlay"   # 하단 그라데이션 + 텍스트 (기본)
    BADGE = "badge"                 # 우측 하단 작은 배지
    FULL_OVERLAY = "full_overlay"   # 전체 어둡게 + 중앙 텍스트


class Story(BaseModel):
    """전체 스토리"""
    title: str
    scenes: List[Scene] = Field(default_factory=list)
    characters: List[CharacterProfile] = Field(default_factory=list) # 3.1 추가
    total_series: int = 1       # 시리즈 개수
    scenes_per_series: List[int] = Field(default_factory=list)
    series_info: Optional[SeriesInfo] = None  # ★ 시리즈 분할 정보
    to_be_continued_enabled: bool = True      # ★ "다음편에 계속" ON/OFF (기본 ON)
    to_be_continued_style: ToBeContinuedStyle = ToBeContinuedStyle.FADE_OVERLAY


# ============================================
# 4. 이미지 관련 모델
# ============================================

class ImageStyle(str, Enum):
    WEBTOON = "webtoon"
    CARD_NEWS = "card_news"
    SIMPLE = "simple"


class SubStyle(str, Enum):
    NORMAL = "normal"
    GHIBLI = "ghibli"
    ROMANCE = "romance"
    BUSINESS = "business"
    COMIC = "comic"
    MINIMAL = "minimal"


class CharacterStyle(BaseModel):
    """인물 스타일 (v2.0)"""
    id: str
    name: str
    prompt_block: str
    locked_attributes: List[str] = Field(default_factory=list)
    reference_images: List[str] = Field(default_factory=list)
    preview_image: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False


class BackgroundStyle(BaseModel):
    """배경 스타일 (v2.0)"""
    id: str
    name: str
    prompt_block: str
    locked_attributes: List[str] = Field(default_factory=list)
    reference_images: List[str] = Field(default_factory=list)
    preview_image: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False


class ReferenceImageSet(BaseModel):
    """3종 레퍼런스 이미지 상태 (캐릭터/연출/화풍)"""
    character_path: Optional[str] = None   # Character.jpg 경로
    method_path: Optional[str] = None      # Method.jpg 경로 (구도/연출)
    style_path: Optional[str] = None       # Style.jpg 경로 (화풍)
    preset_id: Optional[str] = None        # 적용된 프리셋 ID


class ManualPromptOverrides(BaseModel):
    """수동 프롬프트 오버라이드"""
    character_style_prompt: Optional[str] = None
    background_style_prompt: Optional[str] = None
    style_prompt: Optional[str] = None # 통합된 스타일 프롬프트 (v2.0)
    additional_instructions: Optional[str] = None


class ImageEditStatus(str, Enum):
    """이미지 편집 상태"""
    PENDING = "pending"         # 미확정
    CONFIRMED = "confirmed"     # 확정됨
    REGENERATING = "regenerating"  # 재생성 중


class GeneratedImage(BaseModel):
    """생성된 이미지"""
    scene_number: int
    prompt_used: str
    image_url: Optional[str] = None
    local_path: Optional[str] = None
    original_path: Optional[str] = None   # ★ 톤 조절 전 원본 경로
    status: str = "pending"     # pending | generated | approved
    edit_status: ImageEditStatus = ImageEditStatus.PENDING  # ★ 편집 확정 상태
    image_history: List[str] = Field(default_factory=list)  # ★ 이전 이미지 경로 이력
    prompt_history: List[str] = Field(default_factory=list)  # ★ 이전 프롬프트 이력
    tone_adjusted: bool = False  # ★ 톤 조절 적용 여부


# ============================================
# 4.5 썸네일 관련 모델
# ============================================

class ThumbnailPosition(str, Enum):
    """제목 텍스트 위치"""
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class ThumbnailSource(str, Enum):
    """썸네일 생성 방식"""
    AI_GENERATE = "ai_generate"       # AI 자동 생성
    SELECT_SCENE = "select_scene"     # 본편 이미지에서 선택
    UPLOAD = "upload"                 # 직접 업로드


class ThumbnailData(BaseModel):
    """썸네일(커버 이미지) 데이터"""
    enabled: bool = True                           # 썸네일 ON/OFF (기본 ON)
    source: ThumbnailSource = ThumbnailSource.AI_GENERATE
    image_path: Optional[str] = None               # 생성/선택/업로드된 이미지 경로
    selected_scene_number: Optional[int] = None     # SELECT_SCENE일 때 선택한 씬 번호
    # 제목 텍스트 오버레이
    title_text: Optional[str] = None               # 제목 (자동 생성 또는 사용자 입력)
    subtitle_text: Optional[str] = None            # 부제목 (선택)
    series_number: Optional[str] = None            # 시리즈 번호 표시 (예: "2편")
    title_position: ThumbnailPosition = ThumbnailPosition.CENTER
    title_color: str = "#FFFFFF"
    title_size: int = 48
    title_font: str = "NanumGothicBold"            # 굵은 폰트 기본


# ============================================
# 4.7 비파괴 말풍선 레이어 (Non-destructive Bubble Layer)
# ============================================

class BubblePosition(str, Enum):
    """9-Grid 위치"""
    TOP_LEFT = "top-left"
    TOP_CENTER = "top-center"
    TOP_RIGHT = "top-right"
    MIDDLE_LEFT = "middle-left"
    MIDDLE_CENTER = "middle-center"
    MIDDLE_RIGHT = "middle-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_CENTER = "bottom-center"
    BOTTOM_RIGHT = "bottom-right"


class BubbleShape(str, Enum):
    """말풍선 모양"""
    ROUND = "round"
    ELLIPSE = "ellipse"
    SQUARE = "square"
    SHOUT = "shout"
    THOUGHT = "thought"
    WHISPER = "whisper"
    CLOUD = "cloud"
    DARK = "dark"
    EMPHASIS = "emphasis"
    SYSTEM = "system"
    SOFT = "soft"
    # 웹툰 전용 (clip-path 기반)
    STARBURST = "starburst"
    SPIKE = "spike"
    EXPLOSION = "explosion"
    SCALLOP = "scallop"
    WAVY = "wavy"
    FLUFFY = "fluffy"
    JAGGED = "jagged"


class BubbleOverlay(BaseModel):
    """개별 말풍선 오버레이"""
    model_config = {"populate_by_name": True}

    id: str                                          # 고유 ID
    type: str = "dialogue"                           # dialogue | narration
    character: str = ""                              # 캐릭터 이름 (narration이면 빈 문자열)
    text: str = ""                                   # 대사/나레이션 텍스트
    position: BubblePosition = BubblePosition.TOP_CENTER
    shape: BubbleShape = BubbleShape.ROUND
    font_family: str = ""                            # 개별 폰트 (빈 문자열=레이어 글로벌 따라감)
    tail_direction: str = "none"                     # 꼬리 방향: none|bottom-left|bottom-right|...
    tail: str = "none"                               # 프론트엔드 호환 (tail_direction alias)
    narration_style: str = "classic"                 # 나레이션 전용 스타일
    bg_color: str = "#FFFFFF"                        # 말풍선 배경색
    text_color: str = "#000000"                      # 텍스트 색
    border_color: str = "#333333"                    # 테두리 색
    font_size: int = 18                              # px
    bold: bool = False                               # 볼드 여부
    text_align: str = "left"                         # 텍스트 정렬: left | center | right
    visible: bool = True                             # 표시/숨기기 토글
    opacity: float = 0.95                            # 투명도 (0~1)
    # 자유 위치/크기 (퍼센트, 0~100)
    x: Optional[float] = None                        # 왼쪽 위치 %
    y: Optional[float] = None                        # 위쪽 위치 %
    w: Optional[float] = None                        # 폭 %
    h: Optional[float] = None                        # 높이 %

    def model_post_init(self, __context):
        """tail ↔ tail_direction 동기화 (tail 우선)"""
        # tail이 전달되면 tail_direction에 동기화 (프론트 기준)
        if self.tail and self.tail != "none":
            self.tail_direction = self.tail
        elif self.tail == "none":
            # 명시적으로 "none"이면 tail_direction도 "none"으로 통일
            self.tail_direction = "none"
        elif self.tail_direction and self.tail_direction != "none":
            self.tail = self.tail_direction


class CharacterBubbleStyle(BaseModel):
    """캐릭터별 기본 말풍선 스타일"""
    character: str                                   # 캐릭터 이름
    shape: str = "round"                             # 기본 모양
    font_family: str = ""                            # 기본 폰트
    font_size: int = 15                              # 기본 크기
    bg_color: str = "#FFFFFF"                        # 기본 배경색
    text_color: str = "#000000"                      # 기본 글자색
    border_color: str = "#333333"                    # 기본 테두리색
    tail_direction: str = "bottom-left"              # 기본 꼬리 방향


class BubbleLayer(BaseModel):
    """씬별 비파괴 말풍선 레이어 — 원본 이미지는 절대 건드리지 않음"""
    scene_number: int
    bubbles: List[BubbleOverlay] = Field(default_factory=list)
    show_all: bool = True                            # 씬 전체 말풍선 표시/숨기기
    font_family: str = "Nanum Gothic"                # 전체 폰트
    character_styles: List[CharacterBubbleStyle] = Field(default_factory=list)  # 캐릭터별 스타일


# 캐릭터별 자동 색상 팔레트 (최대 8명)
CHARACTER_COLORS = [
    {"bg": "#FFFFFF", "text": "#000000", "border": "#333333"},   # 기본 흰색
    {"bg": "#E3F2FD", "text": "#000000", "border": "#1565C0"},   # 파랑
    {"bg": "#FFF3E0", "text": "#000000", "border": "#F57C00"},   # 주황
    {"bg": "#F3E5F5", "text": "#000000", "border": "#8E24AA"},   # 보라
    {"bg": "#E8F5E9", "text": "#000000", "border": "#2E7D32"},   # 초록
    {"bg": "#FCE4EC", "text": "#000000", "border": "#C2185B"},   # 핑크
    {"bg": "#FFF9C4", "text": "#000000", "border": "#FBC02D"},   # 노랑
    {"bg": "#EFEBE9", "text": "#000000", "border": "#5D4037"},   # 갈색
]


# ============================================
# 5. 캡션 관련 모델
# ============================================

class InstagramCaption(BaseModel):
    """인스타그램 캡션"""
    hook: str                   # 훅 문장 (첫 줄)
    body: str                   # 본문 캡션
    expert_tip: str             # 전문가 Tip
    hashtags: List[str] = Field(default_factory=list)

    def to_string(self) -> str:
        """인스타 발행용 전체 캡션"""
        hashtag_str = " ".join(self.hashtags)
        return f"""{self.hook}

{self.body}

💡 {self.expert_tip}

{hashtag_str}"""


# ============================================
# 6. 발행 관련 모델
# ============================================

class PublishData(BaseModel):
    """발행 데이터"""
    images: List[str] = Field(default_factory=list)  # 이미지 URL 목록
    caption: str = ""
    hashtags: List[str] = Field(default_factory=list)
    scheduled_time: Optional[datetime] = None


# ============================================
# 7. 설정 모델
# ============================================

class RuleSettings(BaseModel):
    """씬 생성 규칙 설정"""
    max_dialogue_len: int = 20
    max_bubbles_per_scene: int = 2
    max_narration_len: int = 30
    auto_split_on_violation: bool = True


class TextSettings(BaseModel):
    """텍스트 설정"""
    font_name: str = "NanumGothic"
    dialogue_font_size: int = 24
    narration_font_size: int = 20
    dialogue_placement: str = "bubble"  # bubble | subtitle
    color: str = "#000000"


class CharacterSettings(BaseModel):
    """캐릭터 설정"""
    questioner_type: str = "일반인"     # 일반인 | 사업자 | 직장인
    expert_type: str = "전문가"         # 전문가 | 세무사 | 변호사 | 노무사 | 회계사
    presets: List[CharacterProfile] = Field(default_factory=list) # 저장된 프리셋
    auto_emotion: bool = True


class LayoutSettings(BaseModel):
    """레이아웃 설정"""
    aspect_ratio: str = "4:5"           # 1:1 | 4:5 | 9:16
    width: int = 1080
    height: int = 1350
    margin: int = 20
    page_number_position: str = "bottom_right" # bottom_right | bottom_center | hide
    show_badge: bool = True             # 시리즈 배지 표시 여부


class ImageSettings(BaseModel):
    """이미지 생성 설정"""
    style: ImageStyle = ImageStyle.WEBTOON
    sub_style: SubStyle = SubStyle.NORMAL
    use_mascot: bool = True
    model: str = ""  # 빈 값 → config.DEFAULT_IMAGE_MODEL 사용
    add_next_episode_tag: bool = True   # "다음 화에 계속" 태그 추가
    
    # Style System 2.0
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    manual_overrides: Optional[ManualPromptOverrides] = None
    
    # 3종 레퍼런스 이미지 (Character/Method/Style)
    reference_images: ReferenceImageSet = Field(default_factory=ReferenceImageSet)
    scene_chaining: bool = True  # 이전 씬 참조 (직전 씬 이미지 + 텍스트 요약)


class OutputSettings(BaseModel):
    """출력 설정"""
    format: str = "individual"   # individual | grid_2x2 | horizontal | vertical
    file_type: str = "png"       # png | jpg | webp
    quality: int = 90
    watermark: Optional[str] = None


class AISettings(BaseModel):
    """AI 엔진 설정"""
    data_model: str = ""   # 빈 값 → config.DEFAULT_TEXT_MODEL 사용
    story_model: str = ""  # 빈 값 → config.DEFAULT_TEXT_MODEL 사용
    image_model: str = ""  # 빈 값 → config.DEFAULT_IMAGE_MODEL 사용
    auto_detect_field: bool = True


class ProjectSettings(BaseModel):
    """전체 프로젝트 설정"""
    rules: RuleSettings = Field(default_factory=RuleSettings)
    text: TextSettings = Field(default_factory=TextSettings)
    character: CharacterSettings = Field(default_factory=CharacterSettings)
    layout: LayoutSettings = Field(default_factory=LayoutSettings)
    image: ImageSettings = Field(default_factory=ImageSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    ai: AISettings = Field(default_factory=AISettings)


# ============================================
# 8. 워크플로우 세션
# ============================================

class WorkflowSession(BaseModel):
    """워크플로우 세션 데이터"""
    session_id: str
    state: WorkflowState = WorkflowState.INITIALIZED
    mode: WorkflowMode = WorkflowMode.AUTO
    keyword: Optional[str] = None
    field_info: Optional[FieldInfo] = None
    story: Optional[Story] = None
    images: List[GeneratedImage] = Field(default_factory=list)
    final_images: List[str] = Field(default_factory=list)
    thumbnail: Optional[ThumbnailData] = None  # ★ 썸네일(커버) 데이터
    caption: Optional[InstagramCaption] = None
    publish_data: Optional[PublishData] = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    collected_data: List[dict] = Field(default_factory=list) # 수집된 자료 저장
    # ★ 이미지 편집 단계 관련
    global_tone_adjustments: List[dict] = Field(default_factory=list)  # 전체 톤 조절 이력
    bubble_layers: List[BubbleLayer] = Field(default_factory=list)     # ★ 비파괴 말풍선 레이어
    last_error: Optional[str] = None  # 백그라운드 작업 실패 시 에러 메시지
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================
# 9. LoRA 학습 관련 모델
# ============================================

class TrainingStatus(str, Enum):
    """LoRA 학습 상태"""
    PENDING = "pending"           # 대기 중
    UPLOADING = "uploading"       # 이미지 업로드 중
    TRAINING = "training"         # 학습 진행 중
    COMPLETED = "completed"       # 완료
    FAILED = "failed"             # 실패


class LoraStyleId(str, Enum):
    """LoRA 학습용 스타일 ID (24컷 생성 시 적용)"""
    ORIGINAL = "original"                   # 원본 스타일 그대로
    REALISTIC_SKETCH = "realistic_sketch"   # 실사 얼굴 + 손그림 몸체
    CHIBI_2HEAD = "chibi_2head"             # 2등신 치비 (Phase 2)
    KAKAO_EMOTICON = "kakao_emoticon"       # 카카오 이모티콘풍 (Phase 2)
    SIMPLE_LINEART = "simple_lineart"       # 단순 선화 (Phase 2)
    CUSTOM = "custom"                       # 커스텀 (Phase 2)


# 스타일별 표시 이름
LORA_STYLE_LABELS = {
    "original": "📷 원본 스타일 그대로",
    "realistic_sketch": "🎨 실사 얼굴 + 손그림 몸체",
    "chibi_2head": "🧸 2등신 치비",
    "kakao_emoticon": "💬 카카오 이모티콘풍",
    "simple_lineart": "✏️ 단순 선화",
    "custom": "🔧 커스텀",
}

# 스타일별 프롬프트 키워드
LORA_STYLE_PROMPTS = {
    "original": "",  # 스타일 변환 없음 — 원본 유지
    "realistic_sketch": "realistic face with hand-drawn ink sketch body, simple stick figure body, white background",
    "chibi_2head": "chibi style, 2-head tall proportion, cute large head, small body, simple colored, white background",
    "kakao_emoticon": "Korean KakaoTalk emoticon style, round soft lines, bright pastel colors, cute expression, white background",
    "simple_lineart": "minimal black line art, clean outline, no shading, white background, monochrome",
    "custom": "",
}


class TrainedCharacter(BaseModel):
    """학습된 캐릭터 (LoRA)"""
    id: str                                     # 고유 ID (uuid)
    name: str                                   # 캐릭터 이름
    trigger_word: str                           # 트리거 워드 (예: "sks_taxman")
    lora_url: str = ""                          # 학습된 LoRA 가중치 URL (fal.ai)
    training_images: List[str] = Field(default_factory=list)   # 학습에 사용된 이미지 경로
    training_count: int = 0                     # 총 학습 이미지 수
    training_rounds: int = 0                    # 학습 횟수 (추가 학습 가능)
    status: TrainingStatus = TrainingStatus.PENDING
    preview_image: Optional[str] = None         # 대표 미리보기 이미지 경로
    description: Optional[str] = None           # 캐릭터 설명
    style_tags: List[str] = Field(default_factory=list)  # 스타일 태그 (예: ["세무사", "안경"])
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None         # 학습 실패 시 오류 메시지
    # ── 명세서 추가 필드 (캐릭터 LoRA 자동 학습) ──
    style_id: str = "original"                  # 학습에 사용된 스타일 (LoraStyleId)
    style_label: str = "📷 원본 스타일 그대로"    # 스타일 표시명
    lora_scale_default: float = 0.8             # 기본 LoRA scale
    original_photo_url: Optional[str] = None    # 최초 업로드한 사진 URL
    sample_images: List[str] = Field(default_factory=list)  # 테스트 생성 샘플 이미지 URLs
    training_steps: int = 1500                  # 학습 스텝 수


class TrainingJob(BaseModel):
    """LoRA 학습 작업"""
    job_id: str                                 # fal.ai 작업 ID
    character_id: str                           # TrainedCharacter.id
    status: TrainingStatus = TrainingStatus.PENDING
    progress: float = 0.0                       # 0.0 ~ 1.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_url: Optional[str] = None            # 완료 시 LoRA 가중치 URL
    error_message: Optional[str] = None


class GenerationSession(BaseModel):
    """24컷 생성 세션 — 사진 업로드부터 학습 시작까지의 상태 관리"""
    session_id: str                             # 고유 세션 ID (uuid)
    photo_url: str = ""                         # 업로드된 원본 사진 URL
    photo_local_path: str = ""                  # 로컬 저장 경로
    style_id: str = "original"                  # 선택된 스타일
    custom_prompt: Optional[str] = None         # 커스텀 스타일 프롬프트
    character_name: str = ""                    # 캐릭터 이름
    trigger_word: str = ""                      # 트리거 워드
    # 24컷 생성 상태
    status: str = "idle"                        # idle | generating | completed | failed
    total_cuts: int = 24
    generated_cuts: List[dict] = Field(default_factory=list)  # [{id, url, label_ko, selected}]
    selected_cut_ids: List[int] = Field(default_factory=list)  # 사용자가 선택한 컷 ID 목록
    # 학습 연결
    character_id: Optional[str] = None          # 학습 시작 후 TrainedCharacter.id
    training_job_id: Optional[str] = None       # fal.ai 학습 작업 ID
    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.now)
    estimated_cost: float = 0.0
