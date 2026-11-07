@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\installed.ok" goto run

echo.
echo  [처음 한 번만] 필요한 것을 설치합니다. 1~3분 걸려요...
echo.
set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 goto nopython

if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail
echo ok> ".venv\installed.ok"

:run
start "" ".venv\Scripts\pythonw.exe" screen_translator.py
exit /b

:nopython
echo  파이썬이 없어요. https://www.python.org/downloads/ 에서 설치해 주세요.
echo  설치할 때 "Add python.exe to PATH" 를 꼭 체크하세요.
pause
exit /b

:fail
echo.
echo  설치에 실패했어요. 인터넷 연결을 확인하고 다시 실행해 주세요.
pause
exit /b
