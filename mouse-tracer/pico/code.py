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
#
# 초록색 LED 가 상태를 알려 줍니다.
#   천천히 깜박임      -> 정상. 자료를 기다리는 중
#   불규칙하게 깜박임  -> 자료를 받아 마우스를 움직이는 중
#   빠르게 깜박임      -> 오류가 반복되는 중

import time
import board
import digitalio
import usb_cdc
import usb_hid
from adafruit_hid.mouse import Mouse

SYNC = 0xAB
FRAME = 5
BLINK = 0.5

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

port = usb_cdc.data
try:
    # 말을 보내다 막히면 안 되므로 기다리는 시간을 짧게 둔다
    port.write_timeout = 0.1
except Exception:
    pass


def say(text):
    """PC 쪽 로그에 보일 한 줄을 보낸다. 실패해도 그냥 넘어간다."""
    try:
        port.write((text + "\n").encode("utf-8"))
    except Exception:
        pass


try:
    mouse = Mouse(usb_hid.devices)
except Exception as start_error:
    # 마우스를 못 만들었으면 최소한 무슨 일인지는 알려 주고,
    # 포트는 계속 비워 준다. 멈추면 PC 가 원인을 볼 수 없다.
    mouse = None
    while True:
        say("MOUSE FAIL " + repr(start_error))
        for _ in range(20):
            if port.in_waiting:
                port.read(port.in_waiting)
            time.sleep(0.05)

BUTTON_BITS = (0x01, 0x02, 0x04)
BUTTON_CODES = (Mouse.LEFT_BUTTON, Mouse.RIGHT_BUTTON, Mouse.MIDDLE_BUTTON)


def clamp(value):
    """한 번에 보낼 수 있는 범위로 자른다."""
    if value > 127:
        return 127
    if value < -127:
        return -127
    return value


def to_signed(value):
    """0~255 로 온 값을 -128~127 로 되돌린다."""
    return value - 256 if value > 127 else value


buf = bytearray()
held = 0            # 지금 눌려 있는 버튼
pend_x = 0          # 아직 못 내보낸 이동량
pend_y = 0
pend_w = 0
last_blink = time.monotonic()
last_good = time.monotonic()
trouble = False
said = 0

say("READY")

while True:
    try:
        waiting = port.in_waiting
        if waiting:
            buf.extend(port.read(waiting))
            led.value = not led.value

            while len(buf) >= FRAME:
                if buf[0] != SYNC:
                    del buf[0]          # 묶음 시작이 아니면 밀어서 다시 찾는다
                    continue

                frame = bytes(buf[:FRAME])
                del buf[:FRAME]
                want = frame[3]

                if want != held:
                    # 버튼이 바뀌기 전에 모은 이동을 먼저 내보내야
                    # 클릭이 제 위치에서 일어난다
                    while pend_x or pend_y or pend_w:
                        cx = clamp(pend_x)
                        cy = clamp(pend_y)
                        cw = clamp(pend_w)
                        pend_x -= cx
                        pend_y -= cy
                        pend_w -= cw
                        mouse.move(x=cx, y=cy, wheel=cw)

                    for index in range(3):
                        bit = BUTTON_BITS[index]
                        if (want & bit) and not (held & bit):
                            mouse.press(BUTTON_CODES[index])
                        elif (held & bit) and not (want & bit):
                            mouse.release(BUTTON_CODES[index])
                    held = want

                pend_x += to_signed(frame[1])
                pend_y += to_signed(frame[2])
                pend_w += to_signed(frame[4])

        if pend_x or pend_y or pend_w:
            cx = clamp(pend_x)
            cy = clamp(pend_y)
            cw = clamp(pend_w)
            pend_x -= cx
            pend_y -= cy
            pend_w -= cw
            mouse.move(x=cx, y=cy, wheel=cw)
        else:
            now = time.monotonic()
            gap = 0.1 if trouble else BLINK
            if now - last_blink >= gap:
                last_blink = now
                led.value = not led.value

        # 한동안 아무 문제 없으면 오류 표시를 내린다
        if trouble and time.monotonic() - last_good > 2.0:
            trouble = False
        if not trouble:
            last_good = time.monotonic()

    except Exception as err:
        # 무슨 일이 있어도 멈추지 않는다. 멈추면 PC 쪽 보내기가
        # 시간 초과로 실패하고, 원인을 볼 방법이 없다.
        trouble = True
        last_good = time.monotonic()
        if said < 5:                 # 같은 말을 끝없이 보내지 않는다
            said += 1
            say("ERR " + repr(err))
        buf = bytearray()
        pend_x = 0
        pend_y = 0
        pend_w = 0
        time.sleep(0.05)
