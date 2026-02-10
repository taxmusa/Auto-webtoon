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
    name: str = Form(...),
    type: str = Form(...), # 'character' or 'background'
    prompt_block: str = Form(...),
    locked_attributes: str = Form("[]"), # JSON string
    visual_attributes: str = Form("{}"), # JSON string
    reference_images: List[UploadFile] = File(None)
):
    """스타일 저장 (이미지 포함)"""
    try:
        locked_attrs = json.loads(locked_attributes)
    except:
        locked_attrs = []
        
    try:
        visual_attrs = json.loads(visual_attributes)
    except:
        visual_attrs = {}
        
    style_id = f"{type}_style_{uuid.uuid4().hex[:8]}"
    
    base_dir = CHAR_STYLE_DIR if type == 'character' else BG_STYLE_DIR
    style_dir = os.path.join(base_dir, style_id)
    os.makedirs(style_dir, exist_ok=True)
    
    # Save Images
    saved_images = []
    if reference_images:
        for file in reference_images:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"ref_{uuid.uuid4().hex[:6]}{file_ext}"
            file_path = os.path.join(style_dir, file_name)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # API에서 접근 가능한 경로로 저장 (assuming static mount needed later, or return relative)
            # For now returning relative path to be served via static
            saved_images.append(f"/app_data/styles/{type}/{style_id}/{file_name}")

    # Meta Data
    if type == 'character':
        style_obj = CharacterStyle(
            id=style_id,
            name=name,
            prompt_block=prompt_block,
            locked_attributes=locked_attrs,
            visual_attributes=visual_attrs,
            reference_images=saved_images
        )
    else:
        style_obj = BackgroundStyle(
            id=style_id,
            name=name,
            prompt_block=prompt_block,
            locked_attributes=locked_attrs,
            visual_attributes=visual_attrs,
            reference_images=saved_images
        )
        
    meta_path = os.path.join(style_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(style_obj.model_dump(), f, ensure_ascii=False, indent=2)
        
    return {"success": True, "style": style_obj.model_dump()}

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
