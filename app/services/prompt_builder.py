"""
이미지 생성용 스타일 프롬프트 조립.
섹션 순서·FROZEN/LOCKED 규칙은 STYLE_CONSISTENCY_POLICY.md 를 준수한다.
"""
from app.models.models import Scene, CharacterProfile, CharacterStyle, BackgroundStyle, ManualPromptOverrides
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

    # 0. 사용자 오버라이드가 있으면 **가장 앞**에 최우선 지시로 삽입
    if additional_en:
        parts.append(f"""
[HIGHEST PRIORITY — USER OVERRIDE INSTRUCTION]
The following instruction takes absolute precedence over every other section below.
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

    # 4. Character Identity
    scene_char_names = [d.character for d in scene.dialogues]
    active_characters = [c for c in characters if c.name in scene_char_names]
    if not active_characters:
        active_characters = characters[:2]

    for i, char in enumerate(active_characters):
        position = "LEFT" if i == 0 else "RIGHT"
        identity = f"Name: {char.name}, Role: {char.role}, Appearance: {char.appearance or 'Professional look'}, Personality: {char.personality or 'Neutral'}"
        parts.append(f"""
[CHARACTER {i+1} IDENTITY - DO NOT MODIFY]
Position: {position}
{identity}
""")

    # 4.5 Character GUARD (정책 §8.2)
    if active_characters:
        parts.append("[GUARD] These character appearances are FROZEN. Do not alter hair, eyes, clothes, or proportions.\n")

    # 5. This Scene
    emotions = [d.emotion for d in scene.dialogues if d.emotion]
    dominant_emotion = emotions[0] if emotions else "neutral"

    parts.append(f"""
[THIS SCENE]
Scene: {scene.scene_description}
Expression: {dominant_emotion}
Narration: {scene.narration or 'None'}
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

    return "\n".join(parts)
