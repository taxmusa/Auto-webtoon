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
    레퍼런스 일관성 시스템 기반 프롬프트 구성.
    3종 레퍼런스(Character/Method/Style)가 시각 스타일을 담당하므로
    프롬프트는 간결하게 핵심만 전달.

    Structure (5섹션):
    1. [STYLE] — 아트 스타일 + 캐릭터 외형 (프롬프트 최상단 = 가장 강한 가중치)
    2. [SCENE] — 이번 장면 시각 묘사
    3. [RULES] — 금지 사항
    4. [USER OVERRIDE] (optional)
    """

    parts = []

    # ── 사전 준비 ──
    additional_en = ""
    if manual_overrides and manual_overrides.additional_instructions:
        additional_en = _translate_to_english(
            manual_overrides.additional_instructions.strip()
        )

    # 스타일 프롬프트 결정
    char_prompt = (
        character_style.prompt_block if character_style
        else "Korean webtoon style, high quality, bright colors"
    )
    if manual_overrides:
        if manual_overrides.character_style_prompt:
            char_prompt = manual_overrides.character_style_prompt
        elif getattr(manual_overrides, "style_prompt", None):
            char_prompt = manual_overrides.style_prompt

    # 등장 캐릭터 결정
    scene_char_names = [d.character for d in scene.dialogues]
    active_chars = [c for c in characters if c.name in scene_char_names]
    if not active_chars:
        active_chars = characters[:2]

    # =====================================================
    # 1. [STYLE] — 아트 스타일 + 캐릭터 외형 (최상단)
    # =====================================================
    char_lines = []
    for char in active_chars:
        vi = char.visual_identity
        if vi:
            glasses_val = (vi.glasses or "").strip().lower()
            if not glasses_val or glasses_val in ("none", "no glasses", "none (no glasses)"):
                glasses_txt = "NO glasses"
            else:
                glasses_txt = vi.glasses

            char_lines.append(
                f"- {char.name}: {vi.gender or '?'}, "
                f"{vi.hair_color or '?'} {vi.hair_style or '?'}, "
                f"{vi.skin_tone or '?'} skin, "
                f"glasses={glasses_txt}, "
                f"outfit={vi.outfit or '?'} ({vi.outfit_color or '?'})"
            )
        else:
            char_lines.append(
                f"- {char.name}: {char.role}, {char.appearance or 'Professional look'}"
            )

    chars_block = "\n".join(char_lines)

    parts.append(f"""[STYLE]
{char_prompt}
Follow the attached reference images for art style, character appearance, and composition.

Characters (keep IDENTICAL across all scenes):
{chars_block}
Do NOT change hair, skin, outfit, or glasses between scenes.
""")

    # =====================================================
    # 2. [SCENE] — 이번 장면 시각 묘사
    # =====================================================
    emotions = [d.emotion for d in scene.dialogues if d.emotion]
    dominant_emotion = emotions[0] if emotions else "neutral"

    _scene_visual = ""
    if hasattr(scene, 'image_prompt') and scene.image_prompt:
        _scene_visual = _clean_scene_desc(scene.image_prompt)
    else:
        _scene_visual = _clean_scene_desc(scene.scene_description or "")

    parts.append(f"""[SCENE]
{_scene_visual}
Expression: {dominant_emotion}
""")

    # =====================================================
    # 3. [RULES] — 금지 사항 (간결하게)
    # =====================================================
    parts.append("""[RULES]
- Generate a SINGLE scene illustration. Do NOT split into multiple panels or comic grid.
- No text, letters, numbers, logos, watermarks, UI elements in the image.
- No speech bubbles or dialogue boxes.
- Show characters fully — do not crop heads or bodies out of frame.
- Use medium or medium-wide shot. Do not use extreme close-ups.
""")

    # =====================================================
    # 4. [USER OVERRIDE] (있을 때만)
    # =====================================================
    if additional_en:
        parts.append(f"""[USER OVERRIDE]
{additional_en}
""")

    return "\n".join(parts)


# ==========================================
# Flux Kontext 프롬프트 최적화
# ==========================================

def _extract_section(full_prompt: str, section_name: str) -> str:
    """프롬프트에서 특정 섹션의 핵심 내용만 추출 (메타/지시문 제외, 순수 내용만)
    
    ★ 필터링 규칙:
    - [헤더], CRITICAL, GUARD, FROZEN, DO NOT, MUST, VERIFY 등 지시문 제거
    - "This is", "The following" 같은 메타 설명 제거
    - 순수 스타일/내용 설명만 추출
    """
    if section_name not in full_prompt:
        return ""
    start = full_prompt.index(section_name)
    header_end = full_prompt.find("\n", start)
    if header_end == -1:
        return ""
    rest = full_prompt[header_end + 1:]
    end_idx = rest.find("\n[")
    block = rest[:end_idx] if end_idx != -1 else rest[:500]
    
    # 지시문·메타 키워드 필터
    _SKIP_KEYWORDS = {
        "CRITICAL", "GUARD", "DO NOT", "FROZEN", "MUST", "VERIFY", "LOCKED",
        "ABSOLUTE", "HIGHEST PRIORITY", "NON-NEGOTIABLE", "This is a MULTI",
        "The following", "Before generating", "If a character", "If you are",
        "maintain this", "consistency is", "Any deviation",
        "✓", "- If", "check:", "rules:", "MANDATORY",
    }
    
    lines = []
    for l in block.split("\n"):
        stripped = l.strip()
        if not stripped:
            continue
        if stripped.startswith("[") or stripped.startswith("-"):
            continue
        # 지시문 키워드 포함 줄 스킵
        upper = stripped.upper()
        if any(kw.upper() in upper for kw in _SKIP_KEYWORDS):
            continue
        lines.append(stripped)
    
    return " ".join(lines[:3])


def _build_character_anchor(characters, active_chars=None) -> str:
    """캐릭터 외모의 핵심 속성만 초단문으로 추출 (Flux용)
    
    ★ 보안 설계: 안경은 명시적으로 2회 언급 (Flux가 높은 확률로 무시하므로)
    예: "Minsu: dark brown short hair, fair skin, no glasses, beige sweater"
    """
    anchors = []
    chars = active_chars or characters[:2]
    for char in chars:
        vi = char.visual_identity
        if not vi:
            continue
        parts = []
        # 머리 (가장 중요한 시각 속성)
        if vi.hair_color and vi.hair_style:
            parts.append(f"{vi.hair_color} {vi.hair_style}")
        elif vi.hair_style:
            parts.append(vi.hair_style)
        # 성별/나이 (화풍에 영향)
        if vi.gender:
            parts.append(vi.gender)
        # 피부
        if vi.skin_tone:
            parts.append(f"{vi.skin_tone} skin")
        # 안경 (★ 명시적 강조 — Flux가 무시하기 쉬움)
        glasses = (vi.glasses or "").strip().lower()
        if not glasses or glasses == "none" or "no glass" in glasses:
            parts.append("without glasses")
            parts.append("bare eyes")  # 이중 강조
        else:
            parts.append(glasses)
        # 옷 (핵심만)
        if vi.outfit:
            outfit_short = vi.outfit[:50].strip()
            parts.append(outfit_short)
        
        if parts:
            anchors.append(f"{char.name}: {', '.join(parts)}")
    
    return "; ".join(anchors)


# 모든 Flux 프롬프트에 포함되는 절대 금지 (간결하지만 강력)
_FLUX_ANTI_TEXT_PREFIX = (
    "No text, no speech bubbles, no words, no letters, "
    "no logos, no watermarks, no writing, no symbols, no marks, no icons. "
    "Pure illustration only. "
)

# 마스터 규칙 import (씬 설명 정제)
from app.services.prompt_rules import clean_scene_description as _clean_scene_desc

# 레이아웃 지시 (간결)
_FLUX_LAYOUT_SUFFIX = (
    "Leave top 25% of image empty for text overlay. "
    "Characters in lower-center, medium shot, not filling the frame. "
)


def build_character_reference_prompt(
    characters,
    character_style=None,
    sub_style_name: str = "",
) -> str:
    """캐릭터 레퍼런스 시트(CRS) 생성용 프롬프트
    
    목적: 씬 생성 전에 "깨끗한 배경 + 정면 포즈" 캐릭터 기준 이미지를 만든다.
    이 이미지를 모든 씬이 참조 → 일관된 캐릭터 외모 + 균일한 품질.
    
    ★ 핵심 원칙:
    1. 흰색 배경 (씬 배경이 복사되지 않도록!)
    2. 정면 상반신 (캐릭터 얼굴/옷 정보 최대화)
    3. 아트 스타일 적용 (모든 씬과 동일한 화풍)
    4. 텍스트/로고 절대 금지
    """
    parts = []
    
    # ── 1. 아트 스타일 ──
    style_prompt = ""
    if sub_style_name and sub_style_name in SUB_STYLES:
        style_prompt = SUB_STYLES[sub_style_name]
    elif character_style and hasattr(character_style, 'prompt_block'):
        style_prompt = character_style.prompt_block
    elif isinstance(character_style, str) and character_style:
        style_prompt = character_style
    
    if style_prompt:
        parts.append(f"Art style: {style_prompt}.")
    
    # ── 2. 캐릭터 외모 (상세하게) ──
    char_descs = []
    for char in (characters or [])[:3]:  # 최대 3명
        vi = char.visual_identity
        if not vi:
            continue
        desc_parts = [char.name]
        if vi.gender:
            desc_parts.append(vi.gender)
        if vi.hair_color and vi.hair_style:
            desc_parts.append(f"{vi.hair_color} {vi.hair_style}")
        elif vi.hair_style:
            desc_parts.append(vi.hair_style)
        if vi.skin_tone:
            desc_parts.append(f"{vi.skin_tone} skin")
        glasses = (vi.glasses or "").strip().lower()
        if not glasses or glasses == "none" or "no glass" in glasses:
            desc_parts.append("without glasses, bare eyes")
        else:
            desc_parts.append(glasses)
        if vi.outfit:
            desc_parts.append(vi.outfit[:60])
        char_descs.append(", ".join(desc_parts))
    
    if char_descs:
        parts.append(f"Character reference sheet: {'; '.join(char_descs)}.")
    else:
        parts.append("Character reference sheet.")
    
    # ── 3. 포즈/구도 지정 ──
    parts.append(
        "Front-facing upper body portrait, neutral relaxed pose, "
        "standing straight, looking at camera, centered composition."
    )
    
    # ── 4. 배경 = 흰색 단색 (씬 배경 복사 방지!) ──
    parts.append(
        "Pure white (#FFFFFF) background only. "
        "No background objects, no scenery, no furniture."
    )
    
    # ── 5. 금지사항 ──
    parts.append(
        "No text, no speech bubbles, no words, no letters, "
        "no logos, no watermarks, no writing, no symbols. "
        "No glasses unless specified. Pure illustration only."
    )
    
    return " ".join(parts)


def optimize_for_flux_kontext(full_prompt: str, scene_description: str = "", 
                               is_reference: bool = False,
                               characters=None) -> str:
    """Flux에 최적화된 프롬프트 생성
    
    ★ 핵심 설계 원칙 (CRS 참조 방식 v4):
    
    [text2img 모드 - CRS 없을 때 폴백]:
      1. 아트 스타일 → 맨 앞 (스타일 확립)
      2. 씬 설명 (캐릭터+장면 확립)
      3. 캐릭터 앵커
    
    [img2img 모드 - 모든 씬 (CRS 참조)]:
      1. ★ 씬 설명이 최우선! (CRS가 캐릭터를 유지하니까)
      2. 아트 스타일
      3. 캐릭터 외모 유지 지시 (간결하게)
      → 프롬프트 = "무엇을 그릴 것인가" 에 집중
    """
    parts = []
    
    # ★ 씬 설명 정제 — 대사/텍스트/숫자 제거 (마스터 규칙)
    scene_description = _clean_scene_desc(scene_description) if scene_description else ""
    
    # 공통: 아트 스타일 추출
    style_text = _extract_section(full_prompt, "[GLOBAL ART STYLE")
    sub_text = _extract_section(full_prompt, "[RENDERING STYLE")
    bg_text = _extract_section(full_prompt, "[BACKGROUND STYLE")
    char_anchor = _build_character_anchor(characters) if characters else ""
    
    # ── 배경 일관성 강제 ──
    _DEFAULT_BG = "Clean, well-lit modern indoor room background with neutral warm tones"
    effective_bg = bg_text if bg_text else _DEFAULT_BG
    
    if is_reference:
        # ═══════════════════════════════════════════
        # IMG2IMG 모드 (모든 씬, CRS 참조):
        # CRS가 캐릭터 외모를 유지하므로,
        # 프롬프트는 "이번 씬에서 무엇이 일어나는가"에 집중
        # ═══════════════════════════════════════════
        
        # ── 1. 씬 설명 = 프롬프트 최상단 (가장 중요!) ──
        if scene_description:
            parts.append(f"NEW SCENE: {scene_description[:300]}.")
        
        # ── 2. 장면 변경 강제 지시 ──
        parts.append(
            "Draw a COMPLETELY DIFFERENT scene from the reference image. "
            "MUST CHANGE: pose, body position, camera angle, background, scene composition. "
            "The reference is ONLY for character face and outfit — ignore everything else."
        )
        
        # ── 3. 아트 스타일 (간결하게) ──
        if style_text:
            parts.append(f"Style: {style_text[:150]}.")
        
        # ── 4. 캐릭터 외모 유지 (CRS 기반, 간결하게) ──
        parts.append(
            "Keep character appearances from reference: same face, hair, skin, outfit."
        )
        
        # ── 5. 배경 일관성 ──
        parts.append(f"Background: {effective_bg}.")
        
        # ── 6. 금지사항 ──
        parts.append("No text, no speech bubbles, no logos.")
        
    else:
        # ═══════════════════════════════════════════
        # TEXT2IMG 모드 (씬 1): 기준 캐릭터 + 스타일 확립
        # ═══════════════════════════════════════════
        
        # ── 1. 아트 스타일 (맨 앞, 전체 길이) ──
        if style_text:
            parts.append(f"Art style: {style_text}.")
        
        if sub_text:
            parts.append(sub_text[:150])
        
        # ── 2. 씬 설명 ──
        if scene_description:
            parts.append(f"Scene: {scene_description[:250]}.")
        
        # ── 3. 텍스트/로고 금지 ──
        parts.append("No text, no speech bubbles, no logos, no watermarks. Pure illustration.")
        
        # ── 4. 캐릭터 앵커 ──
        if char_anchor:
            parts.append(f"Characters: {char_anchor}.")
        
        # ── 5. 배경 (일관성 강제) ──
        parts.append(f"Background: {effective_bg[:80]}.")
    
    # 공통: 레이아웃
    parts.append(_FLUX_LAYOUT_SUFFIX)
    parts.append("No glasses unless specified.")
    
    return " ".join(parts)


# (optimize_for_flux_lora 함수 제거됨 — LoRA 기능 삭제)


# ==========================================
# 씬 체이닝 유틸리티
# ==========================================

def build_scene_chaining_context(
    scenes: list,
    current_scene_number: int,
) -> tuple:
    """이전 씬들의 텍스트 요약을 수집
    
    Returns:
        (prev_summaries: List[str], prev_scene_number: int or None)
        prev_summaries: 이전 씬들의 요약 텍스트 리스트
        prev_scene_number: 직전 씬 번호 (이미지 로딩용)
    """
    prev_summaries = []
    prev_scene_number = None

    if current_scene_number <= 1:
        return prev_summaries, prev_scene_number

    for scene in scenes:
        sn = scene.scene_number if hasattr(scene, 'scene_number') else scene.get('scene_number', 0)
        if sn < current_scene_number:
            # 일관성 강화: title + image_prompt 둘 다 포함 (잘라내지 않음)
            title = (scene.scene_description if hasattr(scene, 'scene_description')
                     else scene.get('scene_description', '')) or ''
            image_prompt = (scene.image_prompt if hasattr(scene, 'image_prompt')
                           else scene.get('image_prompt', '')) or ''
            if image_prompt:
                prev_summaries.append(f"- 장면 {sn}: {title} / {image_prompt}")
            else:
                prev_summaries.append(f"- 장면 {sn}: {title}")

    prev_scene_number = current_scene_number - 1
    return prev_summaries, prev_scene_number


def build_reference_prompt_instructions(
    has_character: bool = False,
    has_method: bool = False,
    has_style: bool = False,
) -> str:
    """3종 레퍼런스 존재 여부에 따른 프롬프트 지시문 생성 (Flux용 텍스트 지시)"""
    if not any([has_character, has_method, has_style]):
        return ""

    instructions = []
    if has_character:
        instructions.append("Maintain character appearances exactly as shown in the character reference image.")
    if has_method:
        instructions.append("Follow the composition, camera angles, and framing style from the method reference.")
    if has_style:
        instructions.append("Apply the exact art style, color palette, and atmosphere from the style reference image.")

    return "\n".join(instructions)
