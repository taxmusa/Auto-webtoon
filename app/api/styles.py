from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import json
from datetime import datetime
import shutil
from app.models.models import CharacterStyle, BackgroundStyle
import uuid
from app.services.gemini_service import get_gemini_service

router = APIRouter(prefix="/api/styles", tags=["styles"])

STYLE_BASE_DIR = "app_data/styles"
CHAR_STYLE_DIR = os.path.join(STYLE_BASE_DIR, "character")
BG_STYLE_DIR = os.path.join(STYLE_BASE_DIR, "background")

os.makedirs(CHAR_STYLE_DIR, exist_ok=True)
os.makedirs(BG_STYLE_DIR, exist_ok=True)

def get_character_style(style_id: str) -> Optional[CharacterStyle]:
    style_path = os.path.join(CHAR_STYLE_DIR, style_id, "meta.json")
    if os.path.exists(style_path):
        try:
            with open(style_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return CharacterStyle(**data)
        except Exception as e:
            print(f"Error loading character style {style_id}: {e}")
    return None

def get_background_style(style_id: str) -> Optional[BackgroundStyle]:
    style_path = os.path.join(BG_STYLE_DIR, style_id, "meta.json")
    if os.path.exists(style_path):
        try:
            with open(style_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return BackgroundStyle(**data)
        except Exception as e:
            print(f"Error loading background style {style_id}: {e}")
    return None

class SaveStyleRequest(BaseModel):
    name: str
    type: str # 'character' or 'background'
    prompt_block: str
    locked_attributes: List[str] = []

@router.get("/character")
async def list_character_styles():
    """저장된 인물 스타일 목록 반환"""
    results = []
    if not os.path.exists(CHAR_STYLE_DIR):
        return []
    
    for style_id in os.listdir(CHAR_STYLE_DIR):
        style_path = os.path.join(CHAR_STYLE_DIR, style_id)
        meta_path = os.path.join(style_path, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    results.append(data)
                except:
                    pass
    return results

@router.get("/background")
async def list_background_styles():
    """저장된 배경 스타일 목록 반환"""
    results = []
    if not os.path.exists(BG_STYLE_DIR):
        return []
    
    for style_id in os.listdir(BG_STYLE_DIR):
        style_path = os.path.join(BG_STYLE_DIR, style_id)
        meta_path = os.path.join(style_path, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    results.append(data)
                except:
                    pass
    return results

@router.post("/save")
async def save_style(
    id: Optional[str] = Form(None), # 수정 시 ID 전달
    name: str = Form(...),
    type: str = Form(...), # 'character' or 'background'
    prompt_block: str = Form(...),
    locked_attributes: str = Form("[]"), # JSON string
    visual_attributes: str = Form("{}"), # JSON string
    reference_images: List[UploadFile] = File(None)
):
    """스타일 저장 (신규 생성 또는 수정)"""
    try:
        locked_attrs = json.loads(locked_attributes)
    except:
        locked_attrs = []
        
    try:
        visual_attrs = json.loads(visual_attributes)
    except:
        visual_attrs = {}

    base_dir = CHAR_STYLE_DIR if type == 'character' else BG_STYLE_DIR
    
    # 수정 모드 (ID 존재)
    if id:
        style_id = id
        style_dir = os.path.join(base_dir, style_id)
        meta_path = os.path.join(style_dir, "meta.json")
        
        if not os.path.exists(meta_path):
             raise HTTPException(status_code=404, detail="Style not found")
             
        with open(meta_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            
        # 기본 스타일 보호
        if existing_data.get("is_default", False):
            raise HTTPException(status_code=403, detail="Cannot modify default style")
            
        # 기존 이미지 유지 (새 이미지가 없으면)
        saved_images = existing_data.get("reference_images", [])
        preview_image = existing_data.get("preview_image") # 유지
    else:
        # 신규 생성
        style_id = f"{type}_style_{uuid.uuid4().hex[:8]}"
        style_dir = os.path.join(base_dir, style_id)
        os.makedirs(style_dir, exist_ok=True)
        saved_images = []
        preview_image = None

    # 새 이미지 저장 (추가)
    if reference_images:
        # 수정 모드라면 기존 이미지를 대체할지, 추가할지 결정해야 함. 
        # 현재 UI 로직상 '대표 이미지' 개념이 강하므로, 새 이미지가 오면 기존 리스트를 초기화하고 덮어쓰는 게 깔끔함 (또는 UI에서 제어)
        # 여기선 '덮어쓰기' 전략 사용 (사용자가 새 이미지를 올렸다는 건 교체 의도)
        if id: 
            saved_images = [] 
            
        for file in reference_images:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"ref_{uuid.uuid4().hex[:6]}{file_ext}"
            file_path = os.path.join(style_dir, file_name)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            saved_images.append(f"/app_data/styles/{type}/{style_id}/{file_name}")

    # Meta Data Update
    if type == 'character':
        style_obj = CharacterStyle(
            id=style_id,
            name=name,
            prompt_block=prompt_block,
            locked_attributes=locked_attrs,
            reference_images=saved_images,
            preview_image=preview_image, # 보존
            is_default=False # 사용자가 생성/수정한 건 무조건 False
        )
    else:
        style_obj = BackgroundStyle(
            id=style_id,
            name=name,
            prompt_block=prompt_block,
            locked_attributes=locked_attrs,
            reference_images=saved_images,
            preview_image=preview_image, # 보존
            is_default=False
        )
        
    meta_path = os.path.join(style_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(style_obj.model_dump(), f, ensure_ascii=False, indent=2)
        
    return {"success": True, "style": style_obj.model_dump()}

@router.delete("/{type}/{style_id}")
async def delete_style(type: str, style_id: str):
    """스타일 삭제"""
    if type not in ['character', 'background']:
        raise HTTPException(status_code=400, detail="Invalid style type")
        
    base_dir = CHAR_STYLE_DIR if type == 'character' else BG_STYLE_DIR
    style_dir = os.path.join(base_dir, style_id)
    meta_path = os.path.join(style_dir, "meta.json")
    
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail="Style not found")
        
    # 기본 스타일 삭제 방지
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("is_default", False):
                raise HTTPException(status_code=403, detail="Cannot delete default style")
    except Exception as e:
        # 파일 읽기 실패 시에도 안전하게 삭제 거부? 
        # 아니면 파일이 깨졌으니 삭제 허용? -> 안전하게 거부 후 수동 해결 유도
        if isinstance(e, HTTPException): raise e
        print(f"Error reading meta.json: {e}")

    try:
        shutil.rmtree(style_dir)
        return {"success": True, "message": "Style deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")

@router.post("/extract")
async def extract_style(image: UploadFile = File(...)):
    """이미지에서 스타일 추출 (Vision AI)"""
    content = await image.read()
    gemini = get_gemini_service()
    try:
        result = await gemini.extract_style_from_image(content)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
