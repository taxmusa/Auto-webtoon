from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
import logging
from dotenv import load_dotenv

# 앱 로거 레벨 설정 (타이밍·디버그 메시지가 콘솔에 표시되도록)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

from app.api.workflow import router as workflow_router
from app.api.styles import router as styles_router
from app.api.edit_stage import router as edit_stage_router
from app.api.training import router as training_router

# 환경 변수 로드
load_dotenv()

app = FastAPI(title="Tax Webtoon Auto-Generator")

# 라우터 등록
app.include_router(workflow_router)
app.include_router(styles_router)
app.include_router(edit_stage_router)
app.include_router(training_router)

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/app_data", StaticFiles(directory="app_data"), name="app_data")
os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

# 학습 캐릭터 이미지 서빙
os.makedirs("trained_characters", exist_ok=True)
app.mount("/trained_characters", StaticFiles(directory="trained_characters"), name="trained_characters")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "홈 - Tax Webtoon Auto-Generator"})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


