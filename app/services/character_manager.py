"""
캐릭터 관리 서비스 (Character Manager)
=====================================
프리셋(화풍)과 독립적으로 캐릭터를 관리하는 모듈.

구조:
  app_data/characters/
    ├── {char_id}/
    │     ├── meta.json      # 이름, 역할, 별명, 외모 등
    │     └── character.jpg   # 캐릭터 레퍼런스 이미지
    └── ...

사용법:
  mgr = CharacterManager()
  mgr.create("전문가", role="세무사", appearance="30대 남성, 단발...")
  chars = mgr.list_all()
  mgr.rename("char_id", "노무사")
"""
import os
import json
import shutil
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# 캐릭터 저장 디렉토리
CHARACTERS_DIR = os.path.join("app_data", "characters")


class CharacterManager:
    """캐릭터 독립 관리 (프리셋과 분리)"""

    def __init__(self):
        os.makedirs(CHARACTERS_DIR, exist_ok=True)

    # ── CRUD ──

    def create(
        self,
        name: str,
        role: str = "",
        appearance: str = "",
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """새 캐릭터 생성"""
        char_id = f"{name.replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        char_dir = os.path.join(CHARACTERS_DIR, char_id)
        os.makedirs(char_dir, exist_ok=True)

        meta = {
            "id": char_id,
            "name": name,
            "role": role,
            "appearance": appearance,
            "aliases": [],  # 별명 목록 (예: "세무사" -> "노무사" 변경 이력)
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._save_meta(char_id, meta)

        if image_bytes:
            self._save_image(char_id, image_bytes)

        logger.info(f"[캐릭터] '{name}' 생성 완료 (ID: {char_id})")
        return meta

    def get(self, char_id: str) -> Optional[Dict[str, Any]]:
        """캐릭터 정보 조회"""
        meta = self._load_meta(char_id)
        if not meta:
            return None
        meta["has_image"] = self._has_image(char_id)
        return meta

    def list_all(self) -> List[Dict[str, Any]]:
        """전체 캐릭터 목록"""
        characters = []
        if not os.path.exists(CHARACTERS_DIR):
            return characters

        for char_id in sorted(os.listdir(CHARACTERS_DIR)):
            char_dir = os.path.join(CHARACTERS_DIR, char_id)
            if not os.path.isdir(char_dir) or char_id.startswith("."):
                continue
            meta = self._load_meta(char_id)
            if meta:
                meta["has_image"] = self._has_image(char_id)
                characters.append(meta)

        return characters

    def update(
        self,
        char_id: str,
        name: Optional[str] = None,
        role: Optional[str] = None,
        appearance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """캐릭터 정보 수정"""
        meta = self._load_meta(char_id)
        if not meta:
            raise ValueError(f"캐릭터를 찾을 수 없습니다: {char_id}")

        if name is not None and name != meta.get("name"):
            # 이름 변경 시 기존 이름을 별명에 추가
            old_name = meta.get("name", "")
            if old_name and old_name not in meta.get("aliases", []):
                meta.setdefault("aliases", []).append(old_name)
            meta["name"] = name

        if role is not None:
            meta["role"] = role
        if appearance is not None:
            meta["appearance"] = appearance

        meta["updated_at"] = datetime.now().isoformat()
        self._save_meta(char_id, meta)
        logger.info(f"[캐릭터] '{meta['name']}' 수정 완료")
        return meta

    def delete(self, char_id: str) -> bool:
        """캐릭터 삭제"""
        char_dir = os.path.join(CHARACTERS_DIR, char_id)
        if not os.path.isdir(char_dir):
            raise ValueError(f"캐릭터를 찾을 수 없습니다: {char_id}")

        shutil.rmtree(char_dir)
        logger.info(f"[캐릭터] '{char_id}' 삭제 완료")
        return True

    def duplicate(self, char_id: str, new_name: str) -> Dict[str, Any]:
        """캐릭터 복제 (같은 이미지, 다른 이름)"""
        meta = self._load_meta(char_id)
        if not meta:
            raise ValueError(f"캐릭터를 찾을 수 없습니다: {char_id}")

        image_bytes = self.load_image(char_id)
        new_meta = self.create(
            name=new_name,
            role=meta.get("role", ""),
            appearance=meta.get("appearance", ""),
            image_bytes=image_bytes,
        )
        logger.info(f"[캐릭터] '{meta['name']}' → '{new_name}' 복제 완료")
        return new_meta

    # ── 이미지 관리 ──

    def save_image(self, char_id: str, image_bytes: bytes) -> str:
        """캐릭터 이미지 저장"""
        return self._save_image(char_id, image_bytes)

    def load_image(self, char_id: str) -> Optional[bytes]:
        """캐릭터 이미지 로드"""
        img_path = os.path.join(CHARACTERS_DIR, char_id, "character.jpg")
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                return f.read()
        return None

    def get_image_path(self, char_id: str) -> Optional[str]:
        """캐릭터 이미지 경로"""
        img_path = os.path.join(CHARACTERS_DIR, char_id, "character.jpg")
        return img_path if os.path.exists(img_path) else None

    # ── 스토리 연동 ──

    def get_names_for_story(self, char_ids: List[str]) -> str:
        """선택된 캐릭터 ID 목록 → 쉼표 구분 이름 문자열"""
        names = []
        for cid in char_ids:
            meta = self._load_meta(cid)
            if meta:
                names.append(meta["name"])
        return ", ".join(names)

    def build_character_sheet_from_selected(
        self, char_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """선택된 캐릭터들의 이미지+이름 조합 (캐릭터 시트 합성용)"""
        result = []
        for cid in char_ids:
            meta = self._load_meta(cid)
            img = self.load_image(cid)
            if meta and img:
                result.append({
                    "id": cid,
                    "name": meta["name"],
                    "role": meta.get("role", ""),
                    "image_bytes": img,
                })
        return result

    # ── 내부 유틸 ──

    def _meta_path(self, char_id: str) -> str:
        return os.path.join(CHARACTERS_DIR, char_id, "meta.json")

    def _load_meta(self, char_id: str) -> Optional[Dict[str, Any]]:
        path = self._meta_path(char_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_meta(self, char_id: str, meta: Dict[str, Any]):
        path = self._meta_path(char_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _save_image(self, char_id: str, image_bytes: bytes) -> str:
        img_path = os.path.join(CHARACTERS_DIR, char_id, "character.jpg")
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        return img_path

    def _has_image(self, char_id: str) -> bool:
        return os.path.exists(
            os.path.join(CHARACTERS_DIR, char_id, "character.jpg")
        )
