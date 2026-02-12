"""
이미지 생성용 스타일 프롬프트 조립.
섹션 순서·FROZEN/LOCKED 규칙은 STYLE_CONSISTENCY_POLICY.md 를 준수한다.
"""
from app.models.models import Scene, CharacterProfile, CharacterStyle, BackgroundStyle, ManualPromptOverrides, VisualIdentity
from typing import List, Optional

# ==========================================
# SUB_STYLES DEFINITION (정책: STYLE_CONSISTENCY_POLICY.md §5)
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

    # 단순 선화 스타일 10개 (배경 최소화 + 캐릭터 표정 중심)
    "wobbly_doodle": (
        "wobbly shaky hand-drawn lines, intentionally imperfect drawing, "
        "simple blob-like character shapes, minimal facial features with big expressive eyes, "
        "solid single color background, no background details, childlike naive art style, "
        "pen on paper feel, no shading, 2-3 colors only"
    ),
    "chunky_marker": (
        "thick marker pen drawing style, chunky bold strokes, slightly uneven ink edges, "
        "simple round character shapes, big dot eyes, small body, "
        "solid flat color background with no detail, felt-tip marker texture, "
        "limited palette 3-4 colors, casual and fun, no gradients no shadows"
    ),
    "circle_human": (
        "extremely minimalist circle head characters, body is simple lines or small rectangle, "
        "stick figure inspired but rounder and cuter, huge expressive circle eyes with dot pupils, "
        "tiny dot mouth, no nose, no ears, no hair detail, plain solid color background, "
        "black outlines only, maximum 2 colors, white characters on colored background"
    ),
    "4koma_gag": (
        "simple Japanese 4-koma comedy manga style, extremely exaggerated facial expressions, "
        "sweat drops and emotion marks, simple oval head characters, minimal body detail, "
        "plain white or single color background, black ink outlines, comedic timing focused, "
        "SD chibi proportions 1:2 head to body ratio, no detailed background"
    ),
    "ballpoint_diary": (
        "blue ballpoint pen drawing on white lined notebook paper, casual diary doodle style, "
        "simple character with round head, minimal features, slightly messy but charming lines, "
        "single blue ink color, notebook paper grid or lines visible in background, "
        "personal and intimate feel, no digital effects, raw sketch quality"
    ),
    "flat_face": (
        "large flat round face filling most of the frame, extremely close-up character face, "
        "oversized head with tiny or no body visible, simple dot eyes and small line mouth, "
        "exaggerated emotional expressions, solid pastel color background, "
        "thick clean black outlines, no background objects, face-focused composition, minimal detail maximum expression"
    ),
    "big_eyes": (
        "character with disproportionately large detailed expressive eyes, eyes take up 40 percent of face, "
        "small simple body, rest of face is minimal with tiny dot nose and simple line mouth, "
        "solid color background, black ink outlines, eyes have detailed pupils and reflections while everything else stays extremely simple, "
        "emotional storytelling through eyes only"
    ),
    "white_blob": (
        "simple white round blob character on solid muted blue or pastel background, "
        "character is white circle or oval shape with thick black outlines, large round eyes with black pupils, "
        "tiny dot nose, simple expressions, minimal body just small stubby arms, no legs or tiny feet, "
        "no background objects at all, clean and minimal Korean webtoon style, emoticon-like simplicity"
    ),
    "mspaint": (
        "intentionally crude MS Paint style digital drawing, slightly pixelated edges, "
        "basic geometric shapes for characters, flat primary colors with paint bucket fill, "
        "no anti-aliasing feel, simple mouse-drawn lines, retro computer art aesthetic, "
        "white or solid background, humorous low-fi quality, 90s internet art vibe"
    ),
    "one_stroke": (
        "continuous single line drawing style character, one unbroken flowing line creates the entire character, "
        "extremely minimalist, no fill colors, thin consistent black line on white or solid color background, "
        "abstract but recognizable human or creature form, artistic and elegant simplicity, "
        "contour drawing technique, no shading no detail, modern art inspired"
    ),
}

# ==========================================
# 한국어 → 영어 변환 (이미지 모델은 영어 프롬프트를 훨씬 정확하게 처리)
# ==========================================
_KO_EN_PHRASES = [
    # 배경 관련
    ("배경은 흰바탕으로만 없애서 처리하고", "Use a pure white (#FFFFFF) background only."),
    ("배경은 흰바탕으로만", "Use a pure white (#FFFFFF) background only."),
    ("흰바탕으로만", "pure white (#FFFFFF) background only"),
    ("흰 배경", "pure white (#FFFFFF) background"),
    ("흰바탕", "pure white (#FFFFFF) background"),
    ("배경 없이", "no background, transparent or white background"),
    ("배경을 없애", "remove all background, use plain white"),
    ("배경은 없애", "remove all background, use plain white"),
    ("배경 제거", "remove background completely"),
    ("단색 배경", "solid single-color background"),
    ("심플한 배경", "simple minimal background"),
    ("깔끔한 배경", "clean minimal background"),
    # 캐릭터 관련
    ("캐릭터만 남겨줘", "Show only the character with nothing else in the scene."),
    ("캐릭터만 남겨", "Show only the character."),
    ("캐릭터만", "character only, nothing else"),
    ("인물만 남겨", "show only the person/character"),
    ("인물만", "person/character only"),
    # 톤/색감
    ("밝게", "brighter"),
    ("어둡게", "darker"),
    ("따뜻하게", "warmer tones"),
    ("차갑게", "cooler tones"),
    ("채도 높게", "higher saturation"),
    ("채도 낮게", "lower saturation, more muted"),
    ("파스텔톤", "soft pastel color tones"),
    # 일반
    ("없애서 처리하고", "remove and"),
    ("처리하고", "and"),
    ("없애서", "remove"),
    ("없애줘", "remove it"),
    ("줘", ""),
]


def _translate_to_english(text: str) -> str:
    """
    추가 지시사항(한국어)을 영어 이미지 프롬프트로 변환.
    완벽한 번역이 아닌, 이미지 모델이 이해할 수 있는 수준의 키워드 치환.
    """
    if not text:
        return ""
    
    result = text.strip()
    
    # 전체 문장이 매칭되는 패턴 먼저 시도
    lower = result.lower().replace(" ", "")
    
    # 흔한 전체 문장 패턴
    _FULL_SENTENCE_MAP = {
        "배경은흰바탕으로만없애서처리하고,캐릭터만남겨줘":
            "Use a pure white (#FFFFFF) background only. Show only the character with no other elements.",
        "배경은흰바탕으로만없애서처리하고캐릭터만남겨줘":
            "Use a pure white (#FFFFFF) background only. Show only the character with no other elements.",
        "배경없이캐릭터만":
            "No background. Pure white (#FFFFFF). Show only the character.",
        "흰배경에캐릭터만":
            "Pure white (#FFFFFF) background. Show only the character.",
    }
    
    normalized = lower.replace(",", "").replace(".", "").replace(" ", "")
    if normalized in _FULL_SENTENCE_MAP:
        return _FULL_SENTENCE_MAP[normalized]
    
    # 구문 단위 치환 (긴 패턴 먼저)
    for ko, en in _KO_EN_PHRASES:
        if ko in result:
            result = result.replace(ko, en)
    
    # 남은 한국어가 있으면 원본도 병기 (안전장치)
    has_korean = any('\uac00' <= c <= '\ud7a3' for c in result)
    if has_korean:
        return f"{result}\n(Original instruction: {text})"
    
    return result


def build_styled_prompt(
    scene: Scene,
    characters: List[CharacterProfile],
    character_style: Optional[CharacterStyle] = None,
    background_style: Optional[BackgroundStyle] = None,
    manual_overrides: Optional[ManualPromptOverrides] = None,
    sub_style_name: Optional[str] = None
) -> str:
    """
    스타일 프리셋이 적용된 최종 프롬프트 구성 (Style System 2.0).
    섹션 순서·FROZEN/LOCKED 규칙: STYLE_CONSISTENCY_POLICY.md §2, §3, §4 준수.

    Structure (순서 변경 금지):
    1. [GLOBAL ART STYLE - DO NOT DEVIATE]
    2. [RENDERING STYLE / VISUAL PRESET]
    3. [BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]
    4. [CHARACTER N IDENTITY - DO NOT MODIFY]
    5. [THIS SCENE]
    6. [LOCKED ATTRIBUTES]
    7. [EXCLUSION]
    8. [USER MANUAL OVERRIDE] (optional)
    """
    
    parts = []

    # -----------------------------------------------------------
    # 추가 지시사항(additional_instructions)은 프롬프트 전체를 관통하는
    # 최우선 제약이므로, 먼저 추출해 두고 관련 섹션을 수정한다.
    # 한국어 → 영어 변환하여 이미지 모델이 정확히 이해하도록 함.
    # -----------------------------------------------------------
    additional = ""
    additional_en = ""
    if manual_overrides and manual_overrides.additional_instructions:
        additional = manual_overrides.additional_instructions.strip()
        additional_en = _translate_to_english(additional)

    # =====================================================
    # 0. ABSOLUTE CHARACTER CONSISTENCY — 프롬프트 최상단
    # 모든 씬의 캐릭터 외모를 완벽하게 동일하게 유지하는 대원칙
    # =====================================================
    # visual_identity 데이터 수집
    vi_blocks = []
    scene_char_names = [d.character for d in scene.dialogues]
    active_chars = [c for c in characters if c.name in scene_char_names]
    if not active_chars:
        active_chars = characters[:2]

    for char in active_chars:
        vi = char.visual_identity
        if vi:
            vi_blocks.append(f"""  [{char.name}]
  - Gender: {vi.gender or 'not specified'}
  - Age: {vi.age_range or 'not specified'}
  - Hair style: {vi.hair_style or 'not specified'}
  - Hair color: {vi.hair_color or 'not specified'}
  - Skin tone: {vi.skin_tone or 'not specified'}
  - Eye shape: {vi.eye_shape or 'not specified'}
  - Glasses: {vi.glasses or 'none'}
  - Outfit: {vi.outfit or 'not specified'}
  - Outfit colors: {vi.outfit_color or 'not specified'}
  - Accessories: {vi.accessories or 'none'}
  - Body type: {vi.body_type or 'average'}
  - Distinguishing features: {vi.distinguishing_features or 'none'}""")
        else:
            # visual_identity가 없으면 appearance에서 추출
            vi_blocks.append(f"""  [{char.name}]
  - Role: {char.role}
  - Appearance: {char.appearance or 'Professional look'}""")

    vi_section = "\n".join(vi_blocks)

    parts.append(f"""
[ABSOLUTE CHARACTER CONSISTENCY — HIGHEST PRIORITY]
This is a MULTI-PANEL comic. Every character MUST look EXACTLY IDENTICAL across ALL scenes.
The following character details are FROZEN and MUST NOT change between scenes:

{vi_section}

CRITICAL RULES:
1. If a character wears glasses → they MUST wear glasses in EVERY scene. If no glasses → NEVER add glasses.
2. Hair style, hair color, and hair length MUST be PIXEL-IDENTICAL across all scenes.
3. Skin tone MUST remain the EXACT SAME shade. Do not darken or lighten between scenes.
4. Outfit and outfit colors MUST be IDENTICAL. Same jacket, same shirt, same tie, same colors.
5. Accessories (watch, belt, bag strap, earrings) MUST be consistent. If present → always present. If absent → always absent.
6. Body proportions and height relationship between characters MUST stay constant.
7. Facial features (eye shape, nose, mouth, jawline) MUST NOT change between scenes.
[GUARD] Character consistency is MORE IMPORTANT than scene-specific details. When in doubt, prioritize consistency.
""")

    # 0.5 사용자 오버라이드가 있으면 상단에 삽입
    if additional_en:
        parts.append(f"""
[USER OVERRIDE INSTRUCTION]
The following instruction takes precedence over style sections below.
{additional_en}
""")

    # 1. Global Art Style (from Character Style or Manual Override)
    char_prompt = character_style.prompt_block if character_style else "Korean webtoon style, high quality"
    if manual_overrides:
        if manual_overrides.character_style_prompt:
            char_prompt = manual_overrides.character_style_prompt
        elif getattr(manual_overrides, "style_prompt", None):
            char_prompt = manual_overrides.style_prompt  # UI "스타일 프롬프트" 필드

    parts.append(f"""
[GLOBAL ART STYLE - DO NOT DEVIATE]
{char_prompt}
[GUARD] Maintain this exact art style consistently. Any deviation breaks visual coherence.
""")

    # 2. Sub Style / Rendering Style
    if sub_style_name and sub_style_name in SUB_STYLES:
        sub_prompt = SUB_STYLES[sub_style_name]
        parts.append(f"""
[RENDERING STYLE / VISUAL PRESET]
{sub_prompt}
""")

    # 3. Background Style
    #    manual_overrides.background_style_prompt 우선 → background_style 객체 → 씬 자연 배경
    bg_prompt = ""
    if manual_overrides and manual_overrides.background_style_prompt:
        # 프론트에서 "배경 지우기" / "단색 배경" 등을 직접 프롬프트로 전달
        bg_prompt = manual_overrides.background_style_prompt
    elif background_style:
        bg_prompt = background_style.prompt_block
    else:
        # 배경 스타일 미지정 시: 씬 내용에 맞는 자연스러운 배경 (하드코딩 X)
        bg_prompt = "Background appropriate for the scene context. Keep it simple and consistent with the art style."

    if additional_en:
        # 배경 관련 키워드가 추가지시에 있으면 배경 섹션을 완전히 대체
        _bg_keywords = ["배경", "background", "흰", "white", "단색", "solid", "없", "remove", "plain",
                         "character only", "no background", "simple"]
        if any(kw in (additional + " " + additional_en).lower() for kw in _bg_keywords):
            bg_prompt = additional_en  # 영어 번역으로 완전 대체

    parts.append(f"""
[BACKGROUND STYLE - CONSISTENT ACROSS ALL SCENES]
{bg_prompt}
""")

    # 4. Character Identity (visual_identity 기반 강화)
    for i, char in enumerate(active_chars):
        position = "LEFT" if i == 0 else "RIGHT"
        vi = char.visual_identity
        
        if vi:
            identity_lines = f"""Name: {char.name}
  Role: {char.role}
  Position: {position}
  Gender: {vi.gender or 'not specified'} | Age: {vi.age_range or 'not specified'}
  Hair: {vi.hair_style or 'not specified'} ({vi.hair_color or 'not specified'})
  Skin tone: {vi.skin_tone or 'not specified'}
  Eyes: {vi.eye_shape or 'not specified'}
  Glasses: {vi.glasses or 'none'}
  Outfit: {vi.outfit or 'not specified'} — Colors: {vi.outfit_color or 'not specified'}
  Accessories: {vi.accessories or 'none'}
  Build: {vi.body_type or 'average'}
  Features: {vi.distinguishing_features or 'none'}"""
        else:
            identity_lines = f"""Name: {char.name}
  Role: {char.role}
  Position: {position}
  Appearance: {char.appearance or 'Professional look'}
  Personality: {char.personality or 'Neutral'}"""

        parts.append(f"""
[CHARACTER {i+1} IDENTITY — FROZEN, DO NOT MODIFY]
{identity_lines}
""")

    # 4.5 Character GUARD (정책 §8.2)
    if active_chars:
        parts.append("""[GUARD] These character appearances are ABSOLUTELY FROZEN across all scenes.
Do NOT alter: hair style, hair color, skin tone, glasses (presence/absence), outfit, outfit colors, accessories, body proportions.
If you are uncertain about any detail, refer back to the [ABSOLUTE CHARACTER CONSISTENCY] section above.
""")

    # 5. This Scene
    emotions = [d.emotion for d in scene.dialogues if d.emotion]
    dominant_emotion = emotions[0] if emotions else "neutral"

    parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {dominant_emotion}
Narration: {scene.narration or 'None'}
""")

    # 5.5 Composition & Layout (인스타툰 말풍선/나레이션 공간 확보)
    parts.append("""
[COMPOSITION & LAYOUT — MANDATORY]
This image is for an Instagram webtoon (insta-toon) where speech bubbles and narration text will be overlaid AFTER generation.
CRITICAL SPACING RULES:
- Leave EMPTY SPACE at the TOP: at least 25-30% of image height. This area MUST be blank or very simple background only.
- Leave EMPTY SPACE at the BOTTOM: at least 15-20% of image height for narration text.
- Characters should occupy only 40-55% of the VERTICAL space, positioned in the LOWER-CENTER of the frame.
- Use a MEDIUM SHOT or MEDIUM-WIDE SHOT. Show characters from waist-up or full body. NEVER use close-up shots that fill the frame.
- Do NOT let any character's head touch the top 25% of the image. Keep heads in the middle zone.
- Maintain generous BREATHING ROOM on LEFT and RIGHT sides (at least 10% each) for side text.
- Background areas must be CLEAN and UNCLUTTERED so text overlay remains readable.
[GUARD] Composition spacing is NON-NEGOTIABLE. Top 25% must be empty. Do NOT fill the frame with characters.
""")

    # 6. Locked Attributes (정책 §4: STYLE / BACKGROUND 접두어)
    locked = "\n[LOCKED ATTRIBUTES]\n"
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

    # 8. 사용자 오버라이드 리마인더 (맨 끝에도 다시 한 번 강조, 영어로)
    if additional_en:
        parts.append(f"""
[REMINDER — APPLY USER OVERRIDE ABOVE ALL ELSE]
{additional_en}
""")

    # 9. FINAL CONSISTENCY REMINDER — 프롬프트 맨 끝
    # AI 모델은 프롬프트의 처음과 끝을 가장 강하게 따르므로, 일관성 규칙을 마지막에 다시 반복
    char_names = [c.name for c in active_chars]
    parts.append(f"""
[FINAL REMINDER — CHARACTER CONSISTENCY CHECK]
Before generating this image, verify:
✓ Each character ({', '.join(char_names)}) matches their FROZEN appearance exactly
✓ Glasses: present/absent matches the character spec (do NOT randomly add or remove)
✓ Hair style and color: IDENTICAL to spec
✓ Skin tone: IDENTICAL to spec
✓ Outfit and colors: IDENTICAL to spec
✓ Accessories: IDENTICAL to spec
✓ Top 25% of image is EMPTY for text overlay
✓ Characters positioned in lower-center, not filling the entire frame
""")

    return "\n".join(parts)


# ==========================================
# Flux Kontext 프롬프트 최적화
# ==========================================

def optimize_for_flux_kontext(full_prompt: str, scene_description: str = "", is_reference: bool = False) -> str:
    """Flux Kontext에 최적화된 프롬프트 생성

    Flux Kontext는:
    - 참조 이미지 기반이므로 캐릭터 외모 설명 최소화 가능
    - 짧고 명확한 프롬프트가 더 정확
    - 'maintain the character appearance from the reference image' 같은 지시가 핵심
    - 불필요한 네거티브/반복 제거
    """
    if not is_reference:
        # 첫 씬 (참조 없음): 풀 프롬프트 사용하되 약간 간결화
        lines = full_prompt.split("\n")
        # GUARD, REMINDER 같은 반복 지시 줄이기
        filtered = []
        skip_guards = 0
        for line in lines:
            if "[GUARD]" in line or "[REMINDER" in line or "[FINAL REMINDER" in line:
                skip_guards += 1
                if skip_guards <= 2:  # 최대 2개만 유지
                    filtered.append(line)
                continue
            filtered.append(line)
        return "\n".join(filtered)

    # 참조 이미지 있을 때: 간결한 프롬프트
    parts = []

    # 핵심 지시
    parts.append("Maintain the EXACT same character appearance from the reference image.")
    parts.append("Same face, hair, outfit, accessories, glasses, skin tone — pixel-identical.")

    # 아트 스타일 유지
    # full_prompt에서 [GLOBAL ART STYLE] 추출
    if "[GLOBAL ART STYLE" in full_prompt:
        style_start = full_prompt.index("[GLOBAL ART STYLE")
        style_end = full_prompt.index("\n[", style_start + 10) if "\n[" in full_prompt[style_start + 10:] else len(full_prompt)
        style_block = full_prompt[style_start:style_start + style_end - style_start]
        # 헤더 제거, 내용만
        style_lines = [l.strip() for l in style_block.split("\n") if l.strip() and not l.startswith("[")]
        if style_lines:
            parts.append("Art style: " + " ".join(style_lines[:2]))

    # 배경
    if "[BACKGROUND STYLE" in full_prompt:
        bg_start = full_prompt.index("[BACKGROUND STYLE")
        bg_end = full_prompt.index("\n[", bg_start + 10) if "\n[" in full_prompt[bg_start + 10:] else len(full_prompt)
        bg_block = full_prompt[bg_start:bg_start + bg_end - bg_start]
        bg_lines = [l.strip() for l in bg_block.split("\n") if l.strip() and not l.startswith("[")]
        if bg_lines:
            parts.append("Background: " + " ".join(bg_lines[:1]))

    # 이 씬의 내용
    if scene_description:
        parts.append(f"Scene: {scene_description}")

    # 레이아웃 지시 (간결)
    parts.append("Leave top 25% of image empty for text overlay. Characters in lower-center, medium shot.")

    # 텍스트 금지
    parts.append("No text, no speech bubbles, no letters in the image.")

    return "\n".join(parts)


def optimize_for_flux_lora(full_prompt: str, trigger_word: str = "") -> str:
    """Flux LoRA에 최적화된 프롬프트 생성

    LoRA는 트리거 워드로 캐릭터를 소환하므로:
    - 트리거 워드를 프롬프트 맨 앞에 배치
    - 캐릭터 외모 설명 축소 (LoRA가 학습함)
    - 씬/배경/구도에 집중
    """
    parts = []

    # 트리거 워드 최우선
    if trigger_word:
        parts.append(f"[trigger: {trigger_word}]")
        parts.append(f"A scene with {trigger_word}.")

    # 아트 스타일
    if "[GLOBAL ART STYLE" in full_prompt:
        style_start = full_prompt.index("[GLOBAL ART STYLE")
        style_end_idx = full_prompt.find("\n[", style_start + 10)
        style_end = style_end_idx if style_end_idx != -1 else style_start + 500
        style_block = full_prompt[style_start:style_end]
        style_lines = [l.strip() for l in style_block.split("\n") if l.strip() and not l.startswith("[")]
        if style_lines:
            parts.append("Style: " + " ".join(style_lines[:2]))

    # 씬 내용
    if "[THIS SCENE]" in full_prompt:
        scene_start = full_prompt.index("[THIS SCENE]")
        scene_end_idx = full_prompt.find("\n[", scene_start + 10)
        scene_end = scene_end_idx if scene_end_idx != -1 else scene_start + 500
        scene_block = full_prompt[scene_start:scene_end]
        scene_lines = [l.strip() for l in scene_block.split("\n") if l.strip() and not l.startswith("[")]
        if scene_lines:
            parts.append(" ".join(scene_lines))

    # 배경
    if "[BACKGROUND STYLE" in full_prompt:
        bg_start = full_prompt.index("[BACKGROUND STYLE")
        bg_end_idx = full_prompt.find("\n[", bg_start + 10)
        bg_end = bg_end_idx if bg_end_idx != -1 else bg_start + 300
        bg_block = full_prompt[bg_start:bg_end]
        bg_lines = [l.strip() for l in bg_block.split("\n") if l.strip() and not l.startswith("[")]
        if bg_lines:
            parts.append("Background: " + " ".join(bg_lines[:1]))

    # 레이아웃
    parts.append("Leave top 25% of image empty. Medium shot. Characters in lower-center.")
    parts.append("No text, no speech bubbles, no letters.")

    return "\n".join(parts)
