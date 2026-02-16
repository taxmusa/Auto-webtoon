# -*- coding: utf-8 -*-
"""SmartTranslator — 한→영 프롬프트 번역기 (사전 + 캐시 + AI 3단계)

번역 우선순위:
  1. 캐시 히트 → 비용 0, 즉시 반환
  2. 로컬 사전(prompt_dictionary.json) → 비용 0, 단어/구문 치환
  3. Gemini AI → 사전으로 미번역된 부분만 AI 호출 (429 재시도 포함)

캐시는 자동 누적되어 동일 입력은 다시 AI를 호출하지 않음.
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 경로 설정 ────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DICT_PATH = _DATA_DIR / "prompt_dictionary.json"
_CACHE_PATH = _DATA_DIR / "translation_cache.json"


class SmartTranslator:
    """한국어 이미지 프롬프트를 영어로 번역하는 3단계 번역기."""

    _instance: Optional["SmartTranslator"] = None
    _lock = threading.Lock()

    # ── 싱글턴 ───────────────────────────────────────────
    @classmethod
    def get_instance(cls) -> "SmartTranslator":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.dictionary: dict = {}      # 카테고리별 한→영 사전
        self.flat_dict: list = []       # (한국어, 영어) 긴 것부터 정렬
        self.cache: dict = {}           # 번역 캐시
        self._cache_dirty = False
        self._load_dictionary()
        self._load_cache()

    # ── 데이터 로드 ──────────────────────────────────────
    def _load_dictionary(self):
        """prompt_dictionary.json 로드 → 3개 리스트로 분리 구성.
        
        - long_dict: 2글자 이상 항목 (안전한 치환)
        - short_words: 1글자 단어 (밤, 방, 집, 산 등 — 단어 경계 체크 후 치환)
        - particles: 1글자 조사 (을, 를, 이, 가 등 — 영어 뒤에서만 치환)
        """
        try:
            if _DICT_PATH.exists():
                with open(_DICT_PATH, "r", encoding="utf-8") as f:
                    self.dictionary = json.load(f)
                
                self.long_dict = []     # 2글자 이상
                self.short_words = []   # 1글자 단어 (조사 아닌 것)
                self.particle_dict = [] # 조사접속사 카테고리의 1글자
                
                for category, entries in self.dictionary.items():
                    is_particle_cat = (category == "조사접속사")
                    for ko, en in entries.items():
                        if len(ko) >= 2:
                            self.long_dict.append((ko, en))
                        elif is_particle_cat:
                            self.particle_dict.append((ko, en))
                        else:
                            self.short_words.append((ko, en))
                
                # 긴 것부터 정렬 (겹침 방지)
                self.long_dict.sort(key=lambda x: len(x[0]), reverse=True)
                
                # flat_dict는 전체 합본 (호환성)
                self.flat_dict = self.long_dict + self.short_words + self.particle_dict
                
                total = len(self.long_dict) + len(self.short_words) + len(self.particle_dict)
                logger.info("[SmartTranslator] 사전 로드 완료: %d개 (긴단어 %d, 짧은단어 %d, 조사 %d)", 
                           total, len(self.long_dict), len(self.short_words), len(self.particle_dict))
            else:
                logger.warning("[SmartTranslator] 사전 파일 없음: %s", _DICT_PATH)
                self.long_dict = []
                self.short_words = []
                self.particle_dict = []
        except Exception as e:
            logger.error("[SmartTranslator] 사전 로드 실패: %s", e)
            self.long_dict = []
            self.short_words = []
            self.particle_dict = []

    def _load_cache(self):
        """translation_cache.json 로드."""
        try:
            if _CACHE_PATH.exists():
                with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info("[SmartTranslator] 캐시 로드 완료: %d개 항목", len(self.cache))
            else:
                self.cache = {}
        except Exception as e:
            logger.warning("[SmartTranslator] 캐시 로드 실패: %s", e)
            self.cache = {}

    def _save_cache(self):
        """캐시를 파일에 저장 (변경 시에만)."""
        if not self._cache_dirty:
            return
        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            self._cache_dirty = False
            logger.info("[SmartTranslator] 캐시 저장 완료 (%d개 항목)", len(self.cache))
        except Exception as e:
            logger.warning("[SmartTranslator] 캐시 저장 실패: %s", e)

    # ── 한국어 감지 ──────────────────────────────────────
    @staticmethod
    def _has_korean(text: str) -> bool:
        return bool(re.search(r'[\uac00-\ud7af\u3131-\u3163]', text))

    @staticmethod
    def _korean_ratio(text: str) -> float:
        """텍스트 내 한국어 문자 비율 (0.0~1.0)."""
        if not text:
            return 0.0
        korean_chars = len(re.findall(r'[\uac00-\ud7af\u3131-\u3163]', text))
        total_chars = len(text.replace(" ", ""))
        return korean_chars / max(total_chars, 1)

    # ── 메인 번역 ────────────────────────────────────────
    def translate(self, korean_prompt: str) -> str:
        """한국어 프롬프트를 영어로 번역. 3단계 파이프라인.
        
        Args:
            korean_prompt: 한국어가 포함된 프롬프트 텍스트
            
        Returns:
            영어로 번역된 프롬프트 텍스트
        """
        if not korean_prompt or not korean_prompt.strip():
            return korean_prompt

        prompt = korean_prompt.strip()

        # 이미 영어만이면 그대로 반환
        if not self._has_korean(prompt):
            return prompt

        # ── 1단계: 캐시 히트 (비용 0) ────────────────────
        cache_key = prompt
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            logger.info("[SmartTranslator] 캐시 히트: '%s' → '%s'", prompt[:30], cached[:50])
            return cached

        # ── 2단계: 사전 치환 (비용 0) ────────────────────
        dict_result = self._dict_translate(prompt)
        korean_ratio = self._korean_ratio(dict_result)

        if korean_ratio < 0.05:
            # 95% 이상 번역됨 → 사전만으로 충분
            cleaned = self._clean_english(dict_result)
            self._cache_set(cache_key, cleaned)
            logger.info("[SmartTranslator] 사전 번역 완료 (잔여 한국어 %.0f%%): %s", 
                       korean_ratio * 100, cleaned[:60])
            return cleaned

        # ── 3단계: AI 번역 (미번역 부분만) ────────────────
        ai_result = self._ai_translate(prompt)
        if ai_result:
            self._cache_set(cache_key, ai_result)
            logger.info("[SmartTranslator] AI 번역 완료: %s", ai_result[:60])
            return ai_result

        # AI 실패 시 → 사전 결과에서 잔여 한국어 제거 후 반환
        fallback = self._remove_korean(dict_result)
        if len(fallback.strip()) < 15:
            fallback = "korean webtoon style, clean illustration. " + fallback
        self._cache_set(cache_key, fallback)
        logger.info("[SmartTranslator] 사전+폴백 번역: %s", fallback[:60])
        return fallback

    def translate_batch(self, texts: list[str]) -> list[str]:
        """여러 텍스트를 한 번에 번역 (Gemini 호출 최소화).
        
        캐시/사전으로 해결되는 것은 즉시 반환하고,
        미번역된 것만 모아서 한 번에 AI 호출.
        """
        results = [""] * len(texts)
        need_ai = {}  # index → korean_text

        for i, text in enumerate(texts):
            if not text or not self._has_korean(text):
                results[i] = text or ""
                continue

            # 캐시 히트
            if text.strip() in self.cache:
                results[i] = self.cache[text.strip()]
                continue

            # 사전 번역 시도
            dict_result = self._dict_translate(text)
            if self._korean_ratio(dict_result) < 0.05:
                cleaned = self._clean_english(dict_result)
                self._cache_set(text.strip(), cleaned)
                results[i] = cleaned
                continue

            # AI 필요
            need_ai[i] = text.strip()

        if not need_ai:
            return results

        # AI 일괄 번역
        ai_results = self._ai_translate_batch(need_ai)
        for idx, translated in ai_results.items():
            results[idx] = translated
            self._cache_set(need_ai[idx], translated)

        # AI 실패한 항목은 사전 폴백
        for idx, original in need_ai.items():
            if not results[idx]:
                fallback = self._remove_korean(self._dict_translate(original))
                if len(fallback.strip()) < 15:
                    fallback = "korean webtoon style illustration. " + fallback
                results[idx] = fallback
                self._cache_set(original, fallback)

        return results

    # ── 사전 번역 ────────────────────────────────────────
    def _dict_translate(self, text: str) -> str:
        """로컬 사전으로 단어/구문 치환. 3단계 분리 처리.
        
        1단계: 2글자 이상 단어/구문 치환 (안전)
        2단계: 1글자 단어(밤, 방, 집 등) 치환 (앞뒤가 공백/구두점일 때만)
        3단계: 1글자 조사(을, 를, 이 등) 치환 (영어 뒤에 올 때만)
        """
        result = text
        
        # ── 1단계: 2글자 이상 키워드 치환 (안전) ──────────
        for ko, en in self.long_dict:
            if ko in result:
                replacement = f" {en} " if en else " "
                result = result.replace(ko, replacement)
        
        result = re.sub(r'\s+', ' ', result).strip()
        
        # ── 2단계: 1글자 단어 치환 (단어 경계 체크) ──────
        # "밤" → "nighttime" 같은 실제 의미 단어
        # 한국어 단어 내부(예: "밤나무")에서는 치환하지 않음
        for ko, en in self.short_words:
            if ko in result:
                # 앞뒤가 공백, 문장부호, 영어, 또는 시작/끝일 때만 치환
                pattern = r'(?<![가-힣])' + re.escape(ko) + r'(?![가-힣])'
                replacement = f" {en} " if en else " "
                result = re.sub(pattern, replacement, result)
        
        result = re.sub(r'\s+', ' ', result).strip()
        
        # ── 3단계: 1글자 조사 치환 (영어 뒤에서만) ──────
        # "coffee를" → "coffee", "girl와" → "girl and"
        for ko, en in self.particle_dict:
            if ko in result:
                replacement = f" {en} " if en else " "
                # 영어/숫자/공백/구두점 바로 뒤의 조사만 치환
                result = re.sub(
                    r'(?<=[a-zA-Z0-9\s,.)}\]\-])' + re.escape(ko),
                    replacement,
                    result
                )
        
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    # ── AI 번역 (단건) ───────────────────────────────────
    def _ai_translate(self, text: str) -> Optional[str]:
        """Gemini AI로 번역 (429 재시도 포함)."""
        try:
            from google import genai as _genai

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
            if not api_key:
                logger.warning("[SmartTranslator] Gemini API 키 없음")
                return None

            client = _genai.Client(api_key=api_key)

            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=self._build_translation_prompt(text)
                    )
                    translated = response.text.strip()
                    # 따옴표 제거
                    if translated.startswith('"') and translated.endswith('"'):
                        translated = translated[1:-1]
                    if translated.startswith("'") and translated.endswith("'"):
                        translated = translated[1:-1]
                    if translated and len(translated) > 5:
                        return translated
                except Exception as retry_err:
                    if "429" in str(retry_err) and attempt < max_retries:
                        wait = 3 * (attempt + 1)
                        logger.warning("[SmartTranslator] Gemini 429, %d초 대기 (%d/%d)",
                                     wait, attempt + 1, max_retries)
                        time.sleep(wait)
                    else:
                        raise retry_err
        except Exception as e:
            logger.warning("[SmartTranslator] AI 번역 실패: %s", e)
        return None

    # ── AI 번역 (일괄) ───────────────────────────────────
    def _ai_translate_batch(self, items: dict[int, str]) -> dict[int, str]:
        """여러 텍스트를 하나의 Gemini 호출로 일괄 번역."""
        results = {}
        try:
            from google import genai as _genai

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
            if not api_key:
                return results

            client = _genai.Client(api_key=api_key)

            # {index: text} → JSON 으로 구성
            batch_map = {str(idx): text for idx, text in items.items()}
            batch_json = json.dumps(batch_map, ensure_ascii=False)

            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=(
                        "You are a strict Korean-to-English LITERAL translator for AI image generation prompts.\n\n"
                        "CRITICAL RULES:\n"
                        "1. Translate LITERALLY. Do NOT interpret, rephrase, or be creative.\n"
                        "2. NEVER change subjects: 여성=woman, 남성=man, 소녀=girl, 소년=boy, 고양이=cat.\n"
                        "3. Keep ALL adjectives, locations, actions exactly as described.\n"
                        "4. Keep ALL English text UNCHANGED.\n"
                        "5. Do NOT add words not in the original (no 'cute', 'beautiful' unless present).\n"
                        "6. Output ONLY valid JSON with same keys. No markdown, no explanation.\n\n"
                        "EXAMPLES:\n"
                        '{"0": "밝은 카페에서 커피를 마시는 여성"} → {"0": "A woman drinking coffee in a bright cafe"}\n\n'
                        f"Translate:\n{batch_json}"
                        )
                    )
                    raw = response.text.strip()
                    # JSON 파싱
                    if raw.startswith("```"):
                        raw = re.sub(r'^```\w*\n?', '', raw)
                        raw = re.sub(r'\n?```$', '', raw)
                    parsed = json.loads(raw)
                    for k, v in parsed.items():
                        idx = int(k)
                        if idx in items and v and len(v) > 5:
                            results[idx] = v.strip()
                    return results
                except Exception as retry_err:
                    if "429" in str(retry_err) and attempt < max_retries:
                        wait = 3 * (attempt + 1)
                        logger.warning("[SmartTranslator] Gemini batch 429, %d초 대기", wait)
                        time.sleep(wait)
                    else:
                        logger.warning("[SmartTranslator] AI 일괄 번역 실패: %s", retry_err)
                        break
        except Exception as e:
            logger.warning("[SmartTranslator] AI batch 번역 실패: %s", e)
        return results

    # ── 번역 프롬프트 ────────────────────────────────────
    @staticmethod
    def _build_translation_prompt(text: str) -> str:
        return (
            "You are a strict Korean-to-English LITERAL translator for AI image generation prompts.\n\n"
            "CRITICAL RULES — VIOLATION = FAILURE:\n"
            "1. Translate LITERALLY word-by-word. Do NOT interpret, rephrase, or be creative.\n"
            "2. NEVER change the subject: 여성=woman, 남성=man, 소녀=girl, 소년=boy, 고양이=cat, 강아지=dog.\n"
            "3. Keep ALL adjectives: 밝은=bright, 어두운=dark, 따뜻한=warm, 화난=angry.\n"
            "4. Keep ALL locations: 카페=cafe, 사무실=office, 학교=school, 공원=park.\n"
            "5. Keep ALL actions: 마시는=drinking, 먹는=eating, 보고있는=looking at.\n"
            "6. Keep ALL English text UNCHANGED. Only translate Korean parts.\n"
            "7. Do NOT add words like 'cute', 'beautiful' unless they appear in the original.\n"
            "8. Output ONLY the translated text. No quotes, no explanation, no markdown.\n\n"
            "EXAMPLES:\n"
            "밝은 카페에서 커피를 마시는 여성 → A woman drinking coffee in a bright cafe\n"
            "화난 표정의 남성이 서류를 던지는 장면 → A scene of an angry man throwing documents\n"
            "어두운 방에서 울고 있는 소녀 → A girl crying in a dark room\n"
            "세무사 사무실에서 안경 쓴 남성이 서류를 보고 있는 장면 → A man wearing glasses looking at documents in a tax accountant office\n\n"
            f"Translate:\n{text}"
        )

    # ── 유틸리티 ─────────────────────────────────────────
    @staticmethod
    def _clean_english(text: str) -> str:
        """사전 치환 결과에서 문법적 정리."""
        result = text
        # 쉼표, 마침표 앞 공백 제거
        result = re.sub(r'\s+([,.])', r'\1', result)
        # 다중 공백 정리
        result = re.sub(r'\s+', ' ', result).strip()
        # 앞뒤 잔여 쉼표 제거
        result = result.strip(',').strip()
        return result

    @staticmethod
    def _remove_korean(text: str) -> str:
        """텍스트에서 한국어 문자만 공백으로 치환."""
        result = re.sub(r'[\uac00-\ud7af\u3131-\u3163\u3200-\u321f]+', ' ', text)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _cache_set(self, key: str, value: str):
        """캐시에 저장."""
        self.cache[key] = value
        self._cache_dirty = True
        self._save_cache()


# ── 모듈 레벨 편의 함수 ─────────────────────────────────
def translate_prompt(korean_prompt: str) -> str:
    """한국어 프롬프트를 영어로 번역 (싱글턴 사용)."""
    return SmartTranslator.get_instance().translate(korean_prompt)


def translate_prompts_batch(texts: list[str]) -> list[str]:
    """여러 프롬프트를 일괄 번역 (싱글턴 사용)."""
    return SmartTranslator.get_instance().translate_batch(texts)
