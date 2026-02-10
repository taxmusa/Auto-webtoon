"""
데이터 모델 정의 - Pydantic 기반
세무 웹툰 자동화 시스템의 핵심 데이터 구조
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

class CharacterProfile(BaseModel):
    """등장인물 프로필"""
    name: str
    role: str                   # 전문가, 일반인, 조력자 등
    appearance: Optional[str] = None # 외모 묘사 (Gemini용)
    personality: Optional[str] = None # 성격


class Dialogue(BaseModel):
    """캐릭터 대사"""
    character: str              # 캐릭터 이름 (예: "민지", "세무사")
    text: str                   # 대사 내용 (최대 20자 권장)
    emotion: Optional[str] = "neutral"  # 표정 (기쁨/걱정/설명/놀람/진지/화남)


class Scene(BaseModel):
    """개별 씬"""
    scene_number: int
    scene_description: str      # 장면 설명 (배경, 상황)
    dialogues: List[Dialogue] = Field(default_factory=list)
    narration: Optional[str] = None  # 나레이션 (최대 30자 권장)
    status: str = "pending"     # pending | approved | needs_edit
    warnings: List[str] = Field(default_factory=list) # 규칙 위반 경고
    layout_meta: Optional[dict] = Field(default_factory=dict) # 씬별 개별 레이아웃 설정


class Story(BaseModel):
    """전체 스토리"""
    title: str
    scenes: List[Scene] = Field(default_factory=list)
    characters: List[CharacterProfile] = Field(default_factory=list) # 3.1 추가
    total_series: int = 1       # 시리즈 개수
    scenes_per_series: List[int] = Field(default_factory=list)


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


class BackgroundStyle(BaseModel):
    """배경 스타일 (v2.0)"""
    id: str
    name: str
    prompt_block: str
    locked_attributes: List[str] = Field(default_factory=list)
    reference_images: List[str] = Field(default_factory=list)


class ManualPromptOverrides(BaseModel):
    """수동 프롬프트 오버라이드"""
    character_style_prompt: Optional[str] = None
    background_style_prompt: Optional[str] = None
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
    expert_type: str = "세무사"         # 세무사 | 변호사 | 노무사 | 회계사
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
    model: str = "dall-e-3"
    model: str = "dall-e-3"
    add_next_episode_tag: bool = True   # "다음 화에 계속" 태그 추가
    
    # Style System 2.0
    character_style_id: Optional[str] = None
    background_style_id: Optional[str] = None
    manual_overrides: Optional[ManualPromptOverrides] = None


class OutputSettings(BaseModel):
    """출력 설정"""
    format: str = "individual"   # individual | grid_2x2 | horizontal | vertical
    file_type: str = "png"       # png | jpg | webp
    quality: int = 90
    watermark: Optional[str] = None


class AISettings(BaseModel):
    """AI 엔진 설정"""
    data_model: str = "gemini-2.0-flash"
    story_model: str = "gemini-2.0-flash"
    image_model: str = "dall-e-3"
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
    caption: Optional[InstagramCaption] = None
    publish_data: Optional[PublishData] = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    collected_data: List[dict] = Field(default_factory=list) # 수집된 자료 저장
    # ★ 이미지 편집 단계 관련
    global_tone_adjustments: List[dict] = Field(default_factory=list)  # 전체 톤 조절 이력
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
