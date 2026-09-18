# -*- coding: utf-8 -*-
"""
마우스 움직임 그대로 따라하기 (Raw Input 기반) - Windows 전용

- 녹화: Win32 Raw Input(WM_INPUT)으로 마우스의 '원시 이동량(dx, dy)'과
        버튼/휠/키보드 입력을 폴링 주기 그대로 타임스탬프와 함께 기록합니다.
- 재생: SendInput의 '상대 이동(MOUSEEVENTF_MOVE)'으로 기록된 시간 간격에 맞춰
        한 칸씩 실제로 움직입니다. 좌표로 순간이동(SetCursorPos)하지 않습니다.

추가 설치 필요 없음: 파이썬 표준 라이브러리만 사용합니다.
"""

import ctypes
import datetime
import json
import os
import queue
import sys
import threading
import time

if os.name != "nt":
    print("이 프로그램은 Windows 전용입니다.")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "마우스 움직임 따라하기"
SIGNATURE = 0x5A6B7C8D  # 우리가 만든 입력을 다시 녹화하지 않기 위한 표식

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm", use_last_error=True)

# 고해상도 디스플레이에서 좌표가 어긋나지 않게
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

if ctypes.sizeof(ctypes.c_void_p) == 8:
    ULONG_PTR = ctypes.c_ulonglong
else:
    ULONG_PTR = ctypes.c_ulong

# Win32 고정폭 타입 (플랫폼에 상관없이 Windows 레이아웃을 그대로 맞춘다)
DWORD = ctypes.c_uint32
ULONG = ctypes.c_uint32
LONG = ctypes.c_int32
USHORT = ctypes.c_uint16
WORD = ctypes.c_uint16
UINT = ctypes.c_uint32
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p
HWND = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p
HMODULE = ctypes.c_void_p
HICON = ctypes.c_void_p
HBRUSH = ctypes.c_void_p
HMENU = ctypes.c_void_p
ATOM = ctypes.c_uint16
WPARAM = ULONG_PTR
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t
LPCWSTR = ctypes.c_wchar_p

# ---------------------------------------------------------------- 상수
WM_INPUT = 0x00FF
WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_APP_STOP = 0x8001
WM_APP_REHOTKEY = 0x8002

RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1

MOUSE_MOVE_RELATIVE = 0x00
MOUSE_MOVE_ABSOLUTE = 0x01
MOUSE_VIRTUAL_DESKTOP = 0x02

RI_MOUSE_WHEEL = 0x0400
RI_MOUSE_HWHEEL = 0x0800

RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000B
RAW_ALIGN = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4

RI_KEY_BREAK = 0x01
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100

# 피코(USB 장치)로 보낼 때 쓰는 값
PICO_SYNC = 0xAB
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SPI_GETMOUSE = 0x0003
SPI_SETMOUSE = 0x0004
SPI_GETMOUSESPEED = 0x0070
SPI_SETMOUSESPEED = 0x0071
SPIF_SENDCHANGE = 0x02

HOTKEY_RECORD, HOTKEY_PLAY, HOTKEY_STOP = 1, 2, 3
ACTIONS = (("record", HOTKEY_RECORD, "녹화"),
           ("play", HOTKEY_PLAY, "재생"),
           ("stop", HOTKEY_STOP, "정지"))

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x01, 0x02, 0x04, 0x4000

# 단축키로 고를 수 있는 키 목록 (이름 -> 가상 키 코드)
KEY_CODES = {}
for _i in range(1, 13):
    KEY_CODES["F{}".format(_i)] = 0x6F + _i          # F1 = 0x70
for _i in range(10):
    KEY_CODES["숫자패드 {}".format(_i)] = 0x60 + _i   # NumPad0 = 0x60
KEY_CODES.update({
    "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
    "PageUp": 0x21, "PageDown": 0x22, "ScrollLock": 0x91, "Pause": 0x13,
    "숫자패드 *": 0x6A, "숫자패드 +": 0x6B, "숫자패드 -": 0x6D,
    "숫자패드 /": 0x6F, "물결표 `": 0xC0,
})
KEY_NAMES = sorted(KEY_CODES, key=lambda k: (KEY_CODES[k], k))

DEFAULT_HOTKEYS = {"record": ["F6", 0], "play": ["F7", 0], "stop": ["F8", 0]}


SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "mouse_tracer_settings.json")


def load_settings():
    """지난번에 쓰던 설정을 읽어 온다. 없거나 깨졌으면 빈 값."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    """지금 설정을 파일에 적어 둔다."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def hotkey_text(entry):
    """['F6', 2] 같은 값을 'Ctrl+F6' 처럼 보여 줄 글자로 바꾼다."""
    name, mods = entry[0], int(entry[1])
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    parts.append(name)
    return "+".join(parts)

# (Raw 플래그, SendInput 플래그, X버튼 데이터, 누를 때 이름, 뗄 때 이름)
BUTTON_MAP = [
    (0x0001, 0x0002, 0, "L",  None),
    (0x0002, 0x0004, 0, None, "L"),
    (0x0004, 0x0008, 0, "R",  None),
    (0x0008, 0x0010, 0, None, "R"),
    (0x0010, 0x0020, 0, "M",  None),
    (0x0020, 0x0040, 0, None, "M"),
    (0x0040, 0x0080, 1, "X1", None),
    (0x0080, 0x0100, 1, None, "X1"),
    (0x0100, 0x0080, 2, "X2", None),
    (0x0200, 0x0100, 2, None, "X2"),
]
# 버튼을 놓는 SendInput 플래그 (강제 정지 시 붙잡힌 버튼 해제용)
RELEASE_MAP = {"L": (0x0004, 0), "R": (0x0010, 0), "M": (0x0040, 0),
               "X1": (0x0100, 1), "X2": (0x0100, 2)}


# ---------------------------------------------------------------- 구조체
class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", DWORD), ("dwSize", DWORD),
                ("hDevice", HANDLE), ("wParam", WPARAM)]


class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", USHORT), ("usButtonData", USHORT)]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [("ulButtons", ULONG), ("btn", _RAWMOUSE_BUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", USHORT), ("u", _RAWMOUSE_UNION),
                ("ulRawButtons", ULONG), ("lLastX", LONG),
                ("lLastY", LONG), ("ulExtraInformation", ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", USHORT), ("Flags", USHORT),
                ("Reserved", USHORT), ("VKey", USHORT),
                ("Message", UINT), ("ExtraInformation", ULONG)]


class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", DWORD), ("dwCount", DWORD),
                ("bRawData", ctypes.c_ubyte * 1)]


class _RAWINPUT_DATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RAWINPUT_DATA)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", USHORT), ("usUsage", USHORT),
                ("dwFlags", DWORD), ("hwndTarget", HWND)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
                ("lParam", LPARAM), ("time", DWORD), ("pt", POINT)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", HINSTANCE), ("hIcon", HICON),
                ("hCursor", HANDLE), ("hbrBackground", HBRUSH),
                ("lpszMenuName", LPCWSTR), ("lpszClassName", LPCWSTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", DWORD), ("u", _INPUT_UNION)]


# ---------------------------------------------------------------- 함수 시그니처
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.RegisterClassW.restype = ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = HWND
user32.CreateWindowExW.argtypes = [DWORD, LPCWSTR, LPCWSTR, DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, HWND, HMENU,
                                   HINSTANCE, ctypes.c_void_p]
user32.GetRawInputData.restype = UINT
user32.GetRawInputData.argtypes = [ctypes.c_void_p, UINT,
                                   ctypes.POINTER(RAWINPUT),
                                   ctypes.POINTER(UINT), UINT]
user32.GetRawInputBuffer.restype = UINT
user32.GetRawInputBuffer.argtypes = [ctypes.POINTER(ctypes.c_ubyte),
                                     ctypes.POINTER(UINT), UINT]
user32.GetRawInputDeviceInfoW.restype = UINT
user32.GetRawInputDeviceInfoW.argtypes = [HANDLE, UINT, ctypes.c_void_p,
                                          ctypes.POINTER(UINT)]
user32.RegisterRawInputDevices.restype = BOOL
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE),
                                           UINT, UINT]
user32.SendInput.restype = UINT
user32.SendInput.argtypes = [UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), HWND, UINT, UINT]
user32.PostThreadMessageW.argtypes = [DWORD, UINT, WPARAM, LPARAM]
user32.RegisterHotKey.argtypes = [HWND, ctypes.c_int, UINT, UINT]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [DWORD, DWORD, DWORD, DWORD, ULONG_PTR]
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte,
                               DWORD, ULONG_PTR]
user32.GetForegroundWindow.restype = HWND
user32.GetWindowTextW.argtypes = [HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(DWORD)]
user32.SystemParametersInfoW.restype = BOOL
user32.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.UnregisterHotKey.argtypes = [HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [HWND]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
kernel32.GetModuleHandleW.restype = HMODULE
kernel32.GetModuleHandleW.argtypes = [LPCWSTR]


class DCB(ctypes.Structure):
    _fields_ = [("DCBlength", DWORD), ("BaudRate", DWORD), ("flags", DWORD),
                ("wReserved", WORD), ("XonLim", WORD), ("XoffLim", WORD),
                ("ByteSize", ctypes.c_ubyte), ("Parity", ctypes.c_ubyte),
                ("StopBits", ctypes.c_ubyte), ("XonChar", ctypes.c_char),
                ("XoffChar", ctypes.c_char), ("ErrorChar", ctypes.c_char),
                ("EofChar", ctypes.c_char), ("EvtChar", ctypes.c_char),
                ("wReserved1", WORD)]


class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [("ReadIntervalTimeout", DWORD),
                ("ReadTotalTimeoutMultiplier", DWORD),
                ("ReadTotalTimeoutConstant", DWORD),
                ("WriteTotalTimeoutMultiplier", DWORD),
                ("WriteTotalTimeoutConstant", DWORD)]


kernel32.CreateFileW.restype = HANDLE
kernel32.CreateFileW.argtypes = [LPCWSTR, DWORD, DWORD, ctypes.c_void_p,
                                 DWORD, DWORD, HANDLE]
kernel32.WriteFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD,
                               ctypes.POINTER(DWORD), ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.GetCommState.argtypes = [HANDLE, ctypes.POINTER(DCB)]
kernel32.SetCommState.argtypes = [HANDLE, ctypes.POINTER(DCB)]
kernel32.SetCommTimeouts.argtypes = [HANDLE, ctypes.POINTER(COMMTIMEOUTS)]


def _open_com(name):
    """COM 포트를 열어 핸들을 돌려준다. 실패하면 None."""
    h = kernel32.CreateFileW("\\\\.\\" + name, GENERIC_WRITE, 0, None,
                             OPEN_EXISTING, 0, None)
    if not h or h == INVALID_HANDLE:
        return None
    return h


def _com_number(name):
    """COM10 이 COM9 보다 뒤에 오도록 번호를 뽑는다."""
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else 0


def list_com_ports():
    """지금 있는 COM 포트 목록을 만든다.

    레지스트리에 이미 적혀 있는 목록을 읽는다. 포트를 하나씩 열어 보는
    방식은 블루투스 시리얼처럼 여는 것만으로 연결을 시도하거나 보드를
    다시 켜는 장치를 건드릴 수 있어서 쓰지 않는다.
    """
    found = []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DEVICEMAP\SERIALCOMM")
        try:
            index = 0
            while True:
                try:
                    _name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                if isinstance(value, str) and value.upper().startswith("COM"):
                    found.append(value)
                index += 1
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass

    if found:
        return sorted(set(found), key=_com_number)

    # 레지스트리를 못 읽는 드문 경우에만 직접 열어 본다
    for i in range(1, 33):
        name = "COM{}".format(i)
        ctypes.set_last_error(0)
        h = _open_com(name)
        if h:
            kernel32.CloseHandle(h)
            found.append(name)
        elif ctypes.get_last_error() == 5:
            found.append(name)   # 이미 누가 쓰는 중이지만 존재하는 포트
    return found


class PicoLink:
    """피코와 이어 주는 시리얼 통로."""

    def __init__(self):
        self.handle = None
        self.name = None

    def open(self, name):
        self.close()
        h = _open_com(name)
        if not h:
            return False
        try:
            dcb = DCB()
            dcb.DCBlength = ctypes.sizeof(DCB)
            kernel32.GetCommState(h, ctypes.byref(dcb))
            dcb.BaudRate = 115200
            dcb.ByteSize = 8
            dcb.Parity = 0
            dcb.StopBits = 0
            kernel32.SetCommState(h, ctypes.byref(dcb))
            to = COMMTIMEOUTS(0, 0, 0, 0, 200)
            kernel32.SetCommTimeouts(h, ctypes.byref(to))
        except Exception:
            pass
        self.handle = h
        self.name = name
        return True

    def write(self, data):
        if not self.handle or not data:
            return False
        written = DWORD(0)
        buf = ctypes.create_string_buffer(bytes(data))
        ok = kernel32.WriteFile(self.handle, buf, len(data),
                                ctypes.byref(written), None)
        return bool(ok) and written.value == len(data)

    def close(self):
        if self.handle:
            try:
                kernel32.CloseHandle(self.handle)
            except Exception:
                pass
        self.handle = None
        self.name = None


def pico_frames(dx, dy, buttons, wheel):
    """피코가 알아듣는 5바이트 묶음으로 쪼갠다 (한 번에 127 까지)."""
    out = bytearray()
    while True:
        cx = max(-127, min(127, dx)); dx -= cx
        cy = max(-127, min(127, dy)); dy -= cy
        cw = max(-127, min(127, wheel)); wheel -= cw
        out += bytes([PICO_SYNC, cx & 0xFF, cy & 0xFF,
                      buttons & 0xFF, cw & 0xFF])
        if dx == 0 and dy == 0 and wheel == 0:
            break
    return bytes(out)


def is_wow64():
    """32비트 파이썬이 64비트 Windows 위에서 도는 중인지 본다.

    그 경우 GetRawInputBuffer 가 64비트 모양으로 자료를 돌려주기 때문에,
    32비트 모양으로 읽으면 어긋난 값을 기록하게 된다.
    """
    try:
        kernel32.GetCurrentProcess.restype = HANDLE
        kernel32.IsWow64Process.argtypes = [HANDLE, ctypes.POINTER(BOOL)]
        flag = BOOL(0)
        if kernel32.IsWow64Process(kernel32.GetCurrentProcess(),
                                   ctypes.byref(flag)):
            return bool(flag.value)
    except Exception:
        pass
    return False


IS_WOW64 = is_wow64()


def clean_events(raw):
    """불러온 기록이 쓸 수 있는 모양인지 본다. 아니면 None 을 돌려준다.

    모양을 확인하기 전에 목록을 바꿔 넣으면, 길이를 계산하다 오류가 나고
    그 오류가 창 갱신 루프를 멈춰 창이 얼어붙는다.
    """
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or not item:
            return None
        kind = item[0]
        if not ((kind == "m" and len(item) == 7)
                or (kind == "k" and len(item) == 5)):
            return None
        for value in item[1:]:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
        out.append(list(item))
    return out


def clean_start_pos(raw):
    """저장된 시작 좌표가 쓸 만한지 본다."""
    if (isinstance(raw, (list, tuple)) and len(raw) == 2
            and all(not isinstance(v, bool) and isinstance(v, (int, float))
                    for v in raw)):
        return (int(raw[0]), int(raw[1]))
    return None


def to_signed16(v):
    return v - 0x10000 if v & 0x8000 else v


def send(inputs):
    """입력을 넣고, 실제로 들어간 개수를 돌려준다."""
    if not inputs:
        return 0
    arr = (INPUT * len(inputs))(*inputs)
    return int(user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)))


def mouse_input(dx=0, dy=0, data=0, flags=0):
    i = INPUT(type=INPUT_MOUSE)
    i.mi = MOUSEINPUT(dx, dy, ctypes.c_uint32(data).value, flags, 0, SIGNATURE)
    return i


def key_input(scan, flags, vk=0):
    """키 입력 하나를 만든다.

    SendInput 은 KEYEVENTF_SCANCODE 가 켜져 있으면 스캔코드만 보고 vk 는
    무시한다. 그래도 vk 를 같이 실어 두는 이유는, SendInput 이 막혀서
    구형 keybd_event 로 내려갔을 때 그쪽은 스캔코드만으로는 동작하지
    않기 때문이다.
    """
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, SIGNATURE)
    return i


# ---------------------------------------------------------------- 엔진
class Engine:
    """녹화/재생을 담당. 모든 Win32 메시지 처리는 listener 스레드에서 돈다."""

    def __init__(self):
        self.events = []          # 기록된 이벤트 목록
        self.start_pos = None     # 녹화 시작 시 커서 위치
        self.recording = False
        self.playing = False
        self._stop_play = threading.Event()
        self._t0 = 0.0
        self._lock = threading.Lock()
        self.log_q = queue.Queue()
        self.record_keyboard = True
        self.hotkeys = dict((k, list(v)) for k, v in DEFAULT_HOTKEYS.items())
        self.hotkey_vks = set()   # 녹화에서 빼야 할 단축키의 키 코드
        self.hwnd = None
        self.thread_id = None
        self._wndproc = None
        self._saved_mouse = None
        self._play_thread = None
        # Raw Input 상태 표시용
        self.raw_ready = False
        self.raw_packets = 0        # 지금까지 받은 원시 패킷 수
        self.raw_dx = 0             # 마지막 원시 이동량
        self.raw_dy = 0
        self.raw_devices = {}       # 장치 핸들 -> 이름
        self.raw_buffered = 0       # 버퍼로 한 번에 긁어온 패킷 수
        self.inj_packets = 0        # 우리가 보낸 입력이 Raw Input 으로 되돌아온 수
        self.inj_hdevice = None     # 그때의 장치 핸들 (합성 입력은 보통 0)
        self.selftest_running = False
        self.pkt_total = 0          # 받은 마우스 패킷 전체
        self.pkt_hdev0 = 0          # 그중 장치 핸들이 0 인 것
        self.pkt_sig = 0            # 그중 우리 표식이 붙은 것
        self.path_buffer = 0        # GetRawInputBuffer 로 읽은 횟수
        self.path_single = 0        # GetRawInputData 로 읽은 횟수
        self._trace_left = 0        # 패킷 내용을 로그로 남길 남은 횟수
        # 재생 방식 (거부당하면 단계적으로 낮춘다)
        self.move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE
        self.send_fail = 0
        self.use_legacy = False
        # 피코(진짜 USB 장치)로 재생하기
        self.pico = PicoLink()
        self.use_pico = False
        self.pico_btn = 0
        self._pico_dx = 0
        self._pico_dy = 0
        self._pico_wheel = 0
        self._pico_sent_btn = 0
        self._pico_flush_t = 0.0
        self._pico_warned = set()   # 같은 안내를 두 번 하지 않으려고
        self._buf = (ctypes.c_ubyte * 65536)()

    # ---------- 로그
    def log(self, msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_q.put("[{}] {}".format(stamp, msg))

    # ---------- 녹화
    def start_record(self):
        if self.playing:
            self.log("재생 중에는 녹화할 수 없습니다.")
            return
        if self.selftest_running:
            self.log("검사가 끝난 뒤에 녹화하세요.")
            return
        with self._lock:
            self.events = []
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            self.start_pos = (pt.x, pt.y)
            self._t0 = time.perf_counter()
            self.recording = True
        self.log("녹화 시작. 마우스를 움직이세요. ({} = 중지)".format(
            hotkey_text(self.hotkeys["record"])))

    def stop_record(self):
        if not self.recording:
            return
        self.recording = False
        self.log("녹화 종료. 이벤트 {}개 / {:.2f}초".format(
            len(self.events), self.duration()))

    def duration(self):
        # 녹화 중에는 다른 스레드가 목록을 갈아치울 수 있으니 한 번만 읽는다.
        # 이 값은 창 갱신 루프가 계속 부르므로 무슨 일이 있어도 던지지 않는다.
        events = self.events
        if not events:
            return 0.0
        try:
            return float(events[-1][1])
        except Exception:
            return 0.0

    # ---------- 원시 입력 처리 (Raw Input)
    def _device_name(self, handle):
        """어느 장치에서 온 원시 입력인지 이름을 한 번만 알아낸다."""
        if handle in self.raw_devices:
            return self.raw_devices[handle]
        name = "알 수 없는 장치"
        try:
            need = UINT(0)
            user32.GetRawInputDeviceInfoW(HANDLE(handle), RIDI_DEVICENAME,
                                          None, ctypes.byref(need))
            if 0 < need.value < 4096:
                buf = ctypes.create_unicode_buffer(need.value + 1)
                if user32.GetRawInputDeviceInfoW(
                        HANDLE(handle), RIDI_DEVICENAME,
                        ctypes.cast(buf, ctypes.c_void_p),
                        ctypes.byref(need)) != 0xFFFFFFFF:
                    name = buf.value or name
        except Exception:
            pass
        self.raw_devices[handle] = name
        return name

    def _handle_packet(self, raw):
        """RAWINPUT 한 개를 해석해 통계에 반영하고, 녹화 중이면 기록한다."""
        t = (time.perf_counter() - self._t0) if self.recording else 0.0

        if raw.header.dwType == RIM_TYPEMOUSE:
            m = raw.data.mouse
            handle = int(raw.header.hDevice or 0)
            extra = int(m.ulExtraInformation)
            bf = m.btn.usButtonFlags
            bd = to_signed16(m.btn.usButtonData)

            self.pkt_total += 1
            if handle == 0:
                self.pkt_hdev0 += 1
            if extra == SIGNATURE:
                self.pkt_sig += 1
            if self._trace_left > 0:
                self._trace_left -= 1
                self.log("   패킷 hDevice={} extra=0x{:X} dx={} dy={} "
                         "usFlags=0x{:X} btn=0x{:X}".format(
                             handle, extra, int(m.lLastX), int(m.lLastY),
                             int(m.usFlags), int(bf)))

            # 합성 입력 판정: 우리 표식이 있거나, 장치 핸들이 0 이거나
            if extra == SIGNATURE or handle == 0:
                self.inj_packets += 1
                self.inj_hdevice = handle
                return

            self.raw_packets += 1
            if handle not in self.raw_devices:
                self.log("원시 입력 장치 감지: {}".format(self._device_name(handle)))
            if m.lLastX or m.lLastY:
                self.raw_dx, self.raw_dy = int(m.lLastX), int(m.lLastY)
            if self.recording and (m.lLastX or m.lLastY or bf):
                self.events.append(["m", round(t, 6), int(m.lLastX),
                                    int(m.lLastY), int(bf), int(bd),
                                    int(m.usFlags)])

        elif raw.header.dwType == RIM_TYPEKEYBOARD:
            k = raw.data.keyboard
            if int(k.ExtraInformation) == SIGNATURE:
                self.inj_packets += 1
                self.inj_hdevice = int(raw.header.hDevice or 0)
                return
            self.raw_packets += 1
            if not (self.recording and self.record_keyboard):
                return
            if k.VKey in self.hotkey_vks:
                return  # 단축키는 기록하지 않는다
            if k.MakeCode == 0:
                return
            self.events.append(["k", round(t, 6), int(k.MakeCode),
                                int(k.Flags), int(k.VKey)])

    def _drain_buffer(self):
        """GetRawInputBuffer 로 쌓인 원시 패킷을 한 번에 모두 가져온다.

        폴링 속도가 높은 마우스(1000Hz 등)에서 패킷을 흘리지 않기 위한 경로다.
        """
        if IS_WOW64:
            # 32비트 파이썬 + 64비트 Windows 조합에서는 버퍼 모양이 달라
            # 어긋난 값을 읽게 된다. 한 건씩 읽는 쪽만 쓴다.
            return 0
        got_any = 0
        for _ in range(64):  # 무한 루프 방지
            size = UINT(ctypes.sizeof(self._buf))
            n = user32.GetRawInputBuffer(self._buf, ctypes.byref(size),
                                         ctypes.sizeof(RAWINPUTHEADER))
            if n == 0 or n == 0xFFFFFFFF:
                break
            addr = ctypes.addressof(self._buf)
            for _i in range(n):
                ri = RAWINPUT.from_address(addr)
                self._handle_packet(ri)
                step = ri.header.dwSize
                if step <= 0:
                    break
                addr = (addr + step + RAW_ALIGN - 1) & ~(RAW_ALIGN - 1)
            got_any += n
            self.path_buffer += 1
            if n < 2:
                break
        if got_any > 1:
            self.raw_buffered = got_any
        return got_any

    def _read_one(self, lparam):
        """버퍼가 비어 있을 때 이번 WM_INPUT 한 건만 직접 읽는다."""
        raw = RAWINPUT()
        size = UINT(ctypes.sizeof(RAWINPUT))
        got = user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT,
                                     ctypes.byref(raw), ctypes.byref(size),
                                     ctypes.sizeof(RAWINPUTHEADER))
        if got == 0 or got == 0xFFFFFFFF:
            return
        self.path_single += 1
        self._handle_packet(raw)

    def _on_raw(self, lparam):
        if not self._drain_buffer():
            self._read_one(lparam)

    # ---------- 메시지 루프 스레드
    def listener(self):
        self.thread_id = kernel32.GetCurrentThreadId()

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                try:
                    self._on_raw(lparam)
                except Exception as e:
                    self.log("입력 처리 오류: {}".format(e))
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            if msg == WM_HOTKEY:
                self._on_hotkey(int(wparam))
                return 0
            if msg == WM_APP_REHOTKEY:
                self._register_hotkeys()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW()
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinst
        cls.lpszClassName = "MouseTracerRawInputWnd"
        user32.RegisterClassW(ctypes.byref(cls))
        self.hwnd = user32.CreateWindowExW(0, "MouseTracerRawInputWnd",
                                           "MouseTracer", 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        if not self.hwnd:
            self.log("숨김 창 생성 실패")
            return

        devs = (RAWINPUTDEVICE * 2)()
        devs[0].usUsagePage, devs[0].usUsage = 0x01, 0x02   # 마우스
        devs[0].dwFlags, devs[0].hwndTarget = RIDEV_INPUTSINK, self.hwnd
        devs[1].usUsagePage, devs[1].usUsage = 0x01, 0x06   # 키보드
        devs[1].dwFlags, devs[1].hwndTarget = RIDEV_INPUTSINK, self.hwnd
        if not user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            self.log("Raw Input 등록 실패 (오류 {})".format(ctypes.get_last_error()))
        else:
            self.raw_ready = True
            self.log("Raw Input 등록 완료. 마우스와 키보드의 원시 입력을 "
                     "직접 받습니다.")
            if IS_WOW64:
                self.log("32비트 파이썬으로 돌고 있습니다. 한 건씩 읽는 "
                         "방식으로 동작합니다. 64비트 파이썬을 쓰면 더 "
                         "빠릅니다.")

        self._register_hotkeys()

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _register_hotkeys(self):
        """지금 설정된 단축키를 Windows 에 등록한다. 리스너 스레드에서 부른다."""
        if not self.hwnd:
            return
        for _key, hid, _label in ACTIONS:
            user32.UnregisterHotKey(self.hwnd, hid)
        self.hotkey_vks = set()
        ok, bad = [], []
        for key, hid, label in ACTIONS:
            entry = self.hotkeys.get(key) or DEFAULT_HOTKEYS[key]
            vk = KEY_CODES.get(entry[0])
            shown = "{} {}".format(label, hotkey_text(entry))
            if vk is None:
                bad.append(shown)
                continue
            mods = int(entry[1]) | MOD_NOREPEAT
            if user32.RegisterHotKey(self.hwnd, hid, mods, vk):
                ok.append(shown)
                self.hotkey_vks.add(vk)
            else:
                bad.append(shown)
        if ok:
            self.log("단축키 · " + " · ".join(ok))
        if bad:
            self.log("단축키 등록 실패 (다른 프로그램이 쓰는 중): "
                     + ", ".join(bad))

    def apply_hotkeys(self):
        """창에서 바꾼 단축키를 리스너 스레드에 넘겨 다시 등록시킨다."""
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_REHOTKEY, 0, 0)

    def _on_hotkey(self, hid):
        if hid == HOTKEY_RECORD:
            self.stop_record() if self.recording else self.start_record()
        elif hid == HOTKEY_PLAY:
            if self.playing:
                self.stop_play()
            else:
                self.log_q.put("@@PLAY@@")
        elif hid == HOTKEY_STOP:
            self.stop_record()
            self.stop_play()

    def shutdown(self):
        self.recording = False
        self.stop_play()
        # 재생 스레드가 눌린 버튼을 놓을 때까지 기다린다. 먼저 포트를 닫으면
        # 피코가 버튼을 누른 채로 남아 프로그램을 끈 뒤에도 계속 눌려 있다.
        thread = self._play_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        if self.pico.handle:
            self.pico.write(pico_frames(0, 0, 0, 0))   # 버튼 모두 놓기
        self.pico.close()
        if self.hwnd:
            for hid in (HOTKEY_RECORD, HOTKEY_PLAY, HOTKEY_STOP):
                user32.UnregisterHotKey(self.hwnd, hid)
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._restore_mouse()

    # ---------- 입력 내보내기 (거부당하면 다른 방식으로 내려간다)
    def _emit_legacy(self, batch):
        """SendInput 이 막힐 때 쓰는 구형 API 경로."""
        for i in batch:
            if i.type == INPUT_MOUSE:
                user32.mouse_event(i.mi.dwFlags, i.mi.dx, i.mi.dy,
                                   i.mi.mouseData, SIGNATURE)
            else:
                # keybd_event 는 KEYEVENTF_SCANCODE 를 모른다. 가상 키 코드로
                # 보내되, 확장키 표시와 뗌 표시만 넘긴다.
                flags = i.ki.dwFlags & (KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP)
                user32.keybd_event(i.ki.wVk & 0xFF, i.ki.wScan & 0xFF,
                                   flags, SIGNATURE)

    def _warn_pico_once(self, kind, message):
        """같은 안내를 재생 한 번에 한 번만 로그에 남긴다."""
        if kind not in self._pico_warned:
            self._pico_warned.add(kind)
            self.log(message)

    def _pico_flush(self):
        """모아 둔 이동량을 피코로 한 번에 보낸다."""
        dx, dy = self._pico_dx, self._pico_dy
        # 휠은 120 단위가 한 칸이다. 모자란 나머지는 다음에 이어서 쓴다.
        wheel = int(self._pico_wheel / 120)
        self._pico_dx = self._pico_dy = 0
        self._pico_wheel -= wheel * 120
        self._pico_flush_t = time.perf_counter()
        if not (dx or dy or wheel or self.pico_btn != self._pico_sent_btn):
            return
        self._pico_sent_btn = self.pico_btn
        if not self.pico.write(pico_frames(dx, dy, self.pico_btn, wheel)):
            self.use_pico = False
            self.log("피코로 보내기 실패. 일반 방식으로 되돌립니다.")

    def _emit_pico(self, batch):
        """재생 입력을 피코로 넘겨 진짜 마우스가 움직이게 한다.

        USB 마우스가 낼 수 있는 속도보다 빠르게 보내면 밀리기만 하므로,
        잔잔한 이동은 잠깐 모았다가 보낸다. 버튼과 휠은 바로 보낸다.
        """
        now_urgent = False
        for i in batch:
            if i.type != INPUT_MOUSE:
                # 피코는 마우스로만 동작해서 키보드는 보낼 수 없다
                self._warn_pico_once(
                    "keyboard",
                    "피코 재생 중에는 키보드 입력이 빠집니다. 마우스만 나갑니다.")
                continue

            fl = i.mi.dwFlags

            if fl & MOUSEEVENTF_ABSOLUTE:
                # 태블릿이나 원격 데스크톱으로 녹화하면 화면 절대좌표가 들어온다.
                # 피코는 상대 이동만 낼 수 있어서, 이 값을 이동량으로 쓰면
                # 커서가 화면 밖으로 튄다. 그래서 건너뛴다.
                self._warn_pico_once(
                    "absolute",
                    "이 기록은 화면 절대좌표로 저장돼 있어 피코로는 재생할 수 "
                    "없습니다. 피코 사용을 끄고 재생하세요.")
                continue

            # 버튼이 바뀌기 직전에 여태 모은 이동을 예전 버튼 상태로 먼저
            # 내보낸다. 그래야 클릭이 제 위치에서 일어난다.
            new_btn = self.pico_btn
            for flag, bit, press in ((MOUSEEVENTF_LEFTDOWN, 0x01, True),
                                     (MOUSEEVENTF_LEFTUP, 0x01, False),
                                     (MOUSEEVENTF_RIGHTDOWN, 0x02, True),
                                     (MOUSEEVENTF_RIGHTUP, 0x02, False),
                                     (MOUSEEVENTF_MIDDLEDOWN, 0x04, True),
                                     (MOUSEEVENTF_MIDDLEUP, 0x04, False)):
                if fl & flag:
                    new_btn = (new_btn | bit) if press else (new_btn & ~bit)
            if new_btn != self.pico_btn:
                self._pico_flush()
                self.pico_btn = new_btn
                now_urgent = True

            if fl & MOUSEEVENTF_MOVE:
                self._pico_dx += int(i.mi.dx)
                self._pico_dy += int(i.mi.dy)
            if fl & MOUSEEVENTF_WHEEL:
                # 한 칸(120)이 안 되는 양도 버리지 않고 모아 둔다
                self._pico_wheel += int(ctypes.c_int32(i.mi.mouseData).value)
                now_urgent = True
            if fl & MOUSEEVENTF_HWHEEL:
                self._warn_pico_once(
                    "hwheel", "피코 재생 중에는 가로 휠이 빠집니다.")
            if fl & (MOUSEEVENTF_XDOWN | MOUSEEVENTF_XUP):
                self._warn_pico_once(
                    "xbutton", "피코 재생 중에는 마우스 옆 버튼이 빠집니다.")

        if now_urgent or (time.perf_counter() - self._pico_flush_t) >= 0.004:
            self._pico_flush()

    def _emit(self, batch):
        if not batch:
            return
        if self.use_pico and self.pico.handle:
            self._emit_pico(batch)
            return
        if self.use_legacy:
            self._emit_legacy(batch)
            return
        n = send(batch)
        if n == len(batch):
            self.send_fail = 0
            return
        err = ctypes.get_last_error()
        self.send_fail += 1
        if self.move_flags & MOUSEEVENTF_MOVE_NOCOALESCE:
            self.move_flags = MOUSEEVENTF_MOVE
            self.log("SendInput 이 거부되었습니다(오류 {}). 단순 이동 "
                     "방식으로 바꿉니다.".format(err))
        elif self.send_fail >= 8:
            self.use_legacy = True
            self.log("SendInput 이 계속 거부되어(오류 {}) 구형 방식으로 "
                     "바꿉니다.".format(err))

    # ---------- Raw Input 자체 검사
    def selftest(self):
        """재생용 합성 입력이 Raw Input 스트림에 실제로 나타나는지 확인한다.

        커서가 제자리로 돌아오도록 좌우로 같은 양만큼만 움직인다.
        """
        if self.selftest_running or self.playing or self.recording:
            return
        self.selftest_running = True
        threading.Thread(target=self._selftest_worker, daemon=True).start()

    def _environment(self):
        """검사에 도움이 되는 주변 상황을 모아 로그로 남긴다."""
        try:
            admin = ctypes.WinDLL("shell32").IsUserAnAdmin()
            self.log("이 프로그램 권한: {}".format(
                "관리자" if admin else "일반 사용자"))
        except Exception:
            pass
        try:
            hwnd = user32.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            pid = DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self.log("맨 앞 창: \"{}\" (프로세스 {})".format(
                buf.value or "제목 없음", pid.value))
        except Exception:
            pass
        try:
            bits = 64 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32
            self.log("파이썬 {}비트 · INPUT 구조체 {}바이트".format(
                bits, ctypes.sizeof(INPUT)))
        except Exception:
            pass

    def _try_method(self, name, mover, shots=10, can_verify=True):
        """한 가지 입력 방법을 시험하고 결과를 돌려준다.

        can_verify 가 False 면 그 방법은 성공 여부를 돌려주지 않는 함수라서,
        몇 번 보냈는지만 셀 수 있다. 성공한 것처럼 적지 않는다.
        """
        pt0 = POINT()
        user32.GetCursorPos(ctypes.byref(pt0))
        b_total, b_inj = self.pkt_total, self.inj_packets
        ok = 0
        err = 0
        ctypes.set_last_error(0)
        for _ in range(shots):
            for dx in (6, -6):
                if mover(dx):
                    ok += 1
                else:
                    err = ctypes.get_last_error()
                time.sleep(0.012)
        time.sleep(0.35)
        pt1 = POINT()
        user32.GetCursorPos(ctypes.byref(pt1))
        moved = (pt0.x != pt1.x) or (pt0.y != pt1.y)
        res = {"name": name, "ok": ok, "total": shots * 2, "err": err,
               "moved": moved, "arrived": self.pkt_total - b_total,
               "inj": self.inj_packets - b_inj, "verified": can_verify}
        head = ("성공 {}/{} · 오류코드 {}".format(ok, shots * 2, err)
                if can_verify else
                "{}번 보냄 (이 방식은 성공 여부 확인 불가)".format(shots * 2))
        self.log("[{}] {} · 커서움직임 {} · 도착패킷 {} · 합성판정 {}".format(
            name, head, "있음" if moved else "없음",
            res["arrived"], res["inj"]))
        return res

    def _selftest_worker(self):
        try:
            self.log("=" * 50)
            self.log("Raw Input 재생 검사 시작")
            self._environment()
            self._trace_left = 8

            flags_nc = MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE
            results = []
            results.append(self._try_method(
                "SendInput 기본", lambda dx: send(
                    [mouse_input(dx, 0, 0, flags_nc)]) == 1))
            results.append(self._try_method(
                "SendInput 단순", lambda dx: send(
                    [mouse_input(dx, 0, 0, MOUSEEVENTF_MOVE)]) == 1))

            def legacy(dx):
                # mouse_event 는 아무것도 돌려주지 않는다. 막혀도 조용하다.
                user32.mouse_event(MOUSEEVENTF_MOVE, dx, 0, 0, SIGNATURE)
                return True
            results.append(self._try_method("구형 mouse_event", legacy,
                                            can_verify=False))

            self._trace_left = 0
            best = None
            for r in results:
                if r["inj"] > 0:
                    best = r
                    break
            worked = [r for r in results if r["moved"]]

            self.log("-" * 50)
            if best:
                self.log("판정: 재생 입력이 Raw Input 으로 잡힙니다.")
                self.log("      성공한 방법은 [{}] 입니다. 장치 핸들 {}.".format(
                    best["name"], self.inj_hdevice))
                self.log("      Raw Input 을 읽는 프로그램은 이 입력을 받습니다.")
            elif worked:
                self.log("판정: 커서는 움직였지만 Raw Input 으로는 돌아오지 "
                         "않았습니다.")
                self.log("      이 PC 에서는 합성 입력이 Raw Input 스트림에 "
                         "나타나지 않습니다.")
                self.log("      Raw Input 만 읽는 프로그램을 움직이려면 실제 "
                         "USB 장치가 필요합니다.")
            else:
                codes = sorted({r["err"] for r in results if r["err"]})
                self.log("판정: 입력이 전혀 들어가지 않았습니다. 오류 코드 "
                         "{}".format(codes or "없음"))
                if 5 in codes:
                    self.log("      코드 5 는 권한 부족입니다. 맨 앞 창이 "
                             "관리자 권한으로 돌고 있습니다.")
                    self.log("      이 프로그램도 마우스 오른쪽 버튼 → "
                             "관리자 권한으로 실행 하면 됩니다.")
                else:
                    self.log("      보안 프로그램이나 게임이 입력 주입을 "
                             "막고 있을 수 있습니다.")
            if self.raw_packets == 0:
                self.log("참고: 하드웨어 원시 입력이 하나도 안 잡혔습니다. "
                         "마우스를 움직여 위쪽 숫자가 오르는지 봐 주세요.")
            self.log("=" * 50)
        except Exception as e:
            self.log("검사 오류: {}".format(e))
        finally:
            self._trace_left = 0
            self.selftest_running = False

    # ---------- 마우스 가속 임시 해제 (재생 후 원래대로 복구)
    def _disable_accel(self):
        self._saved_mouse = None
        try:
            params = (ctypes.c_int * 3)()
            got_accel = user32.SystemParametersInfoW(
                SPI_GETMOUSE, 0, ctypes.byref(params), 0)
            speed = ctypes.c_int()
            got_speed = user32.SystemParametersInfoW(
                SPI_GETMOUSESPEED, 0, ctypes.byref(speed), 0)
            # 지금 값을 못 읽었으면 아무것도 건드리지 않는다. 엉뚱한 값을
            # 적어 두면 나중에 되돌릴 때 마우스 설정이 망가진다.
            if not got_accel or not got_speed or not 1 <= speed.value <= 20:
                self.log("정밀 모드: 지금 마우스 설정을 읽지 못해 건너뜁니다.")
                return
            self._saved_mouse = ([params[0], params[1], params[2]], speed.value)
            flat = (ctypes.c_int * 3)(0, 0, 0)
            user32.SystemParametersInfoW(SPI_SETMOUSE, 0, ctypes.byref(flat), SPIF_SENDCHANGE)
            user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0,
                                         ctypes.c_void_p(10), SPIF_SENDCHANGE)
        except Exception as e:
            self._saved_mouse = None
            self.log("정밀 모드 적용 실패: {}".format(e))

    def _restore_mouse(self):
        if not self._saved_mouse:
            return
        p, speed = self._saved_mouse
        self._saved_mouse = None
        if not 1 <= speed <= 20:
            return   # 이상한 값이면 건드리지 않는다
        try:
            old = (ctypes.c_int * 3)(p[0], p[1], p[2])
            user32.SystemParametersInfoW(SPI_SETMOUSE, 0, ctypes.byref(old), SPIF_SENDCHANGE)
            user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0,
                                         ctypes.c_void_p(speed), SPIF_SENDCHANGE)
        except Exception:
            pass

    # ---------- 재생
    def start_play(self, repeat=1, speed=1.0, goto_start=True, precise=True,
                   gap=0.5):
        if self.recording:
            self.log("녹화 중에는 재생할 수 없습니다.")
            return
        if self.selftest_running:
            self.log("검사가 끝난 뒤에 재생하세요.")
            return
        if self.playing:
            return
        if not self.events:
            self.log("재생할 기록이 없습니다. 먼저 {} 로 녹화하세요.".format(
                hotkey_text(self.hotkeys["record"])))
            return
        self._stop_play.clear()
        self.move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE
        self.send_fail = 0
        self.use_legacy = False
        self.pico_btn = 0
        self._pico_dx = self._pico_dy = self._pico_wheel = 0
        self._pico_sent_btn = 0
        self._pico_flush_t = 0.0
        self._pico_warned = set()   # 같은 안내를 두 번 하지 않으려고
        self.playing = True
        self._play_thread = threading.Thread(
            target=self._play_worker,
            args=(repeat, max(0.05, speed), goto_start, precise, gap),
            daemon=True)
        self._play_thread.start()

    def stop_play(self):
        if self.playing:
            self._stop_play.set()

    def _wait_until(self, target):
        """정확한 타이밍을 위해 sleep + 짧은 busy-wait."""
        while True:
            if self._stop_play.is_set():
                return False
            remain = target - time.perf_counter()
            if remain <= 0:
                return True
            if remain > 0.003:
                time.sleep(min(remain - 0.002, 0.05))
            else:
                while time.perf_counter() < target:
                    pass
                return True

    def _play_worker(self, repeat, speed, goto_start, precise, gap):
        held_buttons = set()
        held_keys = {}
        try:
            winmm.timeBeginPeriod(1)
            if precise:
                self._disable_accel()
            total = repeat if repeat > 0 else -1
            count = 0
            self.log("재생 시작 ({}회, {}배속). 정지는 {} 또는 {}".format(
                "무한" if repeat <= 0 else repeat, speed,
                hotkey_text(self.hotkeys["play"]),
                hotkey_text(self.hotkeys["stop"])))
            while total < 0 or count < total:
                if self._stop_play.is_set():
                    break
                count += 1
                if goto_start and self.start_pos:
                    user32.SetCursorPos(self.start_pos[0], self.start_pos[1])
                    time.sleep(0.03)
                t0 = time.perf_counter()
                for ev in self.events:
                    if not self._wait_until(t0 + ev[1] / speed):
                        break
                    batch = []
                    if ev[0] == "m":
                        _, _, dx, dy, bf, bd, uf = ev
                        if dx or dy:
                            if uf & MOUSE_MOVE_ABSOLUTE:
                                fl = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
                                if uf & MOUSE_VIRTUAL_DESKTOP:
                                    fl |= MOUSEEVENTF_VIRTUALDESK
                                batch.append(mouse_input(dx, dy, 0, fl))
                            else:
                                batch.append(mouse_input(dx, dy, 0,
                                                         self.move_flags))
                        if bf:
                            for raw_flag, si_flag, xdata, press, release in BUTTON_MAP:
                                if bf & raw_flag:
                                    batch.append(mouse_input(0, 0, xdata, si_flag))
                                    if press:
                                        held_buttons.add(press)
                                    if release:
                                        held_buttons.discard(release)
                            if bf & RI_MOUSE_WHEEL:
                                batch.append(mouse_input(0, 0, bd, MOUSEEVENTF_WHEEL))
                            if bf & RI_MOUSE_HWHEEL:
                                batch.append(mouse_input(0, 0, bd, MOUSEEVENTF_HWHEEL))
                    else:
                        _, _, scan, kflags, vkey = ev
                        fl = KEYEVENTF_SCANCODE
                        if kflags & RI_KEY_E0:
                            fl |= KEYEVENTF_EXTENDEDKEY
                        # 왼쪽/오른쪽 Ctrl 처럼 스캔코드가 같고 확장키
                        # 표시만 다른 키가 있다. 둘을 같은 키로 세면 한쪽이
                        # 눌린 채로 남는다.
                        slot = (scan, bool(kflags & RI_KEY_E0))
                        if kflags & RI_KEY_BREAK:
                            fl |= KEYEVENTF_KEYUP
                            held_keys.pop(slot, None)
                        else:
                            held_keys[slot] = (fl, vkey)
                        batch.append(key_input(scan, fl, vkey))
                    self._emit(batch)
                if self._stop_play.is_set():
                    break
                if (total < 0 or count < total) and gap > 0:
                    if not self._wait_until(time.perf_counter() + gap):
                        break
            self.log("재생 종료 ({}회 수행)".format(count))
        except Exception as e:
            self.log("재생 오류: {}".format(e))
        finally:
            # 눌린 채로 남은 버튼/키 강제 해제
            rel = []
            for b in held_buttons:
                if b in RELEASE_MAP:
                    fl, data = RELEASE_MAP[b]
                    rel.append(mouse_input(0, 0, data, fl))
            for (scan, _ext), (fl, vkey) in held_keys.items():
                rel.append(key_input(scan, fl | KEYEVENTF_KEYUP, vkey))
            self._emit(rel)
            if self.use_pico and self.pico.handle:
                self._pico_flush()
            self._restore_mouse()
            try:
                winmm.timeEndPeriod(1)
            except Exception:
                pass
            self.playing = False

    # ---------- 저장 / 불러오기
    def save(self, path):
        data = {"version": 1,
                "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "start_pos": self.start_pos,
                "duration": self.duration(),
                "events": list(self.events)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        self.log("저장 완료: {}".format(os.path.basename(path)))

    def load(self, path):
        if self.recording or self.playing:
            self.log("녹화나 재생 중에는 기록을 불러올 수 없습니다. "
                     "먼저 정지하세요.")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            self.log("기록 파일의 모양이 올바르지 않습니다. 불러오지 않았습니다.")
            return
        events = clean_events(data.get("events"))
        if events is None:
            self.log("기록 내용이 손상되어 불러오지 않았습니다. "
                     "지금 기록은 그대로 둡니다.")
            return
        # 여기까지 통과한 뒤에야 바꿔 넣는다
        self.events = events
        self.start_pos = clean_start_pos(data.get("start_pos"))
        self.log("불러옴: {} (이벤트 {}개 / {:.2f}초)".format(
            os.path.basename(path), len(self.events), self.duration()))


# ---------------------------------------------------------------- GUI
class App:
    def __init__(self, root, engine):
        self.root = root
        self.eng = engine
        root.title(APP_NAME)
        root.geometry("560x910")
        root.minsize(500, 660)

        pad = {"padx": 10, "pady": 4}
        top = ttk.Frame(root, padding=10)
        top.pack(fill="x")

        self.status = tk.StringVar(value="대기 중")
        lbl = ttk.Label(top, textvariable=self.status, font=("맑은 고딕", 16, "bold"))
        lbl.pack(anchor="w")
        self.info = tk.StringVar(value="기록 없음")
        ttk.Label(top, textvariable=self.info, foreground="#555").pack(anchor="w")
        self.raw_info = tk.StringVar(value="Raw Input 준비 중…")
        ttk.Label(top, textvariable=self.raw_info, foreground="#1565c0").pack(anchor="w")
        self.play_info = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.play_info, foreground="#6a1b9a").pack(anchor="w")

        btns = ttk.Frame(root, padding=(10, 6))
        btns.pack(fill="x")
        self.b_rec = ttk.Button(btns, text="● 녹화", command=self.toggle_record)
        self.b_play = ttk.Button(btns, text="▶ 재생", command=self.toggle_play)
        self.b_stop = ttk.Button(btns, text="■ 정지", command=self.stop_all)
        for b in (self.b_rec, self.b_play, self.b_stop):
            b.pack(side="left", expand=True, fill="x", padx=3)

        opt = ttk.LabelFrame(root, text="설정", padding=10)
        opt.pack(fill="x", **pad)

        row1 = ttk.Frame(opt); row1.pack(fill="x", pady=3)
        ttk.Label(row1, text="반복 횟수").pack(side="left")
        self.repeat = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.repeat, width=6).pack(side="left", padx=6)
        ttk.Label(row1, text="(0 = 무한)").pack(side="left")

        row2 = ttk.Frame(opt); row2.pack(fill="x", pady=3)
        ttk.Label(row2, text="재생 속도").pack(side="left")
        self.speed = tk.StringVar(value="1.0")
        ttk.Entry(row2, textvariable=self.speed, width=6).pack(side="left", padx=6)
        ttk.Label(row2, text="배  (1.0 = 녹화한 속도 그대로)").pack(side="left")

        row3 = ttk.Frame(opt); row3.pack(fill="x", pady=3)
        ttk.Label(row3, text="반복 사이 쉬는 시간").pack(side="left")
        self.gap = tk.StringVar(value="0.5")
        ttk.Entry(row3, textvariable=self.gap, width=6).pack(side="left", padx=6)
        ttk.Label(row3, text="초").pack(side="left")

        self.v_kbd = tk.BooleanVar(value=True)
        self.v_goto = tk.BooleanVar(value=True)
        self.v_prec = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="키보드 입력도 함께 기록",
                        variable=self.v_kbd, command=self.sync_opts).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt, text="재생 전 녹화 시작 위치로 커서 이동",
                        variable=self.v_goto).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt, text="정밀 모드 (재생 중 마우스 가속 끔, 끝나면 자동 복구)",
                        variable=self.v_prec).pack(anchor="w", pady=2)

        hk = ttk.LabelFrame(root, text="단축키", padding=10)
        hk.pack(fill="x", **pad)
        self.hk_key = {}
        self.hk_mod = {}
        for row, (key, _hid, label) in enumerate(ACTIONS):
            ttk.Label(hk, text=label).grid(row=row, column=0, sticky="w",
                                           padx=(0, 8), pady=2)
            var = tk.StringVar()
            box = ttk.Combobox(hk, textvariable=var, values=KEY_NAMES,
                               width=12, state="readonly")
            box.grid(row=row, column=1, pady=2)
            self.hk_key[key] = var
            mods = {}
            for col, (name, bit) in enumerate((("Ctrl", MOD_CONTROL),
                                               ("Alt", MOD_ALT),
                                               ("Shift", MOD_SHIFT))):
                v = tk.BooleanVar()
                ttk.Checkbutton(hk, text=name, variable=v).grid(
                    row=row, column=2 + col, padx=4)
                mods[bit] = v
            self.hk_mod[key] = mods
        ttk.Button(hk, text="단축키 적용", command=self.apply_hotkeys).grid(
            row=len(ACTIONS), column=0, columnspan=5, sticky="ew", pady=(8, 0))

        fio = ttk.Frame(root, padding=(10, 2))
        fio.pack(fill="x")
        ttk.Button(fio, text="파일로 저장", command=self.on_save).pack(side="left", expand=True, fill="x", padx=3)
        ttk.Button(fio, text="파일 불러오기", command=self.on_load).pack(side="left", expand=True, fill="x", padx=3)

        diag = ttk.Frame(root, padding=(10, 2))
        diag.pack(fill="x")
        ttk.Button(diag, text="재생 입력이 Raw Input 으로 잡히는지 검사",
                   command=self.eng.selftest).pack(fill="x", padx=3, pady=(0, 4))
        ttk.Button(diag, text="관리자 권한으로 다시 실행",
                   command=self.restart_as_admin).pack(fill="x", padx=3)

        picof = ttk.LabelFrame(root, text="피코로 재생 (진짜 USB 마우스)",
                               padding=10)
        picof.pack(fill="x", **pad)
        prow = ttk.Frame(picof)
        prow.pack(fill="x")
        self.v_pico = tk.BooleanVar(value=False)
        ttk.Checkbutton(prow, text="피코 사용", variable=self.v_pico,
                        command=self.toggle_pico).pack(side="left")
        ttk.Label(prow, text="포트").pack(side="left", padx=(12, 4))
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(prow, textvariable=self.port_var,
                                     width=10, state="readonly")
        self.port_box.pack(side="left")
        ttk.Button(prow, text="포트 찾기",
                   command=self.refresh_ports).pack(side="left", padx=6)
        ttk.Button(picof, text="연결 시험 (커서가 네모를 그립니다)",
                   command=self.test_pico).pack(fill="x", pady=(8, 0))

        logf = ttk.LabelFrame(root, text="로그", padding=6)
        logf.pack(fill="both", expand=True, **pad)
        bar = ttk.Scrollbar(logf, orient="vertical")
        bar.pack(side="right", fill="y")
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled",
                           bg="#1e1e1e", fg="#d4d4d4", relief="flat",
                           yscrollcommand=bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        bar.configure(command=self.log.yview)

        logbtn = ttk.Frame(root, padding=(10, 0, 10, 8))
        logbtn.pack(fill="x")
        ttk.Button(logbtn, text="로그 전체 복사",
                   command=self.copy_log).pack(side="left", expand=True,
                                               fill="x", padx=3)
        ttk.Button(logbtn, text="로그 지우기",
                   command=self.clear_log).pack(side="left", expand=True,
                                                fill="x", padx=3)

        self._rate_t = time.perf_counter()
        self._rate_n = 0
        self._rate = 0

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.pump()
        self.load_saved()

    def sync_opts(self):
        self.eng.record_keyboard = self.v_kbd.get()

    def num(self, var, default, cast=float):
        try:
            return cast(var.get())
        except Exception:
            return default

    def toggle_record(self):
        self.sync_opts()
        self.eng.stop_record() if self.eng.recording else self.eng.start_record()

    def toggle_play(self):
        if self.eng.playing:
            self.eng.stop_play()
        else:
            self.eng.start_play(repeat=self.num(self.repeat, 1, int),
                                speed=self.num(self.speed, 1.0),
                                goto_start=self.v_goto.get(),
                                precise=self.v_prec.get(),
                                gap=self.num(self.gap, 0.5))

    def stop_all(self):
        self.eng.stop_record()
        self.eng.stop_play()

    def on_save(self):
        if not self.eng.events:
            messagebox.showinfo(APP_NAME, "저장할 기록이 없습니다.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         filetypes=[("동작 기록", "*.json")],
                                         initialfile="기록.json")
        if p:
            self.eng.save(p)

    def on_load(self):
        p = filedialog.askopenfilename(filetypes=[("동작 기록", "*.json"),
                                                  ("모든 파일", "*.*")])
        if p:
            try:
                self.eng.load(p)
            except Exception as e:
                messagebox.showerror(APP_NAME, "불러오기 실패: {}".format(e))

    # ---------- 설정 기억하기
    def widget_hotkeys(self):
        """창의 단축키 칸에 지금 찍혀 있는 값. 아직 적용 전일 수 있다."""
        hk = {}
        for key, _hid, _label in ACTIONS:
            mods = 0
            for bit, var in self.hk_mod[key].items():
                if var.get():
                    mods |= bit
            name = self.hk_key[key].get() or self.eng.hotkeys[key][0]
            hk[key] = [name, mods]
        return hk

    def collect(self):
        """저장할 값을 모은다.

        단축키는 창에 찍힌 값이 아니라 실제로 적용된 값을 쓴다. 창의 값은
        겹치는 조합일 수 있는데, 그대로 저장하면 다음에 켤 때 하나가
        조용히 사라진다.
        """
        hk = dict((k, list(v)) for k, v in self.eng.hotkeys.items())
        return {"hotkeys": hk,
                "repeat": self.repeat.get(),
                "speed": self.speed.get(),
                "gap": self.gap.get(),
                "pico_port": self.port_var.get(),
                "keyboard": bool(self.v_kbd.get()),
                "goto_start": bool(self.v_goto.get()),
                "precise": bool(self.v_prec.get())}

    def load_saved(self):
        """지난번에 쓰던 값을 창에 채워 넣는다.

        설정 파일이 어떻게 망가져 있어도 창은 떠야 한다. pythonw 로 띄우면
        시작하다 죽어도 아무 표시가 없어서 원인을 알 수 없다.
        """
        try:
            self._load_saved()
        except Exception as e:
            self.eng.log("설정을 불러오지 못해 기본값으로 시작합니다: "
                         "{}".format(e))
            self.root.after(400, self.eng.apply_hotkeys)

    def _load_saved(self):
        cfg = load_settings()
        saved = cfg.get("hotkeys")
        if not isinstance(saved, dict):
            saved = {}   # 손으로 고쳐 망가진 파일도 그냥 넘긴다
        for key, _hid, _label in ACTIONS:
            entry = saved.get(key)
            if (isinstance(entry, list) and len(entry) == 2
                    and entry[0] in KEY_CODES
                    and isinstance(entry[1], int)
                    and not isinstance(entry[1], bool)
                    and 0 <= entry[1] <= MOD_CONTROL | MOD_ALT | MOD_SHIFT):
                self.eng.hotkeys[key] = [entry[0], int(entry[1])]
            cur = self.eng.hotkeys[key]
            self.hk_key[key].set(cur[0])
            for bit, var in self.hk_mod[key].items():
                var.set(bool(int(cur[1]) & bit))

        for name, var in (("repeat", self.repeat), ("speed", self.speed),
                          ("gap", self.gap), ("pico_port", self.port_var)):
            value = cfg.get(name)
            if isinstance(value, str) and value:
                var.set(value)
        for name, var in (("keyboard", self.v_kbd), ("goto_start", self.v_goto),
                          ("precise", self.v_prec)):
            if isinstance(cfg.get(name), bool):
                var.set(cfg[name])
        self.sync_opts()

        if cfg:
            self.eng.log("지난번 설정을 불러왔습니다.")
        # 리스너가 창을 다 만든 뒤에 단축키를 다시 걸어야 한다
        self.root.after(400, self.eng.apply_hotkeys)

    def save_now(self, quiet=False):
        ok = save_settings(self.collect())
        if quiet:
            return ok
        self.eng.log("설정을 저장했습니다." if ok else
                     "설정 저장 실패. 폴더에 쓸 수 있는지 확인하세요.")
        return ok

    def apply_hotkeys(self):
        cfg = self.widget_hotkeys()
        combos = [(v[0], v[1]) for v in cfg.values()]
        if len(set(combos)) < len(combos):
            self.eng.log("같은 단축키를 두 군데에 넣었습니다. 서로 다르게 "
                         "골라 주세요.")
            return
        self.eng.hotkeys = dict((k, list(v)) for k, v in cfg.items())
        self.eng.apply_hotkeys()
        self.save_now()

    def refresh_ports(self):
        ports = list_com_ports()
        self.port_box["values"] = ports
        current = self.port_var.get()
        if current and current not in ports:
            # 지난번 포트가 사라졌는데 그대로 두면 없는 포트에 연결을 시도한다
            self.eng.log("지난번에 쓰던 {} 가 지금은 보이지 않습니다.".format(
                current))
            self.port_var.set("")
            current = ""
        if ports and not current:
            self.port_var.set(ports[-1])
        self.eng.log("찾은 포트: {}".format(", ".join(ports) if ports
                                           else "없음"))

    def toggle_pico(self):
        if self.v_pico.get():
            name = self.port_var.get()
            if not name:
                self.eng.log("먼저 포트를 고르세요. 포트 찾기 를 눌러보세요.")
                self.v_pico.set(False)
                return
            if self.eng.pico.open(name):
                self.eng.use_pico = True
                self.eng.log("피코 연결됨: {}. 이제 재생이 진짜 USB "
                             "마우스로 나갑니다.".format(name))
            else:
                self.v_pico.set(False)
                self.eng.log("포트를 열지 못했습니다: {}".format(name))
        else:
            if self.eng.playing:
                self.v_pico.set(True)
                self.eng.log("재생 중에는 피코 연결을 끊을 수 없습니다. "
                             "먼저 정지하세요.")
                return
            self.eng.use_pico = False
            self.eng.pico.close()
            self.eng.log("피코 연결을 끊었습니다.")

    def test_pico(self):
        if not self.eng.pico.handle:
            self.eng.log("먼저 피코 사용 을 켜서 연결하세요.")
            return
        if self.eng.playing or self.eng.recording:
            self.eng.log("녹화나 재생 중에는 연결 시험을 할 수 없습니다.")
            return
        threading.Thread(target=self._test_pico_worker, daemon=True).start()

    def _test_pico_worker(self):
        try:
            self.eng.log("연결 시험 신호를 보냅니다.")
            for dx, dy in ((5, 0), (0, 5), (-5, 0), (0, -5)):
                for _ in range(20):
                    if not self.eng.pico.write(pico_frames(dx, dy, 0, 0)):
                        self.eng.log("보내기 실패. 포트를 다시 확인하세요.")
                        return
                    time.sleep(0.008)
            self.eng.log("보냈습니다. 커서가 네모를 그렸으면 성공입니다.")
        except Exception as e:
            self.eng.log("시험 실패: {}".format(e))

    def restart_as_admin(self):
        """입력이 권한 때문에 막힐 때 같은 프로그램을 관리자로 다시 연다."""
        try:
            script = os.path.abspath(__file__)
            r = ctypes.WinDLL("shell32").ShellExecuteW(
                None, "runas", sys.executable, '"{}"'.format(script), None, 1)
            if int(r) > 32:
                self.eng.shutdown()
                self.root.after(300, self.root.destroy)
            else:
                self.eng.log("관리자 실행이 취소되었습니다.")
        except Exception as e:
            self.eng.log("관리자 실행 실패: {}".format(e))

    def copy_log(self):
        try:
            text = self.log.get("1.0", "end").strip()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.eng.log("로그를 클립보드에 복사했습니다. 붙여넣기 하세요.")
        except Exception as e:
            self.eng.log("복사 실패: {}".format(e))

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def pump(self):
        while True:
            try:
                line = self.eng.log_q.get_nowait()
            except queue.Empty:
                break
            if line == "@@PLAY@@":
                self.toggle_play()
                continue
            self.log.configure(state="normal")
            self.log.insert("end", line + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        rec_k = hotkey_text(self.eng.hotkeys["record"])
        play_k = hotkey_text(self.eng.hotkeys["play"])
        stop_k = hotkey_text(self.eng.hotkeys["stop"])
        if self.eng.recording:
            self.status.set("● 녹화 중…")
            self.b_rec.configure(text="● 녹화 중지  ({})".format(rec_k))
        else:
            self.status.set("▶ 재생 중…" if self.eng.playing else "대기 중")
            self.b_rec.configure(text="● 녹화  ({})".format(rec_k))
        self.b_play.configure(
            text=("■ 재생 중지  ({})" if self.eng.playing
                  else "▶ 재생  ({})").format(play_k))
        self.b_stop.configure(text="■ 정지  ({})".format(stop_k))
        n = len(self.eng.events)
        self.info.set("기록 없음" if n == 0 else
                      "이벤트 {}개 · 길이 {:.2f}초".format(n, self.eng.duration()))
        self.update_raw_info()
        self.root.after(60, self.pump)

    def update_raw_info(self):
        """원시 입력이 실제로 들어오고 있는지 초당 패킷 수로 보여준다."""
        now = time.perf_counter()
        span = now - self._rate_t
        if span >= 0.5:
            self._rate = int((self.eng.raw_packets - self._rate_n) / span)
            self._rate_n = self.eng.raw_packets
            self._rate_t = now
        if not self.eng.raw_ready:
            self.raw_info.set("Raw Input 준비 중…")
            return
        dev = len(self.eng.raw_devices)
        self.raw_info.set(
            "Raw Input 동작 중 · 초당 {}패킷 · 최근 이동 dx {:+d}, dy {:+d} · 장치 {}개"
            .format(self._rate, self.eng.raw_dx, self.eng.raw_dy, dev))
        if self.eng.inj_packets:
            self.play_info.set(
                "재생 입력이 Raw Input 으로 되돌아온 수: {}개 (hDevice = {})"
                .format(self.eng.inj_packets, self.eng.inj_hdevice))

    def on_close(self):
        self.save_now(quiet=True)
        self.eng.shutdown()
        self.root.after(120, self.root.destroy)


def main():
    eng = Engine()
    t = threading.Thread(target=eng.listener, daemon=True)
    t.start()
    time.sleep(0.3)
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root, eng)
    try:
        root.mainloop()
    finally:
        eng.shutdown()


if __name__ == "__main__":
    main()
