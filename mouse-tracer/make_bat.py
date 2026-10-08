# -*- coding: utf-8 -*-
"""MouseTracer.bat 안에 지금 mouse_tracer.py 를 다시 넣는다.

    python3 make_bat.py

mouse_tracer.py 를 고친 뒤에는 반드시 한 번 돌려야 한다. 안 돌리면
실행 파일이 옛 코드를 품은 채로 남아, 더블클릭할 때마다 고친 내용이
조용히 되돌려진다. tests/check.py 가 그것을 잡아내 준다.
"""
import base64
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.path.join(HERE, "MouseTracer.bat")
SRC = os.path.join(HERE, "mouse_tracer.py")
MARK = "#####PAYLOAD#####"
WIDTH = 100


def main():
    lines = io.open(BAT, encoding="ascii", newline="").read().split("\r\n")
    index = lines.index(MARK)
    head = lines[:index + 1]

    text = base64.b64encode(io.open(SRC, "rb").read()).decode("ascii")
    body = [text[i:i + WIDTH] for i in range(0, len(text), WIDTH)]

    out = "\r\n".join(head + body) + "\r\n"
    io.open(BAT, "w", encoding="ascii", newline="").write(out)
    print("MouseTracer.bat 다시 만들었습니다 "
          "(머리말 %d줄 + 프로그램 %d줄)" % (len(head), len(body)))


if __name__ == "__main__":
    main()
