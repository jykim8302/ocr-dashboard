# -*- coding: utf-8 -*-
"""mouse_tracer 점검 스크립트.

Windows 전용 프로그램이라 리눅스에서는 실행할 수 없다. 그래서 Win32 함수를
가짜로 바꿔치우고 모듈을 불러들여, 실행 없이 확인할 수 있는 것을 전부 본다.

    python3 tests/check.py

한 항목이라도 실패하면 종료 코드 1 을 돌려준다.
"""
import ctypes, io, sys, types, os, importlib.util, tempfile, random, time

class FakeFunc:
    def __init__(s, n): s.n = n; s.argtypes = None; s.restype = None
    def __call__(s, *a, **k): return 0
class FakeDLL:
    def __init__(s, *a, **k): s._c = {}
    def __getattr__(s, n): return s._c.setdefault(n, FakeFunc(n))

ctypes.WinDLL = FakeDLL
ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
_err = {"v": 0}
ctypes.set_last_error = lambda v: _err.__setitem__("v", v)
ctypes.get_last_error = lambda: _err["v"]
for m in ('tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox'):
    sys.modules[m] = types.ModuleType(m)
for sub in ('ttk', 'filedialog', 'messagebox'):
    setattr(sys.modules['tkinter'], sub, sys.modules['tkinter.' + sub])

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, "mouse_tracer.py")

real = os.name; os.name = 'nt'
spec = importlib.util.spec_from_file_location("mt", TARGET)
mt = importlib.util.module_from_spec(spec); spec.loader.exec_module(mt)
os.name = real

fails = []
ran = [0]
def check(name, ok, detail=""):
    ran[0] += 1
    print(("  통과  " if ok else "  실패  ") + name + (" :: " + detail if detail else ""))
    if not ok: fails.append(name)

print("=== 1. Win32 구조체 크기 (64비트 Windows 기준) ===")
for n, want in (("RAWINPUTHEADER",24), ("RAWMOUSE",24), ("RAWKEYBOARD",16),
                ("RAWINPUT",48), ("RAWINPUTDEVICE",16), ("MOUSEINPUT",32),
                ("KEYBDINPUT",24), ("INPUT",40), ("MSG",48), ("POINT",8),
                ("DCB",28), ("COMMTIMEOUTS",20)):
    got = ctypes.sizeof(getattr(mt, n))
    check("%s = %d" % (n, want), got == want, "실제 %d" % got)
for n, field, want in (("RAWMOUSE","lLastX",12), ("RAWMOUSE","btn",4),
                       ("RAWINPUT","data",24), ("INPUT","mi",8)):
    got = getattr(getattr(mt, n), field).offset
    check("%s.%s 위치 %d" % (n, field, want), got == want, "실제 %d" % got)

print()
print("=== 2. 원시 입력 분류 (진짜 마우스 vs 만들어낸 입력) ===")
e = mt.Engine(); e.recording = True; e._t0 = time.perf_counter()
addr = ctypes.addressof(e._buf)
step = (ctypes.sizeof(mt.RAWINPUT) + mt.RAW_ALIGN - 1) & ~(mt.RAW_ALIGN - 1)
def put(off, dx, dy, extra, hdev, bf=0):
    ri = mt.RAWINPUT.from_address(addr + off)
    ri.header.dwType = mt.RIM_TYPEMOUSE
    ri.header.dwSize = ctypes.sizeof(mt.RAWINPUT)
    ri.header.hDevice = hdev
    ri.data.mouse.lLastX = dx; ri.data.mouse.lLastY = dy
    ri.data.mouse.btn.usButtonFlags = bf
    ri.data.mouse.ulExtraInformation = extra
put(0,        9,  0, mt.SIGNATURE, 0)       # 우리 표식 있는 합성 입력
put(step,     4,  0, 0,            0)       # 표식은 지워졌지만 장치번호 0 -> 합성
put(step*2,   3, -1, 0,            5150)    # 진짜 마우스
put(step*3,   0,  0, 0,            5150, 0x0001)  # 진짜 마우스 왼쪽 누름
calls = {"n": 0}
mt.user32.GetRawInputBuffer = lambda *a: 4 if calls.__setitem__("n", calls["n"]+1) or calls["n"] == 1 else 0
e._drain_buffer()
check("합성 입력 2개 걸러냄", e.inj_packets == 2, "%d개" % e.inj_packets)
check("하드웨어 2개만 기록", len(e.events) == 2, "%d개" % len(e.events))
check("마지막 원시 이동 보존", (e.raw_dx, e.raw_dy) == (3, -1), str((e.raw_dx, e.raw_dy)))
check("장치번호 0 을 합성으로 판정", e.inj_hdevice == 0, str(e.inj_hdevice))

print()
print("=== 3. 재생 로직 (버튼/휠/키보드/자동해제) ===")
sent = []
mt.send = lambda b: (sent.extend(b), len(b))[1]
e2 = mt.Engine()
e2.events = [["m",0.000, 7,-3, 0,      0, 0],
             ["m",0.002, 0, 0, 0x0001, 0, 0],   # 왼쪽 누름
             ["m",0.004, 0, 0, 0x0400, -120, 0],# 휠 아래
             ["k",0.006, 30, 0, 0x41],          # A 누름
             ["m",0.008, 0, 0, 0x0004, 0, 0]]   # 오른쪽 누름 (안 뗌)
e2._play_worker(1, 1.0, False, False, 0)
kinds = [(i.type, hex(i.mi.dwFlags) if i.type == mt.INPUT_MOUSE else hex(i.ki.dwFlags)) for i in sent]
check("이동은 상대 이동 플래그", kinds[0] == (0, '0x2001'), str(kinds[0]))
check("왼쪽 누름 전달", ('0x2' in kinds[1][1]), str(kinds[1]))
check("휠 전달", any(k[1] == '0x800' for k in kinds), "")
check("키보드는 스캔코드로", any(k[0] == 1 and k[1] == '0x8' for k in kinds), "")
check("안 뗀 오른쪽 버튼 자동 해제", any(k[1] == '0x10' for k in kinds[-3:]), str(kinds[-3:]))
check("눌린 키 자동 해제", any(k[0] == 1 and k[1] == '0xa' for k in kinds[-3:]), "")

print()
print("=== 4. 피코 경로 (총 이동량 보존 / 클릭 보존) ===")
buf = bytearray()
class Link:
    handle = 1
    def write(self, d): buf.extend(d); return True
    def close(self): pass
e3 = mt.Engine(); e3.pico = Link(); e3.use_pico = True
random.seed(11); total = [0, 0]
for k in range(1000):
    dx, dy = random.randint(-9, 9), random.randint(-9, 9)
    total[0] += dx; total[1] += dy
    e3._emit([mt.mouse_input(dx, dy, 0, mt.MOUSEEVENTF_MOVE)])
    if k == 300: e3._emit([mt.mouse_input(0,0,0, mt.MOUSEEVENTF_LEFTDOWN)])
    if k == 340: e3._emit([mt.mouse_input(0,0,0, mt.MOUSEEVENTF_LEFTUP)])
    time.sleep(0.0008)
e3._pico_flush()
frames = [buf[i:i+5] for i in range(0, len(buf), 5)]
sx = sy = 0; changes = 0; prev = 0; bad_sync = 0
for f in frames:
    if f[0] != mt.PICO_SYNC: bad_sync += 1
    sx += f[1]-256 if f[1] > 127 else f[1]
    sy += f[2]-256 if f[2] > 127 else f[2]
    if f[3] != prev: changes += 1; prev = f[3]
check("총 이동량 그대로", (sx, sy) == tuple(total), "원본 %s / 전송 %s" % (tuple(total), (sx, sy)))
check("클릭 누름+뗌 2번만", changes == 2, "%d번" % changes)
check("모든 묶음 시작표시 정상", bad_sync == 0, "%d개 깨짐" % bad_sync)
check("전송량 줄어듦", len(frames) < 400, "%d묶음 (원본 1002건)" % len(frames))
check("모든 값 범위 안", all(-127 <= (f[1]-256 if f[1]>127 else f[1]) <= 127 for f in frames), "")

print()
print("=== 5. 피코 펌웨어 (pico/code.py 를 실제로 돌린다) ===")

class _Stop(BaseException):
    """프레임을 다 먹인 뒤 펌웨어의 무한 루프를 빠져나오기 위한 신호.

    펌웨어가 Exception 을 모두 잡아 계속 도는 구조라, 그 그물에 걸리지
    않도록 BaseException 에서 갈라져 나온다.
    """


def run_firmware(frame_bytes, fast=False, fail_at=None):
    """pico/code.py 를 그대로 불러들여 프레임을 먹이고 무엇을 냈는지 본다.

    fast=True 면 boot.py 가 만드는 "큰 걸음 마우스"(한 보고에 32767 까지,
    6바이트 보고) 가 꽂혀 있는 상황을 흉내 낸다. fast=False 면 그 장치가
    없어서 보통 마우스(한 보고에 127 까지) 로 되돌아가는 상황이다.
    """
    moves, buttons, said, reports = [], [], [], []

    class FakeMouse:
        LEFT_BUTTON, RIGHT_BUTTON, MIDDLE_BUTTON = 1, 2, 4
        def __init__(self, devices): pass
        def move(self, x=0, y=0, wheel=0): moves.append((x, y, wheel))
        # 버튼 사건에 그때까지 나간 이동 횟수를 같이 적어 순서를 확인한다
        def press(self, code): buttons.append(("press", code, len(moves)))
        def release(self, code): buttons.append(("release", code, len(moves)))

    class FakePort:
        """자료를 다 먹인 뒤에도 잠깐은 더 돌게 해 준다.

        펌웨어는 한 바퀴에 한 조각씩만 내보내므로, 자료가 떨어지자마자
        멈추면 아직 못 내보낸 이동량이 남는다. 실제 장치에서는 루프가
        계속 도니 그 부분까지 보려면 빈 상태로 몇 바퀴 더 줘야 한다.
        """
        IDLE_ROUNDS = 60

        def __init__(self, data):
            # 묶음 하나를 통째로 주면 한 바퀴에 다 읽어 간다.
            # 여러 토막으로 나눠 주면 한 바퀴에 한 토막씩만 읽어 가서,
            # 실제 장치처럼 "자료가 시간에 걸쳐 들어오는" 상황이 된다.
            if isinstance(data, (bytes, bytearray)):
                self.chunks = [bytearray(data)] if data else []
            else:
                self.chunks = [bytearray(c) for c in data if c]
            self.idle = 0

        @property
        def in_waiting(self):
            if self.chunks:
                self.idle = 0
                return len(self.chunks[0])
            self.idle += 1
            if self.idle > self.IDLE_ROUNDS:
                raise _Stop()
            return 0

        def read(self, n):
            cur = self.chunks[0]
            out = bytes(cur[:n]); del cur[:n]
            if not cur:
                self.chunks.pop(0)
            return out

        def write(self, payload):
            said.append(bytes(payload))
            return len(payload)

    class FakePin:
        pass

    class FakeDirection:
        OUTPUT = "output"
        INPUT = "input"

    class FakeDigitalInOut:
        def __init__(self, pin): self.direction = None; self.value = False

    class FakeStdMouseDev:
        """보통 마우스. 6바이트 보고는 길이가 안 맞아서 거절한다."""
        usage_page, usage = 0x01, 0x02
        def send_report(self, report, report_id=None):
            if len(report) != 4:
                raise ValueError("report length must be 4")
            reports.append(("std", bytes(report)))

    class FakeFastMouseDev:
        """큰 걸음 마우스. 6바이트 보고만 받는다.

        fail_at 을 주면 그 번째 보고에서 한 번 실패한다. 실제 장치에서
        USB 가 잠깐 막히는 상황을 흉내 내서, 그 뒤에도 버튼이 눌린 채로
        남지 않는지 보려는 것이다.
        """
        usage_page, usage = 0x01, 0x02
        def send_report(self, report, report_id=None):
            if len(report) != 6:
                raise ValueError("report length must be 6")
            if fail_at is not None and len(reports) == fail_at:
                reports.append(("실패", bytes(report)))
                raise OSError("USB busy")
            reports.append(("fast", bytes(report)))

    usb_cdc = types.ModuleType("usb_cdc"); usb_cdc.data = FakePort(frame_bytes)
    usb_hid = types.ModuleType("usb_hid")
    # boot.py 와 같은 순서로 꽂아 둔다: 보통 마우스가 먼저, 큰 걸음이 뒤
    usb_hid.devices = ([FakeStdMouseDev(), FakeFastMouseDev()] if fast else [])
    pkg = types.ModuleType("adafruit_hid")
    mouse_mod = types.ModuleType("adafruit_hid.mouse")
    mouse_mod.Mouse = FakeMouse
    pkg.mouse = mouse_mod
    board_mod = types.ModuleType("board"); board_mod.LED = FakePin()
    digitalio_mod = types.ModuleType("digitalio")
    digitalio_mod.DigitalInOut = FakeDigitalInOut
    digitalio_mod.Direction = FakeDirection
    names = ("usb_cdc", "usb_hid", "adafruit_hid", "adafruit_hid.mouse",
             "board", "digitalio")
    saved = dict((n, sys.modules.get(n)) for n in names)
    sys.modules.update({"usb_cdc": usb_cdc, "usb_hid": usb_hid,
                        "adafruit_hid": pkg, "adafruit_hid.mouse": mouse_mod,
                        "board": board_mod, "digitalio": digitalio_mod})
    try:
        fw_spec = importlib.util.spec_from_file_location(
            "pico_code", os.path.join(ROOT, "pico", "code.py"))
        fw = importlib.util.module_from_spec(fw_spec)
        try:
            fw_spec.loader.exec_module(fw)
        except _Stop:
            pass
    finally:
        for n, old in saved.items():
            if old is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = old
    run_firmware.said = said
    run_firmware.used_fast = False
    run_firmware.leaked = False
    if fast:
        # 6바이트 보고를 (가로, 세로, 휠) 과 버튼 변화로 되돌려서,
        # 보통 마우스 쪽과 똑같은 모양으로 견주어 볼 수 있게 한다.
        #
        # 여기서는 멈추지 않는다. 멈추면 뒤에 있는 검사 100여 개가
        # 아예 돌지 않아서, 무엇이 깨졌는지 한눈에 볼 수 없게 된다.
        # 그래서 표시만 남기고 검사 쪽에서 판단하게 한다.
        probe = None
        for _idx in range(len(reports)):
            if reports[_idx] == ("fast", b"\x00" * 6):
                probe = _idx            # 마우스를 고를 때 넣어 본 빈 보고
                break
        run_firmware.used_fast = probe is not None
        prev = 0
        for kind, rep in reports[(len(reports) if probe is None
                                  else probe + 1):]:
            if kind == "실패":
                continue            # 호스트까지 가지 않은 보고
            if kind != "fast":
                run_firmware.leaked = True
                continue            # 보통 마우스로 새어 나간 보고
            btn = rep[0]
            x = int.from_bytes(rep[1:3], "little", signed=True)
            y = int.from_bytes(rep[3:5], "little", signed=True)
            w = rep[5] - 256 if rep[5] > 127 else rep[5]
            moves.append((x, y, w))
            for index, bit in enumerate((0x01, 0x02, 0x04)):
                if (btn & bit) and not (prev & bit):
                    buttons.append(("press", 1 << index, len(moves)))
                elif (prev & bit) and not (btn & bit):
                    buttons.append(("release", 1 << index, len(moves)))
            prev = btn
    run_firmware.reports = reports
    return moves, buttons


# 8-1) 큰 이동량을 먹여도 총합이 보존되고 한 번에 127 을 넘지 않는다
random.seed(5)
pairs = [(random.randint(-400, 400), random.randint(-400, 400)) for _ in range(60)]
data = b"".join(mt.pico_frames(dx, dy, 0, 0) for dx, dy in pairs)
moves, buttons = run_firmware(data)
want = (sum(a for a, _b in pairs), sum(b for _a, b in pairs))
got = (sum(m[0] for m in moves), sum(m[1] for m in moves))
check("펌웨어 총 이동량 보존", got == want, "%s -> %s" % (want, got))
check("한 보고가 127 을 안 넘음",
      all(-127 <= m[0] <= 127 and -127 <= m[1] <= 127 for m in moves), "")

# 8-2) 휠도 그대로 전달된다
moves, buttons = run_firmware(mt.pico_frames(0, 0, 0, 3)
                              + mt.pico_frames(0, 0, 0, -1))
check("펌웨어 휠 전달", sum(m[2] for m in moves) == 2,
      "%d칸" % sum(m[2] for m in moves))

# 8-3) 버튼은 모아 둔 이동을 먼저 내보낸 뒤에 눌린다
data = (mt.pico_frames(30, 0, 0, 0) + mt.pico_frames(20, 0, 0, 0)
        + mt.pico_frames(0, 0, 0x01, 0) + mt.pico_frames(0, 0, 0, 0))
moves, buttons = run_firmware(data)
presses = [b for b in buttons if b[0] == "press"]
check("이동을 먼저 내보낸 뒤 누름",
      bool(presses) and presses[0][2] >= 1 and moves[0] == (50, 0, 0),
      "이동=%s 버튼=%s" % (moves[:2], buttons))
check("누른 뒤 놓기까지", [b[0] for b in buttons] == ["press", "release"],
      str([b[0] for b in buttons]))

# 8-4) 앞에 쓰레기 바이트가 섞여도 다시 맞춰 읽는다
moves, buttons = run_firmware(b"\x00\x11\x22" + mt.pico_frames(7, -5, 0, 0))
check("깨진 앞부분 건너뛰고 복구", moves and moves[0] == (7, -5, 0), str(moves[:1]))

# 8-4-2) PC 가 버튼 자리에 보내는 값은 0~7 뿐이어야 한다.
#        펌웨어가 그 범위로 묶음 시작을 확인하기 때문에, 여기가 넓어지면
#        깨진 바이트를 걸러내는 장치가 조용히 무력해진다.
_btn_bytes = set()
for _b in range(0, 8):
    for _frame_start in range(0, len(mt.pico_frames(300, -300, _b, 200)), 5):
        _f = mt.pico_frames(300, -300, _b, 200)
        _btn_bytes.add(_f[_frame_start + 3])
check("PC 가 보내는 버튼 값은 0~7 뿐",
      _btn_bytes == set(range(8)), str(sorted(_btn_bytes)))

# 8-4-3) PC 가 물으면 언제든 어떤 펌웨어인지 답해야 한다.
#        보드는 PC 가 말을 걸면 인사를 멈추는데, 그 뒤 프로그램을 다시
#        켜면 물어볼 길이 없어서 피코를 뺐다 꽂아야 했다 (실제로 그랬다).
_ask = bytes(mt.PICO_ASK)
run_firmware(mt.pico_frames(1, 0, 0, 0) + _ask, fast=True)
_said = [b for b in run_firmware.said if b.startswith(b"READY")]
check("한 번 말을 건 뒤에 물어도 답함", len(_said) >= 2,
      str(run_firmware.said[:4]))
check("답에 큰 걸음이라고 적혀 있음",
      _said and _said[-1].strip() == b"READY 16", str(_said[-1:]))

# 물어보는 묶음은 움직임이 아니다. 커서가 움직이면 안 된다.
_am, _ab = run_firmware(_ask, fast=True)
check("물어보는 묶음으로는 안 움직임",
      all(m == (0, 0, 0) for m in _am) and _ab == [], str(_am[:3]))

# 옛 펌웨어는 0xAC 를 모른다. 그래도 뒤에 오는 진짜 묶음은 살아야 한다.
_om, _ob = run_firmware(_ask + mt.pico_frames(7, -5, 0, 0), fast=False)
check("옛 펌웨어도 물음표 뒤의 움직임을 살림",
      (sum(m[0] for m in _om), sum(m[1] for m in _om)) == (7, -5), str(_om))

# 8-5) boot.py 가 만든 "큰 걸음 마우스" 가 있으면 그걸 골라 쓴다.
#      고를 때는 전부 0 인 빈 보고를 한 번 넣어 보는데, 뒤에 꽂힌 것부터
#      보기 때문에 보통 마우스에는 엉뚱한 길이가 가지 않아야 한다.
flick = mt.pico_frames(2000, -1500, 0, 0)
moves, buttons = run_firmware(flick, fast=True)
check("큰 걸음 마우스를 골라 씀",
      run_firmware.used_fast and not run_firmware.leaked,
      str([k for k, _r in run_firmware.reports[:3]]))
check("큰 걸음 쪽 총 이동량 보존",
      (sum(m[0] for m in moves), sum(m[1] for m in moves)) == (2000, -1500),
      str((sum(m[0] for m in moves), sum(m[1] for m in moves))))
check("빠른 이동도 보고 한 번으로 끝남", len(moves) == 1, "%d번" % len(moves))

# 8-6) 큰 걸음 마우스가 없으면 보통 마우스로 되돌아간다.
#      그 쪽은 한 보고에 127 까지라서 같은 이동에 보고를 훨씬 많이 쓴다.
slow_moves, _slow_buttons = run_firmware(flick, fast=False)
check("큰 걸음이 없으면 보통 마우스로 되돌아감",
      slow_moves and sum(m[0] for m in slow_moves) == 2000,
      "%d번 보고 / 총 %d" % (len(slow_moves), sum(m[0] for m in slow_moves)))
check("보통 마우스는 같은 이동에 보고를 훨씬 많이 씀",
      len(slow_moves) >= 16 and len(moves) * 8 < len(slow_moves),
      "큰 걸음 %d번 vs 보통 %d번" % (len(moves), len(slow_moves)))

# 8-7) 버튼이 바뀌는 보고에 밀린 이동을 같이 실어서 보고를 한 번 아낀다.
#      (보고 한 번이 USB 간격 한 번이라 그만큼 클릭이 빨리 시작된다)
data = (mt.pico_frames(30, 0, 0, 0) + mt.pico_frames(20, 0, 0, 0)
        + mt.pico_frames(0, 0, 0x01, 0) + mt.pico_frames(0, 0, 0, 0))
moves, buttons = run_firmware(data, fast=True)
press_at = [b[2] for b in buttons if b[0] == "press"][0]
check("누르는 보고에 밀린 이동을 같이 실음",
      moves[press_at - 1] == (50, 0, 0), str(moves[:2]))

# 8-8) 클릭이 늘어나지 않는지. 자료가 시간에 걸쳐 들어오는 상황을 흉내 낸다.
#      한 바퀴(USB 간격 한 번) 에 들어오는 이동량이 127 을 넘으면 보통
#      마우스는 보낼 양이 밀리고, 밀린 양을 비우는 데 보고를 더 쓴다.
#      그래서 누름과 놓음 사이가 녹화보다 길어진다. 실제로 "움직임이
#      부자연스럽고 클릭이 더 오래 눌린다" 고 느껴진 원인이다.
HOLD_ROUNDS = 10


def timed_stream(per_flush, rounds=40, hold=(15, 25), flush_per_round=4):
    """한 바퀴마다 flush_per_round 번씩 보낸 것처럼 토막을 만든다."""
    out = []
    for index in range(rounds):
        btn = 0x01 if hold[0] <= index < hold[1] else 0
        out.append(b"".join(mt.pico_frames(per_flush, 0, btn, 0)
                            for _ in range(flush_per_round)))
    return out


def hold_length(per_flush, fast):
    """눌려 있던 동안 보고를 몇 번 썼는지 센다 (= 눌린 시간)."""
    _m, btns = run_firmware(timed_stream(per_flush), fast=fast)
    kinds = [b[0] for b in btns]
    if kinds != ["press", "release"]:
        return None, len(_m), kinds
    pressed = [b[2] for b in btns if b[0] == "press"][0]
    released = [b[2] for b in btns if b[0] == "release"][0]
    return released - pressed, len(_m), kinds


for _per in (40, 60, 100):
    fast_hold, fast_total, fast_kinds = hold_length(_per, True)
    check("큰 걸음: 한 바퀴 %d 여도 누름/놓음 한 번씩" % (_per * 4),
          fast_kinds == ["press", "release"], str(fast_kinds))
    check("큰 걸음: 한 바퀴 %d 여도 클릭이 안 늘어남" % (_per * 4),
          fast_hold == HOLD_ROUNDS + 1,
          "녹화 %d바퀴 -> %s바퀴" % (HOLD_ROUNDS, fast_hold))
    check("큰 걸음: 한 바퀴 %d 여도 전체 길이가 안 늘어남" % (_per * 4),
          fast_total <= 45, "보고 %d번" % fast_total)

# 8-9) 위 검사가 진짜로 늘어난 것을 잡아내는지 확인한다.
#      보통 마우스 경로는 같은 상황에서 분명히 늘어나야 한다.
slow_hold, slow_total, _k = hold_length(100, False)
check("보통 마우스 경로에서는 클릭이 늘어남 (검사가 작동하는 증거)",
      slow_hold is not None and slow_hold > HOLD_ROUNDS + 5,
      "녹화 %d바퀴 -> %s바퀴" % (HOLD_ROUNDS, slow_hold))
check("보통 마우스 경로에서는 전체도 늘어남 (검사가 작동하는 증거)",
      slow_total > 45 + 20, "보고 %d번" % slow_total)

# 8-10) 깨진 바이트를 버튼으로 오인해서 엉뚱한 버튼을 누르면 안 된다.
#       PC 는 버튼 자리에 0~7 만 보낸다.
junk_moves, junk_buttons = run_firmware(
    b"\xab\x00\x00\xff\x00" * 50 + mt.pico_frames(9, 0, 0, 0), fast=True)
check("깨진 바이트로 엉뚱한 버튼을 누르지 않음", junk_buttons == [],
      str(junk_buttons))
check("깨진 바이트 뒤의 정상 이동은 살림",
      sum(m[0] for m in junk_moves) == 9,
      "총 %d" % sum(m[0] for m in junk_moves))

# 8-11) 보내기가 한 번 실패해도 버튼이 눌린 채로 남지 않는다.
#       눌린 채로 남으면 PC 가 잠긴 것처럼 된다.
err_moves, err_buttons = run_firmware(
    mt.pico_frames(0, 0, 0x01, 0) + mt.pico_frames(5, 0, 0x01, 0),
    fast=True, fail_at=1)
check("보내기가 실패하면 알림을 보냄",
      any(b"ERR" in line for line in run_firmware.said),
      str(run_firmware.said[:3]))
# 실제로 호스트까지 간 보고만 본다. 하나도 없으면 놓은 적이 없는 것이므로
# 비어 있다는 이유로 통과하면 안 된다 (all([]) 은 참이다).
_sent = [rep for kind, rep in run_firmware.reports if kind == "fast"]
check("실패 뒤에 버튼을 반드시 놓아 둠",
      len(_sent) >= 2 and (_sent[-1][0] & 0x07) == 0,
      "호스트로 간 보고 %d개 / 마지막 %s"
      % (len(_sent), _sent[-1].hex() if _sent else "없음"))

# 8-12) 켜진 직후 보고가 한 번 막혀도 큰 걸음 마우스를 포기하지 않는다
_m12, _b12 = run_firmware(mt.pico_frames(2000, 0, 0, 0), fast=True, fail_at=0)
check("탐색이 한 번 막혀도 큰 걸음으로 붙음",
      run_firmware.used_fast and len(_m12) == 1 and _m12[0] == (2000, 0, 0),
      "큰걸음=%s 보고=%s" % (run_firmware.used_fast, _m12[:3]))

print()
print("=== 6. 단축키 ===")
e4 = mt.Engine(); e4.hwnd = 999
reg = []
mt.user32.RegisterHotKey = lambda h, i, m, v: (reg.append((i, m, v)), 0 if v == 0x77 else 1)[1]
mt.user32.UnregisterHotKey = lambda h, i: 1
e4.hotkeys = {"record": ["F9", mt.MOD_CONTROL], "play": ["숫자패드 1", 0], "stop": ["F8", 0]}
e4._register_hotkeys()
check("모든 키 코드 유효", all(n in mt.KEY_CODES for n in mt.KEY_NAMES), "")
check("성공한 것만 기억함 (조합키까지)",
      e4.hotkey_chords == [(0x78, mt.MOD_CONTROL), (0x61, 0)],
      str(e4.hotkey_chords))
check("등록 실패한 것은 목록에 없음",
      all(vk != 0x77 for vk, _m in e4.hotkey_chords), str(e4.hotkey_chords))
check("반복 입력 방지 플래그", all(m & mt.MOD_NOREPEAT for _, m, _ in reg), "")
check("표시 글자", mt.hotkey_text(["F6", mt.MOD_CONTROL | mt.MOD_SHIFT]) == "Ctrl+Shift+F6", "")

print()
print("=== 7. 설정 저장 / 불러오기 ===")
d = tempfile.mkdtemp(); mt.SETTINGS_FILE = os.path.join(d, "s.json")
cfg = {"hotkeys": {"record": ["F9", 2], "play": ["F10", 0], "stop": ["F11", 0]},
       "repeat": "3", "speed": "1.5", "gap": "0.2", "pico_port": "COM7",
       "keyboard": False, "goto_start": True, "precise": False}
mt.save_settings(cfg)
check("왕복 일치", mt.load_settings() == cfg, "")
mt.SETTINGS_FILE = os.path.join(d, "없는파일.json")
check("파일 없으면 빈 값", mt.load_settings() == {}, "")
with open(os.path.join(d, "깨짐.json"), "w") as _f:
    _f.write("{이건 json 이 아님")
mt.SETTINGS_FILE = os.path.join(d, "깨짐.json")
check("깨진 파일도 안 죽음", mt.load_settings() == {}, "")

print()
print("=== 8. 기록 저장 / 불러오기 ===")
e5 = mt.Engine()
e5.events = [["m", 0.1, 3, -2, 1, 0, 0], ["k", 0.2, 30, 0, 65]]
e5.start_pos = (640, 480)
f = os.path.join(d, "rec.json"); e5.save(f)
e6 = mt.Engine(); e6.load(f)
check("기록 왕복 일치", e6.events == e5.events and e6.start_pos == (640, 480), "")
check("길이 계산", abs(e6.duration() - 0.2) < 1e-9, str(e6.duration()))


print()
print("=== 9. 이번에 고친 버그들 (재발 방지) ===")

# 12-1) 지금 마우스 설정을 못 읽으면 저장하지 않는다
e7 = mt.Engine()
writes = []
def spi_fail(action, a, b, c):
    if action in (mt.SPI_GETMOUSE, mt.SPI_GETMOUSESPEED):
        return 0                      # 읽기 실패
    writes.append(action); return 1
mt.user32.SystemParametersInfoW = spi_fail
e7._disable_accel()
check("읽기 실패하면 아무것도 안 바꿈", e7._saved_mouse is None and not writes,
      "저장=%s 변경=%d건" % (e7._saved_mouse, len(writes)))
e7._restore_mouse()
check("되돌릴 것도 없음", not writes, "%d건" % len(writes))

# 12-2) 속도 값이 말이 안 되면 건너뛴다
e8 = mt.Engine(); writes.clear()
def spi_zero(action, a, b, c):
    if action == mt.SPI_GETMOUSESPEED:
        ctypes.cast(b, ctypes.POINTER(ctypes.c_int)).contents.value = 0
        return 1
    if action == mt.SPI_GETMOUSE:
        return 1
    writes.append(action); return 1
mt.user32.SystemParametersInfoW = spi_zero
e8._disable_accel()
check("속도 0 이면 건너뜀", e8._saved_mouse is None and not writes,
      "저장=%s" % (e8._saved_mouse,))

# 12-3) 정상일 때는 저장하고 그대로 되돌린다
e9 = mt.Engine(); applied = []
def spi_ok(action, a, b, c):
    if action == mt.SPI_GETMOUSE:
        arr = ctypes.cast(b, ctypes.POINTER(ctypes.c_int * 3)).contents
        arr[0], arr[1], arr[2] = 6, 10, 1
        return 1
    if action == mt.SPI_GETMOUSESPEED:
        ctypes.cast(b, ctypes.POINTER(ctypes.c_int)).contents.value = 13
        return 1
    if action == mt.SPI_SETMOUSE:
        arr = ctypes.cast(b, ctypes.POINTER(ctypes.c_int * 3)).contents
        applied.append(("accel", arr[0], arr[1], arr[2]))
    else:
        applied.append(("speed", b))
    return 1
mt.user32.SystemParametersInfoW = spi_ok
e9._disable_accel()
check("정상이면 현재값 보관", e9._saved_mouse == ([6, 10, 1], 13), str(e9._saved_mouse))
check("재생 중엔 가속 끔", applied[0] == ("accel", 0, 0, 0), str(applied[0]))
applied.clear()
e9._restore_mouse()
check("끝나면 원래대로", applied and applied[0] == ("accel", 6, 10, 1), str(applied[:1]))

# 12-4) 녹화 중에 목록이 갈아치워져도 duration 이 안 터진다
import threading
e10 = mt.Engine()
stop = threading.Event(); err = []
def churn():
    while not stop.is_set():
        e10.events = [["m", 0.5, 1, 1, 0, 0, 0]]
        e10.events = []
t = threading.Thread(target=churn, daemon=True); t.start()
try:
    for _ in range(40000):
        e10.duration()
except Exception as ex:
    err.append(ex)
stop.set(); t.join(timeout=1)
check("duration 경쟁 상태 없음", not err, str(err[:1]))

# 12-5) 설정 파일이 망가져도 시작할 수 있다
class V:
    def __init__(s): s.v = None
    def set(s, x): s.v = x
    def get(s): return s.v
class R:
    def after(s, ms, fn): pass
fa = mt.App.__new__(mt.App)   # __init__ 없이 껍데기만 (tk 없이 검사하려고)
fa.eng = mt.Engine()
fa.hk_key = dict((k, V()) for k, _h, _l in mt.ACTIONS)
fa.hk_mod = dict((k, dict((b, V()) for b in (mt.MOD_CONTROL, mt.MOD_ALT, mt.MOD_SHIFT)))
                 for k, _h, _l in mt.ACTIONS)
for n in ("repeat", "speed", "gap", "port_var", "v_kbd", "v_goto", "v_prec"):
    setattr(fa, n, V())
fa.sync_opts = lambda: None
fa.root = R()
import json as _json
bad = os.path.join(d, "bad.json")
with open(bad, "w") as _f:
    _json.dump({"hotkeys": ["F6", "F7"], "repeat": 3}, _f)
mt.SETTINGS_FILE = bad
try:
    mt.App.load_saved(fa); ok = True; why = ""
except Exception as ex:
    ok = False; why = repr(ex)
check("hotkeys 가 목록이어도 안 죽음", ok, why)
check("기본 단축키로 되돌아감", fa.hk_key["record"].v == "F6", str(fa.hk_key["record"].v))

# 12-6) 한 칸 못 되는 휠도 버리지 않는다
buf2 = bytearray()
class L2:
    handle = 1
    def write(s, dd): buf2.extend(dd); return True
    def close(s): pass
e11 = mt.Engine(); e11.pico = L2(); e11.use_pico = True
for _ in range(3):
    e11._emit([mt.mouse_input(0, 0, 40, mt.MOUSEEVENTF_WHEEL)])   # 40 x 3 = 120
e11._pico_flush()
notches = sum((f - 256 if f > 127 else f) for f in
              [buf2[i + 4] for i in range(0, len(buf2), 5)])
check("휠 40씩 3번 = 1칸", notches == 1, "%d칸" % notches)


print()
print("=== 10. 전체 검토에서 나온 것들 (재발 방지) ===")

def pico_engine():
    out = bytearray()
    class L:
        handle = 1
        def write(self, dd): out.extend(dd); return True
        def close(self): pass
    en = mt.Engine(); en.pico = L(); en.use_pico = True
    return en, out

def frames_of(out):
    return [out[i:i + 5] for i in range(0, len(out), 5)]

def as_signed(v):
    return v - 256 if v > 127 else v

# 13-1) 화면 절대좌표 기록은 피코로 내보내지 않는다
en, out = pico_engine()
en._emit([mt.mouse_input(32000, 16000, 0,
                         mt.MOUSEEVENTF_MOVE | mt.MOUSEEVENTF_ABSOLUTE)])
en._pico_flush()
logs = []
while not en.log_q.empty(): logs.append(en.log_q.get())
check("절대좌표는 피코로 안 보냄", len(out) == 0, "%d바이트 보냄" % len(out))
check("절대좌표일 때 안내함", any("절대좌표" in l for l in logs), str(logs))

# 13-2) 가로 휠은 조용히 사라지지 않고 알려 준다
en, out = pico_engine()
en._emit([mt.mouse_input(0, 0, 120, mt.MOUSEEVENTF_HWHEEL)])
logs = []
while not en.log_q.empty(): logs.append(en.log_q.get())
check("가로 휠 빠질 때 안내함", any("가로 휠" in l for l in logs), str(logs))

# 13-3) 버튼은 모아 둔 이동과 같은 묶음에 실리지 않는다
en, out = pico_engine()
en._emit([mt.mouse_input(30, 0, 0, mt.MOUSEEVENTF_MOVE)])
en._emit([mt.mouse_input(20, 0, 0, mt.MOUSEEVENTF_MOVE)])
en._emit([mt.mouse_input(0, 0, 0, mt.MOUSEEVENTF_LEFTDOWN)])
en._pico_flush()
fr = frames_of(out)
first_press = next((k for k, f in enumerate(fr) if f[3] == 1), None)
moved_before = sum(as_signed(f[1]) for f in fr[:first_press]) if first_press is not None else 0
check("누름 전에 이동 50 이 먼저 나감",
      first_press is not None and moved_before == 50,
      "묶음=%s" % [(as_signed(f[1]), f[3]) for f in fr])
check("누름 묶음에는 이동이 없음",
      first_press is not None and as_signed(fr[first_press][1]) == 0,
      str(bytes(fr[first_press]) if first_press is not None else None))

# 13-4) 끌 때 재생 스레드를 기다리고 버튼을 놓아 준다
en, out = pico_engine()
en.pico_btn = 0x01          # 왼쪽이 눌려 있는 상태
en._play_thread = None
en.shutdown()
fr = frames_of(out)
check("끄기 전에 버튼 놓기 신호 보냄",
      bool(fr) and fr[-1][3] == 0, str([bytes(f) for f in fr]))

# 13-5) 설정의 조합키 값이 엉뚱해도 기본값으로 시작한다
for broken in ({"hotkeys": {"record": ["F6", "Ctrl"]}},
               {"hotkeys": {"record": ["F6", True]}},
               {"hotkeys": {"record": ["F6", 999]}},
               {"hotkeys": "F6"},
               {"hotkeys": {"record": "F6"}}):
    fb = mt.App.__new__(mt.App)
    fb.eng = mt.Engine()
    fb.hk_key = dict((k, V()) for k, _h, _l in mt.ACTIONS)
    fb.hk_mod = dict((k, dict((b, V()) for b in (mt.MOD_CONTROL, mt.MOD_ALT,
                                                 mt.MOD_SHIFT)))
                     for k, _h, _l in mt.ACTIONS)
    for n in ("repeat", "speed", "gap", "port_var", "v_kbd", "v_goto", "v_prec"):
        setattr(fb, n, V())
    fb.sync_opts = lambda: None
    fb.root = R()
    bp = os.path.join(d, "b.json")
    with open(bp, "w") as _f:
        _json.dump(broken, _f)
    mt.SETTINGS_FILE = bp
    fb.load_saved()
    check("망가진 설정 %s -> 기본값" % str(broken)[:34],
          fb.hk_key["record"].v == "F6", str(fb.hk_key["record"].v))

# 13-6) 안내 문구가 바꾼 단축키를 따라간다
en = mt.Engine()
en.hotkeys = {"record": ["F2", mt.MOD_CONTROL], "play": ["F3", 0],
              "stop": ["F4", 0]}
mt.send = lambda b: len(b)
en.start_record(); en.stop_record()
en.start_play(repeat=1, speed=1.0, goto_start=False, precise=False, gap=0)
en.events = [["m", 0.0, 1, 0, 0, 0, 0]]
en._play_worker(1, 1.0, False, False, 0)
logs = []
while not en.log_q.empty(): logs.append(en.log_q.get())
joined = " ".join(logs)
check("녹화 안내가 설정을 따라감", "Ctrl+F2 = 중지" in joined, joined[:110])
check("기록 없음 안내도 설정을 따라감", "Ctrl+F2 로 녹화" in joined, joined[:160])
check("재생 안내가 설정을 따라감", "정지는 F3 또는 F4" in joined, joined[:200])
check("옛 단축키가 남아 있지 않음",
      not any(x in joined for x in ("F6", "F7", "F8", "F9")), joined[:200])


print()
print("=== 11. 두 번째 전체 검토에서 나온 것들 (재발 방지) ===")

# 14-1) 스캔코드가 같고 확장키 표시만 다른 키를 따로 센다 (왼/오른 Ctrl)
sent2 = []
mt.send = lambda b: (sent2.extend(b), len(b))[1]
ek = mt.Engine()
ek.events = [["k", 0.000, 0x1D, 0, 0xA2],                         # 왼쪽 Ctrl 누름
             ["k", 0.002, 0x1D, mt.RI_KEY_E0, 0xA3],              # 오른쪽 Ctrl 누름
             ["k", 0.004, 0x1D, mt.RI_KEY_BREAK | mt.RI_KEY_E0, 0xA3]]  # 오른쪽만 뗌
ek._play_worker(1, 1.0, False, False, 0)
keys = [i for i in sent2 if i.type == mt.INPUT_KEYBOARD]
ups = [i for i in keys if i.ki.dwFlags & mt.KEYEVENTF_KEYUP]
auto = [i for i in ups if not (i.ki.dwFlags & mt.KEYEVENTF_EXTENDEDKEY)]
check("확장키 짝을 따로 셈 (왼쪽 Ctrl 이 자동 해제됨)",
      len(auto) == 1 and auto[0].ki.wScan == 0x1D,
      "뗌 %d건, 그중 비확장 %d건" % (len(ups), len(auto)))
check("오른쪽 Ctrl 을 두 번 떼지 않음",
      len([i for i in ups if i.ki.dwFlags & mt.KEYEVENTF_EXTENDEDKEY]) == 1, "")

# 14-2) 구형 경로는 가상 키 코드로 보낸다 (스캔코드 플래그는 빼고)
legacy_calls = []
mt.user32.keybd_event = lambda vk, sc, fl, extra_: legacy_calls.append((vk, sc, fl))
mt.user32.mouse_event = lambda *a: None
ek2 = mt.Engine()
ek2._emit_legacy([mt.key_input(0x1D, mt.KEYEVENTF_SCANCODE
                               | mt.KEYEVENTF_EXTENDEDKEY, 0xA3)])
check("구형 경로가 가상 키 코드를 씀",
      legacy_calls and legacy_calls[0][0] == 0xA3, str(legacy_calls))
check("구형 경로에 스캔코드 플래그를 안 넘김",
      legacy_calls and not (legacy_calls[0][2] & mt.KEYEVENTF_SCANCODE),
      hex(legacy_calls[0][2]) if legacy_calls else "")

# 14-3) 마우스 옆 버튼도 조용히 사라지지 않는다
en, out = pico_engine()
en._emit([mt.mouse_input(0, 0, 1, mt.MOUSEEVENTF_XDOWN)])
logs = []
while not en.log_q.empty(): logs.append(en.log_q.get())
check("옆 버튼 빠질 때 안내함", any("옆 버튼" in l for l in logs), str(logs))

# 14-4) 성공 여부를 모르는 방식은 성공했다고 적지 않는다
mt.user32.GetCursorPos = lambda ptr: None
ed = mt.Engine()
ed._try_method("구형 시험", lambda dx: True, shots=1, can_verify=False)
logs = []
while not ed.log_q.empty(): logs.append(ed.log_q.get())
joined = " ".join(logs)
check("확인 불가한 방식은 그렇게 적음", "확인 불가" in joined, joined[:100])
check("성공 2/2 같은 문구를 쓰지 않음", "성공 2/2" not in joined, joined[:100])

# 14-5) 녹화나 재생 중에는 기록을 갈아치울 수 없다
el = mt.Engine()
el.events = [["m", 0.1, 1, 1, 0, 0, 0]]
el.save(os.path.join(d, "keep.json"))
el2 = mt.Engine()
el2.events = [["m", 9.9, 5, 5, 0, 0, 0]]
el2.recording = True
el2.load(os.path.join(d, "keep.json"))
check("녹화 중 불러오기 거절", el2.events == [["m", 9.9, 5, 5, 0, 0, 0]],
      str(el2.events))
el2.recording = False; el2.playing = True
el2.load(os.path.join(d, "keep.json"))
check("재생 중 불러오기 거절", el2.events == [["m", 9.9, 5, 5, 0, 0, 0]],
      str(el2.events))
el2.playing = False
el2.load(os.path.join(d, "keep.json"))
check("멈춰 있으면 불러와짐", len(el2.events) == 1 and el2.events[0][1] == 0.1,
      str(el2.events))

# 14-6) 피코가 COM 포트를 하나만 만들도록 설정돼 있다
boot_src = io.open(os.path.join(ROOT, "pico", "boot.py"), encoding="utf-8").read()
check("boot.py 가 콘솔 포트를 끔", "console=False" in boot_src,
      "console=True 면 COM 포트가 두 개 생겨 어느 쪽인지 알 수 없다")


print()
print("=== 12. 세 번째 전체 검토에서 나온 것들 (재발 방지) ===")

# 12-1) 손상된 기록은 바꿔 넣기 전에 걸러진다
good = [["m", 0.1, 1, 1, 0, 0, 0]]
for broken in ([[]], ["x"], [["m", 0.1, 1]], [["k", 0.1, 1, 2]],
               [["m", 0.1, 1, 1, 0, 0, "x"]], "문자열", [["z", 0.1, 1, 1, 0, 0, 0]]):
    bp = os.path.join(d, "broken.json")
    with open(bp, "w") as _f:
        _json.dump({"version": 1, "events": broken, "start_pos": [1, 2]}, _f)
    eb = mt.Engine(); eb.events = [list(good[0])]
    eb.load(bp)
    ok_keep = eb.events == good
    try:
        eb.duration(); ok_dur = True
    except Exception:
        ok_dur = False
    check("손상 기록 거부 %s" % str(broken)[:26], ok_keep and ok_dur,
          "남은 기록=%s" % eb.events)

# 12-2) 길이 계산은 무슨 값이 들어와도 던지지 않는다
ed2 = mt.Engine()
for junk in ([[]], [["m"]], [["m", "글자"]], None, 5, [[None]]):
    ed2.events = junk
    try:
        ed2.duration(); ok = True
    except Exception:
        ok = False
    check("길이 계산이 안 죽음 %s" % str(junk)[:18], ok, "")
ed2.events = good
check("정상일 때는 제 값", abs(ed2.duration() - 0.1) < 1e-9, str(ed2.duration()))

# 12-3) 저장에는 적용된 단축키만 들어간다 (창에 찍힌 값이 아니라)
fc = mt.App.__new__(mt.App)
fc.eng = mt.Engine()
fc.eng.hotkeys = {"record": ["F6", 0], "play": ["F7", 0], "stop": ["F8", 0]}
fc.hk_key = dict((k, V()) for k, _h, _l in mt.ACTIONS)
fc.hk_mod = dict((k, dict((b, V()) for b in (mt.MOD_CONTROL, mt.MOD_ALT,
                                             mt.MOD_SHIFT)))
                 for k, _h, _l in mt.ACTIONS)
for k, _h, _l in mt.ACTIONS:
    fc.hk_key[k].set("F9")          # 세 칸 모두 같은 키로 (적용은 안 함)
    for b in fc.hk_mod[k]:
        fc.hk_mod[k][b].set(False)
for n in ("repeat", "speed", "gap", "port_var", "v_kbd", "v_goto", "v_prec"):
    setattr(fc, n, V()); getattr(fc, n).set("1")
saved_hk = fc.collect()["hotkeys"]
check("저장값은 적용된 단축키",
      saved_hk == {"record": ["F6", 0], "play": ["F7", 0], "stop": ["F8", 0]},
      str(saved_hk))
check("창에 찍힌 겹치는 값은 저장 안 됨",
      len({tuple(v) for v in saved_hk.values()}) == 3, str(saved_hk))

# 12-4) 검사 도는 중에는 녹화도 재생도 시작하지 않는다
es = mt.Engine(); es.selftest_running = True
es.start_record()
check("검사 중 녹화 거절", not es.recording, "")
es.events = [list(good[0])]
es.start_play(repeat=1, speed=1.0, goto_start=False, precise=False, gap=0)
check("검사 중 재생 거절", not es.playing, "")

# 12-5) 32비트 파이썬에서는 버퍼 읽기를 쓰지 않는다
saved_flag = mt.IS_WOW64
try:
    mt.IS_WOW64 = True
    ew = mt.Engine()
    called = {"n": 0}
    mt.user32.GetRawInputBuffer = lambda *a: called.__setitem__("n", called["n"] + 1) or 1
    got = ew._drain_buffer()
    check("WOW64 면 버퍼 읽기 건너뜀", got == 0 and called["n"] == 0,
          "반환=%s 호출=%d" % (got, called["n"]))
finally:
    mt.IS_WOW64 = saved_flag


print()
print("=== 13. 네 번째 전체 검토에서 나온 것들 (재발 방지) ===")

# 13-1) 커서 움직임 판정: 한쪽으로 보낸 뒤에 재야 잡힌다
pos = {"x": 500, "y": 500}
def fake_getpos(ptr):
    pt = ctypes.cast(ptr, ctypes.POINTER(mt.POINT)).contents
    pt.x, pt.y = pos["x"], pos["y"]
mt.user32.GetCursorPos = fake_getpos
em = mt.Engine()
def moving(step):
    pos["x"] += step      # 실제로 움직이는 입력을 흉내
    return True
res = em._try_method("움직이는 방식", moving, shots=3)
check("움직이면 움직였다고 판정", res["moved"], str(res))
check("검사 뒤 커서는 제자리", pos["x"] == 500, "x=%d" % pos["x"])
pos["x"] = 500
res2 = em._try_method("막힌 방식", lambda step: False, shots=3)
check("안 움직이면 없다고 판정", not res2["moved"], str(res2))

# 13-2) 보내기가 성공했다고 답하면 들어간 것으로 본다
em2 = mt.Engine()
rows = [{"name": "a", "ok": 6, "total": 6, "err": 0, "moved": False,
         "arrived": 0, "inj": 0, "verified": True}]
worked = [r for r in rows if r["moved"] or (r["verified"] and r["ok"] > 0)]
check("커서가 안 잡혀도 성공 횟수로 인정", len(worked) == 1, str(worked))

# 13-3) 피코 보내기가 실패해도 눌린 버튼을 놓아 준다
writes = []
class FailLink:
    handle = 1
    name = "COM9"
    def __init__(self): self.n = 0
    def write(self, dd):
        self.n += 1
        writes.append(bytes(dd))
        return self.n != 1       # 첫 번째만 실패
    def close(self): pass
ef = mt.Engine(); ef.pico = FailLink(); ef.use_pico = True
ef.pico_btn = 0x01
ef._pico_dx = 5
ef._pico_flush()
released = [w for w in writes[1:] if w and w[3] == 0]
check("실패해도 버튼 놓기 시도", bool(released), str(writes))
check("버튼 상태도 비움", ef.pico_btn == 0, str(ef.pico_btn))

# 13-4) 재생이 끝나면 use_pico 가 꺼져 있어도 버튼을 놓는다
writes2 = []
class OkLink:
    handle = 1
    name = "COM9"
    def write(self, dd): writes2.append(bytes(dd)); return True
    def close(self): pass
mt.send = lambda b: len(b)
ep = mt.Engine(); ep.pico = OkLink(); ep.use_pico = False
ep.pico_btn = 0x02          # 피코가 오른쪽 버튼을 잡고 있는 상태
ep.events = [["m", 0.0, 1, 0, 0, 0, 0]]
ep._play_worker(1, 1.0, False, False, 0)
check("재생 끝에 피코 버튼 해제",
      any(w[3] == 0 for w in writes2) and ep.pico_btn == 0, str(writes2))

# 13-5) 저장 실패를 알려 준다
es2 = mt.Engine()
es2.events = [["m", 0.1, 1, 1, 0, 0, 0]]
ok = es2.save(os.path.join(d, "없는폴더", "x.json"))
logs = []
while not es2.log_q.empty(): logs.append(es2.log_q.get())
check("저장 실패 시 False", ok is False, str(ok))
check("저장 실패를 로그에 남김", any("저장 실패" in l for l in logs), str(logs))
check("정상 저장은 True", es2.save(os.path.join(d, "ok.json")) is True, "")


print()
print("=== 14. 다섯 번째 전체 검토에서 나온 것들 (재발 방지) ===")

# 14-1) 이동량이나 키 코드에 소수가 들어오면 안 된다
check("정수는 통과", mt.clean_events([["m", 0.5, 3, -2, 0, 0, 0]]) is not None, "")
check("시각은 소수여도 됨",
      mt.clean_events([["m", 0.123456, 1, 1, 0, 0, 0]]) is not None, "")
coerced = mt.clean_events([["m", 0.5, 3.0, -2.0, 0, 0, 0]])
check("정수와 같은 소수는 정수로 바꿈",
      coerced is not None and coerced[0][2] == 3 and isinstance(coerced[0][2], int),
      str(coerced))
check("3.5 같은 값은 거부", mt.clean_events([["m", 0.5, 3.5, 0, 0, 0, 0]]) is None, "")
check("키 코드 소수도 거부",
      mt.clean_events([["k", 0.5, 30.5, 0, 65]]) is None, "")
# 실제로 재생까지 해본다 (예전에는 여기서 터졌다)
ef2 = mt.Engine()
sent3 = []
mt.send = lambda b: (sent3.extend(b), len(b))[1]
fp = os.path.join(d, "float.json")
with open(fp, "w") as _f:
    _json.dump({"version": 1, "events": [["m", 0.0, 3.0, -2.0, 0, 0, 0]],
                "start_pos": [1, 2]}, _f)
ef2.load(fp)
ef2._play_worker(1, 1.0, False, False, 0)
logs = []
while not ef2.log_q.empty(): logs.append(ef2.log_q.get())
check("소수로 저장된 기록도 재생됨",
      not any("재생 오류" in l for l in logs) and len(sent3) >= 1,
      " ".join(logs)[:90])

# 14-2) 조합키가 붙은 단축키를 조합 상태까지 보고 거른다
eh = mt.Engine()
eh.hotkey_chords = [(0x75, mt.MOD_CONTROL)]     # Ctrl+F6
eh.hotkey_vks = {0x75}
check("단축키 본체 키는 기록에서 뺌", eh._is_hotkey_key(0x75, 0), "")
check("다른 키는 그대로 기록", not eh._is_hotkey_key(0x76, 0), "")
check("조합키 자체는 여기서 안 거름",
      not eh._is_hotkey_key(0xA2, mt.MOD_CONTROL), "")
# 조합키가 붙은 단축키도 본체 키가 목록에 들어가야 한다. 이게 빠지면
# 그 키가 기록에 남고, 재생할 때 단축키를 다시 눌러 재생이 멈춘다.
eh3 = mt.Engine(); eh3.hwnd = 1
mt.user32.RegisterHotKey = lambda h, i, m, v: 1
mt.user32.UnregisterHotKey = lambda h, i: 1
eh3.hotkeys = {"record": ["F6", mt.MOD_CONTROL], "play": ["F7", 0],
               "stop": ["F8", mt.MOD_ALT | mt.MOD_SHIFT]}
eh3._register_hotkeys()
check("조합키 붙은 단축키도 본체 키를 등록",
      eh3.hotkey_vks == {0x75, 0x76, 0x77}, str(sorted(map(hex, eh3.hotkey_vks))))

# 짝이 안 맞는 조합키는 녹화를 끝낼 때 걷어낸다.
# "기록 끝자락" 은 시각으로 판단하므로 검사 데이터에도 시각을 분명히 둔다.
def CTRL_DOWN(t): return ["k", t, 29, 0, 0xA2]
def CTRL_UP(t): return ["k", t, 29, mt.RI_KEY_BREAK, 0xA2]
def MOUSE(t): return ["m", t, 1, 1, 0, 0, 0]
def CLICK(t): return ["m", t, 0, 0, 0x0001, 0, 0]
END = 10.0                      # 기록의 끝 시각
TAIL = END - 0.1                # 끝자락 (단축키 흔적으로 볼 구간)
MID = 1.0                       # 가운데 (일부러 누른 것)

def balanced(events, chords=((0x75, mt.MOD_CONTROL),)):
    eb = mt.Engine()
    eb.hotkey_chords = list(chords)
    return eb.balance_hotkey_mods([list(x) for x in events])

out = balanced([MOUSE(MID), CTRL_UP(END)])
check("누른 적 없는 뗌은 지움", out == [MOUSE(MID)], str(out))
out = balanced([MOUSE(MID), CTRL_DOWN(TAIL), MOUSE(END)])
check("끝자락에 남은 누름은 지움 (뒤에 마우스가 더 와도)",
      out == [MOUSE(MID), MOUSE(END)], str(out))
out = balanced([CTRL_DOWN(0.1), MOUSE(END)])
check("가운데서 눌린 채 이어지면 살림 (일부러 누른 것)",
      out == [CTRL_DOWN(0.1), MOUSE(END)], str(out))
out = balanced([CTRL_DOWN(0.1), MOUSE(MID), CTRL_UP(END)])
check("짝이 맞으면 그대로 둠", len(out) == 3, str(out))

# 마우스가 초당 수백 개씩 끼어들어도 짝을 맞춰야 한다
flood = ([CTRL_DOWN(0.1)] + [MOUSE(0.5)] * 500 + [CTRL_UP(0.9)]
         + [MOUSE(5.0)] * 500 + [CTRL_DOWN(TAIL)] + [MOUSE(END)])
out = balanced(flood)
keys = [e for e in out if e[0] == "k"]
check("마우스가 몰려와도 짝을 맞춤",
      len(out) == len(flood) - 1 and len(keys) == 2
      and not (keys[0][3] & mt.RI_KEY_BREAK)
      and bool(keys[1][3] & mt.RI_KEY_BREAK),
      "%d -> %d, 남은 키 %s" % (len(flood), len(out), keys))
check("마우스 기록은 하나도 안 지움",
      len([e for e in out if e[0] == "m"]) == 1001, "")

# 키를 길게 누르면 같은 누름이 여러 번 들어온다
out = balanced([MOUSE(MID), CTRL_DOWN(TAIL), CTRL_DOWN(TAIL), CTRL_DOWN(END)])
check("끝자락에 길게 누른 것도 전부 지움", out == [MOUSE(MID)], str(out))
out = balanced([CTRL_DOWN(0.1), CTRL_DOWN(0.2), MOUSE(MID), CTRL_UP(END)])
check("길게 누르고 떼면 그대로 둠", len(out) == 4, str(out))

# 일부러 누르고 있는 조합키는 살려야 한다 (Ctrl+클릭)
out = balanced([CTRL_UP(0.05), CTRL_DOWN(0.1), CLICK(MID), MOUSE(END)])
check("Ctrl+클릭의 Ctrl 은 살림",
      out == [CTRL_DOWN(0.1), CLICK(MID), MOUSE(END)], str(out))
out = balanced([CTRL_DOWN(0.1), CLICK(MID), CTRL_DOWN(TAIL), MOUSE(END)])
check("가운데 누름은 살리고 끝자락만 지움",
      out == [CTRL_DOWN(0.1), CLICK(MID), MOUSE(END)], str(out))
out = balanced([CTRL_UP(0.05), CLICK(MID), CTRL_UP(END)])
check("누른 적 없는 뗌은 위치와 무관하게 다 지움",
      out == [CLICK(MID)], str(out))
out = balanced([CTRL_DOWN(TAIL), MOUSE(END)], chords=((0x75, 0),))
check("조합키 안 쓰는 단축키면 손대지 않음", len(out) == 2, str(out))

es3 = mt.Engine()
es3.hotkey_chords = [(0x75, mt.MOD_CONTROL)]
es3.recording = True
es3.events = [MOUSE(MID), CTRL_DOWN(END)]
es3.stop_record()
check("녹화를 끝낼 때 자동으로 정리", es3.events == [MOUSE(MID)],
      str(es3.events))

# 저장은 되는데 못 불러오는 기록이 생기지 않아야 한다
check("녹화 상한이 불러오기 상한과 같음",
      mt.clean_events([["m", mt.MAX_SECONDS, 1, 1, 0, 0, 0]]) is not None
      and mt.clean_events([["m", mt.MAX_SECONDS + 1, 1, 1, 0, 0, 0]]) is None,
      "상한 %s초" % mt.MAX_SECONDS)

# --- 값 범위와 손상된 값 (앞선 검토들에서 나온 것들) ---
check("아주 큰 시각도 예외 없이 거부",
      mt.clean_events([["m", 10 ** 400, 1, 1, 0, 0, 0]]) is None, "")
check("시각이 음수면 거부",
      mt.clean_events([["m", -1.0, 1, 1, 0, 0, 0]]) is None, "")
check("시각이 하루를 넘으면 거부",
      mt.clean_events([["m", 1e18, 1, 1, 0, 0, 0]]) is None, "")
check("하루 안이면 통과",
      mt.clean_events([["m", 86399.0, 1, 1, 0, 0, 0]]) is not None, "")
check("장치 플래그가 NaN 이어도 예외 없이 거부",
      mt.clean_events([["m", 0.1, 1, 1, 0, 0, float("nan")]]) is None, "")
check("이동량이 범위를 넘으면 거부",
      mt.clean_events([["m", 0.1, 2 ** 40, 1, 0, 0, 0]]) is None, "")
check("버튼 플래그가 범위를 넘으면 거부",
      mt.clean_events([["m", 0.1, 1, 1, 0x1FFFF, 0, 0]]) is None, "")
check("키 코드가 범위를 넘으면 거부",
      mt.clean_events([["k", 0.1, 70000, 0, 65]]) is None, "")
check("범위 안이면 통과",
      mt.clean_events([["m", 0.1, -32768, 32767, 0xFFFF, -120, 0]])
      is not None, "")
check("32767 은 통과",
      mt.clean_events([["m", 0.1, 32767, -32768, 0, 0, 0]]) is not None, "")
check("32768 은 거부",
      mt.clean_events([["m", 0.1, 32768, 0, 0, 0, 0]]) is None, "")
# 태블릿이나 원격 데스크톱 기록은 이동량 자리에 화면 절대좌표가 들어온다
check("절대좌표 기록은 65535 까지 통과",
      mt.clean_events([["m", 0.0, 40000, 50000, 0, 0,
                        mt.MOUSE_MOVE_ABSOLUTE]]) is not None, "")
check("절대좌표는 모니터 배치상 음수도 허용",
      mt.clean_events([["m", 0.0, -5000, 70000, 0, 0,
                        mt.MOUSE_MOVE_ABSOLUTE]]) is not None, "")
check("절대좌표 아닌데 40000 이면 거부",
      mt.clean_events([["m", 0.0, 40000, 0, 0, 0, 0]]) is None, "")

# --- 시작 좌표 ---
check("시작 좌표 NaN 거부",
      mt.clean_start_pos([float("nan"), 0]) is None, "")
check("시작 좌표 무한대 거부",
      mt.clean_start_pos([float("inf"), 0]) is None, "")
check("시작 좌표 너무 큰 값 거부",
      mt.clean_start_pos([1e30, 0]) is None, "")
check("시작 좌표 정상값 통과",
      mt.clean_start_pos([640, 480.0]) == (640, 480), "")
eb2 = mt.Engine(); eb2.events = [["m", 0.1, 1, 1, 0, 0, 0]]
badpos = os.path.join(d, "badpos.json")
with io.open(badpos, "w", encoding="utf-8") as _f:
    _f.write('{"version":1,"events":[["m",0.0,5,5,0,0,0]],'
             '"start_pos":[NaN,0]}')
eb2.load(badpos)
logs = []
while not eb2.log_q.empty(): logs.append(eb2.log_q.get())
check("좌표만 깨지면 기록은 살리고 좌표는 버림",
      eb2.events == [["m", 0.0, 5, 5, 0, 0, 0]] and eb2.start_pos is None,
      "%s / %s" % (eb2.events, eb2.start_pos))
check("좌표를 버렸다고 알려줌", any("시작 위치" in l for l in logs), str(logs))

# --- 피코: 버튼 놓는 신호가 실패해도 되돌릴 길이 남아야 한다 ---
rel_writes = []
class ReleaseFailLink:
    handle = 1
    name = "COM9"
    def __init__(self): self.n = 0
    def write(self, dd):
        self.n += 1
        rel_writes.append(bytes(dd))
        return self.n == 1          # 첫 번째(누름)만 성공
    def close(self): pass
erf = mt.Engine(); erf.pico = ReleaseFailLink(); erf.use_pico = True
erf.pico_btn = 0x01
erf._pico_flush()                   # 누름 전달 (성공)
erf.pico_btn = 0
erf.use_pico = True
erf._pico_flush()                   # 놓기 전달 (실패)
check("놓기가 실패하면 한 번 더 시도",
      len(rel_writes) >= 3 and rel_writes[-1][3] == 0, str(rel_writes))
check("놓기까지 실패하면 되돌릴 표시를 남김",
      erf._pico_sent_btn != 0, str(erf._pico_sent_btn))

# 버튼을 누른 채 가만히 있으면 보낼 것이 없어서 한 묶음도 안 나간다.
# 그 사이 보드에서 오류가 나 버튼이 풀리면 되돌릴 방법이 없으므로,
# 누르고 있는 동안에는 같은 상태를 가끔 다시 보내 줘야 한다.
class CountLink:
    def __init__(s): s.writes = []
    def write(s, dd): s.writes.append(bytes(dd)); return True
    def close(s): pass

eh = mt.Engine(); eh.pico = CountLink(); eh.use_pico = True
eh.pico_btn = 0x01
eh._pico_flush()                       # 누름 전달
_after_press = len(eh.pico.writes)
eh._pico_flush()                       # 바로 또 불러도 다시 안 보냄
check("누른 직후에는 같은 상태를 다시 안 보냄",
      len(eh.pico.writes) == _after_press, str(eh.pico.writes))
eh._pico_hold_t -= mt.PICO_HOLD_SEC + 0.01   # 유지 간격이 지난 것으로
eh._pico_flush()
check("누른 채 가만히 있으면 상태를 다시 보냄",
      len(eh.pico.writes) == _after_press + 1
      and eh.pico.writes[-1][3] == 0x01, str(eh.pico.writes))

# 버튼을 안 누르고 가만히 있으면 보낼 것이 없다. 괜한 묶음을 보내면
# 안 된다 (USB 간격을 공짜로 잡아먹는다).
eh.pico_btn = 0
eh._pico_sent_btn = 0
eh._pico_hold_t -= mt.PICO_HOLD_SEC + 0.01
_before = len(eh.pico.writes)
eh._pico_flush()
check("안 누르고 있으면 괜한 묶음을 안 보냄",
      len(eh.pico.writes) == _before, str(eh.pico.writes[-1:]))

check("NaN 이 들어와도 거부",
      mt.clean_events([["m", float("nan"), 1, 1, 0, 0, 0]]) is None, "")
check("무한대도 거부",
      mt.clean_events([["m", 0.1, float("inf"), 1, 0, 0, 0]]) is None, "")

# 14-3) 음수 반복은 무한이 아니라 한 번
sent4 = []
mt.send = lambda b: (sent4.extend(b), len(b))[1]
en2 = mt.Engine()
en2.events = [["m", 0.0, 1, 0, 0, 0, 0]]
en2._play_worker(-1, 1.0, False, False, 0)
check("반복 -1 은 한 번만", len(sent4) == 1, "%d번 보냄" % len(sent4))
sent4.clear()
en2._play_worker(3, 1.0, False, False, 0)
check("반복 3 은 세 번", len(sent4) == 3, "%d번 보냄" % len(sent4))

# 14-4) 저장된 단축키가 겹치면 기본값으로 되돌린다
fd = mt.App.__new__(mt.App)
fd.eng = mt.Engine()
fd.hk_key = dict((k, V()) for k, _h, _l in mt.ACTIONS)
fd.hk_mod = dict((k, dict((b, V()) for b in (mt.MOD_CONTROL, mt.MOD_ALT,
                                             mt.MOD_SHIFT)))
                 for k, _h, _l in mt.ACTIONS)
for n in ("repeat", "speed", "gap", "port_var", "v_kbd", "v_goto", "v_prec"):
    setattr(fd, n, V())
fd.sync_opts = lambda: None
fd.root = R()
dup = os.path.join(d, "dup.json")
with open(dup, "w") as _f:
    _json.dump({"hotkeys": {"record": ["F9", 0], "play": ["F9", 0],
                        "stop": ["F8", 0]}}, _f)
mt.SETTINGS_FILE = dup
fd.load_saved()
combos = [tuple(v) for v in fd.eng.hotkeys.values()]
check("겹치면 기본값으로", len(set(combos)) == 3 and combos[0] == ("F6", 0),
      str(fd.eng.hotkeys))
logs = []
while not fd.eng.log_q.empty(): logs.append(fd.eng.log_q.get())
check("겹쳤다고 알려줌", any("겹쳐서" in l for l in logs), str(logs))


print()
print("=== 14-1. 포트를 못 열었을 때 이유 보여주기 ===")
# 번호만 보여 주면 무엇을 해야 할지 알 수 없다. 자주 나오는 이유는
# 할 일까지 같이 적어 준다.
for _code, _want, _label in (
        (5, "다른 프로그램", "이미 쓰는 중이면 그렇다고 알려줌"),
        (2, "뺐다 꽂", "포트가 없으면 다시 꽂으라고 알려줌"),
        (1234, "오류 1234", "모르는 번호는 번호라도 보여줌")):
    mt.ctypes.set_last_error(_code)
    _why = mt.open_fail_why()
    check(_label, _want in _why, _why)
check("아는 이유에도 번호를 같이 적음",
      (mt.ctypes.set_last_error(5), "5" in mt.open_fail_why())[1], "")

_fl = mt.PicoLink()
mt._open_com_real = mt._open_com
mt._open_com = lambda name, access=0: (mt.ctypes.set_last_error(5), None)[1]
check("열기에 실패하면 이유를 적어 둠",
      not _fl.open("COM9") and "다른 프로그램" in _fl.last_error,
      _fl.last_error)
mt._open_com = mt._open_com_real

_src_fail = io.open(TARGET, encoding="utf-8").read()
check("창도 그 이유를 같이 보여줌",
      _src_fail.count('포트를 열지 못했습니다') == 2
      and _src_fail.count('getattr(self.eng.pico, "last_error", "")') >= 2,
      "")

print()
print("=== 14-2. 피코가 보낸 말 알아듣기 ===")

class HushLink:
    """인사를 멈추라는 묶음이 갔는지 세는 가짜 피코."""
    def __init__(s): s.writes = []; s.handle = 1; s.name = "COM9"
    def write(s, dd): s.writes.append(bytes(dd)); return True
    def read(s, size=512): return b""
    def close(s): pass


def new_app():
    app = mt.App.__new__(mt.App)
    app.eng = mt.Engine()
    app.eng.pico = HushLink()
    app._pico_greeted = False
    app._pico_wait_t = time.perf_counter()
    app._pico_rx = b""
    return app


def say_lines(lines):
    """창이 피코의 말 몇 줄을 받았을 때 로그에 뭐가 남는지 본다."""
    app = new_app()
    for one in lines:
        app._say_pico_line(one)
    say_lines.app = app
    out = []
    while not app.eng.log_q.empty():
        out.append(app.eng.log_q.get())
    return out

for _lines, _want, _label in (
        (["READY 16"], "큰 걸음", "큰 걸음 펌웨어를 알아봄"),
        (["READY 8"], "다시 복사", "옛 펌웨어면 다시 복사하라고 알려줌"),
        (["MOUSE FAIL OSError('왜인지')"], "왜인지",
         "마우스를 못 만든 원인을 그대로 보여줌"),
        (["ERR something"], "ERR something", "모르는 말은 그대로 보여줌")):
    _log = say_lines(_lines)
    check(_label, any(_want in m for m in _log), str(_log)[-110:])

# 펌웨어는 PC 가 말을 걸 때까지 1초마다 인사를 되풀이한다.
# 그대로 다 적으면 로그가 도배된다 (실제로 그랬다).
_flood = say_lines(["READY 16"] * 30)
check("같은 인사를 되풀이해도 한 줄만 적음", len(_flood) == 1, str(_flood))
# 인사가 아닌 말은 되풀이해도 다 적어야 한다 (오류를 놓치면 안 된다)
_errs = say_lines(["ERR 1", "ERR 2", "ERR 3"])
check("오류는 되풀이해도 다 적음", len(_errs) == 3, str(_errs))

# 읽는 곳은 하나뿐이어야 한다. 둘이면 서로 먼저 가져가려고 싸워서
# 해석된 문장 대신 날것이 찍힌다 (실제로 그랬다).
_src_app = io.open(TARGET, encoding="utf-8").read()
check("피코를 읽는 곳이 하나뿐", _src_app.count("pico.read()") + _src_app.count("link.read()") == 1,
      "읽는 곳 %d군데" % (_src_app.count("pico.read()") + _src_app.count("link.read()")))

# 인사를 받은 뒤에야 "그만해도 된다" 고 알려야 한다. 연결하자마자
# 멈추라고 하면 인사할 틈이 없어져서 어떤 펌웨어인지 영영 모른다.
say_lines(["READY 16"])
check("인사를 받은 뒤에 멈추라고 보냄",
      say_lines.app.eng.pico.writes == [mt.pico_frames(0, 0, 0, 0)],
      str(say_lines.app.eng.pico.writes))
check("연결할 때 어떤 펌웨어인지 물어봄",
      "self.eng.pico.write(PICO_ASK)" in _src_app, "")

_quiet = new_app()
_quiet._pico_wait_t = time.perf_counter()
_quiet.poll_pico()
_q1 = []
while not _quiet.eng.log_q.empty():
    _q1.append(_quiet.eng.log_q.get())
check("인사를 기다리는 동안은 조용히 둠", _q1 == [] and not _quiet._pico_greeted,
      str(_q1))

# 옛 펌웨어는 켜질 때 한 번만 인사해서 PC 가 열 즈음엔 이미 지나갔다.
# 조용한 것 자체가 단서이므로, 한참 기다려도 안 오면 알려 줘야 한다.
_quiet._pico_wait_t -= 3.5
_quiet.poll_pico()
_q2 = []
while not _quiet.eng.log_q.empty():
    _q2.append(_quiet.eng.log_q.get())
check("한참 조용하면 옛 방식일 수 있다고 알려줌",
      len(_q2) == 1 and "옛 방식" in _q2[0], str(_q2))
_quiet.poll_pico()
_q3 = []
while not _quiet.eng.log_q.empty():
    _q3.append(_quiet.eng.log_q.get())
check("그 안내도 한 번만 적음", _q3 == [], str(_q3))

print("=== 15. 실행 파일이 지금 코드를 품고 있는지 ===")
import base64 as _b64, hashlib as _hashlib
bat_path = os.path.join(ROOT, "MouseTracer.bat")
try:
    _raw = io.open(bat_path, encoding="ascii", newline="").read().split("\r\n")
    _i = _raw.index("#####PAYLOAD#####")
    _payload = _b64.b64decode("".join(x for x in _raw[_i + 1:] if x))
    _source = io.open(TARGET, "rb").read()
    same = _payload == _source
    detail = "" if same else ("실행 파일 안 %d바이트(%s) vs 원본 %d바이트(%s). "
                              "페이로드를 다시 만들어야 한다."
                              % (len(_payload),
                                 _hashlib.md5(_payload).hexdigest()[:8],
                                 len(_source),
                                 _hashlib.md5(_source).hexdigest()[:8]))
except Exception as _ex:
    same, detail = False, repr(_ex)
check("MouseTracer.bat 안의 프로그램이 원본과 같음", same, detail)


print()
print("=== 15-2. boot.py 의 HID 설명서가 올바른지 ===")
# 설명서가 조금만 틀어져도 Windows 가 장치를 거절해서 마우스가 아예
# 안 생긴다. 그래서 설명서를 직접 훑어 보고를 몇 바이트로 만드는지 센다.
import re as _re
_boot = io.open(os.path.join(ROOT, "pico", "boot.py"), encoding="utf-8").read()
try:
    _body = _boot.split("FAST_MOUSE_DESCRIPTOR = bytes((", 1)[1].split("))", 1)[0]
    _desc = [int(x, 16) for x in _re.findall(r"0x([0-9A-Fa-f]{2})", _body)]
    _i = _depth = _bits = 0
    _rid = _size = _count = None
    while _i < len(_desc):
        _b = _desc[_i]; _i += 1
        _typ, _tag, _n = (_b >> 2) & 3, _b >> 4, _b & 3
        _n = 4 if _n == 3 else _n
        _val = 0
        for _k in range(_n):
            _val |= _desc[_i + _k] << (8 * _k)
        _i += _n
        if _typ == 1 and _tag == 0x8: _rid = _val
        if _typ == 1 and _tag == 0x7: _size = _val
        if _typ == 1 and _tag == 0x9: _count = _val
        if _typ == 0 and _tag == 0xA: _depth += 1
        if _typ == 0 and _tag == 0xC: _depth -= 1
        if _typ == 0 and _tag == 0x8: _bits += _size * _count
    _ok_len = (_i == len(_desc))
except Exception as _ex:
    # _i 까지 반드시 되돌려 둔다. 안 그러면 아래 설명에 앞 검사에서
    # 쓰던 값이 섞여 나오거나, 아예 이름이 없어 검사가 중간에 멈춘다.
    _desc, _ok_len, _depth, _bits, _rid, _i = [], False, -1, -1, None, -1
    print("   (설명서를 읽지 못했습니다: %r)" % (_ex,))

check("설명서가 중간에 끊기지 않음", _ok_len, "%d바이트 중 %d" % (len(_desc), _i))
check("묶음 열고 닫기가 맞음", _depth == 0, "깊이 %d" % _depth)
check("보고가 바이트 단위로 딱 맞음", _bits > 0 and _bits % 8 == 0,
      "%d비트" % _bits)
check("보고 크기가 6바이트", _bits // 8 == 6, "%d바이트" % (_bits // 8))
check("보고 번호가 붙어 있음 (기본 마우스와 같이 쓰려면 필요)",
      _rid not in (None, 0), str(_rid))
# 설명서가 16비트 좌표를 쓰는지 (이게 빠지면 클릭이 다시 길어진다)
check("좌표가 16비트", bytes(_desc).find(bytes((0x75, 0x10))) >= 0, "")
check("좌표 범위가 -32767~32767",
      bytes(_desc).find(bytes((0x16, 0x01, 0x80))) >= 0
      and bytes(_desc).find(bytes((0x26, 0xFF, 0x7F))) >= 0, "")
check("기본 마우스를 같이 남겨 둠 (옛 code.py 도 동작하게)",
      "usb_hid.Device.MOUSE, fast_mouse" in _boot, "")
check("설명서를 거절당하면 기본 마우스로 되돌림",
      "usb_hid.enable((usb_hid.Device.MOUSE,))" in _boot, "")

print()
print("=== 16. 펌웨어가 CircuitPython 에서 못 쓰는 문법을 안 쓰는지 ===")
# 이 검사가 필요한 이유: 하네스는 일반 파이썬으로 돌아서
# CircuitPython 에만 없는 기능은 통과해 버린다. 실제로 bytearray 의
# del 을 쓰다가 보드에서만 터진 적이 있다.
import re as _re
for _name in ("code.py", "boot.py"):
    _src = io.open(os.path.join(ROOT, "pico", _name), encoding="utf-8").read()
    _dels = _re.findall(r"^\s*del\s+\w+\[", _src, _re.M)
    check("%s 에 del 로 항목 지우기 없음" % _name, not _dels, str(_dels))
    check("%s 에 f-문자열 없음" % _name,
          not _re.search(r"""f["']""", _src), "")

print()
print("=" * 52)
print("검사 항목 %d개" % ran[0])
if fails:
    print("실패한 항목 %d개:" % len(fails))
    for f_ in fails: print("  -", f_)
    sys.exit(1)
print("모든 항목 통과")
