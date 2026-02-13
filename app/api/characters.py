"""
캐릭터 관리 API - 독립적인 캐릭터 CRUD
"""
import os
import base64
import logging
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.character_manager import CharacterManager

router = APIRouter(prefix="/api/characters", tags=["characters"])
logger = logging.getLogger(__name__)
mgr = CharacterManager()


# ── Request 모델 ──

class CreateCharacterRequest(BaseModel):
    name: str
    role: str = ""
    appearance: str = ""
    image_base64: Optional[str] = None  # data:image/...;base64,xxx


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    appearance: Optional[str] = None


class DuplicateCharacterRequest(BaseModel):
    new_name: str


# ── 엔드포인트 ──

@router.get("/list")
async def list_characters():
    """전체 캐릭터 목록"""
    characters = mgr.list_all()
    return {"success": True, "characters": characters}


@router.post("/create")
async def create_character(req: CreateCharacterRequest):
    """새 캐릭터 생성"""
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="캐릭터 이름을 입력하세요.")

    image_bytes = None
    if req.image_base64:
        try:
            # data:image/png;base64,xxx 형태 처리
            if "," in req.image_base64:
                image_bytes = base64.b64decode(req.image_base64.split(",", 1)[1])
            else:
                image_bytes = base64.b64decode(req.image_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"이미지 디코딩 실패: {e}")

    meta = mgr.create(
        name=req.name.strip(),
        role=req.role.strip(),
        appearance=req.appearance.strip(),
        image_bytes=image_bytes,
    )
    return {"success": True, "character": meta}


class BuildSheetRequest(BaseModel):
    char_ids: List[str]
    session_id: str = ""


@router.post("/build-sheet")
async def build_character_sheet(req: BuildSheetRequest):
    """여러 캐릭터 이미지를 합성하여 캐릭터 시트로 세션에 저장"""
    from app.services.reference_service import ReferenceService

    chars = mgr.build_character_sheet_from_selected(req.char_ids)
    if not chars:
        raise HTTPException(status_code=400, detail="이미지가 있는 캐릭터가 없습니다.")

    try:
        from PIL import Image
        import io

        images = []
        for c in chars:
            img = Image.open(io.BytesIO(c["image_bytes"]))
            images.append((img, c["name"], c.get("role", "")))

        # 가로 나열 합성
        total_w = sum(img.width for img, _, _ in images) + 20 * (len(images) - 1)
        max_h = max(img.height for img, _, _ in images)
        sheet = Image.new("RGB", (total_w, max_h), (255, 255, 255))

        x_offset = 0
        for img, name, role in images:
            sheet.paste(img, (x_offset, 0))
            x_offset += img.width + 20

        buf = io.BytesIO()
        sheet.save(buf, format="JPEG", quality=90)
        sheet_bytes = buf.getvalue()

        # 세션 레퍼런스로 저장
        if req.session_id:
            ref_svc = ReferenceService(req.session_id)
            ref_svc.save_reference("character", sheet_bytes)

        return {"success": True, "message": f"{len(chars)}명 캐릭터 시트 생성 완료"}
    except Exception as e:
        logger.error(f"캐릭터 시트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{char_id}")
async def get_character(char_id: str):
    """캐릭터 정보 조회"""
    meta = mgr.get(char_id)
    if not meta:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다.")
    return {"success": True, "character": meta}


@router.put("/{char_id}")
async def update_character(char_id: str, req: UpdateCharacterRequest):
    """캐릭터 정보 수정 (이름 변경 시 이전 이름은 별명에 자동 저장)"""
    try:
        meta = mgr.update(char_id, name=req.name, role=req.role, appearance=req.appearance)
        return {"success": True, "character": meta}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{char_id}")
async def delete_character(char_id: str):
    """캐릭터 삭제"""
    try:
        mgr.delete(char_id)
        return {"success": True, "message": "삭제 완료"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{char_id}/duplicate")
async def duplicate_character(char_id: str, req: DuplicateCharacterRequest):
    """캐릭터 복제 (같은 이미지, 다른 이름)"""
    try:
        meta = mgr.duplicate(char_id, req.new_name.strip())
        return {"success": True, "character": meta}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{char_id}/image")
async def get_character_image(char_id: str):
    """캐릭터 이미지 반환"""
    img_path = mgr.get_image_path(char_id)
    if not img_path:
        raise HTTPException(status_code=404, detail="이미지가 없습니다.")
    return FileResponse(img_path, media_type="image/jpeg")


@router.post("/{char_id}/image")
async def upload_character_image(char_id: str, file: UploadFile = File(...)):
    """캐릭터 이미지 업로드"""
    meta = mgr.get(char_id)
    if not meta:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다.")

    image_bytes = await file.read()
    mgr.save_image(char_id, image_bytes)
    return {"success": True, "message": "이미지 업로드 완료"}


@router.post("/{char_id}/image-base64")
async def upload_character_image_base64(char_id: str, data: dict):
    """캐릭터 이미지 base64 업로드"""
    meta = mgr.get(char_id)
    if not meta:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다.")

    image_b64 = data.get("image_base64", "")
    if not image_b64:
        raise HTTPException(status_code=400, detail="이미지 데이터가 없습니다.")

    try:
        if "," in image_b64:
            image_bytes = base64.b64decode(image_b64.split(",", 1)[1])
        else:
            image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미지 디코딩 실패: {e}")

    mgr.save_image(char_id, image_bytes)
    return {"success": True, "message": "이미지 업로드 완료"}
