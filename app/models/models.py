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
    requires_legal_verification: bool = False
    data_collection_method: str = "general_search"


# ============================================
# 3. 스토리 관련 모델
# ============================================

class Dialogue(BaseModel):
    """캐릭터 대사"""
    character: str              # 캐릭터 이름 (예: "민지", "세무사")
    text: str                   # 대사 내용 (최대 20자 권장)
    emotion: Optional[str] = "neutral"  # 표정 (기쁨/걱정/설명/놀람/진지)


class Scene(BaseModel):
    """개별 씬"""
    scene_number: int
    scene_description: str      # 장면 설명 (배경, 상황)
    dialogues: List[Dialogue] = Field(default_factory=list)
    narration: Optional[str] = None  # 나레이션 (최대 30자 권장)
    status: str = "pending"     # pending | approved | needs_edit
    warnings: List[str] = Field(default_factory=list)


class Story(BaseModel):
    """전체 스토리"""
    title: str
    scenes: List[Scene] = Field(default_factory=list)
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


class GeneratedImage(BaseModel):
    """생성된 이미지"""
    scene_number: int
    prompt_used: str
    image_url: Optional[str] = None
    local_path: Optional[str] = None
    status: str = "pending"     # pending | generated | approved


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

class TextSettings(BaseModel):
    """텍스트 설정"""
    font_name: str = "NanumGothic"
    dialogue_font_size: int = 24
    narration_font_size: int = 20
    dialogue_placement: str = "bubble"  # bubble | subtitle


class CharacterSettings(BaseModel):
    """캐릭터 설정"""
    questioner_type: str = "일반인"     # 일반인 | 사업자 | 직장인
    expert_type: str = "세무사"         # 세무사 | 변호사 | 노무사 | 회계사
    auto_emotion: bool = True


class LayoutSettings(BaseModel):
    """레이아웃 설정"""
    aspect_ratio: str = "4:5"           # 1:1 | 4:5 | 9:16
    width: int = 1080
    height: int = 1350
    margin: int = 20
    page_number_position: str = "bottom_right"


class ImageSettings(BaseModel):
    """이미지 생성 설정"""
    style: ImageStyle = ImageStyle.WEBTOON
    sub_style: SubStyle = SubStyle.NORMAL
    use_mascot: bool = True
    model: str = "dall-e-3"


class OutputSettings(BaseModel):
    """출력 설정"""
    format: str = "individual"   # individual | grid_2x2 | horizontal | vertical
    file_type: str = "png"
    quality: int = 90
    watermark: Optional[str] = None


class ProjectSettings(BaseModel):
    """전체 프로젝트 설정"""
    text: TextSettings = Field(default_factory=TextSettings)
    character: CharacterSettings = Field(default_factory=CharacterSettings)
    layout: LayoutSettings = Field(default_factory=LayoutSettings)
    image: ImageSettings = Field(default_factory=ImageSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


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
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
