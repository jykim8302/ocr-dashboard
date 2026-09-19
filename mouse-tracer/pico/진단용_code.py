# 진단용 파일입니다. 잠깐만 쓰고 원래 code.py 로 되돌리세요.
#
# 피코의 초록색 LED 로 지금 상태를 알려 줍니다.
#
#   계속 켜져 있음      -> boot.py 가 적용되지 않았습니다 (데이터 포트 없음)
#   빠르게 깜박임       -> adafruit_hid 라이브러리에 문제가 있습니다
#   천천히 깜박임       -> 정상입니다. 자료를 기다리는 중입니다
#   불규칙하게 깜박임   -> PC 에서 보낸 자료를 잘 받고 있습니다

import time
import board
import digitalio

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# 1. 데이터 포트가 있는지
try:
    import usb_cdc
    port = usb_cdc.data
except Exception:
    port = None

if port is None:
    # boot.py 가 적용되지 않았다. 불을 계속 켜 둔다.
    while True:
        led.value = True
        time.sleep(0.5)

# 2. 마우스 라이브러리가 있는지
library_ok = True
try:
    import usb_hid
    from adafruit_hid.mouse import Mouse
    Mouse(usb_hid.devices)
except Exception:
    library_ok = False

# 3. 자료를 계속 받아서 버린다 (막히지 않는지 보려는 것)
last = time.monotonic()
while True:
    waiting = port.in_waiting
    if waiting:
        port.read(waiting)
        led.value = not led.value      # 자료가 오면 불규칙하게 깜박
        continue

    now = time.monotonic()
    gap = 0.1 if not library_ok else 0.5
    if now - last >= gap:
        last = now
        led.value = not led.value      # 라이브러리 문제면 빠르게, 정상이면 천천히
