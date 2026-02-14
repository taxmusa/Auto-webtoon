"""
레퍼런스 이미지 API — 3종 레퍼런스(Character/Method/Style) 관리 엔드포인트
"""
import os
import io
import base64
import logging
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.services.reference_service import ReferenceService, VALID_TYPES
from app.core.config import get_settings

router = APIRouter(prefix="/api/reference", tags=["reference"])
logger = logging.getLogger(__name__)


def _mime_from_bytes(image_bytes: bytes) -> str:
    """이미지 바이트에서 실제 포맷 감지 → data URL MIME 타입 반환"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        fmt = (img.format or "PNG").upper()
        mime_map = {"PNG": "image/png", "JPEG": "image/jpeg", "JPG": "image/jpeg",
                    "WEBP": "image/webp", "GIF": "image/gif"}
        return mime_map.get(fmt, f"image/{fmt.lower()}")
    except Exception:
        return "image/png"


# ============================================
# Request/Response 모델
# ============================================

class GenerateRefRequest(BaseModel):
    """Character/Method/Style AI 생성 요청"""
    prompt: str
    session_id: Optional[str] = None
    model_name: str = "nano-banana-pro"
    character_name: Optional[str] = None   # 캐릭터 이름 (후처리 합성용)
    character_role: Optional[str] = None   # 캐릭터 역할 (후처리 합성용)
    style_image_base64: Optional[str] = None  # 스타일 참조 이미지 (같은 화풍으로 캐릭터 생성)


class CharacterSheetCharacter(BaseModel):
    """캐릭터 시트 생성용 개별 캐릭터"""
    name: str
    image_data: str  # base64 data URL


class GenerateCharacterSheetRequest(BaseModel):
    """캐릭터 레퍼런스 시트 생성 요청"""
    characters: List[CharacterSheetCharacter]
    session_id: Optional[str] = None
    model_name: str = "nano-banana-pro"


class SavePresetRequest(BaseModel):
    """프리셋 저장 요청"""
    name: str
    description: str = ""
    character_names: List[str] = []  # 캐릭터 이름 목록 (예: ["전문가", "채범", "소미"])
    session_id: Optional[str] = None


class ApplyPresetRequest(BaseModel):
    """프리셋 적용 요청"""
    session_id: Optional[str] = None


class TestPreviewRequest(BaseModel):
    """테스트 미리보기 요청"""
    model_name: str = "nano-banana-pro"
    prompt: str = "두 캐릭터가 카페에서 대화하는 따뜻한 장면"
    session_id: Optional[str] = None


class StatusRequest(BaseModel):
    """상태 조회용"""
    model_name: str = "flux-kontext-dev"


# ============================================
# 레퍼런스 CRUD
# ============================================

@router.get("/{ref_type}")
async def get_reference_image(ref_type: str, session_id: Optional[str] = None):
    """레퍼런스 이미지 조회 (파일 직접 반환)"""
    if ref_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 타입: {ref_type}")

    service = ReferenceService(session_id)
    file_path = service.get_reference_path(ref_type)

    if not file_path:
        raise HTTPException(status_code=404, detail=f"{ref_type} 레퍼런스 이미지가 없습니다.")

    return FileResponse(file_path, media_type="image/jpeg")


@router.post("/upload/{ref_type}")
async def upload_reference_image(
    ref_type: str,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None)
):
    """레퍼런스 이미지 업로드"""
    if ref_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 타입: {ref_type}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    service = ReferenceService(session_id)
    saved_path = service.save_reference(ref_type, image_bytes)

    return {
        "success": True,
        "message": f"{ref_type} 레퍼런스 이미지 업로드 완료",
        "path": saved_path,
    }


@router.delete("/{ref_type}")
async def delete_reference_image(ref_type: str, session_id: Optional[str] = None):
    """레퍼런스 이미지 삭제"""
    if ref_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 타입: {ref_type}")

    service = ReferenceService(session_id)
    deleted = service.delete_reference(ref_type)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"{ref_type} 레퍼런스 이미지가 없습니다.")

    return {"success": True, "message": f"{ref_type} 레퍼런스 이미지 삭제 완료"}


# ============================================
# AI 생성
# ============================================

@router.post("/generate-character")
async def generate_character_image(req: GenerateRefRequest):
    """텍스트 프롬프트로 캐릭터 레퍼런스 이미지 AI 생성 + 이름 후처리 합성"""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

    service = ReferenceService(req.session_id)
    try:
        # 스타일 참조 이미지 디코딩 (같은 화풍으로 2번째+ 캐릭터 생성)
        style_bytes = None
        if req.style_image_base64:
            import re
            match = re.match(r"^data:image/\w+;base64,(.+)$", req.style_image_base64)
            if match:
                style_bytes = base64.b64decode(match.group(1))
            else:
                style_bytes = base64.b64decode(req.style_image_base64)

        image_bytes = await service.generate_character(
            prompt=req.prompt,
            gemini_api_key=settings.gemini_api_key,
            model_name=req.model_name,
            style_image_bytes=style_bytes
        )

        # 이름/역할이 있으면 Pillow로 이미지 상단에 텍스트 후처리 합성
        char_name = (req.character_name or "").strip()
        char_role = (req.character_role or "").strip()
        if char_name:
            image_bytes = ReferenceService.overlay_character_name(
                image_bytes, char_name, char_role
            )

        # Character.jpg로 저장
        service.save_reference("character", image_bytes)

        b64 = base64.b64encode(image_bytes).decode()
        mime = _mime_from_bytes(image_bytes)
        return {
            "success": True,
            "message": "캐릭터 레퍼런스 생성 완료",
            "image_base64": f"data:{mime};base64,{b64}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[레퍼런스] Character 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"캐릭터 레퍼런스 생성 실패: {str(e)}")


@router.post("/generate-method")
async def generate_method_image(req: GenerateRefRequest):
    """Character.jpg 기반으로 Method.jpg(구도/연출) AI 생성"""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

    service = ReferenceService(req.session_id)
    try:
        image_bytes = await service.generate_method(
            prompt=req.prompt,
            gemini_api_key=settings.gemini_api_key,
            model_name=req.model_name
        )
        # Method.jpg로 저장
        service.save_reference("method", image_bytes)

        # base64로 반환
        b64 = base64.b64encode(image_bytes).decode()
        mime = _mime_from_bytes(image_bytes)
        return {
            "success": True,
            "message": "Method 레퍼런스 생성 완료",
            "image_base64": f"data:{mime};base64,{b64}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[레퍼런스] Method 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Method 레퍼런스 생성 실패: {str(e)}")


@router.post("/generate-style")
async def generate_style_image(req: GenerateRefRequest):
    """Character.jpg 기반으로 Style.jpg(화풍) AI 생성"""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

    session_id = req.session_id or ""
    service = ReferenceService(session_id)
    try:
        image_bytes = await service.generate_style(
            prompt=req.prompt,
            gemini_api_key=settings.gemini_api_key,
            model_name=req.model_name
        )
        if not image_bytes or len(image_bytes) < 100:
            raise ValueError("AI가 반환한 이미지가 비어 있거나 손상되었습니다.")
        # Style.jpg로 저장
        service.save_reference("style", image_bytes)

        b64 = base64.b64encode(image_bytes).decode()
        mime = _mime_from_bytes(image_bytes)
        return {
            "success": True,
            "message": "Style 레퍼런스 생성 완료",
            "image_base64": f"data:{mime};base64,{b64}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[레퍼런스] Style 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Style 레퍼런스 생성 실패: {str(e)}")


@router.post("/generate-character-sheet")
async def generate_character_sheet(req: GenerateCharacterSheetRequest):
    """다중 캐릭터 이미지를 합성하여 캐릭터 레퍼런스 시트 생성"""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

    if not req.characters or len(req.characters) == 0:
        raise HTTPException(status_code=400, detail="캐릭터 데이터가 필요합니다.")

    service = ReferenceService(req.session_id)

    # base64 데이터 URL → bytes 변환
    characters_data = []
    for char in req.characters:
        try:
            # "data:image/png;base64,..." 형태에서 데이터 추출
            if "," in char.image_data:
                b64_data = char.image_data.split(",", 1)[1]
            else:
                b64_data = char.image_data
            image_bytes = base64.b64decode(b64_data)
            characters_data.append({"name": char.name, "image_data": image_bytes})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"캐릭터 '{char.name}' 이미지 디코딩 실패: {e}")

    try:
        image_bytes = await service.generate_character_sheet(
            characters=characters_data,
            gemini_api_key=settings.gemini_api_key,
            model_name=req.model_name
        )

        b64 = base64.b64encode(image_bytes).decode()
        return {
            "success": True,
            "message": f"캐릭터 레퍼런스 시트 생성 완료 ({len(req.characters)}명)",
            "image_base64": f"data:{_mime_from_bytes(image_bytes)};base64,{b64}",
        }
    except Exception as e:
        logger.error(f"[레퍼런스] 캐릭터 시트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"캐릭터 시트 생성 실패: {str(e)}")


# ============================================
# 프리셋 관리
# ============================================

@router.get("/presets/list")
async def list_presets():
    """프리셋 목록 조회"""
    presets = ReferenceService.list_presets()
    return {"success": True, "presets": presets}


@router.post("/presets/{preset_id}/apply")
async def apply_preset(preset_id: str, req: ApplyPresetRequest):
    """프리셋 3종을 현재 레퍼런스에 적용"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[프리셋 적용] preset_id={preset_id}, session_id={req.session_id}")
    service = ReferenceService(req.session_id)
    try:
        result = service.apply_preset(preset_id)
        logger.info(f"[프리셋 적용] 완료 — 대상 디렉토리: {service.ref_dir}")
        return {"success": True, "message": f"프리셋 '{preset_id}' 적용 완료"}
    except ValueError as e:
        logger.error(f"[프리셋 적용] 실패: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/presets/save")
async def save_preset(req: SavePresetRequest):
    """현재 레퍼런스를 프리셋으로 저장"""
    service = ReferenceService(req.session_id)
    preset_id = service.save_as_preset(req.name, req.description, req.character_names)
    return {"success": True, "preset_id": preset_id, "message": f"프리셋 '{req.name}' 저장 완료"}


@router.get("/presets/{preset_id}/output")
async def get_preset_output(preset_id: str):
    """프리셋 output.jpg(미리보기 썸네일) 반환 — 빌트인/사용자 모두 지원"""
    preset_dir = ReferenceService._find_preset_dir(preset_id)
    if not preset_dir:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    output_path = os.path.join(preset_dir, "output.jpg")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="프리셋 미리보기 이미지가 없습니다.")
    return FileResponse(output_path, media_type="image/jpeg")


@router.get("/presets/{preset_id}/thumbnail/{ref_type}")
async def get_preset_thumbnail(preset_id: str, ref_type: str):
    """프리셋의 개별 레퍼런스 이미지 반환 (character/method/style)"""
    from app.services.reference_service import TYPE_TO_FILENAME
    if ref_type not in TYPE_TO_FILENAME:
        raise HTTPException(status_code=400, detail=f"잘못된 타입: {ref_type}")
    preset_dir = ReferenceService._find_preset_dir(preset_id)
    if not preset_dir:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다.")
    file_path = os.path.join(preset_dir, TYPE_TO_FILENAME[ref_type])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"{ref_type} 이미지가 없습니다.")
    return FileResponse(file_path, media_type="image/jpeg")


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """사용자 프리셋 삭제 (빌트인은 삭제 불가)"""
    try:
        ReferenceService.delete_preset(preset_id)
        return {"success": True, "message": f"프리셋 '{preset_id}' 삭제 완료"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# 테스트 미리보기
# ============================================

@router.post("/test-preview")
async def test_preview(req: TestPreviewRequest):
    """현재 레퍼런스로 테스트 이미지 1장 생성"""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되지 않았습니다.")

    service = ReferenceService(req.session_id)
    try:
        image_bytes = await service.generate_test_preview(
            model_name=req.model_name,
            gemini_api_key=settings.gemini_api_key,
            prompt=req.prompt
        )
        b64 = base64.b64encode(image_bytes).decode()
        mime = _mime_from_bytes(image_bytes)
        return {
            "success": True,
            "message": "테스트 미리보기 생성 완료",
            "image_base64": f"data:{mime};base64,{b64}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[레퍼런스] 테스트 미리보기 실패: {e}")
        raise HTTPException(status_code=500, detail=f"테스트 미리보기 생성 실패: {str(e)}")


# ============================================
# 상태 조회
# ============================================

@router.get("/status/info")
async def get_reference_status(session_id: Optional[str] = None, model_name: str = "flux-kontext-dev"):
    """3종 레퍼런스 존재 여부 + 모델별 사용 안내 반환"""
    service = ReferenceService(session_id)
    status = service.get_status()
    model_info = ReferenceService.get_model_reference_info(model_name)

    return {
        "success": True,
        "references": status,
        "model_info": model_info,
    }
