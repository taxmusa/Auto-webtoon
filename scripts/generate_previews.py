import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.image_generator import get_generator

load_dotenv()

async def generate_previews():
    styles_dir = "app_data/styles"
    
    # API Key 확인 및 모델 선택
    api_key = os.getenv("OPENAI_API_KEY")
    model = "gpt-image-1"
    
    if not api_key:
        print("OPENAI_API_KEY not found. Trying Google...")
        api_key = os.getenv("GOOGLE_API_KEY")
        model = "gemini-2.0-flash"
    
    if not api_key:
        print("Error: No API key found (OPENAI_API_KEY or GOOGLE_API_KEY required)")
        return

    print(f"Using model: {model}")
    
    # Generator 초기화
    # DALL-E 3는 OpenAI 라이브러리가 필요하므로 try-catch로 안전하게 처리
    try:
        generator = get_generator(model, api_key)
    except Exception as e:
        print(f"Failed to initialize generator: {e}")
        return

    for type_dir in ["character", "background"]:
        base_path = os.path.join(styles_dir, type_dir)
        if not os.path.exists(base_path):
            continue

        for style_id in os.listdir(base_path):
            style_path = os.path.join(base_path, style_id)
            meta_path = os.path.join(style_path, "meta.json")
            preview_path = os.path.join(style_path, "preview.png")

            # 이미지가 이미 존재하면 건너뜀
            if os.path.exists(preview_path):
                print(f"Skipping {style_id} (preview exists)")
                continue

            if not os.path.exists(meta_path):
                continue

            # 메타데이터 로드
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error reading {meta_path}: {e}")
                continue

            prompt = data.get("prompt_block", "")
            if not prompt:
                # 프롬프트가 없으면 설명 사용
                prompt = data.get("description", "")
                if not prompt:
                    print(f"Skipping {style_id} (no prompt/description)")
                    continue

            print(f"Generating preview for {style_id} ({data.get('name')})...")
            try:
                # 미리보기용 프롬프트 강화
                full_prompt = f"{prompt}, masterpiece, best quality, 8k resolution"
                
                if type_dir == "character":
                    full_prompt += ", solo character portrait, centered, white background, simple background"
                else:
                    full_prompt += ", wide shot, scenery, establishing shot"
                
                # 이미지 생성 (1024x1024)
                image_bytes = await generator.generate(full_prompt, aspect_ratio="4:5")
                
                # 저장
                with open(preview_path, "wb") as f:
                    f.write(image_bytes)
                print(f"Saved to {preview_path}")
                
            except Exception as e:
                print(f"Failed to generate {style_id}: {e}")

if __name__ == "__main__":
    asyncio.run(generate_previews())
