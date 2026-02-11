"""
단순 선화 스타일 10개의 preview.png 를 GPT 1 mini 로 생성하여 저장합니다.
실행: 프로젝트 루트에서 python scripts/generate_character_style_previews.py
"""
import os
import json
import asyncio
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.services.image_generator import get_generator

STYLE_DIR = "app_data/styles/character"
MODEL = "gpt-image-1-mini"

# 프리뷰 생성 대상 10개 스타일 (같은 이미지 쓰던 것들)
TARGET_IDS = [
    "char_wobbly_doodle",
    "char_chunky_marker",
    "char_circle_human",
    "char_4koma_gag",
    "char_ballpoint_diary",
    "char_flat_face",
    "char_big_eyes",
    "char_white_blob",
    "char_mspaint",
    "char_one_stroke",
]


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set in .env")
        return

    generator = get_generator(MODEL, api_key)
    print(f"Model: {MODEL}\n")

    for style_id in TARGET_IDS:
        style_path = os.path.join(STYLE_DIR, style_id)
        meta_path = os.path.join(style_path, "meta.json")
        preview_path = os.path.join(style_path, "preview.png")

        if not os.path.exists(meta_path):
            print(f"Skip {style_id}: meta.json not found")
            continue

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name", style_id)
        prompt_block = data.get("prompt_block", "")
        if not prompt_block:
            print(f"Skip {name}: no prompt_block")
            continue

        # 스타일마다 확 달라 보이도록: 스타일 이름 + 고유 특징 강조
        prompt = (
            f"Single character portrait showing exactly this style: \"{name}\". "
            f"{prompt_block}. "
            f"The image must look clearly like \"{name}\" and visually distinct from other cartoon styles. "
            f"Clean illustration, no text, no watermark."
        )
        print(f"Generating: {name} ({style_id})...")

        try:
            image_bytes = await generator.generate(
                prompt,
                size="1024x1024",
                quality="medium"
            )
            if isinstance(image_bytes, bytes):
                os.makedirs(style_path, exist_ok=True)
                with open(preview_path, "wb") as f:
                    f.write(image_bytes)
                print(f"  -> Saved {preview_path}")
            else:
                print(f"  -> Unexpected type: {type(image_bytes)}")
        except Exception as e:
            print(f"  -> Failed: {e}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
