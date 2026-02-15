"""
OpenAI 서비스 - DALL-E 이미지 생성
"""
import logging
from openai import AsyncOpenAI
from typing import Optional
import httpx

from app.core.config import get_settings, STYLE_PROMPTS, SUB_STYLE_PROMPTS, CHARACTER_DESCRIPTIONS
from app.models.models import Scene, ImageStyle, SubStyle, GeneratedImage, LayoutSettings

logger = logging.getLogger(__name__)


class OpenAIService:
    """OpenAI DALL-E 이미지 생성 서비스"""
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
    
    def build_prompt(
        self,
        scene: Scene,
        style: ImageStyle = ImageStyle.WEBTOON,
        sub_style: SubStyle = SubStyle.NORMAL,
        questioner_type: str = "일반인",
        expert_type: str = "세무사",
        aspect_ratio: str = "4:5"
    ) -> str:
        """씬 정보를 바탕으로 이미지 생성 프롬프트 구성"""
        
        style_prompt = STYLE_PROMPTS.get(style.value, STYLE_PROMPTS["webtoon"])
        sub_style_prompt = SUB_STYLE_PROMPTS.get(sub_style.value, "")
        
        # 캐릭터 설명 구성
        characters_in_scene = []
        for dialogue in scene.dialogues:
            char_name = dialogue.character
            if char_name in CHARACTER_DESCRIPTIONS:
                characters_in_scene.append(f"- {char_name}: {CHARACTER_DESCRIPTIONS[char_name]}")
            elif char_name == "민지":
                characters_in_scene.append(f"- {char_name}: {CHARACTER_DESCRIPTIONS.get(questioner_type, CHARACTER_DESCRIPTIONS['일반인'])}")
            else:
                characters_in_scene.append(f"- {char_name}: {CHARACTER_DESCRIPTIONS.get(expert_type, CHARACTER_DESCRIPTIONS['세무사'])}")
        
        characters_desc = "\n".join(characters_in_scene) if characters_in_scene else "- Two Korean people talking"
        
        prompt = f"""{style_prompt}
{sub_style_prompt}

Scene: {scene.scene_description}

Characters:
{characters_desc}

Important rules:
- DO NOT include any text, speech bubbles, letters, words, or typography in the image
- The text will be added separately
- Focus on the characters and background only
- Aspect ratio: {aspect_ratio}
"""
        return prompt.strip()
    
    async def generate_image(
        self,
        scene: Scene,
        style: ImageStyle = ImageStyle.WEBTOON,
        sub_style: SubStyle = SubStyle.NORMAL,
        questioner_type: str = "일반인",
        expert_type: str = "세무사",
        aspect_ratio: str = "4:5",
        model: str = "dall-e-3"
    ) -> GeneratedImage:
        """DALL-E로 이미지 생성"""
        
        prompt = self.build_prompt(scene, style, sub_style, questioner_type, expert_type, aspect_ratio)
        
        # DALL-E 3 크기 매핑
        # 1:1 -> 1024x1024, 4:5 -> 1024x1024 (or 1024x1792), 9:16 -> 1024x1792
        size = "1024x1024"
        if aspect_ratio == "9:16":
            size = "1024x1792"
        elif aspect_ratio == "16:9":
            size = "1792x1024"
        
        if not self.client:
            return GeneratedImage(
                scene_number=scene.scene_number,
                prompt_used=prompt,
                status="error"
            )
        
        try:
            # 모델 매핑 및 Fallback
            api_model = model
            if model.startswith("gpt-image") or model.startswith("dall-e"):
                pass  # 지원 모델 — 그대로 사용
            else:
                # 지원하지 않는 모델명이 들어오면 DALL-E 3로 fallback
                logger.warning(f"[OpenAI] 미지원 모델 '{model}' → dall-e-3 으로 fallback")
                api_model = "dall-e-3"

            response = await self.client.images.generate(
                model=api_model,
                prompt=prompt,
                size=size,
                quality="standard",
                n=1
            )
            
            image_url = response.data[0].url
            
            return GeneratedImage(
                scene_number=scene.scene_number,
                prompt_used=prompt,
                image_url=image_url,
                status="generated"
            )
            
        except Exception as e:
            return GeneratedImage(
                scene_number=scene.scene_number,
                prompt_used=prompt,
                status="error"
            )
    
    async def generate_images_batch(
        self,
        scenes: list[Scene],
        style: ImageStyle = ImageStyle.WEBTOON,
        sub_style: SubStyle = SubStyle.NORMAL,
        aspect_ratio: str = "4:5",
        questioner_type: str = "일반인",
        expert_type: str = "세무사",
        model: str = "dall-e-3"
    ) -> list[GeneratedImage]:
        """여러 씬의 이미지를 순차 생성"""
        results = []
        for scene in scenes:
            result = await self.generate_image(
                scene, style, sub_style, questioner_type, expert_type, aspect_ratio, model
            )
            results.append(result)
        return results


# 싱글톤
_openai_service: Optional[OpenAIService] = None

def get_openai_service() -> OpenAIService:
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
    return _openai_service
