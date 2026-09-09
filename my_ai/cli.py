"""나만의 AI 비서 - 터미널 버전

실행:  python my_ai/cli.py
명령어:  /reset (대화 초기화)   /quit (종료)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from assistant import Assistant  # noqa: E402


def main() -> None:
    ai = Assistant()
    print(f"[{ai.cfg['name']}] {ai.cfg['greeting']}")
    print("(/reset: 대화 초기화, /quit: 종료)\n")
    while True:
        try:
            text = input("나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/reset":
            ai.reset()
            print("대화를 초기화했습니다.\n")
            continue
        print(f"{ai.cfg['name']}: ", end="", flush=True)
        try:
            for chunk in ai.chat(text):
                print(chunk, end="", flush=True)
        except RuntimeError as e:
            print(f"\n[오류] {e}")
        print("\n")


if __name__ == "__main__":
    main()
