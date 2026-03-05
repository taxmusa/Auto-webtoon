@echo off
chcp 65001 >nul 2>&1
title Auto-Webtoon v1.0

:: 가상환경 확인
if not exist "venv\Scripts\activate.bat" (
    echo [오류] 가상환경이 없습니다. install.bat을 먼저 실행해 주세요.
    pause
    exit /b 1
)

:: 가상환경 활성화 + 서버 시작
call venv\Scripts\activate.bat
echo ============================================
echo   Auto-Webtoon v1.0 시작
echo   http://127.0.0.1:8001
echo ============================================
echo   종료하려면 이 창을 닫거나 Ctrl+C를 누르세요
echo.
python run.py
