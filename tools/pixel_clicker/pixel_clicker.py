"""단축키를 누르면, 그 순간 화면 가운데 1픽셀 색을 기억하고
색이 바뀌면 그 자리를 딱 한 번 클릭한 뒤 감시를 끄는 프로그램.
단축키를 다시 누르면 다시 감시를 시작한다.

사용법:
    python pixel_clicker.py           # 실행 (처음엔 단축키 설정부터)
    python pixel_clicker.py --setup   # 단축키 다시 설정

멈추기: 종료 단축키, Ctrl+C, 또는 마우스를 화면 왼쪽 위 모서리로 이동
"""

import argparse
import json
import threading
import time
from pathlib import Path

import mss
import pyautogui
from pynput import keyboard

SETTINGS_FILE = Path(__file__).with_name("hotkey_settings.json")
MODIFIERS = ["ctrl", "alt", "shift", "cmd"]


def key_name(key):
    """눌린 키를 'ctrl', 'f8', 's' 같은 이름으로 바꾼다. 모르는 키는 None."""
    if isinstance(key, keyboard.Key):
        name = key.name
        for side in ("_l", "_r", "_gr"):
            if name.endswith(side):
                name = name[: -len(side)]
        return name
    vk = getattr(key, "vk", None)
    if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()  # Ctrl을 눌러도 글자 키를 제대로 읽기 위해
    if key.char and key.char.isprintable() and not key.char.isspace():
        return key.char.lower()
    return None


def capture_combo(prompt):
    """사용자가 누른 키 조합을 받아 'ctrl+alt+s' 형태로 돌려준다."""
    while True:
        print(prompt)
        pressed, held = [], set()

        def on_press(key):
            name = key_name(key)
            if name:
                if name not in pressed:
                    pressed.append(name)
                held.add(name)

        def on_release(key):
            held.discard(key_name(key))
            if pressed and not held:
                return False  # 모든 키를 떼면 입력 끝

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

        mods = [m for m in MODIFIERS if m in pressed]
        others = [k for k in pressed if k not in MODIFIERS]
        if len(others) == 1:
            combo = "+".join(mods + others)
            print(f"  -> {combo.upper()}")
            return combo
        print("  Ctrl/Alt/Shift 말고 다른 키를 1개 포함해서 눌러 주세요.")


def setup_hotkeys():
    """단축키를 직접 눌러서 정하고 파일에 저장한다."""
    print("=== 단축키 설정 ===")
    start = capture_combo("감시 시작에 쓸 키를 누르세요 (예: F8, Ctrl+Alt+S)")
    while True:
        quit_ = capture_combo("프로그램 종료에 쓸 키를 누르세요 (예: F12)")
        if quit_ != start:
            break
        print("  시작 키와 다른 키로 정해 주세요.")
    settings = {"start_key": start, "quit_key": quit_}
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("저장 완료!\n")
    return settings


def load_hotkeys():
    """저장된 단축키를 읽는다. 없으면 설정부터 한다."""
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if settings.get("start_key") and settings.get("quit_key"):
            return settings
    except (OSError, ValueError):
        pass
    return setup_hotkeys()


def to_pynput(combo):
    """'ctrl+alt+s', 'f8' 같은 입력을 pynput 형식('<ctrl>+<alt>+s', '<f8>')으로 바꾼다."""
    keys = []
    for k in combo.lower().replace(" ", "").split("+"):
        keys.append(k if len(k) == 1 or k.startswith("<") else f"<{k}>")
    return "+".join(keys)


def screen_center(sct):
    """주 모니터의 가운데 좌표(x, y)를 돌려준다."""
    mon = sct.monitors[1]
    return mon["left"] + mon["width"] // 2, mon["top"] + mon["height"] // 2


def read_pixel(sct, x, y):
    """(x, y) 위치 1픽셀의 색을 (R, G, B)로 돌려준다."""
    shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
    return shot.pixel(0, 0)


def is_changed(a, b, tolerance):
    """두 색의 RGB 차이가 허용치보다 크면 True."""
    return max(abs(a[i] - b[i]) for i in range(3)) > tolerance


def main():
    p = argparse.ArgumentParser(description="단축키를 누르면 화면 가운데 픽셀 색이 바뀔 때 클릭")
    p.add_argument("--setup", action="store_true", help="단축키 다시 설정")
    p.add_argument("--tolerance", type=int, default=10, help="색 차이 허용치 0~255 (기본 10)")
    p.add_argument("--interval", type=float, default=0.01, help="검사 간격 초 (기본 0.01)")
    p.add_argument("--button", choices=["left", "right"], default="left", help="클릭 버튼")
    args = p.parse_args()

    settings = setup_hotkeys() if args.setup else load_hotkeys()
    start_key, quit_key = settings["start_key"], settings["quit_key"]

    pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 모서리로 옮기면 즉시 멈춤
    pyautogui.PAUSE = 0

    start = threading.Event()  # 시작 단축키가 눌렸다는 신호
    quit_ = threading.Event()
    hotkeys = keyboard.GlobalHotKeys({
        to_pynput(start_key): start.set,
        to_pynput(quit_key): quit_.set,
    })
    hotkeys.start()

    watching = False
    base = None
    clicks = 0

    with mss.mss() as sct:
        x, y = screen_center(sct)
        print(f"감시 위치: ({x}, {y})")
        print(f"[{start_key.upper()}] 감시 시작   [{quit_key.upper()}] 종료")
        print("(단축키를 바꾸려면 '단축키_바꾸기.bat' 실행)")
        print("대기 중...")

        try:
            while not quit_.is_set():
                if start.is_set():
                    start.clear()
                    watching = True
                    base = read_pixel(sct, x, y)  # 누른 순간의 색을 기준으로
                    print(f"감시 시작! 기준 색 RGB{base}")

                if watching:
                    now = read_pixel(sct, x, y)
                    if is_changed(base, now, args.tolerance):
                        pyautogui.click(x, y, button=args.button)
                        clicks += 1
                        print(f"[{time.strftime('%H:%M:%S')}] 색 변경 RGB{base} -> RGB{now}  클릭! (총 {clicks}회)")
                        watching = False  # 한 번 클릭하면 감시 끄기
                        print(f"감시 꺼짐. [{start_key.upper()}]를 누르면 다시 시작")

                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        except pyautogui.FailSafeException:
            print("마우스가 모서리로 이동해서 멈췄습니다.")
        finally:
            hotkeys.stop()

    print(f"종료. 총 {clicks}회 클릭했습니다.")


if __name__ == "__main__":
    main()
