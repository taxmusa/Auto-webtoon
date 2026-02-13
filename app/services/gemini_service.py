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
    InstagramCaption, CharacterSettings, CharacterProfile, RuleSettings
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

    @staticmethod
    def _build_character_names_prompt(character_names: str) -> str:
        """캐릭터 이름 지정 프롬프트 생성"""
        if not character_names or not character_names.strip():
            return ""
        names = [n.strip() for n in character_names.split(",") if n.strip()]
        if not names:
            return ""
        names_str = ", ".join(names)
        return (
            "\n[등장인물 이름 지정 - 필수]\n"
            f"다음 이름을 반드시 사용하세요. 다른 이름을 만들지 마세요: {names_str}\n"
            "첫 번째 이름이 메인 역할(전문가)이고, 나머지는 보조 역할입니다.\n"
        )

    async def generate_story(
        self,
        keyword: str,
        field_info: FieldInfo,
        collected_data: list,
        scene_count: int = 8,
        character_settings: Optional[CharacterSettings] = None,
        rule_settings: Optional[RuleSettings] = None,
        model: str = "gemini-2.0-flash",
        character_names: str = ""
    ) -> Story:
        """규칙 기반 스토리 생성 - 모델 fallback 지원"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not character_settings:
            character_settings = CharacterSettings()
        if not rule_settings:
            rule_settings = RuleSettings()
        
        # Fallback 모델 순서 정의 (사용자 선택 모델 우선)
        FALLBACK_MODELS = {
            "gemini-2.0-flash": ["gemini-2.5-flash", "gemini-3-flash-preview"],
            "gemini-2.5-pro": ["gemini-2.5-flash", "gemini-3-pro-preview"],
            "gemini-2.5-flash": ["gemini-3-flash-preview"],
            "gemini-3-pro-preview": ["gemini-3-flash-preview"],
            "gemini-3-flash-preview": ["gemini-2.5-flash"]
        }
        models_to_try = [model] + FALLBACK_MODELS.get(model, ["gemini-2.5-flash", "gemini-3-flash-preview"])
            
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
{self._build_character_names_prompt(character_names)}

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

[지침 - 나레이션 스타일]
- 나레이션은 완전한 문장보다는 '핵심 요약 스타일'(개조식, 명사형 종결)로 작성하세요.
- 예시: "단순히 차용증만으로는 부족했습니다." (X) -> "단순히 차용증만으로는 부족." (O)
- 예시: "실제 상환 내역이 중요합니다." (X) -> "실제 상환 내역이 중요." (O)
- 군더더기 없는 짧고 간결한 문체를 사용하세요.

[필수 구조]
- 캐릭터들이 실제 대화하는 형식으로 자연스럽게 설명하세요.
- 각 씬마다 캐릭터의 기분(neutral/happy/sad/surprised/serious/angry)을 지정하세요.
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
- "웹툰 스타일. 밝은 사무실 내부. 세무사가 책상 앞에 앉아 서류를 펼치며 설명하고 있다. 맞은편에 젊은 여성이 걱정스러운 표정으로 앉아 있다. 책상 위에 계산기와 서류가 놓여 있다. 형광등 조명, 미디엄 샷."
- "웹툰 스타일. 카페 내부, 따뜻한 조명. 두 사람이 마주 앉아 대화 중. 전문가는 자신감 있는 미소로 손으로 제스처를 하고, 질문자는 고개를 갸웃하며 궁금해하는 표정. 배경에 커피잔과 창밖 풍경. 미디엄 와이드 샷."

image_prompt 나쁜 예시:
- "세무사가 설명합니다" (X — 너무 짧고 시각 정보 없음)
- "세무사: '이자율은 4.6%입니다'" (X — 대사가 포함됨)

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
            "scene_number": 1,
            "scene_description": "장면 스토리 설명 (어떤 상황인지)",
            "image_prompt": "AI 이미지 생성용 상세 시각 묘사 (캐릭터 위치/포즈/표정, 배경, 조명, 구도 포함. 대사 절대 금지. 80~150자)",
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
                
                logger.info(f"[generate_story] 성공: {try_model}, 씬 수: {len(scenes)}, 캐릭터: {len(parsed_characters)}")
                return Story(
                    title=data.get("title", keyword),
                    scenes=scenes,
                    characters=parsed_characters
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

        # inline_data 형태로 이미지 전달 (PIL 변환 없이 직접 bytes 사용)
        image_part = {
            "inline_data": {
                "mime_type": mime_type,
                "data": image_data
            }
        }

        # Fallback 모델 순서 (사용자 요청: 3.0 Pro 등 고성능 모델 전용)
        # model_list.txt 확인 결과 1.5-pro는 없음. 2.5-pro 사용.
        models_to_try = ["gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.0-flash"]

        for try_model in models_to_try:
            try:
                logger.info(f"[extract_style] 시도 중: {try_model}")
                model = genai.GenerativeModel(try_model)
                response = await model.generate_content_async([STYLE_EXTRACTION_PROMPT, image_part])
                
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


