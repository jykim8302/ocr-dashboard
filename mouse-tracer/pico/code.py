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


def to_signed(value):
    """0~255 로 온 값을 -128~127 로 되돌린다."""
    return value - 256 if value > 127 else value


def main():
    buf = bytearray()
    held = 0  # 지금 눌려 있는 버튼

    while True:
        waiting = port.in_waiting
        if waiting:
            buf.extend(port.read(waiting))

        while len(buf) >= FRAME:
            if buf[0] != SYNC:
                del buf[0]        # 묶음 시작이 아니면 한 칸 밀어서 다시 찾는다
                continue

            frame = bytes(buf[:FRAME])
            del buf[:FRAME]

            dx = to_signed(frame[1])
            dy = to_signed(frame[2])
            want = frame[3]
            wheel = to_signed(frame[4])

            # 버튼은 달라진 것만 누르거나 뗀다
            if want != held:
                for bit, code in BUTTONS:
                    if (want & bit) and not (held & bit):
                        mouse.press(code)
                    elif (held & bit) and not (want & bit):
                        mouse.release(code)
                held = want

            if dx or dy or wheel:
                mouse.move(x=dx, y=dy, wheel=wheel)


main()
