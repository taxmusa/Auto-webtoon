import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path to allow imports
sys.path.append(os.getcwd())

from app.services.prompt_builder import PRESET_STYLES
from app.services.image_generator import get_generator

# Load environment variables
load_dotenv()

async def generate_thumbnails():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables.")
        return

    # Initialize Generator (gpt-image-1-mini -> mapped to dall-e-3 in generator)
    generator = get_generator("gpt-image-1-mini", api_key)
    
    output_dir = "app/static/img/presets"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Starting thumbnail generation for {len(PRESET_STYLES)} presets...")

    for style_id, style_data in PRESET_STYLES.items():
        if style_id == "none":
            continue

        print(f"Generating thumbnail for: {style_data['name']} ({style_id})")
        
        # Construct Prompt
        # Common subject to make thumbnails consistent
        base_subject = "A character standing in a typical setting, showcasing the art style."
        prompt = f"{base_subject} Style description: {style_data['prompt']}. Ensure the image clearly represents this specific art style. High quality, detailed."

        try:
            # Generate Image (1024x1024 for thumbnails)
            image_data = await generator.generate(prompt, quality="standard", aspect_ratio="4:5")
            
            # Save Image
            filename = f"{style_id}.png"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            print(f"Saved: {filepath}")

        except Exception as e:
            print(f"Failed to generate {style_id}: {e}")

    print("All thumbnails generated.")

if __name__ == "__main__":
    asyncio.run(generate_thumbnails())
