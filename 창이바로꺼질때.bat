@echo off
chcp 65001 >nul
title 문제 확인
cd /d "%~dp0"

echo.
echo   ==========================================
echo      문제 확인용 - 이 창은 저절로 닫히지 않습니다
echo   ==========================================
echo.
echo   [현재 폴더]
echo   %~dp0
echo.
echo   [이 폴더에 있는 것]
dir /b "%~dp0" 2>nul
echo.
echo   [파이썬 확인]
where python 2>nul
where py 2>nul
python --version 2>nul
py --version 2>nul
echo.
echo   ==========================================
echo      이제 AI실행.bat 을 실행해 봅니다
echo   ==========================================
echo.

call "%~dp0AI실행.bat"

echo.
echo   ==========================================
echo      끝났습니다. 위 내용을 캡처해서 보내주세요.
echo   ==========================================
pause
