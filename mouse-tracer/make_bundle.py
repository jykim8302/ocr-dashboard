# -*- coding: utf-8 -*-
"""전체 소스를 메모장으로 볼 수 있는 텍스트 한 개로 묶는다.

    python3 make_bundle.py

같은 폴더에 마우스따라하기_전체소스.txt 가 생긴다. 코드를 고친 뒤 다시
돌리면 된다. 만들어진 파일은 저장소에 넣지 않는다 (금세 낡기 때문).
"""
import datetime
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "마우스따라하기_전체소스.txt")
BAR = "=" * 78

FILES = (
    ("mouse_tracer.py", "PC 쪽 본체 — 녹화, 재생, 창, 피코 통신"),
    ("pico/boot.py", "피코 시작 설정 — 시리얼 포트 하나만 만들기"),
    ("pico/code.py", "피코 펌웨어 — 받은 신호를 진짜 마우스로 출력"),
    ("tests/check.py", "점검 스크립트"),
    ("README.md", "설명서"),
    ("pico/설치방법.txt", "피코 설치 순서"),
)

GUIDE = (
    "    1. mouse_tracer.py 의 맨 위 약 400줄은 Win32 구조체 정의입니다.",
    "       건너뛰고 Engine 클래스부터 보시면 됩니다.",
    "    2. 녹화     : Engine._handle_packet, Engine._drain_buffer",
    "    3. 재생     : Engine._play_worker, Engine._wait_until",
    "    4. 피코 통신 : PicoLink, Engine._emit_pico, Engine._pico_flush",
    "    5. 창       : App 클래스",
)


def read(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def build():
    out = [BAR,
           "  마우스 움직임 따라하기 - 전체 소스",
           "  Windows Raw Input 으로 녹화하고, 라즈베리파이 피코로 재생합니다.",
           "  뽑은 날짜: " + datetime.date.today().isoformat(),
           BAR, "", "  [ 들어 있는 것 ]", ""]

    total = 0
    for name, desc in FILES:
        lines = read(name).count("\n") + 1
        total += lines
        out.append("    %-24s %5d줄   %s" % (name, lines, desc))
    out += ["", "    %-24s %5d줄" % ("합계", total), "",
            "  [ 코드 읽는 순서 ]", ""]
    out += list(GUIDE)
    out += ["", BAR, ""]

    for index, (name, desc) in enumerate(FILES, start=1):
        out += ["", BAR,
                "  파일 %d / %d" % (index, len(FILES)),
                "  %s" % name,
                "  %s" % desc,
                BAR, "",
                read(name).rstrip("\n"), ""]

    out += [BAR, "  끝", BAR]
    return "\n".join(out)


def main():
    text = build()
    # 윈도우 메모장에서 한글이 깨지지 않도록 BOM 과 CRLF 로 저장한다
    with io.open(OUT, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)
    print("만들었습니다: %s (%d줄, %d바이트)"
          % (os.path.basename(OUT), text.count("\n") + 1, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
