@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw crosshair_overlay.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw crosshair_overlay.py & exit /b)
echo 파이썬이 설치되어 있지 않아요. https://www.python.org 에서 설치해 주세요.
pause
