@echo off
chcp 65001 >nul
title 나만의 AI
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [!] Python 이 설치되어 있지 않습니다.
    echo      https://www.python.org/downloads/ 에서 설치할 때
    echo      "Add python.exe to PATH" 를 꼭 체크하세요.
    echo.
    pause
    exit /b 1
)

python -c "import anthropic, streamlit" >nul 2>nul
if errorlevel 1 (
    echo  필요한 프로그램을 설치하는 중입니다... (처음 한 번만)
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet "anthropic>=1.0.0" "streamlit>=1.31.0"
)

echo.
echo  브라우저가 자동으로 열립니다. 이 창은 닫지 마세요. (종료: 이 창을 닫기)
echo.
python -m streamlit run my_ai\app.py --server.headless false --browser.gatherUsageStats false
pause
