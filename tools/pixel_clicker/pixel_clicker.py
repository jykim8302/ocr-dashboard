"""단축키를 누르면, 그 순간 화면 가운데 1픽셀 색을 기억하고
색이 바뀌면 그 자리를 클릭하는 프로그램.

사용법:
    python pixel_clicker.py                    # F8: 감시 시작/취소, F12: 종료
    python pixel_clicker.py --key ctrl+alt+s   # 단축키 바꾸기
    python pixel_clicker.py --repeat           # 클릭 후에도 계속 감시

멈추기: 종료 키(기본 F12), Ctrl+C, 또는 마우스를 화면 왼쪽 위 모서리로 이동
"""

import argparse
import threading
import time

import mss
import pyautogui
from pynput import keyboard


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
    p.add_argument("--key", default="f8", help="감시 시작/취소 단축키 (기본 f8, 예: ctrl+alt+s)")
    p.add_argument("--quit-key", default="f12", help="프로그램 종료 단축키 (기본 f12)")
    p.add_argument("--tolerance", type=int, default=10, help="색 차이 허용치 0~255 (기본 10)")
    p.add_argument("--interval", type=float, default=0.01, help="검사 간격 초 (기본 0.01)")
    p.add_argument("--cooldown", type=float, default=0.5, help="--repeat일 때 클릭 후 대기 초 (기본 0.5)")
    p.add_argument("--button", choices=["left", "right"], default="left", help="클릭 버튼")
    p.add_argument("--repeat", action="store_true", help="클릭 후에도 계속 감시 (기본은 1번 클릭 후 대기)")
    args = p.parse_args()

    pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 모서리로 옮기면 즉시 멈춤
    pyautogui.PAUSE = 0

    toggle = threading.Event()  # 단축키가 눌렸다는 신호
    quit_ = threading.Event()
    hotkeys = keyboard.GlobalHotKeys({
        to_pynput(args.key): toggle.set,
        to_pynput(args.quit_key): quit_.set,
    })
    hotkeys.start()

    watching = False
    base = None
    clicks = 0

    with mss.mss() as sct:
        x, y = screen_center(sct)
        print(f"감시 위치: ({x}, {y})")
        print(f"[{args.key.upper()}] 감시 시작/취소   [{args.quit_key.upper()}] 종료")
        print("대기 중...")

        try:
            while not quit_.is_set():
                if toggle.is_set():
                    toggle.clear()
                    watching = not watching
                    if watching:
                        base = read_pixel(sct, x, y)
                        print(f"감시 시작! 기준 색 RGB{base}")
                    else:
                        print("감시 취소. 대기 중...")

                if watching:
                    now = read_pixel(sct, x, y)
                    if is_changed(base, now, args.tolerance):
                        pyautogui.click(x, y, button=args.button)
                        clicks += 1
                        print(f"[{time.strftime('%H:%M:%S')}] 색 변경 RGB{base} -> RGB{now}  클릭! (총 {clicks}회)")
                        if args.repeat:
                            time.sleep(args.cooldown)
                            base = read_pixel(sct, x, y)  # 바뀐 색을 새 기준으로
                        else:
                            watching = False
                            print("대기 중... (단축키를 누르면 다시 감시)")

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
