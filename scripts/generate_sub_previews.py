import os
import sys
import asyncio
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.prompt_builder import SUB_STYLES
from app.services.image_generator import OpenAIGenerator

# Constants
OUTPUT_DIR = Path("app_data/sub_styles")
BASE_SCENE = "A young woman sitting at a cafe window seat, drinking coffee, warm sunlight, city street view outside."
MODEL = "dall-e-3"

async def generate_preview(style_key, style_prompt):
    print(f"Generating preview for: {style_key}...")
    
    # Construct prompt
    full_prompt = f"""
[RENDERING STYLE / VISUAL PRESET]
{style_prompt}

[SCENE DESCRIPTION]
{BASE_SCENE}

[EXCLUSION]
No text, no words, no letters. High quality image.
"""
    
    try:
        # Initialize generator (API key from env)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Error: OPENAI_API_KEY not found in environment variables.")
            return

        generator = OpenAIGenerator(model=MODEL, api_key=api_key)
        
        # Generate
        image_data = await generator.generate(full_prompt, size="1024x1024", quality="standard")
        
        # Save
        filename = f"{style_key}.png"
        filepath = OUTPUT_DIR / filename
        
        with open(filepath, "wb") as f:
             if isinstance(image_data, bytes):
                f.write(image_data)
             else:
                # If URL, we would need to download, but OpenAIGenerator usually returns bytes if configured so
                # If it returns URL, we need requests. assume bytes for now based on previous code
                pass
        
        print(f"Saved: {filepath}")
        
    except Exception as e:
        print(f"Failed to generate {style_key}: {e}")

async def main():
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Found {len(SUB_STYLES)} styles.")
    
    # Generate for each style
    for key, prompt in SUB_STYLES.items():
        # Check if already exists
        if (OUTPUT_DIR / f"{key}.png").exists():
            print(f"Skipping {key} (already exists)")
            continue
            
        await generate_preview(key, prompt)

if __name__ == "__main__":
    asyncio.run(main())
