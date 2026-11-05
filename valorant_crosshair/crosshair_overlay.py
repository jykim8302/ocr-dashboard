"""
발로란트 조준선 오버레이

화면 정중앙에 조준선을 띄워 줍니다. 조준선은 세 가지 방법으로 정할 수 있어요.
- 발로란트 조준선 코드 붙여넣기
- 버튼/슬라이더로 직접 만들기 (만든 조준선은 발로란트 코드로 복사 가능)
- 칸을 칠해서 직접 그리기

- 항상 맨 위에 표시 (게임보다 위)
- 마우스 클릭은 오버레이를 통과해 그대로 게임으로 전달
- F8 키로 켜기/끄기

실행: python crosshair_overlay.py   (Windows 전용, 파이썬 기본 설치만으로 동작)
"""

import ctypes
import json
import os
import sys
import time

IS_WINDOWS = sys.platform == "win32"

# 발로란트 기본 색상 (c 값 0~7), 8은 사용자 지정(u 값)
COLORS = ["FFFFFF", "00FF00", "7FFF00", "DFFF00", "FFFF00", "00FFFF", "FF00FF", "FF0000"]

# 주 무기(P) 조준선 기본값
DEFAULTS = {
    "c": 0,      # 색상 번호
    "h": 1,      # 테두리 켜기
    "t": 1,      # 테두리 두께
    "o": 0.5,    # 테두리 불투명도
    "d": 0,      # 중앙 점 켜기
    "z": 2,      # 중앙 점 두께
    "a": 1,      # 중앙 점 불투명도
    # 안쪽 선 (0x) / 바깥쪽 선 (1x): b 표시, t 두께, l 길이, v 세로 길이, g 세로 길이 따로, o 간격, a 불투명도
    "0b": 1, "0t": 2, "0l": 6, "0v": 6, "0g": 0, "0o": 3, "0a": 0.8,
    "1b": 1, "1t": 2, "1l": 2, "1v": 2, "1g": 0, "1o": 10, "1a": 0.35,
}

EXAMPLE_CODE = "0;P;c;5;h;0;f;0;0l;4;0o;2;0a;1;0f;0;1b;0"

SETTINGS_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ValorantCrosshairOverlay.json"
)


# ---------------------------------------------------------------- 코드 해석 / 그리기

def parse_code(code):
    """조준선 코드 -> 설정 dict. 잘못된 코드면 ValueError."""
    tokens = [t.strip() for t in code.strip().strip(";").split(";")]
    if not tokens or not tokens[0].isdigit():
        raise ValueError("올바른 조준선 코드가 아니에요. (예: 0;P;c;5;...)")

    sections = {None: []}  # 구간 이름 -> [(키, 값)]
    section = None
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("P", "A", "S"):  # 주무기 / 정조준 / 저격총 구간 시작
            section = tok
            sections.setdefault(tok, [])
            i += 1
            continue
        if i + 1 < len(tokens):
            sections[section].append((tok, tokens[i + 1]))
        i += 2
    primary = dict(sections.get("P", []))

    # 화면에 안 그리는 값(사격 오차, 정조준/저격총 설정 등)은 코드 복사할 때 그대로 돌려주기
    cfg = {
        "general": sections[None],
        "extra": [(k, v) for k, v in sections.get("P", []) if k not in DEFAULTS and k != "u"],
        "others": [(s, pairs) for s, pairs in sections.items() if s not in (None, "P")],
    }
    try:
        for key, default in DEFAULTS.items():
            cfg[key] = float(primary.get(key, default))
    except ValueError:
        raise ValueError("코드 안에 잘못된 숫자가 있어요.")

    color = int(cfg["c"])
    hex_color = COLORS[color] if 0 <= color < len(COLORS) else COLORS[0]
    if color == 8 and len(primary.get("u", "")) >= 6:
        hex_color = primary["u"][:6]
    try:
        cfg["rgb"] = tuple(int(hex_color[k:k + 2], 16) for k in (0, 2, 4))
    except ValueError:
        raise ValueError("사용자 지정 색상(u) 값이 잘못됐어요.")
    return cfg


def _span(t):
    """두께 t 를 중심(0) 기준 [시작, 끝) 범위로."""
    return -((t + 1) // 2), t // 2


def build_rects(cfg, scale):
    """조준선을 사각형 목록으로. 반환: ([(x0, y0, x1, y1, 불투명도)], 테두리 두께)"""
    def size(v):
        return max(1, round(v * scale)) if v > 0 else 0

    rects = []
    for p in ("0", "1"):  # 안쪽 선, 바깥쪽 선
        if not cfg[p + "b"]:
            continue
        t = size(cfg[p + "t"])
        hl = size(cfg[p + "l"])
        vl = size(cfg[p + "v"]) if cfg[p + "g"] else hl
        o = round(cfg[p + "o"] * scale)
        a = cfg[p + "a"]
        if not t:
            continue
        lo, hi = _span(t)
        if hl:
            rects += [(o, lo, o + hl, hi, a), (-o - hl, lo, -o, hi, a)]
        if vl:
            rects += [(lo, o, hi, o + vl, a), (lo, -o - vl, hi, -o, a)]

    if cfg["d"]:
        z = size(cfg["z"])
        if z:
            lo, hi = _span(z)
            rects.append((lo, lo, hi, hi, cfg["a"]))

    outline = size(cfg["t"]) if cfg["h"] and cfg["o"] > 0 else 0
    return rects, outline


def render(cfg, scale=1.0):
    """조준선을 정사각형 RGBA 이미지로. 반환: (한 변 크기, bytearray)"""
    rects, ot = build_rects(cfg, scale)
    ext = max([1] + [max(abs(v) for v in r[:4]) for r in rects])
    half = ext + ot + 2
    side = half * 2
    buf = bytearray(side * side * 4)

    def alpha(v):
        return max(0, min(255, round(v * 255)))

    def paint(x0, y0, x1, y1, rgba):
        row = bytes(rgba) * (x1 - x0)
        for y in range(y0 + half, y1 + half):
            start = (y * side + x0 + half) * 4
            buf[start:start + len(row)] = row

    if ot:
        oa = alpha(cfg["o"])
        for x0, y0, x1, y1, _ in rects:
            paint(x0 - ot, y0 - ot, x1 + ot, y1 + ot, (0, 0, 0, oa))
    r, g, b = cfg["rgb"]
    for x0, y0, x1, y1, a in rects:
        paint(x0, y0, x1, y1, (r, g, b, alpha(a)))
    return side, buf


def make_code(cfg):
    """설정 dict -> 발로란트 조준선 코드 (기본값과 다른 것만 적음)."""
    def fmt(v):
        return "%g" % round(v, 3)

    hex_color = "%02X%02X%02X" % cfg["rgb"]
    primary = []
    if hex_color in COLORS:
        if COLORS.index(hex_color) != DEFAULTS["c"]:
            primary += ["c", str(COLORS.index(hex_color))]
    else:
        primary += ["c", "8", "u", hex_color + "FF"]
    for key, default in DEFAULTS.items():
        if key != "c" and round(cfg[key], 3) != default:
            primary += [key, fmt(cfg[key])]
    primary += [t for pair in cfg["extra"] for t in pair]

    parts = ["0"] + [t for pair in cfg["general"] for t in pair]
    if primary:
        parts += ["P"] + primary
    for name, pairs in cfg["others"]:
        parts += [name] + [t for pair in pairs for t in pair]
    return ";".join(parts)


GRID = 40  # 그리기 칸 수 (가운데 4칸이 만나는 점 = 화면 정중앙, 발로란트 조준선과 같은 기준)


def render_pixels(pixels, scale=1.0):
    """그린 그림 {(x, y): (r, g, b, a)} -> 정사각형 RGBA 이미지. 반환: (한 변 크기, bytearray)"""
    side = max(1, round(GRID * scale))
    buf = bytearray(side * side * 4)
    for (cx, cy), rgba in pixels.items():
        x0, x1 = round(cx * scale), max(round((cx + 1) * scale), round(cx * scale) + 1)
        y0, y1 = round(cy * scale), max(round((cy + 1) * scale), round(cy * scale) + 1)
        x1, y1 = min(x1, side), min(y1, side)
        row = bytes(rgba) * (x1 - x0)
        for y in range(y0, y1):
            start = (y * side + x0) * 4
            buf[start:start + len(row)] = row
    return side, buf


def _shape(cfg):
    """설정이 그리기 칸에서 차지하는 자리. 반환: (색 칸 set, 테두리 칸 set)"""
    rects, ot = build_rects(cfg, 1.0)
    c = GRID // 2
    fill, line = set(), set()
    for x0, y0, x1, y1, _ in rects:
        fill.update((x + c, y + c) for y in range(y0, y1) for x in range(x0, x1))
    for x0, y0, x1, y1, _ in rects if ot else ():
        line.update((x + c, y + c) for y in range(y0 - ot, y1 + ot)
                    for x in range(x0 - ot, x1 + ot))
    return fill, line - fill


# 그림 -> 코드 찾을 때 바꿔 보는 값: (키, 후보 값, 같이 켜는 키)
_SEARCH = [("d", [0], None), ("z", range(1, 7), "d"), ("h", [0], None), ("t", range(1, 7), "h")]
for _p in ("0", "1"):
    _SEARCH += [(_p + "b", [0], None), (_p + "l", range(1, 21), _p + "b"),
                (_p + "t", range(1, 11), _p + "b"), (_p + "o", range(0, 21), _p + "b"),
                (_p + "v", range(1, 21), _p + "g"), (_p + "g", [0], None)]


def pixels_to_cfg(pixels):
    """그린 그림과 가장 비슷한 발로란트 조준선 설정 찾기. 반환: (설정, 일치율 0~1)"""
    colors = {}
    for rgba in pixels.values():
        colors[rgba[:3]] = colors.get(rgba[:3], 0) + 1
    shown = {rgb: n for rgb, n in colors.items() if rgb != (0, 0, 0)} or colors
    main = max(shown, key=shown.get)
    # 검은 칸은 테두리로 보기 (전부 검은색이면 검은 조준선)
    want_line = {p for p, c in pixels.items() if c[:3] == (0, 0, 0) and main != (0, 0, 0)}
    want_fill = set(pixels) - want_line

    def error(cfg):
        fill, line = _shape(cfg)
        return len(fill ^ want_fill) + len(line ^ want_line)

    def first_guess(dot):
        # 정중앙 가로줄을 오른쪽으로 훑어서 색 칸 덩어리 = 안쪽 선, 바깥 선
        c = GRID // 2
        cfg = dict(parse_code("0"), o=1.0, d=0.0, h=float(bool(want_line)), **{"0b": 0.0, "1b": 0.0})
        if dot and ((c, c) in want_fill or (c - 1, c - 1) in want_fill):
            cfg["d"] = 1.0
        runs, start = [], None
        for x in range(GRID // 2):
            hit = (c + x, c) in want_fill or (c + x, c - 1) in want_fill
            if hit and start is None:
                start = x
            if not hit and start is not None:
                runs.append((start, x))
                start = None
        if start is not None:
            runs.append((start, GRID // 2))
        if cfg["d"] and runs and runs[0][0] == 0:
            runs.pop(0)
        for p, (x0, x1) in zip(("0", "1"), runs):
            cfg.update({p + "b": 1.0, p + "o": float(x0), p + "l": float(x1 - x0)})
        return cfg

    best, best_err = None, None
    for cfg in (first_guess(True), first_guess(False), dict(parse_code("0"), o=1.0)):
        err = error(cfg)
        improved = True
        while improved:  # 값을 하나씩 바꿔 보면서 더 비슷해지면 채택
            improved = False
            for key, values, enable in _SEARCH:
                for v in values:
                    trial = dict(cfg)
                    trial[key] = float(v)
                    if enable:
                        trial[enable] = 1.0
                    e = error(trial)
                    if e < err:
                        cfg, err, improved = trial, e, True
        if best_err is None or err < best_err:
            best, best_err = cfg, err

    cfg = best
    cfg["rgb"] = main

    # 불투명도: 각 부분이 그려진 칸의 평균 투명도
    def mean_alpha(cells, default):
        alphas = [pixels[p][3] for p in cells if p in pixels]
        return round(sum(alphas) / len(alphas) / 255, 2) if alphas else default

    only = {"0": {"1b": 0.0, "d": 0.0}, "1": {"0b": 0.0, "d": 0.0}, "": {"0b": 0.0, "1b": 0.0}}
    for p, alpha_key in (("0", "0a"), ("1", "1a"), ("", "a")):
        cfg[alpha_key] = mean_alpha(_shape(dict(cfg, h=0.0, **only[p]))[0], 1.0)
    cfg["o"] = mean_alpha(want_line, 0.5) if cfg["h"] else 0.5

    # 꺼진 부분의 값은 기본값으로 (코드를 짧고 깔끔하게)
    unused = [] if cfg["d"] else ["z", "a"]
    unused += [] if cfg["h"] else ["t", "o"]
    for p in ("0", "1"):
        unused += [p + k for k in ("l", "t", "o", "a", "v", "g")] if not cfg[p + "b"] else (
            [] if cfg[p + "g"] else [p + "v"])
    cfg.update({k: float(DEFAULTS[k]) for k in unused})

    wrong = best_err + sum(n for rgb, n in colors.items() if rgb not in (main, (0, 0, 0)))
    return cfg, max(0.0, 1 - wrong / max(1, len(pixels)))


# ---------------------------------------------------------------- Windows 오버레이 창

class Overlay:
    """클릭이 통과되고 항상 맨 위에 있는 투명 창 (픽셀 단위 투명도 지원)."""

    def __init__(self):
        from ctypes import wintypes as w

        self.user32 = u = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = g = ctypes.WinDLL("gdi32", use_last_error=True)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                        ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                        ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                        ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                        ("biClrImportant", w.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", w.BYTE), ("BlendFlags", w.BYTE),
                        ("SourceConstantAlpha", w.BYTE), ("AlphaFormat", w.BYTE)]

        self.BITMAPINFO, self.BLENDFUNCTION, self.w = BITMAPINFO, BLENDFUNCTION, w

        u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU,
                                      w.HINSTANCE, w.LPVOID]
        u.CreateWindowExW.restype = w.HWND
        u.GetDC.argtypes = [w.HWND]
        u.GetDC.restype = w.HDC
        u.ReleaseDC.argtypes = [w.HWND, w.HDC]
        u.UpdateLayeredWindow.argtypes = [w.HWND, w.HDC, ctypes.POINTER(w.POINT),
                                          ctypes.POINTER(w.SIZE), w.HDC, ctypes.POINTER(w.POINT),
                                          w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD]
        u.UpdateLayeredWindow.restype = w.BOOL
        u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        u.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, w.UINT]
        u.DestroyWindow.argtypes = [w.HWND]
        g.CreateCompatibleDC.argtypes = [w.HDC]
        g.CreateCompatibleDC.restype = w.HDC
        g.CreateDIBSection.argtypes = [w.HDC, ctypes.POINTER(BITMAPINFO), w.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
        g.CreateDIBSection.restype = w.HBITMAP
        g.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
        g.SelectObject.restype = w.HGDIOBJ
        g.DeleteObject.argtypes = [w.HGDIOBJ]
        g.DeleteDC.argtypes = [w.HDC]

        ex_style = (0x00080000    # WS_EX_LAYERED     : 투명도
                    | 0x00000020  # WS_EX_TRANSPARENT : 클릭 통과
                    | 0x00000008  # WS_EX_TOPMOST     : 항상 위
                    | 0x00000080  # WS_EX_TOOLWINDOW  : 작업표시줄/Alt+Tab 에 안 보이게
                    | 0x08000000) # WS_EX_NOACTIVATE  : 포커스 안 뺏기
        self.hwnd = u.CreateWindowExW(ex_style, "STATIC", "Crosshair Overlay", 0x80000000,
                                      0, 0, 1, 1, None, None, None, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.visible = True

    def draw(self, side, rgba):
        u, g, w = self.user32, self.gdi32, self.w
        x = u.GetSystemMetrics(0) // 2 - side // 2
        y = u.GetSystemMetrics(1) // 2 - side // 2

        # RGBA -> 미리 곱한(premultiplied) BGRA
        bgra = bytearray(len(rgba))
        for i in range(0, len(rgba), 4):
            a = rgba[i + 3]
            if a:
                bgra[i] = rgba[i + 2] * a // 255
                bgra[i + 1] = rgba[i + 1] * a // 255
                bgra[i + 2] = rgba[i] * a // 255
                bgra[i + 3] = a

        bmi = self.BITMAPINFO()
        h = bmi.bmiHeader
        h.biSize = ctypes.sizeof(h)
        h.biWidth, h.biHeight = side, -side  # 음수 = 위에서 아래로
        h.biPlanes, h.biBitCount = 1, 32

        screen_dc = u.GetDC(None)
        mem_dc = g.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        bitmap = g.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        try:
            ctypes.memmove(bits, bytes(bgra), len(bgra))
            old = g.SelectObject(mem_dc, bitmap)
            ok = u.UpdateLayeredWindow(
                self.hwnd, screen_dc, ctypes.byref(w.POINT(x, y)), ctypes.byref(w.SIZE(side, side)),
                mem_dc, ctypes.byref(w.POINT(0, 0)), 0,
                ctypes.byref(self.BLENDFUNCTION(0, 0, 255, 1)),  # AC_SRC_OVER, AC_SRC_ALPHA
                2)  # ULW_ALPHA
            g.SelectObject(mem_dc, old)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            g.DeleteObject(bitmap)
            g.DeleteDC(mem_dc)
            u.ReleaseDC(None, screen_dc)
        self.set_visible(self.visible)

    def keep_on_top(self):
        if self.visible:
            # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            self.user32.SetWindowPos(self.hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)

    def set_visible(self, on):
        self.visible = on
        self.user32.ShowWindow(self.hwnd, 4 if on else 0)  # SW_SHOWNOACTIVATE / SW_HIDE
        self.keep_on_top()

    def destroy(self):
        self.user32.DestroyWindow(self.hwnd)


# ---------------------------------------------------------------- 설정 창

def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass

# '만들기' 탭 구성: (제목, 켜기 키, [(키, 이름, 최소, 최대, 간격)])
SECTIONS = [
    ("테두리", "h", [("t", "두께", 1, 6, 1), ("o", "불투명도", 0, 1, 0.01)]),
    ("중앙 점", "d", [("z", "두께", 1, 6, 1), ("a", "불투명도", 0, 1, 0.01)]),
    ("안쪽 선", "0b", [("0l", "길이", 0, 20, 1), ("0t", "두께", 0, 10, 1),
                      ("0o", "간격", 0, 20, 1), ("0a", "불투명도", 0, 1, 0.01)]),
    ("바깥 선", "1b", [("1l", "길이", 0, 20, 1), ("1t", "두께", 0, 10, 1),
                      ("1o", "간격", 0, 40, 1), ("1a", "불투명도", 0, 1, 0.01)]),
]


class App:
    PREVIEW = 220
    PREVIEW_BG = (70, 76, 82)
    DRAW_BG = (43, 47, 51)
    CELL = 9  # 그리기 칸 한 칸 크기(px)

    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = root
        self.overlay = Overlay() if IS_WINDOWS else None
        self.f8_down = False
        self.loading = False
        self.save_job = None

        settings = load_settings()
        try:
            self.cfg = parse_code(settings.get("code", EXAMPLE_CODE))
        except ValueError:
            self.cfg = parse_code(EXAMPLE_CODE)
        self.pixels = {}
        for key, value in settings.get("pixels", {}).items():
            try:
                x, y = map(int, key.split(","))
                if not (0 <= x < GRID and 0 <= y < GRID):
                    continue
                self.pixels[(x, y)] = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4, 6))
            except ValueError:
                continue
        self.brush_rgb = (255, 0, 0)

        self.font = ("Malgun Gothic", 10)
        self.bold = ("Malgun Gothic", 11, "bold")
        root.title("발로란트 조준선 오버레이")
        root.resizable(False, False)
        root.configure(padx=12, pady=10)

        left = tk.Frame(root)
        left.grid(row=0, column=0, sticky="n")
        right = tk.Frame(root)
        right.grid(row=0, column=1, sticky="n", padx=(12, 0))

        self.tabs = ttk.Notebook(left)
        self.tabs.pack()
        make_tab = tk.Frame(self.tabs, padx=8, pady=8)
        draw_tab = tk.Frame(self.tabs, padx=8, pady=8)
        self.tabs.add(make_tab, text="  ⚙ 만들기  ")
        self.tabs.add(draw_tab, text="  ✏ 그리기  ")
        self.build_make_tab(make_tab)
        self.build_draw_tab(draw_tab)

        tk.Label(right, text="미리보기", font=self.bold).pack(anchor="w")
        self.canvas = tk.Canvas(right, width=self.PREVIEW, height=self.PREVIEW,
                                bg="#%02x%02x%02x" % self.PREVIEW_BG, highlightthickness=0)
        self.canvas.pack(pady=(4, 8))
        self.show_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="조준선 표시  (F8 로 켜기/끄기)", font=self.font,
                       variable=self.show_var, command=self.update_visible).pack(anchor="w")
        size_row = tk.Frame(right)
        size_row.pack(fill="x")
        tk.Label(size_row, text="크기", font=self.font).pack(side="left")
        self.scale_var = tk.DoubleVar(value=settings.get("scale", 1.0))
        tk.Scale(size_row, from_=0.5, to=3.0, resolution=0.1, orient="horizontal",
                 variable=self.scale_var, length=180,
                 command=lambda v: self.redraw()).pack(side="left", padx=6)
        self.status = tk.Label(right, text="", font=self.font, wraplength=self.PREVIEW,
                               justify="left")
        self.status.pack(anchor="w", pady=(6, 0))
        tip = ("※ 지금 보고 있는 탭의 조준선이 화면에 나와요.\n\n"
               "※ 발로란트 설정 > 비디오 > 화면 모드를 '창 전체화면'으로 해야 "
               "게임 위에 보여요. (전체화면 모드에선 가려짐)")
        if not IS_WINDOWS:
            tip = "※ Windows 가 아니라서 미리보기만 동작해요."
        tk.Label(right, text=tip, font=(self.font[0], 9), fg="#777", justify="left",
                 wraplength=self.PREVIEW).pack(anchor="w", pady=(6, 0))

        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.tabs.select(1 if settings.get("mode") == "draw" else 0)
        self.mode = "draw" if settings.get("mode") == "draw" else "make"
        self.tabs.bind("<<NotebookTabChanged>>", self.on_tab)
        self.load_vars()
        self.redraw()
        if self.overlay:
            self.tick_hotkey()
            self.tick_top()

    # ------------------------------------------------ 만들기 탭

    def color_button(self, parent, hex_color, command):
        b = self.tk.Label(parent, bg="#" + hex_color, width=2, relief="raised", bd=2,
                          cursor="hand2")
        b.bind("<Button-1>", lambda e: command(hex_color))
        b.pack(side="left", padx=1)

    def build_make_tab(self, f):
        tk = self.tk
        tk.Label(f, text="조준선 코드", font=self.bold).pack(anchor="w")
        row = tk.Frame(f)
        row.pack(fill="x", pady=(2, 4))
        self.code_var = tk.StringVar(value=make_code(self.cfg))
        entry = tk.Entry(row, textvariable=self.code_var, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=3)
        entry.bind("<Return>", lambda e: self.apply_code())
        tk.Button(row, text="적용", command=self.apply_code).pack(side="left", padx=(4, 0))
        btns = tk.Frame(f)
        btns.pack(fill="x")
        tk.Button(btns, text="📋 복사한 코드 붙여넣기", font=self.font,
                  command=self.paste_and_apply).pack(side="left", expand=True, fill="x")
        tk.Button(btns, text="📄 코드 복사 (게임에 넣기)", font=self.font,
                  command=self.copy_code).pack(side="left", expand=True, fill="x", padx=(4, 0))

        tk.Label(f, text="색상", font=self.bold).pack(anchor="w", pady=(10, 2))
        colors = tk.Frame(f)
        colors.pack(anchor="w")
        for hex_color in COLORS:
            self.color_button(colors, hex_color, self.set_color)
        tk.Button(colors, text="🎨 직접 고르기", font=self.font,
                  command=lambda: self.ask_color(self.cfg["rgb"], self.set_color)
                  ).pack(side="left", padx=(8, 0))
        self.swatch = tk.Label(colors, width=3, relief="sunken", bd=2)
        self.swatch.pack(side="left", padx=6)

        grid = tk.Frame(f)
        grid.pack(fill="x", pady=(8, 0))
        self.vars = {}
        for n, (title, on_key, sliders) in enumerate(SECTIONS):
            box = tk.LabelFrame(grid, text=title, font=self.font, padx=6, pady=2)
            box.grid(row=n // 2, column=n % 2, sticky="nsew", padx=3, pady=3)
            self.vars[on_key] = tk.BooleanVar()
            tk.Checkbutton(box, text="켜기", font=self.font, variable=self.vars[on_key],
                           command=self.on_builder).pack(anchor="w")
            for key, name, lo, hi, step in sliders:
                r = tk.Frame(box)
                r.pack(fill="x")
                tk.Label(r, text=name, width=6, anchor="w", font=self.font).pack(side="left")
                self.vars[key] = tk.DoubleVar()
                tk.Scale(r, from_=lo, to=hi, resolution=step, orient="horizontal",
                         variable=self.vars[key], length=130,
                         command=lambda v: self.on_builder()).pack(side="left")

    def load_vars(self):
        """설정 -> 만들기 탭 버튼/슬라이더"""
        self.loading = True
        for key, var in self.vars.items():
            var.set(bool(self.cfg[key]) if isinstance(var, self.tk.BooleanVar) else self.cfg[key])
        self.swatch.configure(bg="#%02x%02x%02x" % self.cfg["rgb"])
        self.loading = False

    def on_builder(self):
        """만들기 탭에서 뭔가 바꿀 때마다 바로 반영"""
        if self.loading:
            return
        for key, var in self.vars.items():
            self.cfg[key] = float(var.get())
        self.code_var.set(make_code(self.cfg))
        self.redraw()

    def set_color(self, hex_color):
        self.cfg["rgb"] = tuple(int(hex_color[k:k + 2], 16) for k in (0, 2, 4))
        self.swatch.configure(bg="#" + hex_color)
        self.code_var.set(make_code(self.cfg))
        self.redraw()

    def ask_color(self, current, command):
        from tkinter import colorchooser

        picked = colorchooser.askcolor(color="#%02x%02x%02x" % current, parent=self.root)
        if picked and picked[1]:
            command(picked[1][1:].upper())

    def set_status(self, text, ok=True):
        self.status.configure(text=text, fg="#1a7f37" if ok else "#c62828")

    def paste_and_apply(self):
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            self.set_status("클립보드가 비어 있어요.", ok=False)
            return
        self.code_var.set(text.strip())
        self.apply_code()

    def apply_code(self):
        try:
            self.cfg = parse_code(self.code_var.get())
        except ValueError as e:
            self.set_status(str(e), ok=False)
            return
        self.load_vars()
        self.redraw()
        self.set_status("✔ 적용됐어요! 화면 가운데를 확인하세요.")

    def copy_code(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(make_code(self.cfg))
        self.set_status("✔ 코드를 복사했어요. 발로란트 설정 > 조준선 > 가져오기(Import)에 "
                        "붙여넣으면 게임에도 똑같이 적용돼요.")

    # ------------------------------------------------ 그리기 탭

    def build_draw_tab(self, f):
        tk = self.tk
        top = tk.Frame(f)
        top.pack(fill="x")
        tk.Label(top, text="색", font=self.bold).pack(side="left", padx=(0, 4))
        for hex_color in COLORS + ["000000"]:
            self.color_button(top, hex_color, self.set_brush)
        tk.Button(top, text="🎨", command=lambda: self.ask_color(self.brush_rgb, self.set_brush)
                  ).pack(side="left", padx=(6, 0))
        self.brush_swatch = tk.Label(top, width=3, relief="sunken", bd=2,
                                     bg="#%02x%02x%02x" % self.brush_rgb)
        self.brush_swatch.pack(side="left", padx=6)

        opts = tk.Frame(f)
        opts.pack(fill="x", pady=(4, 0))
        tk.Label(opts, text="불투명도", font=self.font).pack(side="left")
        self.brush_alpha = tk.DoubleVar(value=1.0)
        tk.Scale(opts, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
                 variable=self.brush_alpha, length=110).pack(side="left", padx=(4, 12))
        tk.Label(opts, text="대칭", font=self.font).pack(side="left")
        self.sym_var = tk.StringVar(value="8")
        for value, text in (("1", "없음"), ("4", "4방향"), ("8", "+ 모양")):
            tk.Radiobutton(opts, text=text, value=value, variable=self.sym_var,
                           font=self.font).pack(side="left")

        size = GRID * self.CELL
        self.board = tk.Canvas(f, width=size, height=size, highlightthickness=1,
                               highlightbackground="#555", cursor="crosshair",
                               bg="#%02x%02x%02x" % self.DRAW_BG)
        self.board.pack(pady=6)
        center = (GRID // 2 - 1, GRID // 2)
        self.cells = {}
        for y in range(GRID):
            for x in range(GRID):
                line = "#596068" if x in center and y in center else (
                    "#41474d" if x in center or y in center else "#363b40")
                self.cells[(x, y)] = self.board.create_rectangle(
                    x * self.CELL, y * self.CELL, (x + 1) * self.CELL, (y + 1) * self.CELL,
                    outline=line)
        self.refresh_board()
        for seq, erase in (("<Button-1>", False), ("<B1-Motion>", False),
                           ("<Button-3>", True), ("<B3-Motion>", True)):
            self.board.bind(seq, lambda e, er=erase: self.paint(e, er))

        tk.Label(f, text="왼쪽 클릭: 그리기   오른쪽 클릭: 지우기   (가운데 4칸 사이 = 화면 정중앙)",
                 font=(self.font[0], 9), fg="#777").pack()
        btns = tk.Frame(f)
        btns.pack(fill="x", pady=(4, 0))
        tk.Button(btns, text="🗑 전체 지우기", font=self.font,
                  command=self.clear_drawing).pack(side="left", expand=True, fill="x")
        tk.Button(btns, text="⬇ '만들기' 조준선 가져오기", font=self.font,
                  command=self.import_made).pack(side="left", expand=True, fill="x", padx=(4, 0))
        tk.Button(f, text="🔁 이 그림을 발로란트 코드로 바꾸기", font=self.bold,
                  command=self.drawing_to_code).pack(fill="x", pady=(4, 0))

    def set_brush(self, hex_color):
        self.brush_rgb = tuple(int(hex_color[k:k + 2], 16) for k in (0, 2, 4))
        self.brush_swatch.configure(bg="#" + hex_color)

    def blend(self, rgba, bg):
        a = rgba[3] / 255
        return "#%02x%02x%02x" % tuple(round(rgba[k] * a + bg[k] * (1 - a)) for k in range(3))

    def refresh_board(self, cells=None):
        for p in cells or self.cells:
            rgba = self.pixels.get(p)
            fill = self.blend(rgba, self.DRAW_BG) if rgba else ""
            self.board.itemconfigure(self.cells[p], fill=fill)

    def paint(self, event, erase):
        x, y = event.x // self.CELL, event.y // self.CELL
        if not (0 <= x < GRID and 0 <= y < GRID):
            return
        m = GRID - 1
        targets = {(x, y)}
        if self.sym_var.get() in ("4", "8"):
            targets |= {(m - x, y), (x, m - y), (m - x, m - y)}
        if self.sym_var.get() == "8":
            targets |= {(b, a) for a, b in targets}
        rgba = (*self.brush_rgb, round(self.brush_alpha.get() * 255))
        changed = False
        for p in targets:
            if erase:
                changed |= self.pixels.pop(p, None) is not None
            elif self.pixels.get(p) != rgba:
                self.pixels[p] = rgba
                changed = True
        if changed:
            self.refresh_board(targets)
            self.redraw()
            self.set_status("")

    def clear_drawing(self):
        from tkinter import messagebox

        if self.pixels and messagebox.askyesno("전체 지우기", "그린 그림을 모두 지울까요?",
                                               parent=self.root):
            self.pixels.clear()
            self.refresh_board()
            self.redraw()

    def import_made(self):
        """'만들기' 탭의 조준선을 그리기 칸으로 옮겨서 고쳐 그릴 수 있게"""
        from tkinter import messagebox

        if self.pixels and not messagebox.askyesno(
                "가져오기", "지금 그린 그림을 지우고 '만들기' 조준선을 가져올까요?", parent=self.root):
            return
        side, rgba = render(self.cfg, 1.0)
        shift = GRID // 2 - side // 2
        self.pixels.clear()
        for y in range(side):
            for x in range(side):
                i = (y * side + x) * 4
                gx, gy = x + shift, y + shift
                if rgba[i + 3] and 0 <= gx < GRID and 0 <= gy < GRID:
                    self.pixels[(gx, gy)] = tuple(rgba[i:i + 4])
        self.refresh_board()
        self.redraw()
        self.set_status("✔ 가져왔어요. 이제 마음대로 고쳐 그려 보세요.")

    def drawing_to_code(self):
        """그린 그림과 가장 비슷한 발로란트 조준선을 찾아서 코드로"""
        if not self.pixels:
            self.set_status("먼저 그림을 그려 주세요.", ok=False)
            return
        self.set_status("바꾸는 중...")
        self.root.update_idletasks()
        self.cfg, match = pixels_to_cfg(self.pixels)
        code = make_code(self.cfg)
        self.code_var.set(code)
        self.load_vars()
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.tabs.select(0)
        self.on_tab()
        paste = "코드도 복사해 뒀으니 발로란트 설정 > 조준선 > 가져오기(Import)에 붙여넣으세요."
        if match >= 0.99:
            self.set_status("✔ 똑같이 바꿨어요! " + paste)
        elif match >= 0.8:
            self.set_status("✔ 비슷하게 바꿨어요 (일치 %d%%). " % (match * 100) + paste)
        else:
            self.set_status("⚠ 이 그림은 발로란트 조준선으로 표현하기 어려워서 많이 달라요 "
                            "(일치 %d%%). 그림은 '그리기' 탭에 그대로 있어요." % (match * 100), ok=False)
        return match

    # ------------------------------------------------ 화면 표시

    def on_tab(self, _event=None):
        self.mode = "draw" if self.tabs.index("current") == 1 else "make"
        self.redraw()
        if self.mode == "draw" and not self.pixels:
            self.set_status("칸을 클릭해서 조준선을 그려 보세요.")

    def redraw(self):
        if not hasattr(self, "mode"):
            return  # 아직 창을 만드는 중
        scale = self.scale_var.get()
        if self.mode == "draw":
            side, rgba = render_pixels(self.pixels, scale)
        else:
            side, rgba = render(self.cfg, scale)
        if self.overlay:
            self.overlay.draw(side, rgba)
        self.draw_preview(side, rgba)
        if self.save_job:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(500, self.save_now)

    def save_now(self):
        self.save_job = None
        save_settings({
            "code": make_code(self.cfg),
            "scale": self.scale_var.get(),
            "mode": self.mode,
            "pixels": {"%d,%d" % p: "%02X%02X%02X%02X" % c for p, c in self.pixels.items()},
        })

    def draw_preview(self, side, rgba):
        # 회색 배경 위에 합성해서 확대해 보여주기
        rows = []
        for y in range(side):
            row = [self.blend(rgba[(y * side + x) * 4:(y * side + x) * 4 + 4], self.PREVIEW_BG)
                   for x in range(side)]
            rows.append("{" + " ".join(row) + "}")
        img = self.tk.PhotoImage(width=side, height=side)
        img.put(" ".join(rows))
        zoom = max(1, min(4, self.PREVIEW // side))
        self.preview_img = img.zoom(zoom)
        self.canvas.delete("all")
        self.canvas.create_image(self.PREVIEW // 2, self.PREVIEW // 2, image=self.preview_img)

    def update_visible(self):
        if self.overlay:
            self.overlay.set_visible(self.show_var.get())

    def tick_hotkey(self):
        down = bool(self.overlay.user32.GetAsyncKeyState(0x77) & 0x8000)  # F8
        if down and not self.f8_down:
            self.show_var.set(not self.show_var.get())
            self.update_visible()
        self.f8_down = down
        self.root.after(50, self.tick_hotkey)

    def tick_top(self):
        self.overlay.keep_on_top()  # 게임이 맨 위를 가져가도 다시 올라오게
        self.root.after(1500, self.tick_top)

    def quit(self):
        self.save_now()
        if self.overlay:
            self.overlay.destroy()
        self.root.destroy()


def enable_dpi_awareness():
    """디스플레이 배율(125% 등)에서도 픽셀 단위로 정확하게 그리기."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def selftest():
    """CI 확인용: 만들기/그리기 조준선을 띄우고 화면 중앙에 실제로 그려졌는지 검사."""
    import tkinter as tk

    global SETTINGS_PATH
    SETTINGS_PATH = os.devnull

    for code in [EXAMPLE_CODE, "0", "0;P;c;8;u;FF8800FF;h;1;t;2;o;1;d;1;z;3;0b;0;1b;0",
                 "0;s;1;P;0g;1;0v;9;1b;0;a;0.35;o;0.123"]:
        cfg = parse_code(code)
        assert parse_code(make_code(cfg)) == cfg, (code, make_code(cfg))
    print("code round trip: OK")

    root = tk.Tk()
    app = App(root)

    def pump():
        for _ in range(10):
            root.update()
            time.sleep(0.03)

    def red_at_center():
        if not IS_WINDOWS:
            return None
        try:
            from PIL import ImageGrab
        except ImportError:
            return None
        sw = app.overlay.user32.GetSystemMetrics(0)
        sh = app.overlay.user32.GetSystemMetrics(1)
        shot = ImageGrab.grab(bbox=(sw // 2 - 20, sh // 2 - 20, sw // 2 + 20, sh // 2 + 20))
        px = shot.convert("RGB").tobytes()
        return sum(1 for i in range(0, len(px), 3)
                   if px[i] > 200 and px[i + 1] < 60 and px[i + 2] < 60)

    def check(name, expected):
        pump()
        red = red_at_center()
        print("%s: red pixels at screen center = %s (expected %d)" % (name, red, expected))
        assert red is None or red == expected, name

    # 1) 만들기: 코드로 빨간 + 모양 (팔 4개 x 10x4 = 160칸)
    app.tabs.select(0)
    app.on_tab()
    app.code_var.set("0;P;c;7;h;0;0t;4;0l;10;0o;2;0a;1;1b;0")
    app.apply_code()
    assert app.cfg["rgb"] == (255, 0, 0) and app.vars["0l"].get() == 10
    check("make tab", 160)

    # 2) 그리기: + 모양 대칭으로 한쪽 팔(8칸)만 그리면 두께 2칸짜리 팔 4개 = 64칸
    app.tabs.select(1)
    app.on_tab()

    class Click:
        def __init__(self, x, y):
            self.x, self.y = x * app.CELL + 2, y * app.CELL + 2

    mid = GRID // 2
    app.set_brush("FF0000")
    for x in range(mid + 2, mid + 10):
        app.paint(Click(x, mid), erase=False)
    assert len(app.pixels) == 64, len(app.pixels)
    check("draw tab", 64)
    app.paint(Click(mid + 9, mid), erase=True)  # 끝 칸 지우기 -> 대칭으로 8칸 지워짐
    assert len(app.pixels) == 56, len(app.pixels)
    check("draw tab after erase", 56)

    # 3) 그림 -> 코드: 그린 + 모양이 똑같은 코드로 바뀌어야 함
    match = app.drawing_to_code()
    print("drawing -> code:", app.code_var.get(), "match", match)
    assert match == 1.0 and app.mode == "make", match
    assert root.clipboard_get() == make_code(app.cfg) == make_code(parse_code(root.clipboard_get()))
    check("converted code", 56)

    app.show_var.set(False)
    app.update_visible()
    check("hidden", 0)
    app.quit()
    print("SELFTEST PASSED")


def main():
    if IS_WINDOWS:
        enable_dpi_awareness()
    if "--selftest" in sys.argv:
        selftest()
        return
    import tkinter as tk

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
