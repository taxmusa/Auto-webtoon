from app.models.models import Scene, CharacterProfile, CharacterStyle, BackgroundStyle, ManualPromptOverrides
from typing import List, Optional
# ==========================================
# SUB_STYLES DEFINITION
# ==========================================
SUB_STYLES = {
    # 기존 스타일
    "ghibli": "studio ghibli inspired, soft colors, dreamy atmosphere, detailed background, cell shading",
    "romance": "soft pastel colors, warm lighting, emotional, shoujo manga style, sparkling eyes, delicate lines",
    "business": "professional, corporate style, clean, flat design, infographic style, trustworthy",
    
    # 추가 10개 (인스타툰 프리셋)
    "round_lineart": (
        "simple round line drawing style, thick black outlines, "
        "minimal detail, cute rounded shapes, white or solid pastel background, "
        "no shading, flat colors only, chibi-like proportions with big head, "
        "hand-drawn feel, doodle aesthetic"
    ),

    "pastel_flat": (
        "flat illustration style, soft pastel color palette, "
        "no gradients, no shadows, clean vector-like shapes, "
        "simple facial features with dot eyes, minimal background, "
        "modern Korean illustration style, muted warm tones"
    ),

    "bold_cartoon": (
        "bold cartoon style, very thick black outlines 4-5px, "
        "bright saturated flat colors, exaggerated expressions, "
        "simple geometric shapes, pop art influence, "
        "no gradient, solid color fills, high contrast"
    ),

    "pencil_sketch": (
        "pencil sketch style, hand-drawn rough lines, "
        "grayscale with occasional single accent color, "
        "notebook paper texture, casual doodle feel, "
        "imperfect lines, crosshatch shading, minimal detail"
    ),

    "monoline": (
        "monoline illustration style, single consistent line weight, "
        "no fill colors, outline only, clean and minimal, "
        "white background, modern simple aesthetic, "
        "thin continuous lines, no shading"
    ),

    "watercolor_soft": (
        "soft watercolor illustration style, light color bleeding edges, "
        "pastel tones, gentle brush strokes, slightly transparent colors, "
        "white paper background showing through, dreamy and warm, "
        "simple character design with minimal facial features"
    ),

    "neon_pop": (
        "neon pop style illustration, dark navy or black background, "
        "bright neon accent colors pink cyan yellow, "
        "simple flat character design, glowing edges, "
        "bold minimal shapes, high visual contrast, modern and trendy"
    ),

    "emoji_icon": (
        "emoji-like simple icon style illustration, "
        "extremely simplified characters, circle heads, dot eyes, "
        "line mouth, no nose, stick-figure inspired but cute, "
        "solid bright background, 2-3 colors maximum per scene, "
        "Google emoji aesthetic, flat design"
    ),

    "retro_90s": (
        "1990s retro cartoon style, slightly grainy texture, "
        "warm vintage color palette with orange brown teal, "
        "rounded character shapes, simple dot eyes, "
        "nostalgic feel, VHS-era cartoon aesthetic, "
        "thick outlines, limited color palette 4-5 colors"
    ),

    "cutout_collage": (
        "paper cutout collage style illustration, "
        "torn paper edges, layered flat shapes, "
        "craft paper texture, handmade feel, "
        "simple character shapes from geometric cuts, "
        "warm earth tones with one bright accent color, "
        "scrapbook aesthetic, tactile and trendy"
    ),
}

def build_styled_prompt(
    scene: Scene,
    characters: List[CharacterProfile],
    character_style: Optional[CharacterStyle] = None,
    background_style: Optional[BackgroundStyle] = None,
    manual_overrides: Optional[ManualPromptOverrides] = None,
    sub_style_name: Optional[str] = None
) -> str:
    """
    스타일 프리셋이 적용된 최종 프롬프트 구성 (Style System 2.0)
    
    Structure:
    1. [GLOBAL ART STYLE]
    2. [SUB STYLE / RENDERING]  <-- Added
    3. [BACKGROUND STYLE]
    4. [CHARACTER IDENTITY]
    5. [THIS SCENE]
    6. [LOCKED ATTRIBUTES]
    7. [EXCLUSION]
    8. [USER MANUAL OVERRIDE]
    """
    
    parts = []
    
    # 1. Global Art Style (from Character Style or Manual Override)
    char_prompt = character_style.prompt_block if character_style else "Korean webtoon style, high quality"
    if manual_overrides and manual_overrides.character_style_prompt:
        char_prompt = manual_overrides.character_style_prompt
        
    parts.append(f"""
[GLOBAL ART STYLE - DO NOT DEVIATE]
{char_prompt}
""")

    # 2. Sub Style / Rendering Style (New)
    if sub_style_name and sub_style_name in SUB_STYLES:
        sub_prompt = SUB_STYLES[sub_style_name]
        parts.append(f"""
[RENDERING STYLE / VISUAL PRESET]
{sub_prompt}
""")
    
    # 3. Background Style
    bg_prompt = background_style.prompt_block if background_style else "Modern office setting, bright lighting"
    if manual_overrides and manual_overrides.background_style_prompt:
        bg_prompt = manual_overrides.background_style_prompt
        
    parts.append(f"""
[BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]
{bg_prompt}
""")
    
    # 4. Character Identity
    # Note: CharacterDNA logic is simplified here as we strictly follow the file 'STYLE_SYSTEM.md'.
    # Dealing with simple CharacterProfile from models.py for now.
    # Ideally should come from DNA templates if available.
    
    scene_char_names = [d.character for d in scene.dialogues]
    active_characters = [c for c in characters if c.name in scene_char_names]
    
    # If no dialogue characters found, use all (or first 2)
    if not active_characters:
        active_characters = characters[:2]
        
    for i, char in enumerate(active_characters):
        position = "LEFT" if i == 0 else "RIGHT"
        # Simple Identity Block construction since we don't have full DNA in CharacterProfile yet
        # If we had DNA, we would use it here.
        identity = f"Name: {char.name}, Role: {char.role}, Appearance: {char.appearance or 'Professional look'}, Personality: {char.personality or 'Neutral'}"
        
        parts.append(f"""
[CHARACTER {i+1} IDENTITY - DO NOT MODIFY]
Position: {position}
{identity}
""")

    # 5. This Scene
    # Extract emotion from dialogues
    emotions = [d.emotion for d in scene.dialogues if d.emotion]
    dominant_emotion = emotions[0] if emotions else "neutral"
    
    parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {dominant_emotion}
Narration: {scene.narration or 'None'}
""")
    
    # 6. Locked Attributes
    locked = "\n[LOCKED ATTRIBUTES]:\n"
    if character_style and character_style.locked_attributes:
        for attr in character_style.locked_attributes:
            locked += f"- STYLE: {attr}\n"
            
    if background_style and background_style.locked_attributes:
        for attr in background_style.locked_attributes:
            locked += f"- BACKGROUND: {attr}\n"
            
    parts.append(locked)
    
    # 7. Exclusion
    parts.append("""
[EXCLUSION]
DO NOT include any text, speech bubbles, letters, words, 
numbers, or typography in the image. The image must be 
completely free of any written content.
""")

    # 8. Additional Instructions
    if manual_overrides and manual_overrides.additional_instructions:
        parts.append(f"""
[USER MANUAL OVERRIDE]
{manual_overrides.additional_instructions}
""")
        
    return "\n".join(parts)
