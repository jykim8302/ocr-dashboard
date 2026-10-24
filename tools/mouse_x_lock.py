"""
마우스 Y축 고정 도구 (Windows 전용)

F8 을 누르면 지금 마우스 높이(Y)에 고정되어 좌우로만 움직입니다.
F8 을 한 번 더 누르면 원래대로 풀립니다.
종료: 이 창을 닫거나 Ctrl+C

실행:
    uv run tools/mouse_x_lock.py
    (또는 tools/mouse_x_lock.bat 더블클릭)

추가 패키지 설치가 필요 없습니다. (파이썬 기본 ctypes 만 사용)
"""

import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    sys.exit("이 도구는 Windows 에서만 동작합니다.")

user32 = ctypes.windll.user32

HOTKEY_KEY = 0x77  # F8 (다른 키로 바꾸려면 이 값을 수정: F9=0x78, F10=0x79)
HOTKEY_NAME = "F8"
HOTKEY_ID = 1
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
MOD_NOREPEAT = 0x4000

# 여러 모니터를 합친 전체 화면 범위
SM_XVIRTUALSCREEN = 76
SM_CXVIRTUALSCREEN = 78


def lock_y(y):
    """마우스가 높이 y 의 한 줄(좌우)에서만 움직이도록 가둡니다."""
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    right = left + user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    rect = wintypes.RECT(left, y, right, y + 1)
    user32.ClipCursor(ctypes.byref(rect))


def unlock():
    user32.ClipCursor(None)


def main():
    # 고해상도(배율 125%, 150% 등) 화면에서도 좌표가 정확하도록 설정
    user32.SetProcessDPIAware()

    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, HOTKEY_KEY):
        sys.exit(f"{HOTKEY_NAME} 키를 등록할 수 없습니다. 다른 프로그램이 사용 중인지 확인하세요.")

    print("=" * 50)
    print(f"  [{HOTKEY_NAME}]  마우스 Y축 고정 / 해제")
    print("  종료: 이 창 닫기 또는 Ctrl+C")
    print("=" * 50)

    locked_y = None
    msg = wintypes.MSG()
    try:
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if locked_y is None:
                        pt = wintypes.POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        locked_y = pt.y
                        lock_y(locked_y)
                        print(f"🔒 고정됨 (Y = {locked_y}) - 좌우로만 움직입니다")
                    else:
                        locked_y = None
                        unlock()
                        print("🔓 해제됨 - 자유롭게 움직입니다")

            # 창 전환 등으로 Windows 가 고정을 풀어버릴 수 있어서 계속 다시 걸어줍니다
            if locked_y is not None:
                lock_y(locked_y)

            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        unlock()
        user32.UnregisterHotKey(None, HOTKEY_ID)
        print("종료되었습니다.")


if __name__ == "__main__":
    main()
