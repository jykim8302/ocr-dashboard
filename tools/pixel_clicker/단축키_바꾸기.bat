@echo off
cd /d "%~dp0"
pip install -q -r requirements.txt
python pixel_clicker.py --setup %*
pause
