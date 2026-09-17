# -*- coding: utf-8 -*-
"""mouse_tracer 점검 스크립트.

Windows 전용 프로그램이라 리눅스에서는 실행할 수 없다. 그래서 Win32 함수를
가짜로 바꿔치우고 모듈을 불러들여, 실행 없이 확인할 수 있는 것을 전부 본다.

    python3 tests/check.py

한 항목이라도 실패하면 종료 코드 1 을 돌려준다.
"""
import ctypes, sys, types, os, importlib.util, tempfile, random, time

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

print("=== 4. Win32 구조체 크기 (64비트 Windows 기준) ===")
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
print("=== 5. 원시 입력 분류 (진짜 마우스 vs 만들어낸 입력) ===")
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
print("=== 6. 재생 로직 (버튼/휠/키보드/자동해제) ===")
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
print("=== 7. 피코 경로 (총 이동량 보존 / 클릭 보존) ===")
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
print("=== 8. 피코 펌웨어 누적 로직 ===")
def firmware(frames_in):
    px = py = 0; out = []
    def flush():
        nonlocal px, py
        while px or py:
            cx = 127 if px > 127 else (-127 if px < -127 else px)
            cy = 127 if py > 127 else (-127 if py < -127 else py)
            px -= cx; py -= cy; out.append((cx, cy))
    for dx, dy in frames_in:
        px += dx; py += dy
    flush(); return out
random.seed(5)
fin = [(random.randint(-127,127), random.randint(-127,127)) for _ in range(800)]
want = (sum(f[0] for f in fin), sum(f[1] for f in fin))
out = firmware(fin)
check("펌웨어도 총량 보존", (sum(o[0] for o in out), sum(o[1] for o in out)) == want,
      "%s -> %s" % (want, (sum(o[0] for o in out), sum(o[1] for o in out))))

print()
print("=== 9. 단축키 ===")
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
print("=== 10. 설정 저장 / 불러오기 ===")
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
print("=== 11. 기록 저장 / 불러오기 ===")
e5 = mt.Engine()
e5.events = [["m", 0.1, 3, -2, 1, 0, 0], ["k", 0.2, 30, 0, 65]]
e5.start_pos = (640, 480)
f = os.path.join(d, "rec.json"); e5.save(f)
e6 = mt.Engine(); e6.load(f)
check("기록 왕복 일치", e6.events == e5.events and e6.start_pos == (640, 480), "")
check("길이 계산", abs(e6.duration() - 0.2) < 1e-9, str(e6.duration()))


print()
print("=== 12. 이번에 고친 버그들 (재발 방지) ===")

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
fa = type("FakeApp", (), {})()
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
print("=" * 52)
if fails:
    print("실패한 항목 %d개:" % len(fails))
    for f_ in fails: print("  -", f_)
    sys.exit(1)
print("모든 항목 통과")
