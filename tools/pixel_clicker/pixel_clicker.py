"""화면 가운데 1픽셀의 색이 바뀌면 그 자리를 클릭하는 프로그램.

사용법:
    python pixel_clicker.py            # 색이 바뀔 때마다 클릭
    python pixel_clicker.py --once     # 한 번만 클릭하고 종료

멈추기: Ctrl+C 또는 마우스를 화면 왼쪽 위 모서리로 이동
"""

import argparse
import time

import mss
import pyautogui


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
    p = argparse.ArgumentParser(description="화면 가운데 픽셀 색이 바뀌면 클릭")
    p.add_argument("--tolerance", type=int, default=10, help="색 차이 허용치 0~255 (기본 10)")
    p.add_argument("--interval", type=float, default=0.01, help="검사 간격 초 (기본 0.01)")
    p.add_argument("--cooldown", type=float, default=0.5, help="클릭 후 대기 초 (기본 0.5)")
    p.add_argument("--delay", type=int, default=3, help="시작 전 대기 초 (기본 3)")
    p.add_argument("--button", choices=["left", "right"], default="left", help="클릭 버튼")
    p.add_argument("--once", action="store_true", help="한 번 클릭하고 종료")
    args = p.parse_args()

    pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 모서리로 옮기면 즉시 멈춤
    pyautogui.PAUSE = 0

    with mss.mss() as sct:
        x, y = screen_center(sct)
        print(f"감시 위치: ({x}, {y})")
        for s in range(args.delay, 0, -1):
            print(f"{s}초 후 시작...")
            time.sleep(1)

        base = read_pixel(sct, x, y)
        print(f"기준 색: RGB{base}  |  멈추려면 Ctrl+C")
        clicks = 0

        try:
            while True:
                now = read_pixel(sct, x, y)
                if is_changed(base, now, args.tolerance):
                    pyautogui.click(x, y, button=args.button)
                    clicks += 1
                    print(f"[{time.strftime('%H:%M:%S')}] 색 변경 RGB{base} -> RGB{now}  클릭! (총 {clicks}회)")
                    if args.once:
                        break
                    time.sleep(args.cooldown)
                    base = read_pixel(sct, x, y)  # 바뀐 색을 새 기준으로
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        except pyautogui.FailSafeException:
            print("마우스가 모서리로 이동해서 멈췄습니다.")

    print(f"종료. 총 {clicks}회 클릭했습니다.")


if __name__ == "__main__":
    main()
