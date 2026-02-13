"""
레퍼런스 이미지 서비스 — 3종 레퍼런스(Character/Method/Style) 관리
3종 레퍼런스 체이닝 기반 캐릭터 일관성 시스템
"""
import os
import json
import shutil
import uuid
import logging
import asyncio
import time
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# 레퍼런스 이미지 저장 기본 디렉토리
REFERENCE_BASE_DIR = os.path.join("app_data", "reference")

# 프리셋 디렉토리 (이중 구조)
# 빌트인: 프로그램과 함께 배포되는 기본 프리셋 (app/presets/)
# 사용자: 런타임에 사용자가 만드는 커스텀 프리셋 (app_data/reference_presets/)
BUILTIN_PRESET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "presets")
USER_PRESET_DIR = os.path.join("app_data", "reference_presets")
# 하위 호환 alias
PRESET_BASE_DIR = USER_PRESET_DIR

# 허용되는 레퍼런스 타입
VALID_TYPES = {"character", "method", "style"}

# 파일명 매핑
TYPE_TO_FILENAME = {
    "character": "character.jpg",
    "method": "method.jpg",
    "style": "style.jpg",
}


class ReferenceService:
    """3종 레퍼런스 이미지 관리 및 AI 생성 서비스"""

    def __init__(self, session_id: Optional[str] = None):
        """
        session_id가 있으면 세션별 레퍼런스, 없으면 글로벌 레퍼런스 사용
        """
        if session_id:
            self.ref_dir = os.path.join(REFERENCE_BASE_DIR, "sessions", session_id)
        else:
            self.ref_dir = os.path.join(REFERENCE_BASE_DIR, "global")
        os.makedirs(self.ref_dir, exist_ok=True)

    # ============================================
    # 모델명 매핑
    # ============================================

    _MODEL_NAME_MAP = {
        "nano-banana": "gemini-2.5-flash-image",
        "nano-banana-pro": "gemini-3-pro-image-preview",
    }

    def _resolve_model_name(self, model_name: str) -> str:
        """UI 모델명을 실제 Gemini API 모델명으로 변환"""
        return self._MODEL_NAME_MAP.get(model_name, model_name)

    @staticmethod
    def _extract_image_bytes(raw_data) -> bytes:
        """Gemini inline_data.data에서 실제 이미지 바이트를 추출.
        
        Google GenAI SDK 버전에 따라 raw bytes 또는 base64 문자열이 반환될 수 있음.
        두 경우 모두 올바르게 처리하여 항상 raw 이미지 bytes를 반환.
        """
        import base64 as b64mod

        # str인 경우 → base64 디코딩
        if isinstance(raw_data, str):
            logger.debug(f"[_extract_image_bytes] str 타입 수신, 길이={len(raw_data)}, 시작={raw_data[:20]}")
            return b64mod.b64decode(raw_data)

        # bytes인 경우
        if isinstance(raw_data, (bytes, bytearray)):
            # 이미 raw 이미지인지 시그니처로 확인
            # JPEG: ff d8, PNG: 89 50 4e 47, WEBP: 52 49 46 46...57 45 42 50, GIF: 47 49 46 38
            if len(raw_data) > 4:
                if raw_data[0] == 0xFF and raw_data[1] == 0xD8:
                    logger.debug("[_extract_image_bytes] 이미 raw JPEG bytes")
                    return bytes(raw_data)
                if raw_data[:4] == b'\x89PNG':
                    logger.debug("[_extract_image_bytes] 이미 raw PNG bytes")
                    return bytes(raw_data)
                if len(raw_data) > 12 and raw_data[8:12] == b'WEBP':
                    logger.debug("[_extract_image_bytes] 이미 raw WEBP bytes")
                    return bytes(raw_data)

            # raw 이미지가 아니면 base64 텍스트일 가능성이 높음
            try:
                text = raw_data.decode('ascii')
                decoded = b64mod.b64decode(text)
                logger.debug(f"[_extract_image_bytes] base64 bytes 디코딩 성공: {len(raw_data)} → {len(decoded)} bytes")
                return decoded
            except (UnicodeDecodeError, Exception) as e:
                logger.debug(f"[_extract_image_bytes] base64 디코딩 실패, raw 반환: {e}")
                return bytes(raw_data)

        logger.warning(f"[_extract_image_bytes] 예상 외 타입: {type(raw_data)}")
        return raw_data if raw_data else b""

    # ============================================
    # 파일 관리
    # ============================================

    def _get_path(self, ref_type: str) -> str:
        """레퍼런스 타입에 해당하는 파일 경로 반환"""
        if ref_type not in VALID_TYPES:
            raise ValueError(f"유효하지 않은 레퍼런스 타입: {ref_type}. 허용: {VALID_TYPES}")
        return os.path.join(self.ref_dir, TYPE_TO_FILENAME[ref_type])

    def save_reference(self, ref_type: str, image_bytes: bytes) -> str:
        """레퍼런스 이미지 저장"""
        file_path = self._get_path(ref_type)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"[레퍼런스] {ref_type} 이미지 저장 완료: {file_path}")
        return file_path

    def load_reference(self, ref_type: str) -> Optional[bytes]:
        """레퍼런스 이미지 로드 (없으면 None)"""
        file_path = self._get_path(ref_type)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return f.read()
        return None

    def delete_reference(self, ref_type: str) -> bool:
        """레퍼런스 이미지 삭제"""
        file_path = self._get_path(ref_type)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"[레퍼런스] {ref_type} 이미지 삭제: {file_path}")
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """3종 레퍼런스 존재 여부 및 경로 반환"""
        status = {}
        for ref_type in VALID_TYPES:
            file_path = self._get_path(ref_type)
            exists = os.path.exists(file_path)
            status[ref_type] = {
                "exists": exists,
                "path": file_path if exists else None,
                "size": os.path.getsize(file_path) if exists else 0,
            }
        return status

    def get_reference_path(self, ref_type: str) -> Optional[str]:
        """레퍼런스 이미지 경로 반환 (없으면 None)"""
        file_path = self._get_path(ref_type)
        return file_path if os.path.exists(file_path) else None

    # ============================================
    # AI 생성 (Gemini 사용)
    # ============================================

    async def generate_character(self, prompt: str, gemini_api_key: str,
                                  model_name: str = "gemini-3-pro-image-preview",
                                  style_image_bytes: Optional[bytes] = None) -> bytes:
        """텍스트 프롬프트로 캐릭터 레퍼런스 이미지 AI 생성
        
        style_image_bytes가 있으면 해당 화풍을 그대로 따라하여
        같은 프리셋 내 여러 캐릭터의 아트 스타일 일관성을 보장
        """
        if style_image_bytes:
            # 스타일 참조 이미지가 있는 경우: 해당 화풍으로 생성 (화풍 일관성 보장)
            full_prompt = f"""다음 프롬프트에 따라 캐릭터 레퍼런스 이미지를 생성해주세요.

{prompt}

**중요 지시사항:**
- 반드시 아래 첨부된 스타일 참조 이미지의 화풍/그림체/선화 스타일/채색 방식/색상 팔레트를 그대로 따라해주세요.
- 마치 같은 작가가 그린 것처럼 아트 스타일이 동일해야 합니다.
- 단색 배경(녹색 #00FF00, 흰색, 또는 밝은 회색)을 사용하세요.
- 캐릭터의 전신이 머리부터 발끝까지 완전히 보이도록 하세요.
- 캐릭터가 정면을 바라보는 자연스러운 포즈로 그려주세요.
- 얼굴 특징(눈 색, 머리 색/스타일), 의상 디테일, 액세서리를 명확하게 표현하세요.
- 반드시 1:1 정사각형 비율의 이미지로 생성해주세요.
- 이미지에 텍스트, 글자, 문자를 절대 넣지 마세요.
"""
            return await self._generate_with_character_ref(
                full_prompt, style_image_bytes, gemini_api_key, model_name
            )
        else:
            # 스타일 참조 이미지가 없는 경우: 자유롭게 생성
            full_prompt = f"""다음 프롬프트에 따라 캐릭터 레퍼런스 이미지를 생성해주세요.

{prompt}

**중요 지시사항:**
- 단색 배경(녹색 #00FF00, 흰색, 또는 밝은 회색)을 사용하세요.
- 캐릭터의 전신이 머리부터 발끝까지 완전히 보이도록 하세요.
- 캐릭터가 정면을 바라보는 자연스러운 포즈로 그려주세요.
- 얼굴 특징(눈 색, 머리 색/스타일), 의상 디테일, 액세서리를 명확하게 표현하세요.
- 캐릭터 디자인 시트 스타일로, 깨끗하고 선명한 선화로 그려주세요.
- 배경에 어떤 장식이나 요소도 넣지 마세요. 순수하게 캐릭터만 그려주세요.
- 반드시 1:1 정사각형 비율의 이미지로 생성해주세요.
- 이미지에 텍스트, 글자, 문자를 절대 넣지 마세요.
"""
            return await self._generate_text_to_image(full_prompt, gemini_api_key, model_name)

    async def generate_method(self, prompt: str, gemini_api_key: str,
                               model_name: str = "nano-banana-pro") -> bytes:
        """Method.jpg(구도/연출 레퍼런스) AI 생성 — Character.jpg 있으면 참조"""
        character_bytes = self.load_reference("character")

        full_prompt = f"""다음 프롬프트에 따라 구도/연출 레퍼런스 이미지를 생성해주세요.

{prompt}

**중요 지시사항:**
{('- 첨부된 캐릭터 레퍼런스 이미지의 캐릭터를 그대로 사용하세요.' + chr(10) + '- 캐릭터 외형(얼굴, 헤어스타일, 의상, 체형)을 정확히 유지하세요.' + chr(10) + '- ⚠️ 화풍/그림체 일관성: 첨부된 캐릭터 이미지와 동일한 아트 스타일(선화 굵기, 채색 방식, 그림체)로 그려주세요. 절대 다른 화풍으로 그리지 마세요.' + chr(10)) if character_bytes else ''}
- 다양한 카메라 앵글(전신, 클로즈업, 뒷모습, 디테일 샷)을 보여주세요.
- 여러 컷(4~6컷)으로 나눠진 만화/웹툰 형태의 구도를 보여주세요.
- 컷 사이에 검은 테두리로 구분하세요.
- 반드시 1:1 정사각형 비율의 이미지로 생성해주세요.
- 이미지에 텍스트, 글자, 문자를 절대 넣지 마세요.
"""
        if character_bytes:
            return await self._generate_with_character_ref(full_prompt, character_bytes,
                                                            gemini_api_key, model_name)
        else:
            return await self._generate_text_to_image(full_prompt, gemini_api_key, model_name)

    async def generate_style(self, prompt: str, gemini_api_key: str,
                              model_name: str = "nano-banana-pro") -> bytes:
        """Style.jpg(화풍 레퍼런스) AI 생성 — Character + Method 있으면 모두 참조"""
        character_bytes = self.load_reference("character")
        method_bytes = self.load_reference("method")

        # 참조 이미지 설명 구성
        ref_instructions = ""
        if character_bytes:
            ref_instructions += "- 첨부된 '캐릭터 레퍼런스' 이미지의 캐릭터를 그대로 사용하세요.\n"
            ref_instructions += "- ⚠️ 화풍/그림체 일관성: 첨부된 캐릭터 이미지와 완전히 동일한 아트 스타일(선화 굵기, 채색 방식, 그림체, 색상 팔레트)로 그려주세요.\n"
        if method_bytes:
            ref_instructions += "- 첨부된 '연출 레퍼런스' 이미지의 구도/앵글 스타일을 참고하세요.\n"

        full_prompt = f"""다음 프롬프트에 따라 화풍 레퍼런스 이미지를 생성해주세요.

{prompt}

**중요 지시사항:**
{ref_instructions if ref_instructions else ''}
- 아트 스타일(색감, 선화 스타일, 질감, 분위기)을 명확하게 보여주세요.
- 배경 디테일이 풍부한 완성된 일러스트레이션으로 그려주세요.
- 전체적인 화풍과 색감이 잘 드러나는 구도를 사용하세요.
- 반드시 1:1 정사각형 비율의 이미지로 생성해주세요.
- 이미지에 텍스트, 글자, 문자를 절대 넣지 마세요.
"""
        # 참조 이미지 수에 따라 멀티 이미지 전송
        ref_images = []
        if character_bytes:
            ref_images.append(("캐릭터 레퍼런스", character_bytes))
        if method_bytes:
            ref_images.append(("연출 레퍼런스", method_bytes))

        if ref_images:
            return await self._generate_with_multi_ref(full_prompt, ref_images,
                                                        gemini_api_key, model_name)
        else:
            return await self._generate_text_to_image(full_prompt, gemini_api_key, model_name)

    async def generate_character_sheet(
        self,
        characters: List[Dict[str, Any]],
        gemini_api_key: str,
        model_name: str = "nano-banana-pro"
    ) -> bytes:
        """다중 캐릭터 이미지를 합성하여 캐릭터 레퍼런스 시트 생성
        
        characters: [{"name": "이름", "image_data": bytes}, ...]
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Google GenAI 라이브러리가 설치되지 않았습니다.")

        actual_model = self._resolve_model_name(model_name)
        client = genai.Client(api_key=gemini_api_key)

        # 캐릭터 이름 목록
        name_list = "\n".join(
            f'Character {i+1}: "{c["name"]}"'
            for i, c in enumerate(characters)
        )

        prompt = f"""Create a single character reference sheet image combining all the provided character images.

**Requirements:**
- Place each character's name ABOVE their image in large, bold text (at least 20px equivalent, clearly readable)
- Use a solid color background (light gray #F0F0F0 or similar neutral tone)
- Arrange characters side by side in a single row if 4 or fewer, otherwise use a grid layout
- Each character should be clearly separated with adequate spacing
- Keep the original character appearance exactly as provided - do not modify their design
- The text/name labels must be clearly visible and positioned directly above each character image
- Clean, professional layout suitable for a character reference sheet

**Character Names (in order):**
{name_list}

Please generate this character reference sheet image."""

        # 멀티모달 파츠 구성
        from PIL import Image
        import io

        contents = [prompt]
        for char in characters:
            img = Image.open(io.BytesIO(char["image_data"]))
            contents.append(img)
            contents.append(f'(위 이미지의 캐릭터 이름: "{char["name"]}")')

        def _sync_generate():
            return client.models.generate_content(
                model=actual_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    # 일관성 보장: 항상 TEXT + IMAGE 모두 허용
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_generate),
            timeout=120
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = self._extract_image_bytes(part.inline_data.data)
                    # Character.jpg로 저장
                    self.save_reference("character", image_bytes)
                    logger.info("[레퍼런스] 캐릭터 레퍼런스 시트 AI 생성 및 저장 완료")
                    return image_bytes

        raise ValueError("Gemini 응답에서 이미지를 찾을 수 없습니다.")

    async def _generate_text_to_image(
        self,
        prompt: str,
        gemini_api_key: str,
        model_name: str
    ) -> bytes:
        """텍스트만으로 이미지 생성 (캐릭터 참조 없음)"""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Google GenAI 라이브러리가 설치되지 않았습니다.")

        actual_model = self._resolve_model_name(model_name)
        client = genai.Client(api_key=gemini_api_key)

        def _sync_generate():
            return client.models.generate_content(
                model=actual_model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_generate),
            timeout=120
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return self._extract_image_bytes(part.inline_data.data)

        raise ValueError("Gemini 응답에서 이미지를 찾을 수 없습니다.")

    async def _generate_with_multi_ref(
        self,
        prompt: str,
        ref_images: List[tuple],  # [(label, bytes), ...]
        gemini_api_key: str,
        model_name: str
    ) -> bytes:
        """여러 참조 이미지를 동시에 전송하여 이미지 생성
        
        각 이미지 앞에 라벨 텍스트를 삽입하여
        AI가 각 참조 이미지의 역할(캐릭터/연출/스타일)을 명확히 구분하도록 함
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Google GenAI 라이브러리가 설치되지 않았습니다.")

        from PIL import Image
        import io

        actual_model = self._resolve_model_name(model_name)
        client = genai.Client(api_key=gemini_api_key)

        contents = [prompt]
        for label, img_bytes in ref_images:
            # 레퍼런스 체이닝: 각 이미지 앞에 설명 라벨 삽입
            contents.append(f"(아래는 {label} 이미지입니다. 이 이미지의 화풍과 특징을 참고하세요.)")
            img = Image.open(io.BytesIO(img_bytes))
            contents.append(img)

        def _sync_generate():
            return client.models.generate_content(
                model=actual_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_generate),
            timeout=120
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return self._extract_image_bytes(part.inline_data.data)

        raise ValueError("Gemini 응답에서 이미지를 찾을 수 없습니다.")

    async def _generate_with_character_ref(
        self,
        prompt: str,
        character_bytes: bytes,
        gemini_api_key: str,
        model_name: str
    ) -> bytes:
        """Character.jpg를 참조하여 이미지 생성 (Method/Style 공통 로직)
        
        이미지 앞에 설명 라벨 텍스트를 삽입하여
        AI가 참조 이미지의 역할을 명확히 인식하도록 함
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Google GenAI 라이브러리가 설치되지 않았습니다.")

        from PIL import Image
        import io

        actual_model = self._resolve_model_name(model_name)
        client = genai.Client(api_key=gemini_api_key)
        char_img = Image.open(io.BytesIO(character_bytes))

        # 레퍼런스 체이닝: 이미지 앞에 라벨 텍스트 삽입
        contents = [
            prompt,
            "(중요: 반드시 1:1 정사각형 비율의 이미지로 생성해주세요. 가로와 세로 길이가 동일해야 합니다.)",
            "(아래는 Character.jpg 캐릭터 레퍼런스 이미지입니다. 이 캐릭터의 화풍과 특징을 참고하세요.)",
            char_img
        ]

        def _sync_generate():
            return client.models.generate_content(
                model=actual_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_generate),
            timeout=120
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return self._extract_image_bytes(part.inline_data.data)

        raise ValueError("Gemini 응답에서 이미지를 찾을 수 없습니다.")

    # ============================================
    # 프리셋 관리
    # ============================================

    # ── 프리셋 내부 유틸 ──

    @staticmethod
    def _scan_preset_dir(base_dir: str, source: str) -> List[Dict[str, Any]]:
        """특정 디렉토리의 프리셋 목록을 스캔"""
        presets = []
        if not os.path.exists(base_dir):
            return presets

        for preset_id in sorted(os.listdir(base_dir)):
            preset_dir = os.path.join(base_dir, preset_id)
            if not os.path.isdir(preset_dir):
                continue
            # .gitkeep 등 파일 무시
            if preset_id.startswith("."):
                continue

            meta_path = os.path.join(preset_dir, "meta.json")
            meta = {"name": preset_id, "description": ""}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    pass

            has_files = {
                t: os.path.exists(os.path.join(preset_dir, TYPE_TO_FILENAME[t]))
                for t in VALID_TYPES
            }
            has_output = os.path.exists(os.path.join(preset_dir, "output.jpg"))

            presets.append({
                "id": preset_id,
                "name": meta.get("name", preset_id),
                "description": meta.get("description", ""),
                "character_names": meta.get("character_names", []),
                "has_character": has_files["character"],
                "has_method": has_files["method"],
                "has_style": has_files["style"],
                "has_output": has_output,
                "source": source,  # "builtin" 또는 "user"
            })

        return presets

    @staticmethod
    def _find_preset_dir(preset_id: str) -> Optional[str]:
        """프리셋 ID로 실제 디렉토리 경로 반환 (빌트인 우선 → 사용자)"""
        for base in [BUILTIN_PRESET_DIR, USER_PRESET_DIR]:
            d = os.path.join(base, preset_id)
            if os.path.isdir(d):
                return d
        return None

    @staticmethod
    def list_presets() -> List[Dict[str, Any]]:
        """빌트인 + 사용자 프리셋 목록 조회 (빌트인 먼저)"""
        os.makedirs(BUILTIN_PRESET_DIR, exist_ok=True)
        os.makedirs(USER_PRESET_DIR, exist_ok=True)

        builtin = ReferenceService._scan_preset_dir(BUILTIN_PRESET_DIR, "builtin")
        user = ReferenceService._scan_preset_dir(USER_PRESET_DIR, "user")
        return builtin + user

    def apply_preset(self, preset_id: str) -> bool:
        """프리셋의 3종 레퍼런스를 현재 디렉토리에 복사 (빌트인/사용자 모두 지원)"""
        preset_dir = self._find_preset_dir(preset_id)
        if not preset_dir:
            raise ValueError(f"프리셋을 찾을 수 없습니다: {preset_id}")

        copied = 0
        for ref_type in VALID_TYPES:
            src = os.path.join(preset_dir, TYPE_TO_FILENAME[ref_type])
            if os.path.exists(src):
                dst = self._get_path(ref_type)
                shutil.copy2(src, dst)
                copied += 1
                logger.info(f"[프리셋] {preset_id}/{ref_type} → {dst}")

        logger.info(f"[프리셋] '{preset_id}' 적용 완료 ({copied}개 파일)")
        return copied > 0

    def save_as_preset(self, name: str, description: str = "",
                       character_names: Optional[List[str]] = None) -> str:
        """현재 레퍼런스 3종을 사용자 프리셋으로 저장
        
        Args:
            name: 프리셋 이름
            description: 프리셋 설명
            character_names: 캐릭터 이름 목록 (예: ["전문가", "채범", "소미"])
        """
        preset_id = f"{name.replace(' ', '_').lower()}_{uuid.uuid4().hex[:6]}"
        preset_dir = os.path.join(USER_PRESET_DIR, preset_id)
        os.makedirs(preset_dir, exist_ok=True)

        saved = 0
        for ref_type in VALID_TYPES:
            src = self._get_path(ref_type)
            if os.path.exists(src):
                dst = os.path.join(preset_dir, TYPE_TO_FILENAME[ref_type])
                shutil.copy2(src, dst)
                saved += 1

        # 메타 정보 저장 (character_names 포함)
        meta = {
            "name": name,
            "description": description,
            "character_names": character_names or [],
            "source": "user"
        }
        with open(os.path.join(preset_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"[프리셋] '{name}' 저장 완료 (ID: {preset_id}, {saved}개 파일, "
                    f"캐릭터: {character_names})")
        return preset_id

    @staticmethod
    def delete_preset(preset_id: str) -> bool:
        """사용자 프리셋 삭제 (빌트인은 삭제 불가)"""
        # 빌트인 프리셋인지 확인
        builtin_dir = os.path.join(BUILTIN_PRESET_DIR, preset_id)
        if os.path.isdir(builtin_dir):
            raise ValueError("기본 내장 프리셋은 삭제할 수 없습니다.")

        user_dir = os.path.join(USER_PRESET_DIR, preset_id)
        if not os.path.isdir(user_dir):
            raise ValueError(f"프리셋을 찾을 수 없습니다: {preset_id}")

        shutil.rmtree(user_dir)
        logger.info(f"[프리셋] '{preset_id}' 삭제 완료")
        return True

    # ============================================
    # 모델별 레퍼런스 적용
    # ============================================

    def load_for_model(self, model_name: str = "") -> Dict[str, Optional[bytes]]:
        """레퍼런스 이미지 3종을 모두 로드하여 반환
        
        Gemini 3.0 Preview로 모델 고정이므로 항상 3장 전부 반환.
        3종 레퍼런스 체이닝: Character + Method + Style 항상 첨부
        """
        return {
            "character": self.load_reference("character"),
            "method": self.load_reference("method"),
            "style": self.load_reference("style"),
        }

    @staticmethod
    def get_model_reference_info(model_name: str = "") -> Dict[str, str]:
        """레퍼런스 사용 방식 안내 텍스트 반환 (Gemini 고정)"""
        return {
            "level": "full",
            "message": "Gemini 3.0 Preview는 3종 레퍼런스(캐릭터/연출/화풍)를 모두 활용합니다.",
            "supports": ["character", "method", "style"],
        }

    # ============================================
    # 테스트 미리보기
    # ============================================

    async def generate_test_preview(
        self,
        model_name: str,
        gemini_api_key: str,
        prompt: str = "두 캐릭터가 카페에서 대화하는 따뜻한 장면"
    ) -> bytes:
        """현재 레퍼런스로 테스트 이미지 1장 생성"""
        refs = self.load_for_model(model_name)
        model_lower = model_name.lower() if model_name else ""

        # Gemini 계열: 3종 레퍼런스 + 프롬프트
        if any(k in model_lower for k in ["gemini", "nano-banana"]):
            return await self._test_preview_gemini(refs, prompt, gemini_api_key, model_name)

        # 그 외: Character만 참조 가능하면 Gemini로 대체 생성
        if refs.get("character"):
            return await self._test_preview_gemini(refs, prompt, gemini_api_key,
                                                    "nano-banana-pro")

        raise ValueError("테스트 미리보기를 위한 레퍼런스 이미지가 없습니다.")

    async def _test_preview_gemini(
        self,
        refs: Dict[str, Optional[bytes]],
        prompt: str,
        gemini_api_key: str,
        model_name: str
    ) -> bytes:
        """Gemini로 테스트 미리보기 생성"""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Google GenAI 라이브러리가 설치되지 않았습니다.")

        from PIL import Image
        import io

        client = genai.Client(api_key=gemini_api_key)

        # 프롬프트 구성
        full_prompt = f"""다음 장면을 이미지로 생성해주세요:

{prompt}

**참조 이미지 정보:**
"""
        ref_descriptions = []
        if refs.get("character"):
            ref_descriptions.append("- 첫 번째 이미지(Character)는 캐릭터 레퍼런스입니다. 이 캐릭터의 외형과 특징을 정확히 유지하세요.")
        if refs.get("method"):
            ref_descriptions.append("- 두 번째 이미지(Method)는 연출 레퍼런스입니다. 이 구도와 연출 방식을 참고하세요.")
        if refs.get("style"):
            ref_descriptions.append("- 세 번째 이미지(Style)는 화풍 레퍼런스입니다. 이 색감, 선화 스타일, 분위기를 반드시 적용하세요.")

        full_prompt += "\n".join(ref_descriptions)

        # 콘텐츠 구성
        contents = [full_prompt]
        for ref_type in ["character", "method", "style"]:
            if refs.get(ref_type):
                img = Image.open(io.BytesIO(refs[ref_type]))
                contents.append(img)

        actual_model = self._resolve_model_name(model_name)

        def _sync_generate():
            return client.models.generate_content(
                model=actual_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_generate),
            timeout=120
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return self._extract_image_bytes(part.inline_data.data)

        raise ValueError("테스트 미리보기 생성 실패: Gemini 응답에서 이미지를 찾을 수 없습니다.")
