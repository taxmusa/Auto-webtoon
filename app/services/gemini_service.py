"""
Gemini AI 서비스 - 텍스트 생성
- 분야 감지
- 스토리 생성
- 캡션 생성
"""
from google import genai
from google.genai import types
import asyncio
from typing import Optional
import json
import re

from app.core.config import get_settings, SPECIALIZED_FIELDS, FIELD_HASHTAGS
from app.models.models import (
    FieldInfo, SpecializedField, Story, Scene, Dialogue,
    InstagramCaption, CharacterSettings, CharacterProfile, RuleSettings
)


class GeminiService:
    """Gemini AI 서비스 — 신형 google.genai SDK 사용"""
    
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.gemini_api_key or ""
        self.client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=180_000)  # 180초 (밀리초 단위)
        ) if self._api_key else None
        self._default_model = "gemini-3-flash-preview"
        self.last_used_model: Optional[str] = None

    async def detect_field(self, keyword: str, model: str = "gemini-3-flash-preview") -> FieldInfo:
        """AI를 사용하여 키워드에서 분야, 기준 년도, 법정 검증 필요성 자동 감지 - 모델 fallback 지원"""
        import logging
        import datetime
        logger = logging.getLogger(__name__)
        current_year_str = str(datetime.datetime.now().year)
        
        # Fallback 모델 순서 정의
        FALLBACK_MODELS = {
            "gemini-3-pro-preview": ["gemini-3-flash-preview", "gemini-2.0-flash"],
            "gemini-3-flash-preview": ["gemini-2.0-flash"],
            "gemini-2.0-flash": []
        }
        
        models_to_try = [model] + FALLBACK_MODELS.get(model, ["gemini-2.0-flash"])
        
        prompt = f"""키워드 "{keyword}"를 분석하여 다음 정보를 JSON 형식으로 반환하세요.
        현재 시각은 {current_year_str}년입니다. 특별한 언급이 없으면 기준 년도는 {current_year_str}년으로 설정하세요.
        
        [분석 항목]
        1. field: 세무, 법률, 노무, 회계, 부동산정책, 의학, 금융, 교육, 기술, 일반 중 하나
           - 키워드의 핵심 주제를 기반으로 가장 적합한 분야를 선택하세요.
        2. target_year: 해당 키워드와 관련된 기준 년도 (예: 2025, 2026). 
           - 키워드에 년도가 명시되어 있으면 그 년도를 따르고, 없으면 현재 년도({current_year_str})를 기본값으로 합니다.
        3. requires_legal_verification: 정확한 법령/규정 확인이 필수적인지 여부 (true/false)
           - 법률, 세금, 의료 등 정확성이 중요한 분야는 true로 설정
        4. reason: 왜 그렇게 판단했는지에 대한 짧은 근거 (한국어)
        
        [예시]
        키워드: "건강한 식습관" -> field: "일반", target_year: "{current_year_str}"
        키워드: "주식 투자 입문" -> field: "금융", target_year: "{current_year_str}"
        키워드: "2025년 상속세 개정안" -> field: "세무", target_year: "2025"
        
        [출력 형식]
        {{
            "field": "분야",
            "target_year": "{current_year_str}",
            "requires_legal_verification": true,
            "reason": "한 두 문장 근거"
        }}"""

        for try_model in models_to_try:
            for attempt in range(1, 3):  # 모델당 최대 2회 시도
                try:
                    logger.info(f"[detect_field] 시도 중: {try_model} (attempt {attempt})")
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=try_model,
                            contents=prompt
                        ),
                        timeout=30
                    )
                    text = response.text
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        data = json.loads(match.group())
                    else:
                        raise ValueError("JSON not found in response")
                    
                    self.last_used_model = try_model
                    logger.info(f"[detect_field] 성공: {try_model}")
                    return FieldInfo(
                        field=SpecializedField(data.get("field", "일반")),
                        target_year=data.get("target_year", current_year_str),
                        requires_legal_verification=data.get("requires_legal_verification", False),
                        reason=data.get("reason"),
                        confidence_score=0.9
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"[detect_field] {try_model} 타임아웃 (attempt {attempt})")
                    if attempt < 2:
                        await asyncio.sleep(2)
                        continue
                except Exception as e:
                    err_str = str(e).lower()
                    is_transient = "504" in err_str or "503" in err_str or "unavailable" in err_str or "deadline" in err_str
                    logger.warning(f"[detect_field] {try_model} 실패 (attempt {attempt}): {e}")
                    if is_transient and attempt < 2:
                        await asyncio.sleep(3)
                        continue
                break  # 비일시적 에러 → 다음 모델로
        
        # 모든 모델 실패 시 기본값 반환 (에러가 아닌 기본값 → 자료 수집은 계속 진행)
        logger.error(f"[detect_field] 모든 모델 실패 → 기본값(일반) 반환")
        return FieldInfo(field=SpecializedField.GENERAL, target_year=current_year_str)

    @staticmethod
    def is_synopsis_keyword(keyword: str) -> bool:
        """스토리 시놉시스로 볼 입력인지 여부 (자료 수집/분야감지 생략용)"""
        k = (keyword or "").strip()
        if len(k) >= 80:
            return True
        synopsis_keywords = ("스토리", "씬", "장면", "인스타툰", "만들", "그리")
        return any(w in k for w in synopsis_keywords)

    async def collect_data(self, keyword: str, field_info: Optional[FieldInfo] = None, model: str = "gemini-3-flash-preview", expert_mode: bool = False) -> list:
        """주제와 관련된 상세 자료 수집 (1회 API 호출로 분야 판단 + 자료 수집 동시 수행)"""
        import logging
        logger = logging.getLogger(__name__)

        # 스토리 시놉시스 감지
        if self.is_synopsis_keyword(keyword):
            logger.info("[collect_data] 스토리 시놉시스로 판단하여 API 호출 없이 통과")
            return [{"title": "스토리 시놉시스", "content": keyword}]

        FALLBACK_MODELS = {
            "gemini-3-pro-preview": ["gemini-3-flash-preview", "gemini-2.0-flash"],
            "gemini-3-flash-preview": ["gemini-2.0-flash"],
            "gemini-2.0-flash": []
        }
        models_to_try = [model] + FALLBACK_MODELS.get(model, ["gemini-2.0-flash"])

        import datetime
        current_year_str = str(datetime.datetime.now().year)

        # 분야 힌트: field_info가 있으면 사용, 없으면 AI가 자동 판단
        field_hint = ""
        if field_info and field_info.field.value != "일반":
            field_hint = f"(참고: 이 키워드는 '{field_info.field.value}' 분야로 판단됨, 기준 년도: {field_info.target_year})"

        if expert_mode:
            prompt = f"""당신은 해당 분야의 최고 수준 전문가입니다.
키워드를 분석하여 해당 분야(세무/법률/노무/금융/의학/부동산 등)를 자동 판단하고, 그 분야 전문가 수준으로 작성하세요.
{field_hint}

키워드 "{keyword}"에 대해 전문가 수준의 상세 자료를 작성하세요.

[핵심 지침]
1. 기준 년도: {current_year_str}년 최신 정보 기준으로 작성하세요.
2. 키워드의 분야를 자동 판단하여 해당 분야 전문가처럼 작성하세요.
   - 세무: 세법 조항, 공제 금액, 세율, 신고 기한 등 정확한 숫자 기재
   - 법률: 법조문, 판례번호, 분쟁 사례 포함
   - 금융: 수익률, 위험도, 세제 혜택 비교
   - 기타: 구체적 수치, 사례, 근거 포함

[전문가 모드 요청 사항]
1. 제목과 상세 본문 내용을 포함하여 **8~12개**의 항목으로 정리하세요.
2. 각 항목의 본문은 **200자 이상** 상세하게 작성하세요.
3. 정확한 법령명/조항, 금액, 세율, 기한 등 **구체적 수치**를 반드시 포함하세요.
4. 일반인이 자주 놓치는 **실무 팁**이나 **주의사항**을 포함하세요.
5. 각 항목에 **source_hint**(근거 법령/출처 힌트)를 추가하세요.
6. SNS 콘텐츠(웹툰/카드뉴스)로 설명하기 좋은 정보 위주로 선정하세요.

[출력 형식 (JSON)]
[
    {{"title": "자료 제목1", "content": "상세 설명 내용 ({current_year_str}년 기준)...", "source_hint": "근거 법령 또는 출처 힌트"}},
    ...
]"""
        else:
            prompt = f"""키워드 "{keyword}"에 대해 SNS(인스타그램/블로그)용 콘텐츠 제작을 위한 상세 자료를 수집해 주세요.
{field_hint}

[핵심 지침]
1. 기준 년도: 무조건 최신 {current_year_str}년 (또는 그 이후) 정보를 기준으로 작성하세요.
   - 사용자가 특정 년도를 명시하지 않았다면, 자동으로 {current_year_str}년 개정 내용을 적용해야 합니다.
2. 분야 자동 판단: 키워드를 보고 해당 분야(세무/법률/노무/금융/의학/부동산/교육/기술/일반)를 자동 판단하여 전문 지식을 바탕으로 작성하세요.

[요청 사항]
1. 제목과 상세 본문 내용을 포함하여 5~8개의 항목으로 정리하세요.
2. 실제 법령, 개정안, 정확한 공제 금액 등 구체적인 수치를 반드시 포함하세요.
3. 인스타그램 카드뉴스나 웹툰으로 설명하기 좋은 정보 위주로 선정하세요.
4. "일반"적인 내용보다는 "전문적이고 실질적인 팁"을 포함하세요.

[출력 형식 (JSON)]
[
    {{"title": "자료 제목1", "content": "상세 설명 내용 ({current_year_str}년 기준)..."}},
    ...
]"""
        
        last_error = None
        for try_model in models_to_try:
            for attempt in range(1, 4):  # 모델당 최대 3회 시도
                try:
                    logger.info(f"[collect_data] 시도 중: {try_model} (attempt {attempt})")
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=try_model,
                            contents=prompt
                        ),
                        timeout=90
                    )
                    # JSON 파싱 (리스트 형태 추출)
                    match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    if match:
                        result = json.loads(match.group())
                        self.last_used_model = try_model
                        logger.info(f"[collect_data] 성공: {try_model} (attempt {attempt}), {len(result)}개 항목")
                        return result
                    else:
                        raise ValueError("JSON list not found in response")

                except asyncio.TimeoutError:
                    last_error = "Gemini API 응답 시간 초과 (90초)"
                    logger.warning(f"[collect_data] {try_model} 타임아웃 (attempt {attempt})")
                    if attempt < 3:
                        wait = 3 * attempt
                        logger.info(f"[collect_data] {wait}초 후 재시도")
                        await asyncio.sleep(wait)
                        continue
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    is_transient = any(k in err_str for k in ["504", "503", "unavailable", "deadline", "rate", "429", "quota", "resource_exhausted"])
                    logger.warning(f"[collect_data] {try_model} 실패 (attempt {attempt}): {e}")
                    if is_transient and attempt < 3:
                        wait = 5 * attempt
                        logger.info(f"[collect_data] 일시적 에러 → {wait}초 후 재시도")
                        await asyncio.sleep(wait)
                        continue
                break  # 비일시적 에러 → 다음 모델로

            if try_model != models_to_try[-1]:
                logger.info(f"[collect_data] 다음 모델로 전환: {models_to_try[models_to_try.index(try_model)+1]}")
        
        # 모든 모델 실패 → 예외 raise (엔드포인트에서 적절한 HTTP 코드로 처리)
        logger.error(f"[collect_data] 모든 모델·재시도 실패. 마지막 오류: {last_error}")
        raise RuntimeError(f"자료 수집 실패: {last_error}")

    @staticmethod
    def _build_character_names_prompt(
        character_names: str, 
        monologue_mode: bool = False, 
        monologue_character: str = "",
        characters_input: list = None
    ) -> str:
        """캐릭터 이름+역할 지정 프롬프트 생성 (구조적 입력 우선)"""
        
        ROLE_LABELS = {
            "expert": "전문가",
            "questioner": "질문자", 
            "helper": "조력자",
            "none": "일반 등장인물"
        }
        ROLE_INSTRUCTIONS = {
            "expert": "정보를 설명하고 답변합니다. 질문하지 않습니다. 전문적 내용을 쉽게 풀어서 설명하는 역할입니다.",
            "questioner": "궁금한 점을 짧게 묻고, 놀라거나 반응합니다. 직접 전문 내용을 설명하면 안 됩니다.",
            "helper": "보조적으로 정보를 추가하거나 상황을 진행합니다. 전문가를 보조하는 역할입니다.",
            "none": "특별한 역할 없이 자연스럽게 대화에 참여합니다. 스토리 흐름에 맞게 자유롭게 행동합니다."
        }
        
        # 구조적 입력이 있으면 우선 사용
        if characters_input and len(characters_input) > 0:
            valid_chars = [c for c in characters_input if c.get("name", "").strip()]
            if not valid_chars:
                return ""
            
            # 독백 모드: 사용자가 명시적으로 켠 경우만 (캐릭터 1명이어도 자동 독백 안 함)
            is_monologue = monologue_mode
            if is_monologue:
                mono_name = monologue_character.strip() if monologue_character else valid_chars[0]["name"]
                return (
                    f"\n[등장인물 - 독백 모드 - 필수]\n"
                    f"캐릭터는 '{mono_name}' 1명만 등장합니다. 다른 캐릭터를 절대 만들지 마세요.\n"
                    f"'{mono_name}'가 시청자(독자)에게 직접 설명하는 1인 독백 형식입니다.\n"
                    f"대화 상대 없이 혼자서 모든 내용을 설명합니다.\n"
                )
            
            # 다중 캐릭터: 이름-역할 명시적 매핑
            lines = ["\n[등장인물 이름 및 역할 지정 - 필수]"]
            lines.append("아래 캐릭터만 등장시키세요. 다른 이름을 만들지 마세요.\n")
            for c in valid_chars:
                name = c["name"].strip()
                role = c.get("role", "expert")
                role_label = ROLE_LABELS.get(role, "전문가")
                role_inst = ROLE_INSTRUCTIONS.get(role, "")
                lines.append(f"- '{name}': {role_label} 역할. {role_inst}")
            lines.append("")
            lines.append("★ 역할을 절대 바꾸지 마세요! 전문가가 질문하거나, 질문자가 전문 내용을 설명하면 안 됩니다.")
            lines.append("★ 각 씬의 대사에서 character 필드에 위 이름을 정확히 사용하세요.")
            return "\n".join(lines) + "\n"
        
        # 하위 호환: 기존 character_names 문자열 방식
        if not character_names or not character_names.strip():
            return ""
        names = [n.strip() for n in character_names.split(",") if n.strip()]
        if not names:
            return ""

        is_monologue = monologue_mode
        mono_char = monologue_character.strip() if monologue_character else (names[0] if len(names) == 1 else "")

        if is_monologue and mono_char:
            return (
                f"\n[등장인물 - 독백 모드 - 필수]\n"
                f"캐릭터는 '{mono_char}' 1명만 등장합니다. 다른 캐릭터를 절대 만들지 마세요.\n"
                f"'{mono_char}'가 시청자(독자)에게 직접 설명하는 1인 독백 형식입니다.\n"
                f"대화 상대 없이 혼자서 모든 내용을 설명합니다.\n"
            )
        else:
            names_str = ", ".join(names)
            lines = [
                "\n[등장인물 이름 지정 - 필수]",
                f"다음 이름을 반드시 사용하세요. 다른 이름을 만들지 마세요: {names_str}",
            ]
            if len(names) >= 2:
                lines.append(f"- '{names[0]}': 전문가 역할. 정보를 설명하고 답변합니다. 질문하지 않습니다.")
                lines.append(f"- '{names[1]}': 질문자 역할. 궁금한 점을 짧게 묻고 반응합니다. 직접 설명하지 않습니다.")
                for extra in names[2:]:
                    lines.append(f"- '{extra}': 조력자 역할.")
                lines.append("★ 역할을 절대 바꾸지 마세요!")
            else:
                lines.append(f"'{names[0]}'이(가) 메인 역할(전문가)입니다.")
            return "\n".join(lines) + "\n"

    async def generate_story(
        self,
        keyword: str,
        field_info: FieldInfo,
        collected_data: list,
        scene_count: int = 8,
        character_settings: Optional[CharacterSettings] = None,
        rule_settings: Optional[RuleSettings] = None,
        model: str = "gemini-3-flash-preview",
        character_names: str = "",
        characters_input: list = None,
        monologue_mode: bool = False,
        monologue_character: str = ""
    ) -> Story:
        """규칙 기반 스토리 생성 - 모델 fallback 지원"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not character_settings:
            character_settings = CharacterSettings()
        if not rule_settings:
            rule_settings = RuleSettings()

        # 독백 모드: 사용자가 명시적으로 켠 경우만 (캐릭터 1명이어도 자동 독백 안 함)
        char_names_list = [n.strip() for n in character_names.split(",") if n.strip()] if character_names else []
        is_monologue = monologue_mode
        
        # Fallback 모델 순서 정의
        FALLBACK_MODELS = {
            "gemini-3-pro-preview": ["gemini-3-flash-preview", "gemini-2.0-flash"],
            "gemini-3-flash-preview": ["gemini-2.0-flash"],
            "gemini-2.0-flash": []
        }
        models_to_try = [model] + FALLBACK_MODELS.get(model, ["gemini-2.0-flash"])
            
        data_str = "\n".join([f"- {d['title']}: {d['content']}" for d in collected_data])
        
        # 대사 길이 증가 (충분한 설명을 위해)
        max_dialogue = max(rule_settings.max_dialogue_len, 50)
        max_narration = max(rule_settings.max_narration_len, 60)
        
        # 독백/대화 모드 분기 텍스트 (f-string 중첩 방지)
        if is_monologue:
            structure_text = (
                "- 캐릭터가 혼자 시청자(독자)에게 직접 설명하는 1인 독백 형식입니다.\n"
                "- 대화 상대 없이 모든 씬에서 1명의 캐릭터만 등장합니다. 두 번째 캐릭터를 절대 만들지 마세요.\n"
                '- 각 씬의 대사는 시청자에게 말하듯 자연스럽게 작성하세요. 예: "여러분, 이거 알면 완전 달라져요!"\n'
                "- 각 씬마다 캐릭터의 감정을 한글로 지정하세요."
            )
        else:
            structure_text = (
                "- 캐릭터들이 실제 대화하는 형식으로 자연스럽게 설명하세요.\n"
                "- 각 씬마다 캐릭터의 감정을 한글로 지정하세요 (일반/웃으며/밝게/진지하게/놀라며/화내며/슬프게/걱정하며/당황하며/자신있게/속삭이며/소리치며/궁금해하며/감탄하며/고민하며/장난스럽게/뿌듯하게/차분하게/다급하게/부끄러워하며)."
            )
        
        char_names_prompt = self._build_character_names_prompt(character_names, monologue_mode, monologue_character, characters_input)
        
        # 구조적 캐릭터 입력이 있으면 역할별 이름을 프롬프트에 반영
        if characters_input and len(characters_input) > 0:
            valid_ci = [c for c in characters_input if c.get("name", "").strip()]
            expert_name = next((c["name"] for c in valid_ci if c.get("role") == "expert"), None)
            questioner_name = next((c["name"] for c in valid_ci if c.get("role") == "questioner"), None)
            char_setting_text = ""
            for c in valid_ci:
                role_label = {"expert": "전문가", "questioner": "질문자", "helper": "조력자", "none": "일반 등장인물"}.get(c.get("role", ""), "전문가")
                char_setting_text += f"- {c['name']}: {role_label}\n"
            dialogue_quality_text = f"""[중요 지침 - 대화 품질]
1. **전문가 대사는 충분히 설명해야 합니다!** 
   - "그건 안 돼요." (X) → 너무 짧음
   - "그 방법은 이런 이유로 효과적이에요. 구체적으로 설명해 드릴게요." (O) → 적절함
2. {expert_name or '전문가'}만 전문 내용을 설명/답변합니다. {questioner_name or '질문자'}가 전문 내용을 설명하면 안 됩니다!
3. {questioner_name or '질문자'}는 짧게 질문하고 반응(놀람, 궁금, 감탄 등)만 합니다.
4. 내용이 많으면 2~3개 씬에 나눠서 설명해도 됩니다. 억지로 한 씬에 압축하지 마세요."""
        else:
            char_setting_text = f"- 질문자 유형: {character_settings.questioner_type}\n- 전문가 유형: {character_settings.expert_type}\n"
            dialogue_quality_text = """[중요 지침 - 대화 품질]
1. **전문가 대사는 충분히 설명해야 합니다!** 
   - "그건 안 돼요." (X) → 너무 짧음
   - "그 방법은 이런 이유로 효과적이에요. 구체적으로 설명해 드릴게요." (O) → 적절함
2. 질문자는 짧게, 전문가는 충분히 설명하는 형태로 작성하세요.
3. 내용이 많으면 2~3개 씬에 나눠서 설명해도 됩니다. 억지로 한 씬에 압축하지 마세요."""
        
        prompt = f"""당신은 전문 웹툰 스토리 작가입니다. 다음 자료를 바탕으로 웹툰 스토리를 작성하세요.

[자료]
{data_str}

[캐릭터 설정]
{char_setting_text}
{char_names_prompt}

{dialogue_quality_text}

[제약 조건]
1. 총 씬 개수: {scene_count} (표지 1장 + 본문 {scene_count - 1}장)
2. 한 캐릭터 대사: {max_dialogue}자 이내 (충분히 활용하세요)
3. 한 씬당 말풍선: 최대 {rule_settings.max_bubbles_per_scene}개
4. 나레이션: {max_narration}자 이내

[표지 씬 — 반드시 scene_number: 0으로 생성]
- 표지(썸네일)는 scene_number를 반드시 0으로 설정하세요.
- 주인공(첫 번째 캐릭터) 1명만 등장합니다.
- 대사는 딱 1개: 전체 스토리를 대변하는 임팩트 있고 호기심을 유발하는 한 마디 (예: "이거 알면 인생이 달라져요!", "모르면 손해! 지금 알려드릴게요")
- 나레이션은 없습니다.
- image_prompt: 주인공을 중심으로 한 시선을 끄는 포즈. 정면 또는 약간 측면 앵글. 배경은 주제와 어울리는 심플한 배경. 미디엄 샷 또는 클로즈업.
- 표정과 감정은 스토리 주제에 맞게 자유롭게 선택 (놀란, 궁금한, 자신감 있는, 당황한, 진지한 등 — 주제가 충격적이면 놀란 표정, 꿀팁이면 자신감, 경고성이면 걱정 등)
- 표지 씬 다음에 본문 씬들이 scene_number: 1부터 시작합니다.

[지침 - 나레이션 스타일]
- 나레이션은 완전한 문장보다는 '핵심 요약 스타일'(개조식, 명사형 종결)로 작성하세요.
- 예시: "이것만으로는 충분하지 않았습니다." (X) -> "이것만으로는 부족." (O)
- 예시: "핵심 포인트를 기억해야 합니다." (X) -> "핵심 포인트 기억." (O)
- 군더더기 없는 짧고 간결한 문체를 사용하세요.

[필수 구조]
{structure_text}
- 전문적인 내용도 이해하기 쉽게 풀어서 설명하세요.

[이미지 프롬프트 — 매우 중요]
각 씬마다 "image_prompt" 필드를 반드시 작성하세요. 이것은 AI 이미지 생성 모델에게 전달되는 시각 묘사입니다.
scene_description은 스토리 설명이고, image_prompt는 그림을 그리기 위한 상세한 시각 지시입니다.

image_prompt 작성 규칙:
1. **한국어로 작성** (나중에 자동 번역됨)
2. **대사/텍스트 절대 포함 금지** — 말풍선이나 글자에 대한 언급 없이, 순수하게 그림만 묘사
3. **구체적 시각 요소만 포함**: 캐릭터 위치, 포즈, 표정, 배경, 조명, 구도, 분위기
4. **카메라 앵글** 명시: 예) "미디엄 샷", "클로즈업", "전신 샷", "약간 위에서 내려다보는 앵글"
5. **캐릭터별 포즈/동작** 구체적으로: "팔짱을 끼고 서있다", "책상에 기대어 설명하고 있다"
6. **표정** 구체적으로: "당황한 표정으로 눈을 크게 뜨고", "자신감 넘치는 미소"
7. **배경/환경** 상세히: "밝은 형광등이 켜진 사무실", "창밖으로 도시 야경이 보이는"
8. **조명/분위기**: "따뜻한 조명", "밝지만 캐릭터 그림자가 짙은", "역광으로 실루엣"
9. **80~150자** 범위로 작성

image_prompt 좋은 예시:
- "웹툰 스타일. 밝은 사무실 내부. 전문가가 책상 앞에 앉아 서류를 펼치며 설명하고 있다. 맞은편에 젊은 여성이 궁금한 표정으로 앉아 있다. 책상 위에 노트북과 서류가 놓여 있다. 형광등 조명, 미디엄 샷."
- "웹툰 스타일. 카페 내부, 따뜻한 조명. 두 사람이 마주 앉아 대화 중. 전문가는 자신감 있는 미소로 손으로 제스처를 하고, 질문자는 고개를 갸웃하며 궁금해하는 표정. 배경에 커피잔과 창밖 풍경. 미디엄 와이드 샷."

image_prompt 나쁜 예시:
- "전문가가 설명합니다" (X — 너무 짧고 시각 정보 없음)
- "전문가: '이 방법이 좋습니다'" (X — 대사가 포함됨)

[캐릭터 외모 — 매우 중요]
각 캐릭터에 대해 visual_identity를 반드시 포함하세요.
이 정보는 이미지 생성 시 모든 씬에서 동일한 외모를 유지하는 데 사용됩니다.
구체적이고 정확하게, 아래 12가지 속성을 모두 채워주세요.
- gender: "male" 또는 "female"
- age_range: 예) "early 30s", "mid 40s"
- hair_style: 예) "short straight hair, side-parted to the left" (길이, 스타일, 가르마 방향)
- hair_color: 예) "jet black #1A1A1A" (색상 + 헥스코드)
- skin_tone: 예) "warm beige, light tan" (밝기와 톤 포함)
- eye_shape: 예) "almond-shaped, medium size, double eyelid"
- glasses: 기본값은 "none (no glasses)". 안경을 쓰는 캐릭터는 특별한 이유가 없으면 만들지 마세요. 대부분의 캐릭터는 안경을 쓰지 않습니다.
- outfit: 예) "navy blue suit jacket, white dress shirt, blue striped tie" (상의, 하의, 넥타이 등 구체적)
- outfit_color: 예) "navy #1B2A4A jacket, white #FFFFFF shirt, blue #3B5998 tie" (각 부위별 헥스코드)
- accessories: 예) "silver watch on left wrist, black leather belt" 또는 "none"
- body_type: 예) "slim build, average height"
- distinguishing_features: 예) "small mole on right cheek" 또는 "none"

[출력 형식 (JSON)]
{{
    "title": "제목",
    "characters": [
        {{
            "name": "이름",
            "role": "역할(전문가/질문자/조력자)",
            "appearance": "외모 묘사 (1~2문장 요약)",
            "personality": "성격",
            "visual_identity": {{
                "gender": "male/female",
                "age_range": "나이대",
                "hair_style": "구체적 헤어스타일",
                "hair_color": "색상 + 헥스코드",
                "skin_tone": "피부톤",
                "eye_shape": "눈 형태",
                "glasses": "안경 유무 및 상세 또는 none",
                "outfit": "복장 상세",
                "outfit_color": "부위별 색상 + 헥스코드",
                "accessories": "액세서리 또는 none",
                "body_type": "체형",
                "distinguishing_features": "특이사항 또는 none"
            }}
        }}
    ],
    "scenes": [
        {{
            "scene_number": 0,
            "scene_description": "표지 — 전체 스토리를 대변하는 장면",
            "image_prompt": "주인공 클로즈업 또는 미디엄 샷. 스토리 주제에 맞는 표정(놀란/궁금한/자신감/걱정 등), 정면 응시. 주제와 어울리는 심플한 배경. 80~150자",
            "dialogues": [
                {{"character": "주인공 이름", "text": "전체 스토리를 대변하는 임팩트 한 마디", "emotion": "스토리에 맞는 감정"}}
            ],
            "narration": ""
        }},
        {{
            "scene_number": 1,
            "scene_description": "장면 스토리 설명 (어떤 상황인지)",
            "image_prompt": "AI 이미지 생성용 상세 시각 묘사 (캐릭터 위치/포즈/표정, 배경, 조명, 구도 포함. 대사 절대 금지. 80~150자)",
            "dialogues": [
                {{"character": "이름", "text": "대사({max_dialogue}자내)", "emotion": "한글 감정 (예: 웃으며, 진지하게, 놀라며, 화내며, 슬프게, 걱정하며, 당황하며, 자신있게, 속삭이며, 소리치며, 일반)"}}
            ],
            "narration": "나레이션({max_narration}자내, 선택)"
        }}
    ]
}}"""

        last_error = None
        for try_model in models_to_try:
            try:
                logger.info(f"[generate_story] 시도 중: {try_model}")
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=try_model,
                        contents=prompt
                    ),
                    timeout=120
                )
                data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
                
                scenes = []
                for s in data.get("scenes", []):
                    dialogues = [Dialogue(**d) for d in s.get("dialogues", [])]
                    scene = Scene(
                        scene_number=s.get("scene_number"),
                        scene_description=s.get("scene_description"),
                        image_prompt=s.get("image_prompt"),
                        dialogues=dialogues,
                        narration=s.get("narration")
                    )
                    scene.warnings = self._validate_scene_density(scene, rule_settings)
                    scenes.append(scene)
                
                # 캐릭터 파싱 (visual_identity 포함)
                from app.models.models import VisualIdentity
                parsed_characters = []
                for c in data.get("characters", []):
                    vi_data = c.pop("visual_identity", None)
                    char = CharacterProfile(**c)
                    if vi_data and isinstance(vi_data, dict):
                        char.visual_identity = VisualIdentity(**vi_data)
                    parsed_characters.append(char)
                
                self.last_used_model = try_model
                logger.info(f"[generate_story] 성공: {try_model}, 씬 수: {len(scenes)}, 캐릭터: {len(parsed_characters)}")
                return Story(
                    title=data.get("title", keyword),
                    scenes=scenes,
                    characters=parsed_characters
                )
            except asyncio.TimeoutError:
                last_error = "스토리 생성 타임아웃 (120초)"
                logger.warning(f"[generate_story] {try_model} 타임아웃 (120초)")
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"[generate_story] {try_model} 실패: {str(e)}")
                continue
        
        # 모든 모델 실패
        raise Exception(f"스토리 생성 실패: {str(last_error)}")

    def _validate_scene_density(self, scene: Scene, rules: RuleSettings) -> list:
        """씬의 텍스트 밀도 검사"""
        warnings = []
        for d in scene.dialogues:
            if len(d.text) > rules.max_dialogue_len:
                warnings.append(f"{d.character} 대사가 너무 깁니다 ({len(d.text)}자 > {rules.max_dialogue_len}자)")
        
        if len(scene.dialogues) > rules.max_bubbles_per_scene:
            warnings.append(f"말풍선이 너무 많습니다 ({len(scene.dialogues)}개 > {rules.max_bubbles_per_scene}개)")
            
        if scene.narration and len(scene.narration) > rules.max_narration_len:
            warnings.append(f"나레이션이 너무 깁니다 ({len(scene.narration)}자 > {rules.max_narration_len}자)")
            
        return warnings
    
    async def generate_caption(
        self,
        keyword: str,
        field: SpecializedField,
        story_summary: str,
        model: str = "gemini-3-flash-preview",
        character_names: list[str] | None = None
    ) -> InstagramCaption:
        """인스타그램 캡션 생성 - 모델 fallback + 재시도 + 캐릭터명 후처리 제거"""
        import logging
        logger = logging.getLogger(__name__)

        # Fallback 모델 순서 (빠른 모델 우선)
        FALLBACK_MODELS = {
            "gemini-3-pro-preview": ["gemini-3-flash-preview", "gemini-2.0-flash"],
            "gemini-3-flash-preview": ["gemini-2.0-flash"],
            "gemini-2.0-flash": []
        }
        models_to_try = [model] + FALLBACK_MODELS.get(model, ["gemini-2.0-flash"])
        
        # 캐릭터명 금지 목록 프롬프트 구성
        char_ban_text = ""
        if character_names:
            names_str = ", ".join(f"'{n}'" for n in character_names)
            char_ban_text = f"\n   - 다음 이름은 웹툰 속 가상인물이므로 절대 사용 금지: {names_str}"
        
        prompt = f"""당신은 인스타그램 마케팅 전문가입니다.

[입력 정보]
주제: {keyword}
분야: {field.value}
스토리 요약: {story_summary}

[생성 규칙]

1. 훅 문장 (첫 줄)
   - 이모지로 시작
   - 호기심 유발 또는 문제 제기
   - 15자 내외

2. 본문 캡션
   - 친근한 말투
   - 주제의 핵심 내용 요약
   - CTA 포함 (저장, 공유 유도)
   - 3~5문장
   - 가독성을 위해 2~3문장마다 줄 바꿈(\\n)을 넣을 것
   - 강조나 분위기에 맞게 본문 중간에 적절한 이모지를 사용할 것 (예: 💡, ✅, 💰, 👋, 📌 등)
   - 웹툰 속 가상 캐릭터 이름(등장인물명)은 절대 캡션에 포함하지 마세요{char_ban_text}
   - 주제와 핵심 정보 중심으로 작성하세요

3. 전문가 Tip
   - 핵심 정보 1줄 요약
   - 실용적인 조언
   - 20자 내외

4. 해시태그
   - 15~20개
   - 주제 관련 태그 포함

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요.
- hook, expert_tip: 한 줄.
- body: 본문은 여러 줄 가능. 줄바꿈(\\n)과 이모지를 활용해 가독성 있게 작성.
예시:
{{
  "hook": "🔥 훅 문장",
  "body": "첫 번째 문단입니다. 스토리를 요약해 드려요.\\n\\n두 번째 문단이에요 💡 핵심만 전달합니다.\\n\\n저장해두고 활용해보세요! ✅",
  "expert_tip": "전문가 팁",
  "hashtags": ["#태그1", "#태그2"]
}}"""

        for try_model in models_to_try:
            try:
                logger.info(f"[generate_caption] 시도 중: {try_model}")
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=try_model,
                        contents=prompt
                    ),
                    timeout=30
                )
                text = response.text.strip()
                
                json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
                if json_match:
                    text = json_match.group(1)
                
                data = json.loads(text)
                
                # 분야별 기본 해시태그 추가
                hashtags = data.get("hashtags", [])
                base_tags = FIELD_HASHTAGS.get(field.value, [])
                all_tags = list(set(hashtags + base_tags))[:20]
                
                hook = data.get("hook", "")
                body = data.get("body", "")
                expert_tip = data.get("expert_tip", "")
                
                # ★ 캐릭터명 후처리 제거 (프롬프트 무시 대비 안전장치)
                if character_names:
                    for cname in character_names:
                        if not cname:
                            continue
                        # "전문가 '김세무'가" → "전문가가" 패턴 제거
                        import re as _re
                        for quote_pat in [f"'{cname}'", f"'{cname}'", f'"{cname}"', f"「{cname}」"]:
                            hook = hook.replace(quote_pat, "")
                            body = body.replace(quote_pat, "")
                            expert_tip = expert_tip.replace(quote_pat, "")
                        # 이름 자체 제거
                        hook = hook.replace(cname, "")
                        body = body.replace(cname, "")
                        expert_tip = expert_tip.replace(cname, "")
                    # 연속 공백 정리
                    hook = " ".join(hook.split())
                    body = _re.sub(r' +', ' ', body)
                    expert_tip = " ".join(expert_tip.split())
                
                self.last_used_model = try_model
                logger.info(f"[generate_caption] 성공: {try_model}")
                return InstagramCaption(
                    hook=hook,
                    body=body,
                    expert_tip=expert_tip,
                    hashtags=all_tags
                )
                
            except asyncio.TimeoutError:
                logger.warning(f"[generate_caption] {try_model} 타임아웃 (30초) → 다음 모델 시도")
            except Exception as e:
                logger.warning(f"[generate_caption] {try_model} 실패: {str(e)}")
                if try_model != models_to_try[-1]:
                    await asyncio.sleep(1)
                    continue

        # 모든 모델 실패 시 기본 캡션 반환 (500 에러 대신)
        logger.error(f"[generate_caption] 모든 모델 실패, 기본 캡션 반환")
        default_tags = FIELD_HASHTAGS.get(field.value, ["#웹툰", "#정보", "#꿀팁"])
        return InstagramCaption(
            hook=f"📌 {keyword} 알아보기",
            body=f"{keyword}에 대해 알아두면 좋은 정보를 웹툰으로 정리했어요!\n\n저장해두고 필요할 때 확인해보세요 ✅",
            expert_tip=f"{keyword} 관련 전문가 팁",
            hashtags=default_tags[:20]
        )



    async def extract_style_from_image(self, image_data: bytes) -> dict:
        """이미지에서 스타일(인물/배경) 분석 및 추출"""
        import logging
        logger = logging.getLogger(__name__)
        
        # STYLE_SYSTEM.md 3.1 Vision AI Analysis Prompt
        STYLE_EXTRACTION_PROMPT = """
        You are an expert visual style analyst for Korean webtoon/cartoon images.
        
        Analyze the uploaded image(s) and extract two separate style profiles:
        
        ## CHARACTER STYLE (인물 스타일)
        Describe the following visual attributes of how characters are drawn:
        - line_style: outline thickness, sketch vs clean, ink quality
        - color_palette: skin tones (with hex codes), hair colors, clothing color tendencies
        - proportion: head-to-body ratio, eye size relative to face
        - shading: cel-shading, gradient, flat color, shadow style
        - lighting: direction, warmth, shadow intensity on characters
        - expression_style: how eyes/mouth are drawn, level of expressiveness
        
        ## BACKGROUND STYLE (배경 스타일)  
        Describe the following visual attributes of backgrounds:
        - setting: type of location (office, outdoor, abstract, etc.)
        - color_palette: dominant colors with hex codes
        - lighting: ambient light color, direction, intensity
        - detail_level: photorealistic, simplified, abstract
        - depth: depth-of-field blur, flat, layered
        - texture: smooth gradient, watercolor, flat vector, etc.
        
        ## OUTPUT FORMAT
        Return ONLY valid JSON with these exact keys. Do not include markdown formatting (```json ... ```).
        {
          "character_style": {
            "prompt_block": "<one paragraph prompt that captures all character style attributes>",
            "visual_attributes": { "line_style": "...", "color_palette": "...", "proportion": "...", "shading": "...", "lighting": "...", "expression_style": "..." },
            "locked_attributes": ["<top 3-4 most distinctive attributes>"]
          },
          "background_style": {
            "prompt_block": "<one paragraph prompt that captures all background style attributes>",
            "visual_attributes": { "setting": "...", "color_palette": "...", "lighting": "...", "detail_level": "...", "depth": "...", "texture": "..." },
            "locked_attributes": ["<top 3-4 most distinctive attributes>"]
          }
        }
        """

        # 이미지 MIME type 감지
        mime_type = "image/png"
        if image_data[:3] == b'\xff\xd8\xff':
            mime_type = "image/jpeg"
        elif image_data[:4] == b'\x89PNG':
            mime_type = "image/png"
        elif image_data[:4] == b'RIFF':
            mime_type = "image/webp"

        # 신형 SDK: Part.from_bytes로 이미지 전달
        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

        # Fallback 모델 순서 (사용자 요청: 3.0 Pro 등 고성능 모델 전용)
        models_to_try = ["gemini-3-pro-preview", "gemini-3-flash-preview"]

        for try_model in models_to_try:
            try:
                logger.info(f"[extract_style] 시도 중: {try_model}")
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=try_model,
                        contents=[STYLE_EXTRACTION_PROMPT, image_part]
                    ),
                    timeout=60
                )
                
                text = response.text
                # 로깅 추가 (디버깅용)
                if len(text) < 200:
                    logger.debug(f"[extract_style] {try_model} 응답(일부): {text}")
                
                # 마크다운 코드 블록 제거 시도
                text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
                text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
                text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
                
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    logger.info(f"[extract_style] 성공: {try_model}")
                    return result
                else:
                    logger.error(f"[extract_style] JSON 파싱 실패. 응답 내용: {text[:500]}...")
                    raise ValueError("JSON not found in response")
                    
            except Exception as e:
                logger.warning(f"[extract_style] {try_model} 실패: {e}")
                if try_model != models_to_try[-1]:
                    continue
        
        # 모든 모델 실패 시
        logger.error("[extract_style] 모든 모델 실패")
        raise Exception("스타일 추출에 실패했습니다. 다시 시도해주세요.")


# 싱글톤 인스턴스
_gemini_service: Optional[GeminiService] = None

def get_gemini_service() -> GeminiService:
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service

def get_gemini_client():
    """싱글톤 GeminiService의 Client 반환 (매번 새로 만들지 않고 재사용)"""
    return get_gemini_service().client


