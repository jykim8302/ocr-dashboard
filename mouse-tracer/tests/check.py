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
def check(name, ok, detail=""):
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

class _Stop(Exception):
    """프레임을 다 먹인 뒤 펌웨어의 무한 루프를 빠져나오기 위한 신호."""


def run_firmware(frame_bytes):
    """pico/code.py 를 그대로 불러들여 프레임을 먹이고 무엇을 냈는지 본다."""
    moves, buttons = [], []

    class FakeMouse:
        LEFT_BUTTON, RIGHT_BUTTON, MIDDLE_BUTTON = 1, 2, 4
        def __init__(self, devices): pass
        def move(self, x=0, y=0, wheel=0): moves.append((x, y, wheel))
        # 버튼 사건에 그때까지 나간 이동 횟수를 같이 적어 순서를 확인한다
        def press(self, code): buttons.append(("press", code, len(moves)))
        def release(self, code): buttons.append(("release", code, len(moves)))

    class FakePort:
        def __init__(self, data): self.data = bytearray(data)
        @property
        def in_waiting(self):
            if not self.data:
                raise _Stop()
            return len(self.data)
        def read(self, n):
            out = bytes(self.data[:n]); del self.data[:n]; return out

    usb_cdc = types.ModuleType("usb_cdc"); usb_cdc.data = FakePort(frame_bytes)
    usb_hid = types.ModuleType("usb_hid"); usb_hid.devices = []
    pkg = types.ModuleType("adafruit_hid")
    mouse_mod = types.ModuleType("adafruit_hid.mouse")
    mouse_mod.Mouse = FakeMouse
    pkg.mouse = mouse_mod
    names = ("usb_cdc", "usb_hid", "adafruit_hid", "adafruit_hid.mouse")
    saved = dict((n, sys.modules.get(n)) for n in names)
    sys.modules.update({"usb_cdc": usb_cdc, "usb_hid": usb_hid,
                        "adafruit_hid": pkg, "adafruit_hid.mouse": mouse_mod})
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

print()
print("=== 6. 단축키 ===")
e4 = mt.Engine(); e4.hwnd = 999
reg = []
mt.user32.RegisterHotKey = lambda h, i, m, v: (reg.append((i, m, v)), 0 if v == 0x77 else 1)[1]
mt.user32.UnregisterHotKey = lambda h, i: 1
e4.hotkeys = {"record": ["F9", mt.MOD_CONTROL], "play": ["숫자패드 1", 0], "stop": ["F8", 0]}
e4._register_hotkeys()
check("모든 키 코드 유효", all(n in mt.KEY_CODES for n in mt.KEY_NAMES), "")
check("성공한 것만 녹화에서 제외", e4.hotkey_vks == {0x78, 0x61}, str(sorted(map(hex, e4.hotkey_vks))))
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
open(os.path.join(d, "깨짐.json"), "w").write("{이건 json 이 아님")
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
_json.dump({"hotkeys": ["F6", "F7"], "repeat": 3}, open(bad, "w"))
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
    _json.dump(broken, open(bp, "w"))
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
    _json.dump({"version": 1, "events": broken, "start_pos": [1, 2]},
               open(bp, "w"))
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
    except Exception as ex:
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
print("=" * 52)
if fails:
    print("실패한 항목 %d개:" % len(fails))
    for f_ in fails: print("  -", f_)
    sys.exit(1)
print("모든 항목 통과")
