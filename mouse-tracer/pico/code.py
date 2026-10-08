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
# USB 마우스는 정해진 간격(대개 8밀리초)마다 한 번씩만 보고할 수 있습니다.
# 그래서 받은 묶음을 그 간격 사이에 모아 두었다가 한 보고로 내보냅니다.
#
# boot.py 가 만들어 둔 "큰 걸음 마우스" 를 찾으면 한 보고에 32767 까지
# 담을 수 있어서, 아무리 빨리 움직여도 보낼 양이 밀리지 않습니다.
# 못 찾으면 보통 마우스로 내보내는데, 그 쪽은 한 보고에 127 까지만
# 담기므로 빠른 구간에서 양이 밀리고, 밀린 만큼 늦어집니다.
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

SYNC = 0xAB
FRAME = 5
BLINK = 0.5
FAST_LIMIT = 32767      # 큰 걸음 마우스가 한 보고에 담을 수 있는 양
SLOW_LIMIT = 127        # 보통 마우스가 한 보고에 담을 수 있는 양
WHEEL_LIMIT = 127

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


# ---- 어느 마우스로 내보낼지 고른다 -------------------------------------
#
# 큰 걸음 마우스와 보통 마우스는 겉보기 쓰임새가 똑같아서 이름으로는
# 구별되지 않는다. 그래서 6바이트 보고를 받아 주는지 직접 넣어 본다.
# 보통 마우스는 길이가 맞지 않아 거절한다. 전부 0 인 보고라서 넣어 봐도
# 커서는 움직이지 않는다. 뒤에 있는 것부터 보는 이유는 큰 걸음 마우스가
# 뒤에 등록돼 있어서, 보통 마우스에 엉뚱한 길이를 넣는 일을 아예 피하려는
# 것이다.

fast_dev = None
mouse = None
start_error = None
LIMIT = SLOW_LIMIT

try:
    cands = []
    for dev in usb_hid.devices:
        try:
            if dev.usage_page == 0x01 and dev.usage == 0x02:
                cands.append(dev)
        except Exception:
            pass
    # 켜진 직후에는 USB 준비가 아직 안 끝나서 보고가 한두 번 막힐 수 있다.
    # 그 한 번을 보고 포기하면 이번 전원이 켜져 있는 동안 내내 느린 쪽으로
    # 돌게 되므로, 길이가 안 맞는 경우(ValueError) 가 아니면 잠깐 기다려
    # 다시 본다.
    for _attempt in range(20):
        busy = False
        for index in range(len(cands) - 1, -1, -1):
            try:
                cands[index].send_report(b"\x00\x00\x00\x00\x00\x00")
                fast_dev = cands[index]
                LIMIT = FAST_LIMIT
                break
            except ValueError:
                pass            # 6바이트를 안 받는 장치. 다시 봐도 같다
            except Exception:
                busy = True     # 아직 준비가 안 됐을 수 있다
        if fast_dev is not None or not busy:
            break
        time.sleep(0.05)
except Exception:
    fast_dev = None

if fast_dev is None:
    try:
        from adafruit_hid.mouse import Mouse
        mouse = Mouse(usb_hid.devices)
        BUTTON_CODES = (Mouse.LEFT_BUTTON, Mouse.RIGHT_BUTTON,
                        Mouse.MIDDLE_BUTTON)
    except Exception as err:
        start_error = err

if fast_dev is None and mouse is None:
    # 마우스를 못 만들었으면 최소한 무슨 일인지는 알려 주고,
    # 포트는 계속 비워 준다. 멈추면 PC 가 원인을 볼 수 없다.
    while True:
        say("MOUSE FAIL " + repr(start_error))
        for _ in range(20):
            if port.in_waiting:
                port.read(port.in_waiting)
            time.sleep(0.05)

BUTTON_BITS = (0x01, 0x02, 0x04)
fb_btn = 0              # 보통 마우스 쪽에 실제로 눌러 둔 버튼


def clamp(value, limit):
    """한 번에 보낼 수 있는 범위로 자른다."""
    if value > limit:
        return limit
    if value < -limit:
        return -limit
    return value


def to_signed(value):
    """0~255 로 온 값을 -128~127 로 되돌린다."""
    return value - 256 if value > 127 else value


def emit(x, y, wheel, buttons):
    """이동과 버튼 상태를 한 보고로 내보내고, 실제로 내보낸 양을 돌려준다."""
    global fb_btn
    cw = clamp(wheel, WHEEL_LIMIT)
    if fast_dev is not None:
        cx = clamp(x, FAST_LIMIT)
        cy = clamp(y, FAST_LIMIT)
        fast_dev.send_report(bytes((buttons & 0x1F,
                                    cx & 0xFF, (cx >> 8) & 0xFF,
                                    cy & 0xFF, (cy >> 8) & 0xFF,
                                    cw & 0xFF)))
        return cx, cy, cw

    cx = clamp(x, SLOW_LIMIT)
    cy = clamp(y, SLOW_LIMIT)
    if cx or cy or cw:
        # 보통 마우스는 이동과 버튼을 따로 보고해야 한다. 움직일 것이
        # 없을 때까지 보고를 쓰면 그만큼 클릭이 늦어지므로 건너뛴다.
        mouse.move(x=cx, y=cy, wheel=cw)
    if buttons != fb_btn:
        for index in range(3):
            bit = BUTTON_BITS[index]
            if (buttons & bit) and not (fb_btn & bit):
                mouse.press(BUTTON_CODES[index])
            elif (fb_btn & bit) and not (buttons & bit):
                mouse.release(BUTTON_CODES[index])
        fb_btn = buttons
    return cx, cy, cw


def too_big(x, y, wheel):
    """한 보고로 다 못 담는 양인지 본다."""
    return (x > LIMIT or x < -LIMIT or y > LIMIT or y < -LIMIT
            or wheel > WHEEL_LIMIT or wheel < -WHEEL_LIMIT)


buf = bytearray()
pos = 0             # 버퍼에서 어디까지 읽었는지
held = 0            # PC 가 알려 준, 지금 눌려 있어야 하는 버튼
pend_x = 0          # 아직 못 내보낸 이동량
pend_y = 0
pend_w = 0
last_blink = time.monotonic()
last_good = time.monotonic()
trouble = False
said = 0
want_release = False    # 오류 뒤 버튼을 놓아 줘야 하는지
greeting = "READY " + ("16" if fast_dev is not None else "8")
greeted = False         # PC 가 첫 자료를 보내 줬는지
last_greet = 0.0

# 첫 자료가 오기 전까지는 인사를 되풀이한다. PC 가 포트를 여는 시점은
# 피코가 켜진 시점보다 한참 뒤라서, 한 번만 말하면 아무도 못 듣는다.
say(greeting)

while True:
    try:
        waiting = port.in_waiting
        if waiting:
            buf.extend(port.read(waiting))
            led.value = not led.value

            # CircuitPython 의 bytearray 는 del 을 지원하지 않는다.
            # 그래서 지우는 대신 어디까지 읽었는지만 세어 둔다.
            while len(buf) - pos >= FRAME:
                if buf[pos] != SYNC:
                    pos += 1            # 묶음 시작이 아니면 한 칸 밀어 다시 찾는다
                    continue

                want = buf[pos + 3]
                if want > 0x07:
                    # 버튼 자리에는 1,2,4 를 더한 값(0~7) 만 올 수 있다.
                    # 그 밖의 값이면 묶음 시작을 잘못 짚은 것이므로, 다섯
                    # 바이트를 삼키지 말고 한 칸만 밀어 다시 찾는다.
                    # 안 그러면 깨진 바이트 때문에 엉뚱한 버튼이 눌린다.
                    pos += 1
                    continue

                frame = bytes(buf[pos:pos + FRAME])
                pos += FRAME

                if want != held:
                    # 모아 둔 이동을 먼저 비운다. 마지막 한 보고에 새 버튼
                    # 상태를 같이 실어서, 클릭이 이동이 끝난 자리에서
                    # 일어나게 한다. 이렇게 하면 보고를 한 번 덜 쓴다.
                    while True:
                        more = too_big(pend_x, pend_y, pend_w)
                        ex, ey, ew = emit(pend_x, pend_y, pend_w,
                                          held if more else want)
                        pend_x -= ex
                        pend_y -= ey
                        pend_w -= ew
                        if not more:
                            break
                    held = want

                greeted = True
                pend_x += to_signed(frame[1])
                pend_y += to_signed(frame[2])
                pend_w += to_signed(frame[4])

            if pos:
                buf = buf[pos:]         # 다 쓴 앞부분을 잘라 낸다
                pos = 0

        if want_release:
            # 오류 뒤에는 버튼을 놓는 보고를 반드시 한 번 내보낸다.
            # 보낼 이동이 없으면 아무 보고도 안 나가므로, PC 쪽에서는
            # 버튼이 눌린 채로 남아 화면이 잠긴 것처럼 보인다.
            emit(0, 0, 0, 0)
            want_release = False

        if pend_x or pend_y or pend_w:
            ex, ey, ew = emit(pend_x, pend_y, pend_w, held)
            pend_x -= ex
            pend_y -= ey
            pend_w -= ew
        else:
            now = time.monotonic()
            gap = 0.1 if trouble else BLINK
            if now - last_blink >= gap:
                last_blink = now
                led.value = not led.value
            if not greeted and now - last_greet >= 1.0:
                last_greet = now
                say(greeting)

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
        pos = 0
        pend_x = 0
        pend_y = 0
        pend_w = 0
        held = 0
        # 버튼이 눌린 채로 남으면 안 된다. 여기서 바로 놓으려 하면 같은
        # 오류로 또 막힐 수 있으므로, 표시만 남겨 두고 다음 바퀴에서
        # 성공할 때까지 다시 시도한다.
        want_release = True
        time.sleep(0.05)
