"""
이미지 편집 서비스 - Pillow 기반 톤 조절
- 채도, 밝기, 대비, 선명도 조절 (무료)
- 따뜻하게/차갑게 필터 (무료)
- 전체 이미지 일괄 적용
- 이미지 이력 관리 (되돌리기 지원)
"""
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import os
import shutil
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================
# Pillow로 무료 처리 가능한 톤 조절 키워드
# ============================================
PILLOW_ADJUSTABLE = {
    "채도": "saturation",
    "밝기": "brightness",
    "밝게": "brightness",
    "어둡게": "brightness_down",
    "대비": "contrast",
    "선명도": "sharpness",
    "선명하게": "sharpness",
    "부드럽게": "sharpness_down",
    "따뜻하게": "warm_filter",
    "따뜻한": "warm_filter",
    "차갑게": "cool_filter",
    "차가운": "cool_filter",
    "세피아": "sepia_filter",
    "흑백": "grayscale",
}


class ToneAdjuster:
    """이미지 톤 조절 (Pillow 기반, 무료)"""

    def adjust_saturation(self, image: Image.Image, factor: float = 1.3) -> Image.Image:
        """채도 조절 (1.0 = 원본, >1.0 = 채도 증가, <1.0 = 채도 감소)"""
        return ImageEnhance.Color(image).enhance(factor)

    def adjust_brightness(self, image: Image.Image, factor: float = 1.2) -> Image.Image:
        """밝기 조절 (1.0 = 원본, >1.0 = 밝게, <1.0 = 어둡게)"""
        return ImageEnhance.Brightness(image).enhance(factor)

    def adjust_contrast(self, image: Image.Image, factor: float = 1.3) -> Image.Image:
        """대비 조절 (1.0 = 원본, >1.0 = 대비 증가, <1.0 = 대비 감소)"""
        return ImageEnhance.Contrast(image).enhance(factor)

    def adjust_sharpness(self, image: Image.Image, factor: float = 1.5) -> Image.Image:
        """선명도 조절 (1.0 = 원본, >1.0 = 선명하게, <1.0 = 부드럽게)"""
        return ImageEnhance.Sharpness(image).enhance(factor)

    def apply_warm_filter(self, image: Image.Image, intensity: float = 1.15) -> Image.Image:
        """따뜻한 필터 (R↑, B↓)"""
        arr = np.array(image, dtype=np.float32)
        arr[:, :, 0] = np.clip(arr[:, :, 0] * intensity, 0, 255)  # R 증가
        arr[:, :, 2] = np.clip(arr[:, :, 2] / intensity, 0, 255)  # B 감소
        return Image.fromarray(arr.astype(np.uint8))

    def apply_cool_filter(self, image: Image.Image, intensity: float = 1.15) -> Image.Image:
        """차가운 필터 (B↑, R↓)"""
        arr = np.array(image, dtype=np.float32)
        arr[:, :, 2] = np.clip(arr[:, :, 2] * intensity, 0, 255)  # B 증가
        arr[:, :, 0] = np.clip(arr[:, :, 0] / intensity, 0, 255)  # R 감소
        return Image.fromarray(arr.astype(np.uint8))

    def apply_sepia_filter(self, image: Image.Image) -> Image.Image:
        """세피아 필터"""
        arr = np.array(image, dtype=np.float32)
        sepia_matrix = np.array([
            [0.393, 0.769, 0.189],
            [0.349, 0.686, 0.168],
            [0.272, 0.534, 0.131]
        ])
        sepia_img = arr[:, :, :3].dot(sepia_matrix.T)
        sepia_img = np.clip(sepia_img, 0, 255).astype(np.uint8)
        return Image.fromarray(sepia_img)

    def apply_grayscale(self, image: Image.Image) -> Image.Image:
        """흑백 변환"""
        return image.convert("L").convert("RGB")

    def apply_adjustment(self, image: Image.Image, effect: str, value: float = 1.0) -> Image.Image:
        """단일 효과 적용"""
        effect_map = {
            "saturation": lambda img, v: self.adjust_saturation(img, v),
            "brightness": lambda img, v: self.adjust_brightness(img, v),
            "brightness_down": lambda img, v: self.adjust_brightness(img, 1.0 / v if v > 0 else 0.8),
            "contrast": lambda img, v: self.adjust_contrast(img, v),
            "sharpness": lambda img, v: self.adjust_sharpness(img, v),
            "sharpness_down": lambda img, v: self.adjust_sharpness(img, 1.0 / v if v > 0 else 0.7),
            "warm_filter": lambda img, v: self.apply_warm_filter(img, v),
            "cool_filter": lambda img, v: self.apply_cool_filter(img, v),
            "sepia_filter": lambda img, _: self.apply_sepia_filter(img),
            "grayscale": lambda img, _: self.apply_grayscale(img),
        }

        handler = effect_map.get(effect)
        if handler:
            return handler(image, value)
        else:
            logger.warning(f"알 수 없는 효과: {effect}")
            return image

    def apply_batch(
        self,
        image_paths: list[str],
        adjustments: list[dict],
        output_dir: str
    ) -> list[str]:
        """
        여러 이미지에 동일한 조절 일괄 적용
        
        Args:
            image_paths: 이미지 파일 경로 목록
            adjustments: [{"effect": "saturation", "value": 1.3}, ...]
            output_dir: 결과 이미지 저장 디렉토리
            
        Returns:
            조절된 이미지 파일 경로 목록
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for path in image_paths:
            try:
                img = Image.open(path).convert("RGB")

                for adj in adjustments:
                    effect = adj.get("effect", "")
                    value = adj.get("value", 1.0)
                    img = self.apply_adjustment(img, effect, value)

                # 저장
                filename = os.path.basename(path)
                name, ext = os.path.splitext(filename)
                output_path = os.path.join(output_dir, f"{name}_edited{ext}")
                img.save(output_path, quality=95)
                results.append(output_path)
                logger.info(f"톤 조절 완료: {path} → {output_path}")

            except Exception as e:
                logger.error(f"톤 조절 실패 ({path}): {e}")
                results.append(path)  # 실패 시 원본 경로 유지

        return results


def parse_tone_command(user_command: str) -> Optional[dict]:
    """
    사용자 자연어 명령을 분석하여 Pillow 처리 가능 여부 판단
    
    Returns:
        {"type": "pillow", "effects": [{"effect": "saturation", "value": 1.3}]}
        또는 {"type": "ai_required", "message": "AI 재생성이 필요합니다"}
        또는 None (인식 불가)
    """
    command = user_command.strip().lower()

    matched_effects = []

    # 강도 키워드 파싱
    intensity = 1.3  # 기본 강도
    if "살짝" in command or "약간" in command or "조금" in command:
        intensity = 1.1
    elif "많이" in command or "강하게" in command or "확" in command:
        intensity = 1.5

    # 방향 키워드 파싱 (증가/감소)
    decrease = "낮" in command or "줄" in command or "덜" in command or "내" in command

    for keyword, effect in PILLOW_ADJUSTABLE.items():
        if keyword in command:
            value = intensity
            if decrease and effect in ("saturation", "brightness", "contrast", "sharpness"):
                value = 1.0 / intensity  # 감소 방향
            matched_effects.append({"effect": effect, "value": value})

    if matched_effects:
        return {
            "type": "pillow",
            "effects": matched_effects,
            "cost": 0,
            "message": f"✅ 무료로 적용 가능합니다 ({len(matched_effects)}개 효과)"
        }

    # AI 재생성이 필요한 키워드 감지
    ai_keywords = ["구도", "배경", "포즈", "표정", "스타일", "캐릭터", "추가", "제거", "바꿔"]
    for kw in ai_keywords:
        if kw in command:
            return {
                "type": "ai_required",
                "effects": [],
                "cost": -1,  # 비용 계산 필요
                "message": f"⚠️ AI 재생성이 필요합니다 ('{kw}' 변경은 이미지를 새로 생성해야 합니다)"
            }

    return None


class ImageHistoryManager:
    """이미지 이력 관리 (되돌리기 지원)"""

    def __init__(self, history_dir: str = "output/image_history"):
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)

    def save_to_history(self, image_path: str, session_id: str, scene_number: int) -> str:
        """현재 이미지를 이력에 저장하고 이력 경로 반환"""
        if not os.path.exists(image_path):
            return image_path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(self.history_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)

        ext = os.path.splitext(image_path)[1]
        history_path = os.path.join(session_dir, f"scene_{scene_number}_{timestamp}{ext}")
        shutil.copy2(image_path, history_path)

        logger.info(f"이미지 이력 저장: {image_path} → {history_path}")
        return history_path

    def restore_from_history(self, history_path: str, target_path: str) -> bool:
        """이력에서 이전 이미지 복원"""
        if not os.path.exists(history_path):
            logger.error(f"이력 파일 없음: {history_path}")
            return False

        shutil.copy2(history_path, target_path)
        logger.info(f"이미지 복원: {history_path} → {target_path}")
        return True


# 싱글톤 인스턴스
_tone_adjuster: Optional[ToneAdjuster] = None
_history_manager: Optional[ImageHistoryManager] = None


def get_tone_adjuster() -> ToneAdjuster:
    global _tone_adjuster
    if _tone_adjuster is None:
        _tone_adjuster = ToneAdjuster()
    return _tone_adjuster


def get_history_manager() -> ImageHistoryManager:
    global _history_manager
    if _history_manager is None:
        _history_manager = ImageHistoryManager()
    return _history_manager
