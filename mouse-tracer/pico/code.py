# 라즈베리파이 피코에 넣는 파일 (2/2)
#
# PC 가 시리얼로 보낸 마우스 움직임을 받아서, 진짜 USB 마우스처럼 출력합니다.
# 피코가 실제 HID 장치라서 Windows 의 Raw Input 에도 정상으로 잡힙니다.
#
# 보내는 형식은 5바이트 한 묶음입니다.
#   0번: 0xAB (묶음 시작 표시)
#   1번: 가로 이동량 (-127 ~ 127)
#   2번: 세로 이동량 (-127 ~ 127)
#   3번: 눌린 버튼 (1=왼쪽, 2=오른쪽, 4=가운데 를 더한 값)
#   4번: 휠 (-127 ~ 127)
#
# USB 마우스는 정해진 간격으로만 보고할 수 있어서, PC 가 더 빨리 보내도
# 그대로 다 내보낼 수는 없습니다. 그래서 못 내보낸 이동량을 모아 두었다가
# 다음 차례에 이어서 내보냅니다. 이러면 움직인 총량이 어긋나지 않습니다.

import usb_cdc
import usb_hid
from adafruit_hid.mouse import Mouse

SYNC = 0xAB
FRAME = 5

mouse = Mouse(usb_hid.devices)
port = usb_cdc.data

BUTTONS = (
    (0x01, Mouse.LEFT_BUTTON),
    (0x02, Mouse.RIGHT_BUTTON),
    (0x04, Mouse.MIDDLE_BUTTON),
)


def main():
    buf = bytearray()
    held = 0          # 지금 눌려 있는 버튼
    pend_x = 0        # 아직 못 내보낸 이동량
    pend_y = 0
    pend_w = 0

    def flush():
        """모아 둔 이동량을 한 번 내보낸다."""
        nonlocal pend_x, pend_y, pend_w
        while pend_x or pend_y or pend_w:
            cx = 127 if pend_x > 127 else (-127 if pend_x < -127 else pend_x)
            cy = 127 if pend_y > 127 else (-127 if pend_y < -127 else pend_y)
            cw = 127 if pend_w > 127 else (-127 if pend_w < -127 else pend_w)
            pend_x -= cx
            pend_y -= cy
            pend_w -= cw
            mouse.move(x=cx, y=cy, wheel=cw)

    def set_buttons(want):
        """버튼 상태를 맞춘다."""
        nonlocal held
        for bit, code in BUTTONS:
            if (want & bit) and not (held & bit):
                mouse.press(code)
            elif (held & bit) and not (want & bit):
                mouse.release(code)
        held = want

    while True:
        waiting = port.in_waiting
        if waiting:
            buf.extend(port.read(waiting))

            while len(buf) >= FRAME:
                if buf[0] != SYNC:
                    del buf[0]        # 묶음 시작이 아니면 한 칸 밀어 다시 찾는다
                    continue

                frame = bytes(buf[:FRAME])
                del buf[:FRAME]

                want = frame[3]
                if want != held:
                    # 버튼이 바뀌는 순간에는 여태 모은 이동을 먼저 내보내
                    # 클릭 위치가 밀리지 않게 한다
                    flush()
                    set_buttons(want)

                dx = frame[1]
                dy = frame[2]
                dw = frame[4]
                pend_x += dx - 256 if dx > 127 else dx
                pend_y += dy - 256 if dy > 127 else dy
                pend_w += dw - 256 if dw > 127 else dw

        if pend_x or pend_y or pend_w:
            flush()


main()
