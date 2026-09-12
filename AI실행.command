#!/bin/bash
# Mac 용 더블클릭 실행 파일
# 처음 한 번은 파일에서 우클릭 > 열기 를 선택하세요.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  =========================================="
echo "     나만의 AI 비서를 시작합니다"
echo "  =========================================="
echo ""

# 1. AI 프로그램 파일 찾기
APP=""
[ -f "$DIR/my_ai/app.py" ] && APP="$DIR/my_ai/app.py"
if [ -z "$APP" ]; then
    APP="$(find "$DIR" -name app.py -type f 2>/dev/null | head -n 1)"
fi
if [ -z "$APP" ]; then
    echo "  [!] AI 프로그램 파일을 찾을 수 없습니다. (my_ai/app.py)"
    echo ""
    echo "      지금 실행된 위치:"
    echo "      $DIR"
    echo ""
    echo "      ** 가장 흔한 원인 **"
    echo "      압축을 풀지 않고 zip 안에서 바로 실행한 경우입니다."
    echo "      먼저 압축을 풀고, 풀린 폴더 안의 AI실행.command 를 실행하세요."
    echo ""
    echo "      참고 - 지금 이 폴더에 있는 것:"
    ls -1 "$DIR"
    echo ""
    read -p "  엔터를 누르면 닫힙니다."
    exit 1
fi

# 2. 파이썬 찾기
PYEXE=""
command -v python3 >/dev/null 2>&1 && PYEXE=python3
if [ -z "$PYEXE" ]; then
    echo "  [!] 파이썬이 설치되어 있지 않습니다."
    echo "      https://www.python.org/downloads/ 에서 설치하세요."
    echo ""
    read -p "  엔터를 누르면 닫힙니다."
    exit 1
fi

# 3. 필요한 프로그램 설치
if ! $PYEXE -c "import anthropic, streamlit" >/dev/null 2>&1; then
    echo "  처음 실행이라 필요한 프로그램을 설치합니다."
    echo "  인터넷 속도에 따라 2~5분 걸릴 수 있습니다. 그대로 기다려 주세요..."
    echo ""
    $PYEXE -m pip install --upgrade pip --quiet --disable-pip-version-check --no-warn-script-location
    if ! $PYEXE -m pip install --quiet --disable-pip-version-check --no-warn-script-location "anthropic>=1.0.0" "streamlit>=1.31.0"; then
        echo ""
        echo "  [!] 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요."
        read -p "  엔터를 누르면 닫힙니다."
        exit 1
    fi
    echo "  설치가 끝났습니다."
    echo ""
fi

# 4. 첫 실행 때 이메일 묻는 질문 끄기
mkdir -p "$HOME/.streamlit"
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
    printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

# 5. 실행
echo "  AI를 켜는 중입니다. 잠시 후 브라우저가 자동으로 열립니다."
echo "  브라우저가 안 열리면 아래에 표시되는 Local URL 주소를 복사해서 넣으세요."
echo ""
echo "  * 이 창을 닫으면 AI도 꺼집니다."
echo ""

$PYEXE -m streamlit run "$APP" --browser.gatherUsageStats false

echo ""
echo "  AI가 종료되었습니다."
read -p "  엔터를 누르면 닫힙니다."
