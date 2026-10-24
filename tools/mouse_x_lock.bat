@echo off
chcp 65001 > nul
cd /d "%~dp0.."
where uv > nul 2>&1
if %errorlevel%==0 (
    uv run tools/mouse_x_lock.py
) else (
    python tools/mouse_x_lock.py
)
pause
