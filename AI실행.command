#!/bin/bash
# Mac 용 더블클릭 실행 파일. 처음 한 번만 터미널에서: chmod +x AI실행.command
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Python 3 가 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서 설치하세요."
    read -p "엔터를 누르면 닫힙니다."
    exit 1
fi

if ! python3 -c "import anthropic, streamlit" >/dev/null 2>&1; then
    echo "필요한 프로그램을 설치하는 중입니다... (처음 한 번만)"
    python3 -m pip install --quiet --upgrade pip
    python3 -m pip install --quiet "anthropic>=1.0.0" "streamlit>=1.31.0"
fi

echo "브라우저가 자동으로 열립니다. 이 창은 닫지 마세요."
python3 -m streamlit run my_ai/app.py --server.headless false --browser.gatherUsageStats false
