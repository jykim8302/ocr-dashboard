# 라즈베리파이 피코에 넣는 파일 (1/2)
# 이 파일은 피코가 켜질 때 딱 한 번 실행됩니다.
#
# 피코를 두 가지로 동시에 동작하게 만듭니다.
#   1. USB 마우스 (HID)
#   2. PC 와 데이터를 주고받는 시리얼 포트
#
# 이 파일이 없으면 PC 가 피코로 움직임을 보낼 수 없습니다.

import usb_cdc

usb_cdc.enable(console=True, data=True)
