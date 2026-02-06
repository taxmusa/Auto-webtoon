"""
Pillow 서비스 - 텍스트 오버레이
- 한글 폰트 렌더링
- 말풍선 그리기
- 페이지 번호/배지
"""
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple
import os
import httpx
from io import BytesIO

from app.core.config import get_settings
from app.models.models import Scene, Dialogue, TextSettings, LayoutSettings


class PillowService:
    """Pillow 텍스트 오버레이 서비스"""
    
    # 말풍선 스타일
    BUBBLE_STYLES = {
        "round": {
            "border_radius": 20,
            "padding": 15,
            "bg_color": (255, 255, 255, 230),
            "border_color": (0, 0, 0),
            "border_width": 2
        },
        "square": {
            "border_radius": 5,
            "padding": 12,
            "bg_color": (255, 255, 255, 230),
            "border_color": (0, 0, 0),
            "border_width": 2
        }
    }
    
    def __init__(self):
        settings = get_settings()
        self.fonts_dir = settings.fonts_dir
        self._font_cache = {}
    
    def _get_font(self, font_name: str, size: int) -> ImageFont.FreeTypeFont:
        """폰트 로드 (캐싱)"""
        cache_key = f"{font_name}_{size}"
        if cache_key not in self._font_cache:
            font_path = os.path.join(self.fonts_dir, f"{font_name}.ttf")
            if os.path.exists(font_path):
                self._font_cache[cache_key] = ImageFont.truetype(font_path, size)
            else:
                # 기본 폰트 사용
                self._font_cache[cache_key] = ImageFont.load_default()
        return self._font_cache[cache_key]
    
    async def load_image_from_url(self, url: str) -> Image.Image:
        """URL에서 이미지 로드"""
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return Image.open(BytesIO(response.content)).convert("RGBA")
    
    def load_image_from_path(self, path: str) -> Image.Image:
        """로컬 경로에서 이미지 로드"""
        return Image.open(path).convert("RGBA")
    
    def draw_rounded_rectangle(
        self,
        draw: ImageDraw.ImageDraw,
        xy: Tuple[int, int, int, int],
        radius: int,
        fill: Tuple[int, ...],
        outline: Tuple[int, ...] = None,
        width: int = 1
    ):
        """둥근 모서리 사각형 그리기"""
        x1, y1, x2, y2 = xy
        
        # 배경
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        
        # 모서리
        draw.pieslice([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=fill)
        draw.pieslice([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=fill)
        draw.pieslice([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=fill)
        draw.pieslice([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=fill)
        
        # 외곽선
        if outline:
            draw.arc([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=outline, width=width)
            draw.arc([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=outline, width=width)
            draw.arc([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=outline, width=width)
            draw.arc([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=outline, width=width)
            draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=width)
            draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=width)
            draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=width)
            draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=width)
    
    def draw_speech_bubble(
        self,
        image: Image.Image,
        text: str,
        position: Tuple[int, int],
        font: ImageFont.FreeTypeFont,
        style: str = "round",
        max_width: int = 300
    ) -> Image.Image:
        """말풍선 그리기"""
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        style_config = self.BUBBLE_STYLES.get(style, self.BUBBLE_STYLES["round"])
        padding = style_config["padding"]
        radius = style_config["border_radius"]
        
        # 텍스트 크기 계산
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 말풍선 좌표
        x, y = position
        bubble_width = min(text_width + padding * 2, max_width)
        bubble_height = text_height + padding * 2
        
        x1 = x
        y1 = y
        x2 = x + bubble_width
        y2 = y + bubble_height
        
        # 말풍선 그리기
        self.draw_rounded_rectangle(
            draw,
            (x1, y1, x2, y2),
            radius,
            style_config["bg_color"],
            style_config["border_color"],
            style_config["border_width"]
        )
        
        # 텍스트 그리기
        draw.text(
            (x + padding, y + padding),
            text,
            font=font,
            fill=(0, 0, 0)
        )
        
        return Image.alpha_composite(image, overlay)
    
    def add_subtitle(
        self,
        image: Image.Image,
        character: str,
        text: str,
        font: ImageFont.FreeTypeFont,
        position: str = "bottom"
    ) -> Image.Image:
        """하단 자막 스타일 추가"""
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        full_text = f"{character}: \"{text}\""
        
        # 자막 영역 (하단 20%)
        img_width, img_height = image.size
        subtitle_height = int(img_height * 0.15)
        y_pos = img_height - subtitle_height
        
        # 반투명 배경
        draw.rectangle(
            [0, y_pos, img_width, img_height],
            fill=(0, 0, 0, 180)
        )
        
        # 텍스트 중앙 정렬
        bbox = draw.textbbox((0, 0), full_text, font=font)
        text_width = bbox[2] - bbox[0]
        x_pos = (img_width - text_width) // 2
        text_y = y_pos + (subtitle_height - (bbox[3] - bbox[1])) // 2
        
        draw.text((x_pos, text_y), full_text, font=font, fill=(255, 255, 255))
        
        return Image.alpha_composite(image, overlay)
    
    def add_page_number(
        self,
        image: Image.Image,
        page_num: int,
        total_pages: int,
        position: str = "bottom_right"
    ) -> Image.Image:
        """페이지 번호 추가"""
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        text = f"{page_num}/{total_pages}"
        font = self._get_font("NanumGothic", 18)
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        img_width, img_height = image.size
        margin = 20
        
        if position == "bottom_right":
            x = img_width - text_width - margin
            y = img_height - text_height - margin
        elif position == "bottom_left":
            x = margin
            y = img_height - text_height - margin
        elif position == "top_right":
            x = img_width - text_width - margin
            y = margin
        else:  # top_left
            x = margin
            y = margin
        
        # 배경
        padding = 5
        draw.rectangle(
            [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
            fill=(0, 0, 0, 150)
        )
        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        
        return Image.alpha_composite(image, overlay)
    
    async def overlay_scene(
        self,
        image_url: str,
        scene: Scene,
        text_settings: TextSettings,
        page_num: int = 1,
        total_pages: int = 1
    ) -> Image.Image:
        """씬에 텍스트 오버레이 적용"""
        # 이미지 로드
        image = await self.load_image_from_url(image_url)
        
        font = self._get_font(text_settings.font_name, text_settings.dialogue_font_size)
        
        if text_settings.dialogue_placement == "bubble":
            # 말풍선 스타일
            img_width, img_height = image.size
            y_offset = int(img_height * 0.1)
            
            for i, dialogue in enumerate(scene.dialogues[:2]):  # 최대 2개
                x_pos = 50 if i == 0 else img_width - 350
                image = self.draw_speech_bubble(
                    image,
                    dialogue.text,
                    (x_pos, y_offset + i * 80),
                    font
                )
        else:
            # 자막 스타일
            if scene.dialogues:
                dialogue = scene.dialogues[0]
                image = self.add_subtitle(image, dialogue.character, dialogue.text, font)
        
        # 페이지 번호
        image = self.add_page_number(image, page_num, total_pages)
        
        return image
    
    def save_image(self, image: Image.Image, path: str, format: str = "PNG", quality: int = 90):
        """이미지 저장"""
        if format.upper() == "PNG":
            image.save(path, "PNG")
        else:
            # JPEG는 RGBA 지원 안함
            rgb_image = image.convert("RGB")
            rgb_image.save(path, "JPEG", quality=quality)


# 싱글톤
_pillow_service: Optional[PillowService] = None

def get_pillow_service() -> PillowService:
    global _pillow_service
    if _pillow_service is None:
        _pillow_service = PillowService()
    return _pillow_service
