"""
Gemini AI 서비스 - 텍스트 생성
- 분야 감지
- 스토리 생성
- 캡션 생성
"""
import google.generativeai as genai
from typing import Optional
import json
import re

from app.core.config import get_settings, SPECIALIZED_FIELDS, FIELD_HASHTAGS
from app.models.models import (
    FieldInfo, SpecializedField, Story, Scene, Dialogue,
    InstagramCaption, CharacterSettings, CharacterProfile
)


class GeminiService:
    """Gemini AI 서비스"""
    
    def __init__(self):
        settings = get_settings()
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    async def detect_field(self, keyword: str, model: str = "gemini-2.0-flash") -> FieldInfo:
        """AI를 사용하여 키워드에서 분야, 기준 년도, 법정 검증 필요성 자동 감지 - 모델 fallback 지원"""
        import logging
        import datetime
        logger = logging.getLogger(__name__)
        current_year_str = str(datetime.datetime.now().year)
        
        # Fallback 모델 순서 정의
        FALLBACK_MODELS = {
            "gemini-2.0-flash": ["gemini-2.5-flash", "gemini-3-flash-preview"],
            "gemini-2.5-pro": ["gemini-2.5-flash", "gemini-3-pro-preview"],
            "gemini-2.5-flash": ["gemini-3-flash-preview"],
            "gemini-3-pro-preview": ["gemini-3-flash-preview"],
            "gemini-3-flash-preview": []
        }
        
        models_to_try = [model] + FALLBACK_MODELS.get(model, [])
        
        prompt = f"""키워드 "{keyword}"를 분석하여 다음 정보를 JSON 형식으로 반환하세요.
        현재 시각은 {current_year_str}년입니다. 특별한 언급이 없으면 기준 년도는 {current_year_str}년으로 설정하세요.
        
        [분석 항목]
        1. field: 세무, 법률, 노무, 회계, 부동산정책, 일반 중 하나
           - 특히 '세금', '절세', '증여', '상속', '공제', '연말정산', '부가세', '종소세' 등 세금 관련 키워드는 반드시 "세무"로 분류하세요.
        2. target_year: 해당 키워드와 관련된 기준 년도 (예: 2025, 2026). 
           - 키워드에 년도가 명시되어 있으면 그 년도를 따르고, 없으면 현재 년도({current_year_str})를 기본값으로 합니다.
        3. requires_legal_verification: 정확한 법령/규정 확인이 필수적인지 여부 (true/false)
           - 세금 계산, 법적 절차 등은 반드시 true로 설정
        4. reason: 왜 그렇게 판단했는지에 대한 짧은 근거 (한국어)
        
        [예시]
        키워드: "2025년 상속세 개정안" -> field: "세무", target_year: "2025"
        키워드: "증여세 절세 방법" -> field: "세무", target_year: "{current_year_str}"
        
        [출력 형식]
        {{
            "field": "분야",
            "target_year": "{current_year_str}",
            "requires_legal_verification": true,
            "reason": "한 두 문장 근거"
        }}"""

        for try_model in models_to_try:
            try:
                logger.info(f"[detect_field] 시도 중: {try_model}")
                current_model = genai.GenerativeModel(try_model)
                response = await current_model.generate_content_async(prompt)
                text = response.text
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                else:
                    raise ValueError("JSON not found in response")
                
                logger.info(f"[detect_field] 성공: {try_model}")
                return FieldInfo(
                    field=SpecializedField(data.get("field", "일반")),
                    target_year=data.get("target_year", current_year_str),
                    requires_legal_verification=data.get("requires_legal_verification", False),
                    reason=data.get("reason"),
                    confidence_score=0.9
                )
            except Exception as e:
                logger.warning(f"[detect_field] {try_model} 실패: {str(e)}")
                if try_model != models_to_try[-1]:
                    continue
        
        # 모든 모델 실패 시 기본값 반환
        logger.error(f"[detect_field] 모든 모델 실패")
        return FieldInfo(field=SpecializedField.GENERAL, target_year=current_year_str)

    async def collect_data(self, keyword: str, field_info: FieldInfo, model: str = "gemini-2.0-flash") -> list:
        """주제와 관련된 상세 자료 수집 (제목 + 본문) - 모델 fallback 지원"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Fallback 모델 순서 정의
        FALLBACK_MODELS = {
            "gemini-2.0-flash": ["gemini-2.5-flash", "gemini-3-flash-preview"],
            "gemini-2.5-pro": ["gemini-2.5-flash", "gemini-3-pro-preview"],
            "gemini-2.5-flash": ["gemini-3-flash-preview"],
            "gemini-3-pro-preview": ["gemini-3-flash-preview"],
            "gemini-3-flash-preview": []
        }
        
        models_to_try = [model] + FALLBACK_MODELS.get(model, [])
        
        # 최신 년도 주입
        import datetime
        current_year_str = str(datetime.datetime.now().year)

        prompt = f"""키워드 "{keyword}"에 대해 SNS(인스타그램/블로그)용 콘텐츠 제작을 위한 상세 자료를 수집해 주세요.
        
        [핵심 지침]
        1. 기준 년도: 무조건 최신 {current_year_str}년 (또는 그 이후) 정보를 기준으로 작성하세요.
           - 사용자가 특정 년도를 명시하지 않았다면, 자동으로 {current_year_str}년 개정 내용을 적용해야 합니다.
        2. 분야 자동 판단: 키워드를 보고 세무, 법률, 부동산 등 전문 분야라면 해당 전문 지식을 바탕으로 작성하세요.
           (입력된 분야 참고: {field_info.field.value}, 기준 년도: {field_info.target_year})
        
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
            try:
                logger.info(f"[collect_data] 시도 중: {try_model}")
                current_model = genai.GenerativeModel(try_model)
                response = await current_model.generate_content_async(prompt)
                
                # JSON 파싱 (리스트 형태 추출)
                match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    logger.info(f"[collect_data] 성공: {try_model}, {len(result)}개 항목")
                    return result
                else:
                    raise ValueError("JSON list not found in response")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"[collect_data] {try_model} 실패: {str(e)}")
                if try_model != models_to_try[-1]:
                    logger.info(f"[collect_data] 다음 모델로 시도: {models_to_try[models_to_try.index(try_model)+1]}")
                continue
        
        # 모든 모델 실패
        logger.error(f"[collect_data] 모든 모델 실패. 마지막 오류: {last_error}")
        return [{"title": keyword, "content": f"정보를 불러오지 못했습니다. ({last_error}) 다시 시도해 주세요."}]

    async def generate_story(
        self,
        keyword: str,
        field_info: FieldInfo,
        collected_data: list,
        scene_count: int = 8,
        character_settings: Optional[CharacterSettings] = None,
        rule_settings: Optional[RuleSettings] = None
    ) -> Story:
        """규칙 기반 스토리 생성 - 모델 fallback 지원"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not character_settings:
            character_settings = CharacterSettings()
        if not rule_settings:
            rule_settings = RuleSettings()
        
        # Fallback 모델 순서 정의
        models_to_try = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-3-flash-preview"]
            
        data_str = "\n".join([f"- {d['title']}: {d['content']}" for d in collected_data])
        
        # 대사 길이 증가 (충분한 설명을 위해)
        max_dialogue = max(rule_settings.max_dialogue_len, 50)
        max_narration = max(rule_settings.max_narration_len, 60)
        
        prompt = f"""당신은 전문 웹툰 스토리 작가입니다. 다음 자료를 바탕으로 웹툰 스토리를 작성하세요.

[자료]
{data_str}

[캐릭터 설정]
- 질문자 유형: {character_settings.questioner_type}
- 전문가 유형: {character_settings.expert_type}

[중요 지침 - 대화 품질]
1. **전문가 대사는 충분히 설명해야 합니다!** 
   - "연 4.6% 이자가 법정." (X) → 너무 짧음
   - "연 4.6% 이율로 이자를 지급해야 증여로 보지 않아요." (O) → 적절함
2. 질문자는 짧게, 전문가는 충분히 설명하는 형태로 작성하세요.
3. 내용이 많으면 2~3개 씬에 나눠서 설명해도 됩니다. 억지로 한 씬에 압축하지 마세요.

[제약 조건]
1. 총 씬 개수: {scene_count}
2. 한 캐릭터 대사: {max_dialogue}자 이내 (충분히 활용하세요)
3. 한 씬당 말풍선: 최대 {rule_settings.max_bubbles_per_scene}개
4. 나레이션: {max_narration}자 이내

[필수 구조]
- 캐릭터들이 실제 대화하는 형식으로 자연스럽게 설명하세요.
- 각 씬마다 캐릭터의 기분(neutral/happy/sad/surprised/serious/angry)을 지정하세요.
- 전문적인 내용도 이해하기 쉽게 풀어서 설명하세요.

[출력 형식 (JSON)]
{{
    "title": "제목",
    "characters": [
        {{"name": "이름", "role": "역할(전문가/질문자/조력자)", "appearance": "외모 묘사", "personality": "성격"}}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_description": "장면 시각적 묘사",
            "dialogues": [
                {{"character": "이름", "text": "대사({max_dialogue}자내)", "emotion": "기분"}}
            ],
            "narration": "나레이션({max_narration}자내, 선택)"
        }}
    ]
}}"""

        last_error = None
        for try_model in models_to_try:
            try:
                logger.info(f"[generate_story] 시도 중: {try_model}")
                current_model = genai.GenerativeModel(try_model)
                response = await current_model.generate_content_async(prompt)
                data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
                
                scenes = []
                for s in data.get("scenes", []):
                    dialogues = [Dialogue(**d) for d in s.get("dialogues", [])]
                    scene = Scene(
                        scene_number=s.get("scene_number"),
                        scene_description=s.get("scene_description"),
                        dialogues=dialogues,
                        narration=s.get("narration")
                    )
                    scene.warnings = self._validate_scene_density(scene, rule_settings)
                    scenes.append(scene)
                
                logger.info(f"[generate_story] 성공: {try_model}, 씬 수: {len(scenes)}")
                return Story(
                    title=data.get("title", keyword),
                    scenes=scenes,
                    characters=[CharacterProfile(**c) for c in data.get("characters", [])]
                )
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
        story_summary: str
    ) -> InstagramCaption:
        """인스타그램 캡션 생성"""
        
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
   - 스토리 내용 요약
   - CTA 포함 (저장, 공유 유도)
   - 3~5문장

3. 전문가 Tip
   - 핵심 정보 1줄 요약
   - 실용적인 조언
   - 20자 내외

4. 해시태그
   - 15~20개
   - 주제 관련 태그 포함

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요:
{{
  "hook": "🔥 훅 문장",
  "body": "본문 캡션",
  "expert_tip": "전문가 팁",
  "hashtags": ["#태그1", "#태그2"]
}}"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
            
            data = json.loads(text)
            
            # 분야별 기본 해시태그 추가
            hashtags = data.get("hashtags", [])
            base_tags = FIELD_HASHTAGS.get(field.value, [])
            all_tags = list(set(hashtags + base_tags))[:20]
            
            return InstagramCaption(
                hook=data.get("hook", ""),
                body=data.get("body", ""),
                expert_tip=data.get("expert_tip", ""),
                hashtags=all_tags
            )
            
        except Exception as e:
            return InstagramCaption(
                hook=f"🔥 {keyword} 핵심 정리!",
                body=f"{keyword}에 대해 알아봤어요. 저장해두고 참고하세요!",
                expert_tip="전문가와 상담하면 더 정확해요!",
                hashtags=FIELD_HASHTAGS.get(field.value, ["#정보", "#꿀팁"])
            )



# 싱글톤 인스턴스
_gemini_service: Optional[GeminiService] = None

def get_gemini_service() -> GeminiService:
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
