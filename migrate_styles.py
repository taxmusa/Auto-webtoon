
import os
import json
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

STYLE_BASE_DIR = "app_data/styles"
CHAR_STYLE_DIR = os.path.join(STYLE_BASE_DIR, "character")
BG_STYLE_DIR = os.path.join(STYLE_BASE_DIR, "background")

# 기본 제공 스타일 ID 목록 (여기에 포함되지 않으면 커스텀으로 간주)
DEFAULT_CHAR_STYLES = [
    "char_webtoon",
    "char_shonen",
    "char_bw_pen", 
    "char_chibi",
    "char_crayon",
    "char_flat_vector",
    "char_ghibli",
    "char_meme_doodle",
    "char_pixel_art",
    "char_retro_anime",
    "char_romance",
    
    # 혹시 모를 추가 기본 스타일
]

DEFAULT_BG_STYLES = [
    "bg_modern_office",
    "bg_fantasy_forest",
    "bg_school_classroom",
    "bg_cyberpunk_city",
    "bg_coffee_shop",
    # ... 필요한 경우 추가
]

def migrate_style_meta(style_dir, style_id, is_char=True):
    meta_path = os.path.join(style_dir, "meta.json")
    if not os.path.exists(meta_path):
        logger.warning(f"Skipping {style_id}: meta.json not found")
        return

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 이미 is_default 필드가 있고 올바르게 설정된 경우 스킵 (선택 사항)
        # 하지만 명시적으로 재설정하는 것이 안전함
        
        # 기본 스타일 여부 판단
        default_list = DEFAULT_CHAR_STYLES if is_char else DEFAULT_BG_STYLES
        is_default = style_id in default_list
        
        # 필드 업데이트
        data["is_default"] = is_default
        
        # 저장
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        type_str = "Character" if is_char else "Background"
        status_str = "DEFAULT" if is_default else "CUSTOM"
        logger.info(f"[{type_str}] {style_id} -> {status_str} (is_default={is_default})")
        
    except Exception as e:
        logger.error(f"Failed to migrate {style_id}: {e}")

def main():
    logger.info("Starting style data migration...")
    
    # 1. Character Styles
    if os.path.exists(CHAR_STYLE_DIR):
        for style_id in os.listdir(CHAR_STYLE_DIR):
            style_path = os.path.join(CHAR_STYLE_DIR, style_id)
            if os.path.isdir(style_path):
                migrate_style_meta(style_path, style_id, is_char=True)
    
    # 2. Background Styles
    if os.path.exists(BG_STYLE_DIR):
        for style_id in os.listdir(BG_STYLE_DIR):
            style_path = os.path.join(BG_STYLE_DIR, style_id)
            if os.path.isdir(style_path):
                migrate_style_meta(style_path, style_id, is_char=False)
                
    logger.info("Migration completed.")

if __name__ == "__main__":
    main()
