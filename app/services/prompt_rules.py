"""
프롬프트 마스터 규칙 (Prompt Master Rules)
==========================================
모든 이미지 생성 경로(LoRA, 일반, 미리보기)에서 공통 적용되는 대원칙.

사용법:
    from app.services.prompt_rules import (
        MASTER_NEGATIVE, build_final_prompt, clean_scene_description,
        build_character_anchor
    )
"""

import re
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# 마스터 네거티브 프롬프트 — 절대 금지 사항
# fal.ai의 negative_prompt 파라미터로 전달
# ═══════════════════════════════════════════════════
MASTER_NEGATIVE = (
    "text, speech bubbles, dialogue boxes, captions, subtitles, "
    "writing, letters, words, numbers, digits, symbols, "
    "logos, watermarks, stamps, seals, signatures, labels, annotations, "
    "UI elements, signs, banners, titles, credits, "
    "blurry, low quality, distorted face, extra limbs, extra fingers, "
    "deformed hands, ugly, duplicate, morbid, mutilated, "
    "bad anatomy, bad proportions, disfigured, poorly drawn face, "
    "out of frame, cropped badly"
)


# ═══════════════════════════════════════════════════
# 마스터 포지티브 프롬프트 — 항상 포함되는 품질/일관성 지시
# ═══════════════════════════════════════════════════
MASTER_POSITIVE_PREFIX = (
    "no text, no speech bubbles, no writing, no logos, no watermarks, "
    "no words, no letters, no numbers, no captions"
)

MASTER_POSITIVE_SUFFIX = (
    "consistent character appearance throughout, "
    "same clothing colors and style in every scene, "
    "professional illustration, clean composition, "
    "clear focal point, high quality artwork, "
    "pure illustration only, absolutely no text or writing anywhere in the image"
)

# LoRA 전용 스타일 앵커 — LoRA 사용 시 추가
LORA_STYLE_ANCHOR = (
    "consistent art style, same drawing technique, "
    "uniform line weight, same color palette"
)


# ═══════════════════════════════════════════════════
# 씬 설명 정제 함수 — 대사/텍스트/숫자를 완전 제거
# ═══════════════════════════════════════════════════
def clean_scene_description(desc: str) -> str:
    """씬 설명에서 텍스트/대사/숫자를 제거하고 시각적 요소만 남김
    
    Args:
        desc: 원본 씬 설명 (영어 또는 한국어)
    
    Returns:
        정제된 씬 설명 (이미지에 텍스트가 렌더링되지 않도록)
    """
    if not desc:
        return ""
    
    cleaned = desc
    
    # 1. 따옴표로 감싼 대사 제거
    cleaned = re.sub(r'"[^"]*"', '', cleaned)
    cleaned = re.sub(r"'[^']*'", '', cleaned)
    cleaned = re.sub(r'\u201c[^\u201d]*\u201d', '', cleaned)  # "..." (유니코드)
    cleaned = re.sub(r'\u2018[^\u2019]*\u2019', '', cleaned)  # '...' (유니코드)
    
    # 2. 대사 동사 뒤의 내용 제거
    cleaned = re.sub(
        r'\b(says?|said|saying|tells?|told|telling|asks?|asked|asking|'
        r'explains?|explained|explaining|mentions?|mentioned|replies?|replied|'
        r'shouts?|shouted|whispers?|whispered|announces?|announced|'
        r'exclaims?|exclaimed|responds?|responded|talks?|talked)\b[^.,;]*[.,;]?',
        '', cleaned, flags=re.IGNORECASE
    )
    
    # 3. 텍스트/문서 관련 표현 제거
    cleaned = re.sub(
        r'\b(reads?|reading|writes?|writing|written|shows? text|'
        r'displays?|displayed|labeled|titled|signed|signing|'
        r'document|letter|note|message|email|contract|certificate|'
        r'paper|form|receipt|invoice|bill|report)\b[^.,;]*[.,;]?',
        '', cleaned, flags=re.IGNORECASE
    )
    
    # 4. 숫자/금액 표현 제거
    cleaned = re.sub(r'\$[\d,.]+', '', cleaned)
    cleaned = re.sub(r'[\d,.]+\s*(원|만원|억|달러|percent|%|세|살|년|월|일)', '', cleaned)
    cleaned = re.sub(r'\b\d{2,}\b', '', cleaned)  # 2자리 이상 숫자
    
    # 5. 한국어 대사 패턴 제거
    cleaned = re.sub(r'[가-힣]+\s*(이라고|라고|하고|라며|하며)\s*(말|대답|외침|속삭임)?', '', cleaned)
    
    # 6. 정리
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'^[,.\s]+|[,.\s]+$', '', cleaned).strip()
    
    # 너무 짧아지면 원본에서 핵심만 추출
    if len(cleaned) < 15:
        # 원본에서 시각적 키워드만 추출
        visual_keywords = extract_visual_keywords(desc)
        if visual_keywords:
            cleaned = visual_keywords
        else:
            cleaned = desc[:120]
    
    return cleaned


def extract_visual_keywords(desc: str) -> str:
    """설명에서 시각적으로 의미 있는 키워드만 추출"""
    # 시각적 요소 패턴
    visual_patterns = [
        r'\b(sitting|standing|walking|running|looking|smiling|crying|'
        r'holding|pointing|waving|hugging|shaking hands|'
        r'office|room|home|cafe|street|park|school|hospital|'
        r'desk|chair|table|computer|phone|window|door|'
        r'happy|sad|angry|worried|surprised|confused|excited|'
        r'young|old|man|woman|boy|girl|child|couple|family|'
        r'wearing|dressed|suit|casual|formal)\b[^.,;]*',
    ]
    
    keywords = []
    for pattern in visual_patterns:
        matches = re.findall(pattern, desc, re.IGNORECASE)
        keywords.extend(matches)
    
    return ", ".join(keywords[:8]) if keywords else ""


# ═══════════════════════════════════════════════════
# 캐릭터 앵커 프롬프트 생성
# ═══════════════════════════════════════════════════
def build_character_anchor(characters: list, scene_number: int = 1) -> str:
    """스토리 캐릭터 정보에서 일관된 외모 설명 생성
    
    모든 씬에 동일한 캐릭터 설명이 들어가서 외모 일관성 유지.
    """
    if not characters:
        return "single character, consistent appearance"
    
    # 주요 캐릭터 (최대 2명)
    main_chars = characters[:2]
    parts = []
    
    for char in main_chars:
        name = getattr(char, 'name', '') or ''
        desc = getattr(char, 'description', '') or getattr(char, 'appearance', '') or ''
        
        if desc:
            # 외모 설명에서 핵심만 추출
            parts.append(f"{name}: {desc[:80]}")
    
    if parts:
        anchor = ", ".join(parts)
    else:
        anchor = "consistent character appearance"
    
    # 캐릭터 수 명시
    if len(main_chars) == 1:
        anchor = f"single character, {anchor}"
    elif len(main_chars) == 2:
        anchor = f"two characters, {anchor}"
    
    return anchor


# ═══════════════════════════════════════════════════
# 최종 프롬프트 빌더 — 모든 경로에서 사용
# ═══════════════════════════════════════════════════
def build_final_prompt(
    scene_description: str,
    trigger_word: str = "",
    style_prompt: str = "",
    bg_prompt: str = "",
    character_anchor: str = "",
    is_lora: bool = False,
    extra_instructions: str = ""
) -> str:
    """모든 마스터 규칙이 적용된 최종 프롬프트 생성
    
    구조:
      [네거티브 접두사] + [트리거 워드] + [캐릭터 앵커] + 
      [정제된 씬 설명] + [스타일] + [배경] + [품질 접미사]
    """
    # 씬 설명 정제
    clean_desc = clean_scene_description(scene_description)
    
    parts = []
    
    # 1. 네거티브 접두사 (프롬프트 앞부분에 위치 — Flux가 앞부분을 강하게 따름)
    parts.append(MASTER_POSITIVE_PREFIX)
    
    # 2. 트리거 워드 (LoRA)
    if trigger_word:
        parts.append(trigger_word)
    
    # 3. 캐릭터 앵커 (외모 일관성)
    if character_anchor:
        parts.append(character_anchor)
    
    # 4. LoRA 스타일 앵커
    if is_lora:
        parts.append(LORA_STYLE_ANCHOR)
    
    # 5. 정제된 씬 설명 (핵심)
    if clean_desc:
        # 길이 제한 (너무 길면 LoRA 스타일이 약해짐)
        max_len = 150 if is_lora else 250
        if len(clean_desc) > max_len:
            clean_desc = clean_desc[:max_len]
        parts.append(clean_desc)
    
    # 6. 사용자 스타일 프롬프트
    if style_prompt:
        parts.append(style_prompt)
    
    # 7. 배경 스타일
    if bg_prompt:
        parts.append(bg_prompt)
    
    # 8. 추가 지시
    if extra_instructions:
        parts.append(extra_instructions)
    
    # 9. 품질 접미사 (프롬프트 뒷부분에도 — Flux가 뒷부분도 강하게 따름)
    parts.append(MASTER_POSITIVE_SUFFIX)
    
    prompt = ", ".join(p for p in parts if p and p.strip())
    
    logger.info(f"[PROMPT] 최종 프롬프트 ({len(prompt)}자): {prompt[:100]}...")
    
    return prompt


def get_negative_prompt() -> str:
    """negative_prompt 파라미터로 전달할 문자열 반환"""
    return MASTER_NEGATIVE
