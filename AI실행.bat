@echo off
chcp 65001 >nul
title 나만의 AI
cd /d "%~dp0"

echo.
echo   ==========================================
echo      나만의 AI 비서를 시작합니다
echo   ==========================================
echo.

rem ---------- 1. 파이썬 찾기 ----------
set PYEXE=
where python >nul 2>nul && set PYEXE=python
if not defined PYEXE (
    where py >nul 2>nul && set PYEXE=py
)
if not defined PYEXE (
    echo   [!] 파이썬이 설치되어 있지 않습니다.
    echo.
    echo       https://www.python.org/downloads/ 에서 설치하세요.
    echo       설치 화면에서 "Add python.exe to PATH" 를 꼭 체크하세요.
    echo.
    pause
    exit /b 1
)

rem ---------- 2. 필요한 프로그램 설치 ----------
%PYEXE% -c "import anthropic, streamlit" >nul 2>nul
if errorlevel 1 (
    echo   처음 실행이라 필요한 프로그램을 설치합니다.
    echo   인터넷 속도에 따라 2~5분 걸릴 수 있습니다. 그대로 기다려 주세요...
    echo.
    %PYEXE% -m pip install --upgrade pip --quiet --disable-pip-version-check --no-warn-script-location
    %PYEXE% -m pip install --quiet --disable-pip-version-check --no-warn-script-location "anthropic>=1.0.0" "streamlit>=1.31.0"
    if errorlevel 1 (
        echo.
        echo   [!] 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
        echo.
        pause
        exit /b 1
    )
    echo   설치가 끝났습니다.
    echo.
)

rem ---------- 3. 첫 실행 때 이메일 묻는 질문 끄기 ----------
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>nul
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

rem ---------- 4. 실행 ----------
echo   AI를 켜는 중입니다. 잠시 후 브라우저가 자동으로 열립니다.
echo   브라우저가 안 열리면 아래에 표시되는 Local URL 주소를 복사해서 넣으세요.
echo.
echo   * 이 창을 닫으면 AI도 꺼집니다.
echo.

%PYEXE% -m streamlit run my_ai\app.py --browser.gatherUsageStats false

echo.
echo   AI가 종료되었습니다.
pause
