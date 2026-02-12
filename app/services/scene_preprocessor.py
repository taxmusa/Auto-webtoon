"""
씬 설명 전처리 서비스

이미지 생성 AI가 처리하기 어려운 요소를 자동 변환:
- 숫자/금액 → 시각적 비유 (예: "1.5억" → "large stack of gold coins")
- 인포그래픽 요청 → 캐릭터 중심 장면 (예: "차트 보여줌" → "character pointing at a board")
- UI/텍스트 요청 → 물리적 소품 (예: "로고가 뜬다" → "poster on wall")
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)


# ============================
# 패턴 기반 빠른 전처리 (Gemini 불필요)
# ============================

# 숫자+단위 패턴 (한국어 금액 등)
_NUMBER_PATTERNS = [
    # 한국어 금액: 1.5억, 2억 1,739만, 1000만 등
    (r'\d[\d,.]*\s*억\s*[\d,.]*\s*만?\s*원?', '_AMOUNT_'),
    (r'\d[\d,.]*\s*만\s*원?', '_AMOUNT_'),
    # 퍼센트
    (r'\d[\d,.]*\s*%', '_PERCENT_'),
    # 법정 이자율 등 구체적 수치
    (r'(?:법정\s*)?이자(?:율)?\s*\d[\d,.]*\s*%?', '_INTEREST_'),
]

# 인포그래픽/UI 관련 키워드
_INFOGRAPHIC_KEYWORDS = [
    "인포그래픽", "차트", "그래프", "도표", "수식", "계산",
    "양식", "서류", "이체 내역", "로고", "아이콘",
    "숫자가 강조", "글자가 찍히", "화면에", "모니터를",
    "합쳐지는", "나타난다", "표시된다"
]

# 텍스트 표현 패턴
_TEXT_DISPLAY_PATTERNS = [
    r"['\"].*?['\"]\s*(?:라는|이라는)\s*(?:글자|텍스트|문구)",
    r"화면에\s+.*?\s+(?:뜬다|나타난다|표시된다|보인다)",
]


def _has_problematic_content(description: str) -> bool:
    """씬 설명에 이미지 생성이 어려운 요소가 있는지 판단"""
    # 숫자/금액 패턴
    for pattern, _ in _NUMBER_PATTERNS:
        if re.search(pattern, description):
            return True
    
    # 인포그래픽 키워드
    for kw in _INFOGRAPHIC_KEYWORDS:
        if kw in description:
            return True
    
    # 텍스트 표현 패턴
    for pattern in _TEXT_DISPLAY_PATTERNS:
        if re.search(pattern, description):
            return True
    
    return False


def _quick_transform(description: str) -> str:
    """패턴 기반 빠른 변환 (Gemini 없이)
    
    ★ 핵심: 숫자/텍스트 요소를 시각적 소품으로 대체
    """
    result = description
    
    # 1. "화면에 X이 나타난다/합쳐진다" → "캐릭터가 설명하는 장면"
    result = re.sub(
        r'화면에\s+(.+?)\s+(?:나타난다|합쳐진다|표시된다|뜬다)',
        r'캐릭터가 큰 화이트보드 앞에서 중요한 내용을 설명하고 있다',
        result
    )
    
    # 2. "X라는 글자가 찍히는/표시되는" → "문서를 작성하는"
    result = re.sub(
        r"['\"].*?['\"]\s*(?:라는|이라는)\s*(?:글자|텍스트|문구)\s*(?:가|이)\s*(?:찍히|표시|나타)",
        '중요한 문서를 꼼꼼하게 작성하',
        result
    )
    
    # 3. 한국어 금액을 시각적 비유로
    result = re.sub(r'\d[\d,.]*\s*억\s*[\d,.]*\s*만?\s*원?', '큰 금액', result)
    result = re.sub(r'\d[\d,.]*\s*만\s*원?', '상당한 금액', result)
    
    # 4. 퍼센트/이자율
    result = re.sub(r'(?:법정\s*)?이자(?:율)?\s*\d[\d,.]*\s*%?', '이자율 기준', result)
    result = re.sub(r'\d[\d,.]*\s*%', '비율', result)
    
    # 5. "인포그래픽이 나타난다" → 소품 기반 장면
    result = re.sub(
        r'인포그래픽\w*\s*(?:이|가)\s*(?:나타|등장|보이)',
        '캐릭터가 차트가 그려진 큰 화이트보드를 가리키며 설명하',
        result
    )
    
    # 6. "X 로고와 Y 아이콘이 모니터를 비춘다" → 물리적 장면
    result = re.sub(
        r'로고\w*\s*(?:와|과)\s*.*?\s*아이콘\w*\s*(?:이|가)\s*모니터를\s*비춘다',
        '컴퓨터 모니터 앞에서 진지하게 화면을 확인하고 있다',
        result
    )
    
    # 7. "양식이 화면에 뜬다" → 서류 기반
    result = re.sub(
        r'양식\w*\s*(?:이|가)\s*화면에\s*뜬다',
        '중요한 서류를 테이블 위에 펼쳐놓고 검토하고 있다',
        result
    )
    
    # 8. "이체 내역에 'X'라는 글자가 찍히는 장면" → 물리적
    result = re.sub(
        r'(?:이체\s*내역|통장|계좌).*?(?:찍히|표시|보이).*?(?:장면|모습)',
        '통장을 손에 들고 내용을 확인하는 장면',
        result
    )
    
    return result


async def preprocess_scenes_for_image_gen(scenes: List) -> List:
    """씬 설명을 이미지 생성에 적합하도록 전처리
    
    1단계: 패턴 기반 빠른 변환 (모든 씬)
    2단계: 변환 불가한 경우 원본 유지 (안전)
    
    ★ 원본 설명은 scene.description_original에 백업
    """
    for scene in scenes:
        desc = scene.scene_description or ""
        
        if not desc or not _has_problematic_content(desc):
            continue
        
        # 원본 백업
        if not scene.scene_description_original:
            scene.scene_description_original = desc
        
        # 패턴 기반 변환
        transformed = _quick_transform(desc)
        
        if transformed != desc:
            scene.scene_description = transformed
            logger.info(
                f"[전처리] 씬 {scene.scene_number}: "
                f"'{desc[:50]}...' → '{transformed[:50]}...'"
            )
    
    return scenes
