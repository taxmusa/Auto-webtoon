"""
설정 관리 - 환경변수 및 기본 설정
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, Tuple
from functools import lru_cache

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """환경 변수 기반 설정"""
    
    # 앱 정보
    app_name: str = "Tax Webtoon Auto-Generator"
    debug: bool = False
    
    # AI API 키
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    
    # 이미지 호스팅 - Cloudinary
    cloudinary_cloud_name: Optional[str] = Field(default=None, alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: Optional[str] = Field(default=None, alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: Optional[str] = Field(default=None, alias="CLOUDINARY_API_SECRET")
    
    # Instagram Graph API
    instagram_access_token: Optional[str] = Field(default=None, alias="INSTAGRAM_ACCESS_TOKEN")
    instagram_user_id: Optional[str] = Field(default=None, alias="INSTAGRAM_USER_ID")
    
    @field_validator("instagram_access_token", "instagram_user_id", mode="before")
    @classmethod
    def strip_instagram(cls, v):
        return v.strip() if v and isinstance(v, str) else v
    
    # 기본 설정
    default_ai_model: str = "gemini-3-flash-preview"
    default_image_model: str = "nano-banana-pro"
    max_scenes_per_series: int = 10
    
    # 폰트 경로
    fonts_dir: str = "fonts"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings()


def get_instagram_credentials() -> Tuple[str, str]:
    """.env에서 인스타 토큰/유저ID 직접 읽기 (캐시 없음). 설정 화면·발행 동일 소스로 env만 수정하면 반영."""
    token, user_id = "", ""
    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if key.strip() == "INSTAGRAM_ACCESS_TOKEN":
                    token = val
                elif key.strip() == "INSTAGRAM_USER_ID":
                    user_id = val
    return (token, user_id)


# 분야별 키워드 매핑
SPECIALIZED_FIELDS = {
    "세무": ["세금", "소득세", "부가세", "법인세", "종합소득", "원천징수", "세무사", "국세청", "절세", "연말정산"],
    "법률": ["법률", "소송", "계약", "변호사", "판례", "민법", "형법", "법적", "재판"],
    "노무": ["노동", "근로", "퇴직금", "4대보험", "노무사", "해고", "임금", "근로기준법", "연차"],
    "회계": ["회계", "재무제표", "분개", "결산", "감사", "회계사", "복식부기", "장부"],
    "부동산정책": ["부동산", "양도세", "취득세", "임대사업자", "분양", "청약", "전세", "월세"]
}

# 분야별 기본 해시태그
FIELD_HASHTAGS = {
    "세무": ["#세무사", "#세금", "#절세", "#세금정보", "#국세청", "#세무상담"],
    "법률": ["#변호사", "#법률상담", "#법률정보", "#계약서", "#법률팁"],
    "노무": ["#노무사", "#근로기준법", "#노동법", "#4대보험", "#노무상담"],
    "회계": ["#회계사", "#재무제표", "#회계정보", "#결산", "#회계팁"],
    "부동산정책": ["#부동산", "#부동산정책", "#양도세", "#취득세", "#부동산투자"]
}

# 캐릭터 설명 (이미지 생성용)
CHARACTER_DESCRIPTIONS = {
    "일반인": "young korean person, casual attire, friendly expression, confused or curious look",
    "사업자": "korean business owner in their 30s-40s, semi-formal attire, thoughtful expression",
    "직장인": "korean office worker in business casual, tired but attentive expression",
    "전문가": "korean professional in smart casual attire, confident and knowledgeable expression",
    "세무사": "middle-aged korean professional, glasses, neat suit, kind and knowledgeable appearance",
    "변호사": "korean lawyer in formal suit, confident and professional expression",
    "노무사": "korean labor consultant, smart casual attire, approachable expression",
    "회계사": "korean accountant, glasses, formal attire, detail-oriented appearance"
}

# 이미지 스타일 프롬프트
STYLE_PROMPTS = {
    "webtoon": "korean webtoon style, clean lines, vibrant colors, anime-inspired, expressive characters",
    "card_news": "modern infographic style, clean design, professional, flat design, corporate colors",
    "simple": "minimalist design, solid color background, simple and clean, modern"
}

SUB_STYLE_PROMPTS = {
    "normal": "",
    "ghibli": "studio ghibli inspired, soft colors, dreamy atmosphere, gentle lighting",
    "romance": "soft pastel colors, warm lighting, emotional, gentle atmosphere",
    "business": "professional, corporate style, clean, modern office setting"
}



# (LoRA 학습 설정은 제거됨 — 레퍼런스 이미지 기반 일관성으로 전환)
