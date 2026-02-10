from app.models.models import Scene, CharacterProfile, CharacterStyle, BackgroundStyle, ManualPromptOverrides
from typing import List, Optional

def build_styled_prompt(
    scene: Scene,
    characters: List[CharacterProfile],
    character_style: Optional[CharacterStyle] = None,
    background_style: Optional[BackgroundStyle] = None,
    manual_overrides: Optional[ManualPromptOverrides] = None
) -> str:
    """
    스타일 프리셋이 적용된 최종 프롬프트 구성 (Style System 2.0)
    
    Structure:
    1. [GLOBAL ART STYLE] (Character Style Prompt)
    2. [BACKGROUND STYLE]
    3. [CHARACTER IDENTITY] (DNA)
    4. [THIS SCENE]
    5. [LOCKED ATTRIBUTES]
    6. [EXCLUSION]
    7. [USER MANUAL OVERRIDE]
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
    
    # 2. Background Style
    bg_prompt = background_style.prompt_block if background_style else "Modern office setting, bright lighting"
    if manual_overrides and manual_overrides.background_style_prompt:
        bg_prompt = manual_overrides.background_style_prompt
        
    parts.append(f"""
[BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]
{bg_prompt}
""")
    
    # 3. Character Identity
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

    # 4. This Scene
    # Extract emotion from dialogues
    emotions = [d.emotion for d in scene.dialogues if d.emotion]
    dominant_emotion = emotions[0] if emotions else "neutral"
    
    parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {dominant_emotion}
Narration: {scene.narration or 'None'}
""")
    
    # 5. Locked Attributes
    locked = "\n[LOCKED ATTRIBUTES]:\n"
    if character_style and character_style.locked_attributes:
        for attr in character_style.locked_attributes:
            locked += f"- STYLE: {attr}\n"
            
    if background_style and background_style.locked_attributes:
        for attr in background_style.locked_attributes:
            locked += f"- BACKGROUND: {attr}\n"
            
    parts.append(locked)
    
    # 6. Exclusion
    parts.append("""
[EXCLUSION]
DO NOT include any text, speech bubbles, letters, words, 
numbers, or typography in the image. The image must be 
completely free of any written content.
""")

    # 7. Additional Instructions
    if manual_overrides and manual_overrides.additional_instructions:
        parts.append(f"""
[USER MANUAL OVERRIDE]
{manual_overrides.additional_instructions}
""")
        
    return "\n".join(parts)
