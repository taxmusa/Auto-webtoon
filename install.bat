@echo off
chcp 65001 >nul 2>&1
title Auto-Webtoon 설치 프로그램

echo ============================================
echo   Auto-Webtoon v1.0 설치 프로그램
echo ============================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo Python 3.10 이상을 설치해 주세요: https://www.python.org/downloads/
    echo 설치 시 "Add Python to PATH" 반드시 체크하세요!
    pause
    exit /b 1
)

echo [1/4] Python 확인 완료
python --version
echo.

:: 가상환경 생성
if not exist "venv" (
    echo [2/4] 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패
        pause
        exit /b 1
    )
    echo      가상환경 생성 완료
) else (
    echo [2/4] 가상환경 이미 존재합니다
)
echo.

:: 패키지 설치
echo [3/4] 필수 패키지 설치 중... (약 2~5분 소요)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)
echo      패키지 설치 완료
echo.

:: Playwright 브라우저 설치
echo [4/4] 텍스트 렌더링용 브라우저 설치 중...
playwright install chromium
if errorlevel 1 (
    echo [경고] Playwright 브라우저 설치 실패 - 텍스트 오버레이 기능이 제한될 수 있습니다
) else (
    echo      브라우저 설치 완료
)
echo.

:: .env 파일 확인
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [참고] .env 파일이 생성되었습니다. API 키를 입력해 주세요.
        echo       .env 파일을 메모장으로 열어 GEMINI_API_KEY 등을 입력하세요.
    )
) else (
    echo [참고] .env 파일이 이미 존재합니다
)
echo.

echo ============================================
echo   설치 완료!
echo ============================================
echo.
echo   실행 방법: start.bat 더블클릭
echo   또는: python run.py
echo.
pause
