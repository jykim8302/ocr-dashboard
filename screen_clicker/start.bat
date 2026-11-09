@echo off
chcp 65001 > nul
cd /d "%~dp0"
where uv > nul 2> nul
if %errorlevel%==0 (
    uv run --with-requirements requirements.txt python screen_clicker.py
) else (
    python -m pip install -q -r requirements.txt
    python screen_clicker.py
)
if errorlevel 1 pause
