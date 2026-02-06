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
    InstagramCaption, CharacterSettings
)


class GeminiService:
    """Gemini AI 서비스"""
    
    def __init__(self):
        settings = get_settings()
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
    
    def detect_field(self, keyword: str) -> FieldInfo:
        """키워드에서 분야 자동 감지"""
        keyword_lower = keyword.lower()
        
        for field_name, keywords in SPECIALIZED_FIELDS.items():
            if any(kw in keyword_lower for kw in keywords):
                return FieldInfo(
                    field=SpecializedField(field_name),
                    requires_legal_verification=True,
                    data_collection_method="specialized"
                )
        
        return FieldInfo(
            field=SpecializedField.GENERAL,
            requires_legal_verification=False,
            data_collection_method="general_search"
        )
    
    async def generate_story(
        self,
        keyword: str,
        field: SpecializedField,
        scene_count: int = 8,
        character_settings: Optional[CharacterSettings] = None
    ) -> Story:
        """스토리 생성"""
        if character_settings is None:
            character_settings = CharacterSettings()
        
        prompt = f"""당신은 전문적인 웹툰 스토리 작가입니다.

[입력 정보]
주제: {keyword}
분야: {field.value}

[설정]
씬 개수: {scene_count}
질문자 캐릭터: {character_settings.questioner_type} (이름: 민지)
전문가 캐릭터: {character_settings.expert_type}

[규칙]
1. 각 씬은 다음 형식으로 작성:
   - 장면 설명 (배경, 상황)
   - 캐릭터 대사 (최대 20자)
   - 나레이션 (최대 30자, 선택)

2. 한 씬에 말풍선은 최대 2개

3. 스토리 구조:
   - 도입 (1-2씬): 문제 상황 제시, 질문자의 고민
   - 전개 (3-{scene_count-2}씬): 전문가 설명
   - 마무리 (마지막 1-2씬): 핵심 정리, 행동 유도

4. 대화체로 친근하게 작성

5. 대사는 반드시 20자 이내로 작성

[출력 형식]
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트 없이 JSON만 출력:
{{
  "title": "제목",
  "scenes": [
    {{
      "scene_number": 1,
      "scene_description": "장면 설명",
      "dialogues": [
        {{"character": "민지", "text": "대사 (20자 이내)"}},
        {{"character": "{character_settings.expert_type}", "text": "대사 (20자 이내)"}}
      ],
      "narration": "나레이션 (선택, 30자 이내)"
    }}
  ]
}}"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            
            # JSON 추출 (```json ... ``` 형태 처리)
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
            
            data = json.loads(text)
            
            scenes = []
            for s in data.get("scenes", []):
                dialogues = [
                    Dialogue(
                        character=d.get("character", ""),
                        text=d.get("text", "")
                    )
                    for d in s.get("dialogues", [])
                ]
                scene = Scene(
                    scene_number=s.get("scene_number", len(scenes) + 1),
                    scene_description=s.get("scene_description", ""),
                    dialogues=dialogues,
                    narration=s.get("narration")
                )
                # 콘텐츠 밀도 검증
                scene.warnings = self._validate_scene_density(scene)
                scenes.append(scene)
            
            return Story(
                title=data.get("title", keyword),
                scenes=scenes
            )
            
        except Exception as e:
            # 에러 시 기본 스토리 반환
            return Story(
                title=keyword,
                scenes=[
                    Scene(
                        scene_number=1,
                        scene_description=f"스토리 생성 중 오류: {str(e)}",
                        dialogues=[]
                    )
                ]
            )
    
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
    
    def _validate_scene_density(self, scene: Scene) -> list:
        """씬의 콘텐츠 밀도 검증"""
        warnings = []
        
        for dialogue in scene.dialogues:
            if len(dialogue.text) > 20:
                warnings.append(
                    f"대사가 너무 깁니다 ({len(dialogue.text)}자 → 20자 권장)"
                )
        
        if len(scene.dialogues) > 2:
            warnings.append(
                f"말풍선이 너무 많습니다 ({len(scene.dialogues)}개 → 2개 권장)"
            )
        
        if scene.narration and len(scene.narration) > 30:
            warnings.append(
                f"나레이션이 너무 깁니다 ({len(scene.narration)}자 → 30자 권장)"
            )
        
        return warnings


# 싱글톤 인스턴스
_gemini_service: Optional[GeminiService] = None

def get_gemini_service() -> GeminiService:
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
