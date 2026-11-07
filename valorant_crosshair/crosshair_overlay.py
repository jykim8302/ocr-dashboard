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

import base64
import ctypes
import json
import math
import os
import sys
import time
import zlib

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

# 발로란트에서 고를 수 있는 값의 범위 (이상한 코드가 들어와도 이 안으로 맞춤)
LIMITS = {
    "t": (1, 6), "o": (0, 1), "z": (1, 6), "a": (0, 1),
    "0t": (0, 10), "0l": (0, 20), "0v": (0, 20), "0o": (0, 20), "0a": (0, 1),
    "1t": (0, 10), "1l": (0, 20), "1v": (0, 20), "1o": (0, 40), "1a": (0, 1),
}

EXAMPLE_CODE = "0;P;c;5;h;0;f;0;0l;4;0o;2;0a;1;0f;0;1b;0"

APP_TITLE = "발로란트 조준선 오버레이"
OVERLAY_CLASS = "ValorantCrosshairOverlay"

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
            if not math.isfinite(cfg[key]):
                raise ValueError
            if key in LIMITS:
                lo, hi = LIMITS[key]
                cfg[key] = min(max(cfg[key], lo), hi)
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


SS = 4          # 그린 그림은 그리기 칸 한 칸을 SS x SS 로 잘게 나눠 저장 (부드러운 선/도형용)
HI = GRID * SS  # 저장하는 그림 한 변 크기


def raster_set_cell(raster, x, y, rgba):
    """그리기 칸 (x, y) 하나를 rgba 로 채우기"""
    row = bytes(rgba) * SS
    for yy in range(y * SS, (y + 1) * SS):
        i = (yy * HI + x * SS) * 4
        raster[i:i + len(row)] = row


def _content_box(raster):
    """그림이 있는 범위 (x0, y0, x1, y1), 비어 있으면 None"""
    x0, x1, rows = HI, 0, []
    for y in range(HI):
        alpha = raster[y * HI * 4 + 3:(y + 1) * HI * 4:4]
        if alpha.strip(b"\0"):
            rows.append(y)
            x0 = min(x0, len(alpha) - len(alpha.lstrip(b"\0")))
            x1 = max(x1, len(alpha.rstrip(b"\0")))
    return (x0, rows[0], x1, rows[-1] + 1) if rows else None


def render_raster(raster, scale=1.0):
    """그린 그림 -> 화면 크기에 맞춘 정사각형 RGBA 이미지 (부드럽게 축소/확대)"""
    side = max(1, round(GRID * scale))
    out = bytearray(side * side * 4)
    box = _content_box(raster)
    if not box:
        return side, out
    f = HI / side  # 출력 한 칸 = 그림 f 칸

    def weights(o):
        a, b = o * f, (o + 1) * f
        return [(s, min(b, s + 1) - max(a, s)) for s in range(int(a), min(HI, math.ceil(b)))
                if min(b, s + 1) > max(a, s)]

    ox0, ox1 = int(box[0] / f), min(side, math.ceil(box[2] / f))
    oy0, oy1 = int(box[1] / f), min(side, math.ceil(box[3] / f))
    wx = {o: weights(o) for o in range(ox0, ox1)}
    for oy in range(oy0, oy1):
        wy = weights(oy)
        for ox in range(ox0, ox1):
            sa = sr = sg = sb = tw = 0.0
            for sy, w1 in wy:
                row = sy * HI
                for sx, w2 in wx[ox]:
                    w = w1 * w2
                    tw += w
                    i = (row + sx) * 4
                    a = raster[i + 3]
                    if a:
                        wa = w * a
                        sa += wa
                        sr += raster[i] * wa
                        sg += raster[i + 1] * wa
                        sb += raster[i + 2] * wa
            if sa:
                i = (oy * side + ox) * 4
                out[i:i + 4] = bytes((round(sr / sa), round(sg / sa), round(sb / sa),
                                      min(255, round(sa / tw))))
    return side, out


def raster_to_pixels(raster):
    """그린 그림 -> 그리기 칸 {(x, y): (r, g, b, a)} (반 이상 칠해진 칸만)"""
    side, rgba = render_raster(raster, 1.0)
    return {(i // 4 % side, i // 4 // side): tuple(rgba[i:i + 4])
            for i in range(0, len(rgba), 4) if rgba[i + 3] >= 128}


def shape_distance(kind, ax, ay, bx, by):
    """도형 경계까지의 거리 함수 (안쪽은 음수). 좌표는 그림(HI) 단위"""
    if kind == "line":
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy

        def dist(px, py):
            t = ((px - ax) * dx + (py - ay) * dy) / l2 if l2 else 0.0
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            return math.hypot(px - ax - t * dx, py - ay - t * dy)
        return dist
    cx, cy = (ax + bx) / 2, (ay + by) / 2
    hx, hy = max(abs(bx - ax) / 2, 0.5), max(abs(by - ay) / 2, 0.5)
    if kind == "rect":
        def dist(px, py):
            qx, qy = abs(px - cx) - hx, abs(py - cy) - hy
            return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0)
        return dist

    def dist(px, py):  # 타원
        nx, ny = (px - cx) / hx, (py - cy) / hy
        grad = 2 * math.hypot(nx / hx, ny / hy)
        return (nx * nx + ny * ny - 1) / grad if grad else -min(hx, hy)
    return dist


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
        u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        u.DefWindowProcW.restype = ctypes.c_ssize_t
        u.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
        u.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
        kernel32.GetModuleHandleW.restype = w.HMODULE
        hinst = kernel32.GetModuleHandleW(None)

        if not Overlay._wndproc:  # 창 종류 등록 (프로그램마다 한 번)
            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC),
                            ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                            ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                            ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                            ("lpszClassName", w.LPCWSTR)]

            def wndproc(hwnd, msg, wparam, lparam):
                if msg == 0x0312:  # WM_HOTKEY: F8 눌림 (게임 화면에서도 옴)
                    Overlay.hotkey_hits += 1
                    return 0
                return u.DefWindowProcW(hwnd, msg, wparam, lparam)

            Overlay._wndproc = WNDPROC(wndproc)
            wc = WNDCLASSW(lpfnWndProc=Overlay._wndproc, hInstance=hinst,
                           lpszClassName=OVERLAY_CLASS)
            u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
            if not u.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())

        ex_style = (0x00080000    # WS_EX_LAYERED     : 투명도
                    | 0x00000020  # WS_EX_TRANSPARENT : 클릭 통과
                    | 0x00000008  # WS_EX_TOPMOST     : 항상 위
                    | 0x00000080  # WS_EX_TOOLWINDOW  : 작업표시줄/Alt+Tab 에 안 보이게
                    | 0x08000000) # WS_EX_NOACTIVATE  : 포커스 안 뺏기
        self.hwnd = u.CreateWindowExW(ex_style, OVERLAY_CLASS, "Crosshair Overlay", 0x80000000,
                                      0, 0, 1, 1, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.visible = True
        # F8 을 윈도우 단축키로 등록 (게임이 관리자 권한이어도 동작). 다른 프로그램이 이미
        # F8 을 쓰고 있으면 실패 -> 키 상태를 직접 읽는 방식으로 대신함
        self.hotkey = bool(u.RegisterHotKey(self.hwnd, 1, 0x4000, 0x77))  # MOD_NOREPEAT, F8

    _wndproc = None
    hotkey_hits = 0

    def take_hotkey(self):
        """지난번 확인 뒤로 F8 이 눌렸는지"""
        hit, Overlay.hotkey_hits = Overlay.hotkey_hits > 0, 0
        return hit

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
        if self.hotkey:
            self.user32.UnregisterHotKey(self.hwnd, 1)
        self.user32.DestroyWindow(self.hwnd)


def close_other_instances():
    """이미 켜져 있는 이 프로그램(과 그 조준선)을 닫기. 두 번 실행하면 조준선이 두 개 떠서
    하나를 꺼도 다른 하나가 남는 문제를 막음"""
    from ctypes import wintypes as w

    u = ctypes.WinDLL("user32")
    u.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
    u.FindWindowW.restype = w.HWND
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    for _ in range(50):  # 최대 5초 기다림
        found = [h for h in (u.FindWindowW(None, APP_TITLE),
                             u.FindWindowW(OVERLAY_CLASS, None),
                             u.FindWindowW("Static", "Crosshair Overlay"))  # 예전 버전 조준선
                 if h]
        if not found:
            return
        for h in found:
            u.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
        time.sleep(0.1)


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
    CELL = 8  # 그리기 칸 한 칸 크기(px)

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
        self.raster = bytearray(HI * HI * 4)  # 그린 그림 (RGBA, 한 칸 = SS x SS)
        try:
            data = zlib.decompress(base64.b64decode(settings.get("drawing", "")))
            if len(data) == len(self.raster):
                self.raster[:] = data
        except (ValueError, zlib.error):
            pass
        for key, value in settings.get("pixels", {}).items():  # 예전 버전에서 그린 그림
            try:
                x, y = map(int, key.split(","))
                if 0 <= x < GRID and 0 <= y < GRID and "drawing" not in settings:
                    raster_set_cell(self.raster, x, y, bytes.fromhex(value))
            except ValueError:
                continue
        self.undo_stack = []
        self.stroke = None
        self.redraw_job = None
        self.brush_rgb = (255, 0, 0)

        self.font = ("Malgun Gothic", 10)
        self.bold = ("Malgun Gothic", 11, "bold")
        root.title(APP_TITLE)
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

    TOOLS = (("pixel", "▦ 픽셀"), ("brush", "🖌 붓"), ("line", "╱ 직선"),
             ("rect", "▭ 사각형"), ("ellipse", "◯ 원"))
    HINTS = {
        "pixel": "왼쪽 클릭: 칸 칠하기   오른쪽 클릭: 지우기",
        "brush": "왼쪽 드래그: 그리기   오른쪽 드래그: 지우개",
        "shape": "드래그해서 크기 정하기 (Shift: 반듯하게)   오른쪽 드래그: 그 모양으로 지우기",
    }

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

        tools = tk.Frame(f)
        tools.pack(fill="x", pady=(4, 0))
        tk.Label(tools, text="도구", font=self.font).pack(side="left")
        self.tool_var = tk.StringVar(value="pixel")
        for value, text in self.TOOLS:
            tk.Radiobutton(tools, text=text, value=value, variable=self.tool_var, font=self.font,
                           indicatoron=False, padx=4, command=self.on_tool
                           ).pack(side="left", padx=1)

        opts = tk.Frame(f)
        opts.pack(fill="x")
        tk.Label(opts, text="굵기", font=self.font).pack(side="left")
        self.width_var = tk.DoubleVar(value=2.0)
        self.width_scale = tk.Scale(opts, from_=0.5, to=8, resolution=0.5, orient="horizontal",
                                    variable=self.width_var, length=90)
        self.width_scale.pack(side="left", padx=(2, 6))
        self.fill_var = tk.BooleanVar(value=False)
        self.fill_check = tk.Checkbutton(opts, text="채우기", font=self.font, variable=self.fill_var)
        self.fill_check.pack(side="left")
        tk.Label(opts, text="불투명도", font=self.font).pack(side="left", padx=(6, 0))
        self.brush_alpha = tk.DoubleVar(value=1.0)
        tk.Scale(opts, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
                 variable=self.brush_alpha, length=90).pack(side="left", padx=2)

        sym = tk.Frame(f)
        sym.pack(fill="x")
        tk.Label(sym, text="대칭", font=self.font).pack(side="left")
        self.sym_var = tk.StringVar(value="8")
        for value, text in (("1", "없음"), ("4", "4방향"), ("8", "+ 모양")):
            tk.Radiobutton(sym, text=text, value=value, variable=self.sym_var,
                           font=self.font).pack(side="left")

        size = GRID * self.CELL
        self.board = tk.Canvas(f, width=size, height=size, highlightthickness=1,
                               highlightbackground="#555", cursor="arrow",  # 윈도우 기본 포인터
                               bg="#%02x%02x%02x" % self.DRAW_BG)
        self.board.pack(pady=6)
        self.board_img = tk.PhotoImage(width=size, height=size)
        self.board.create_image(0, 0, image=self.board_img, anchor="nw")
        for i in range(GRID + 1):  # 칸 선 (가운데 십자선 = 화면 정중앙)
            p = i * self.CELL
            tag, color = ("center", "#6a7178") if i == GRID // 2 else ("grid", "#363b40")
            self.board.create_line(p, 0, p, size, fill=color, tags=tag)
            self.board.create_line(0, p, size, p, fill=color, tags=tag)
        self.ring = self.board.create_oval(0, 0, 0, 0, outline="#bbbbbb", state="hidden")
        self.refresh_board()
        for button, erase in (("1", False), ("3", True)):
            self.board.bind("<Button-%s>" % button, lambda e, er=erase: self.stroke_start(e, er))
            self.board.bind("<B%s-Motion>" % button, self.stroke_move)
            self.board.bind("<ButtonRelease-%s>" % button, self.stroke_end)
        self.board.bind("<Motion>", self.move_ring)
        self.board.bind("<Leave>", lambda e: self.board.itemconfigure(self.ring, state="hidden"))
        self.root.bind("<Control-z>", lambda e: self.undo())

        self.hint = tk.Label(f, text="", font=(self.font[0], 9), fg="#777")
        self.hint.pack()
        btns = tk.Frame(f)
        btns.pack(fill="x", pady=(4, 0))
        tk.Button(btns, text="↶ 되돌리기", font=self.font,
                  command=self.undo).pack(side="left", expand=True, fill="x")
        tk.Button(btns, text="🗑 전체 지우기", font=self.font,
                  command=self.clear_drawing).pack(side="left", expand=True, fill="x", padx=4)
        tk.Button(btns, text="⊕ 가운데로", font=self.font,
                  command=self.center_drawing).pack(side="left", expand=True, fill="x")
        tk.Button(f, text="⬇ '만들기' 조준선 가져오기", font=self.font,
                  command=self.import_made).pack(fill="x", pady=(4, 0))
        tk.Button(f, text="🔁 이 그림을 발로란트 코드로 바꾸기", font=self.bold,
                  command=self.drawing_to_code).pack(fill="x", pady=(4, 0))
        self.on_tool()

    def on_tool(self):
        tool = self.tool_var.get()
        self.board.itemconfigure("grid", state="normal" if tool == "pixel" else "hidden")
        self.width_scale.configure(state="disabled" if tool == "pixel" else "normal")
        self.fill_check.configure(state="normal" if tool in ("rect", "ellipse") else "disabled")
        self.hint.configure(text=self.HINTS.get(tool, self.HINTS["shape"]))
        self.board.itemconfigure(self.ring, state="hidden")

    def set_brush(self, hex_color):
        self.brush_rgb = tuple(int(hex_color[k:k + 2], 16) for k in (0, 2, 4))
        self.brush_swatch.configure(bg="#" + hex_color)

    def blend(self, rgba, bg):
        a = rgba[3] / 255
        return "#%02x%02x%02x" % tuple(round(rgba[k] * a + bg[k] * (1 - a)) for k in range(3))

    def refresh_board(self, box=None):
        """그림(box 범위, 그림 단위)을 그리기 판에 다시 그리기"""
        x0, y0, x1, y1 = box or (0, 0, HI, HI)
        zoom = self.CELL // SS
        empty = "#%02x%02x%02x" % self.DRAW_BG
        rows = []
        for y in range(y0, y1):
            row = []
            for x in range(x0, x1):
                i = (y * HI + x) * 4
                color = self.blend(self.raster[i:i + 4], self.DRAW_BG) if self.raster[i + 3] else empty
                row += [color] * zoom
            rows += ["{" + " ".join(row) + "}"] * zoom
        if rows:
            self.board_img.put(" ".join(rows), to=(x0 * zoom, y0 * zoom))

    def has_drawing(self):
        return any(self.raster[3::4])

    def mirrors(self, m):
        """대칭 설정에 맞는 좌표 변환 목록 (m = 반대편 끝 좌표)"""
        fs = [lambda x, y: (x, y)]
        if self.sym_var.get() in ("4", "8"):
            fs += [lambda x, y: (m - x, y), lambda x, y: (x, m - y), lambda x, y: (m - x, m - y)]
        if self.sym_var.get() == "8":
            fs += [lambda x, y, f=f: f(y, x) for f in list(fs)]
        return fs

    def move_ring(self, event):
        """붓 크기만큼 동그라미를 마우스 따라 보여주기"""
        if self.tool_var.get() != "brush":
            return
        r = self.width_var.get() * self.CELL / 2
        self.board.coords(self.ring, event.x - r, event.y - r, event.x + r, event.y + r)
        self.board.itemconfigure(self.ring, state="normal")

    # 한 번 누르고 뗄 때까지 = 한 획. 시작할 때 그림을 저장해 두고 그 위에 그려서
    # 같은 획 안에서 겹친 곳이 진해지지 않게 (그림판과 같은 방식)
    def stroke_start(self, event, erase):
        self.push_undo()
        self.stroke = {"erase": erase, "base": bytes(self.raster), "cov": bytearray(HI * HI),
                       "start": (event.x / self.CELL, event.y / self.CELL), "last": None,
                       "box": None}
        self.stroke_move(event)

    def stroke_move(self, event):
        s = getattr(self, "stroke", None)
        if not s:
            return
        self.move_ring(event)
        tool = self.tool_var.get()
        p = (event.x / self.CELL, event.y / self.CELL)
        if tool == "pixel":
            box = self.paint_cells(p)
        elif tool == "brush":
            q = s["last"] or p
            r = self.width_var.get() * SS / 2
            box = None
            for f in self.mirrors(GRID):
                (ax, ay), (bx, by) = f(*q), f(*p)
                box = self.union(box, self.stamp(
                    shape_distance("line", ax * SS, ay * SS, bx * SS, by * SS), r,
                    (min(ax, bx) * SS, min(ay, by) * SS, max(ax, bx) * SS, max(ay, by) * SS)))
        else:
            if event.state & 0x0001:  # Shift: 정사각형 / 정원 / 반듯한 선
                p = self.snap(s["start"], p, tool)
            box = self.draw_shape(tool, s["start"], p)
        s["last"] = p
        if box:
            self.refresh_board(box)
            self.request_redraw()
            self.set_status("")

    def stroke_end(self, _event=None):
        s = getattr(self, "stroke", None)
        self.stroke = None
        if s and self.raster == s["base"] and self.undo_stack:
            self.undo_stack.pop()  # 아무것도 안 바뀐 획은 되돌리기 목록에서 빼기
        self.redraw()

    @staticmethod
    def union(a, b):
        if not a or not b:
            return a or b
        return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])

    @staticmethod
    def snap(start, p, tool):
        dx, dy = p[0] - start[0], p[1] - start[1]
        if tool == "line":  # 가로/세로/대각선으로
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            d = math.hypot(dx, dy)
            return start[0] + d * math.cos(ang), start[1] + d * math.sin(ang)
        d = max(abs(dx), abs(dy))
        return start[0] + math.copysign(d, dx), start[1] + math.copysign(d, dy)

    def paint_cells(self, p):
        """픽셀 도구: 칸 단위로 칠하기 (빠르게 움직여도 빈틈 없게 사이 칸도 칠함)"""
        s = self.stroke
        cur = (math.floor(p[0]), math.floor(p[1]))
        last = s["last"] and (math.floor(s["last"][0]), math.floor(s["last"][1])) or cur
        steps = max(abs(cur[0] - last[0]), abs(cur[1] - last[1]), 1)
        rgba = (0, 0, 0, 0) if s["erase"] else (*self.brush_rgb, round(self.brush_alpha.get() * 255))
        box = None
        for k in range(steps + 1):
            x = round(last[0] + (cur[0] - last[0]) * k / steps)
            y = round(last[1] + (cur[1] - last[1]) * k / steps)
            for f in self.mirrors(GRID - 1):
                cx, cy = f(x, y)
                if 0 <= cx < GRID and 0 <= cy < GRID:
                    raster_set_cell(self.raster, cx, cy, rgba)
                    box = self.union(box, (cx * SS, cy * SS, (cx + 1) * SS, (cy + 1) * SS))
        return box

    def draw_shape(self, tool, a, b):
        """도형 도구: 획 시작 그림으로 되돌린 뒤 지금 크기로 다시 그리기"""
        s = self.stroke
        old = s["box"]
        if old:
            x0, y0, x1, y1 = old
            for y in range(y0, y1):
                i, j = (y * HI + x0) * 4, (y * HI + x1) * 4
                self.raster[i:j] = s["base"][i:j]
                s["cov"][y * HI + x0:y * HI + x1] = bytes(x1 - x0)
        half = self.width_var.get() * SS / 2
        filled = self.fill_var.get() and tool != "line"
        box = None
        for f in self.mirrors(GRID):
            (ax, ay), (bx, by) = f(*a), f(*b)
            dist = shape_distance(tool, ax * SS, ay * SS, bx * SS, by * SS)
            if filled:
                cover = dist
            elif tool == "line":
                cover = lambda px, py, d=dist: d(px, py) - half
            else:
                cover = lambda px, py, d=dist: abs(d(px, py)) - half
            box = self.union(box, self.stamp(cover, 0, (min(ax, bx) * SS, min(ay, by) * SS,
                                                       max(ax, bx) * SS, max(ay, by) * SS),
                                             pad=half))
        s["box"] = box
        return self.union(old, box)

    def stamp(self, dist, r, bounds, pad=None):
        """거리 함수 dist 로 정한 모양을 부드러운 가장자리로 칠하기 (r = 붓 반지름)"""
        s = self.stroke
        base, cov, raster = s["base"], s["cov"], self.raster
        pad = r if pad is None else pad
        x0, y0 = max(0, int(bounds[0] - pad - 1)), max(0, int(bounds[1] - pad - 1))
        x1, y1 = min(HI, int(bounds[2] + pad + 2)), min(HI, int(bounds[3] + pad + 2))
        if x0 >= x1 or y0 >= y1:
            return None
        cr, cg, cb = self.brush_rgb
        ca = self.brush_alpha.get()
        erase = s["erase"]
        for y in range(y0, y1):
            for x in range(x0, x1):
                c = r + 0.5 - dist(x + 0.5, y + 0.5)
                if c <= 0:
                    continue
                c = 255 if c >= 1 else int(c * 255)
                k = y * HI + x
                if c <= cov[k]:
                    continue
                cov[k] = c
                i = k * 4
                ba = base[i + 3]
                if erase:
                    raster[i:i + 4] = bytes((base[i], base[i + 1], base[i + 2], ba * (255 - c) // 255))
                    continue
                sa = ca * c / 255
                fa = ba / 255 * (1 - sa)
                oa = sa + fa
                raster[i:i + 4] = bytes((round((cr * sa + base[i] * fa) / oa),
                                         round((cg * sa + base[i + 1] * fa) / oa),
                                         round((cb * sa + base[i + 2] * fa) / oa),
                                         round(oa * 255)))
        return x0, y0, x1, y1

    def push_undo(self):
        self.undo_stack.append(bytes(self.raster))
        del self.undo_stack[:-30]

    def undo(self):
        if self.mode != "draw":
            return
        if not self.undo_stack:
            self.set_status("더 되돌릴 게 없어요.", ok=False)
            return
        self.raster[:] = self.undo_stack.pop()
        self.refresh_board()
        self.redraw()

    def request_redraw(self):
        """그리는 중에는 화면/미리보기를 조금씩 모아서 갱신 (버벅임 방지)"""
        if not self.redraw_job:
            self.redraw_job = self.root.after(40, self.redraw)

    def clear_drawing(self):
        from tkinter import messagebox

        if self.has_drawing() and messagebox.askyesno("전체 지우기", "그린 그림을 모두 지울까요?",
                                                      parent=self.root):
            self.push_undo()
            self.raster[:] = bytes(len(self.raster))
            self.refresh_board()
            self.redraw()

    def center_drawing(self):
        """그린 그림 전체를 옮겨서 가운데(= 화면 정중앙)에 맞추기"""
        box = _content_box(self.raster)
        if not box:
            self.set_status("먼저 그림을 그려 주세요.", ok=False)
            return
        x0, y0, x1, y1 = box
        # 칸 단위로 옮겨서 픽셀 그림이 흐려지지 않게
        dx = min(max(round((HI - x0 - x1) / 2 / SS) * SS, -x0), HI - x1)
        dy = min(max(round((HI - y0 - y1) / 2 / SS) * SS, -y0), HI - y1)
        if dx == dy == 0:
            self.set_status("✔ 이미 가운데에 있어요.")
            return
        self.push_undo()
        old = bytes(self.raster)
        self.raster[:] = bytes(len(self.raster))
        for y in range(y0, y1):
            row = old[(y * HI + x0) * 4:(y * HI + x1) * 4]
            i = ((y + dy) * HI + x0 + dx) * 4
            self.raster[i:i + len(row)] = row
        self.refresh_board()
        self.redraw()
        self.set_status("✔ 가운데로 옮겼어요.")

    def import_made(self):
        """'만들기' 탭의 조준선을 그리기 칸으로 옮겨서 고쳐 그릴 수 있게"""
        from tkinter import messagebox

        if self.has_drawing() and not messagebox.askyesno(
                "가져오기", "지금 그린 그림을 지우고 '만들기' 조준선을 가져올까요?", parent=self.root):
            return
        self.push_undo()
        side, rgba = render(self.cfg, 1.0)
        shift = GRID // 2 - side // 2
        self.raster[:] = bytes(len(self.raster))
        for y in range(side):
            for x in range(side):
                i = (y * side + x) * 4
                gx, gy = x + shift, y + shift
                if rgba[i + 3] and 0 <= gx < GRID and 0 <= gy < GRID:
                    raster_set_cell(self.raster, gx, gy, rgba[i:i + 4])
        self.refresh_board()
        self.redraw()
        self.set_status("✔ 가져왔어요. 이제 마음대로 고쳐 그려 보세요.")

    def drawing_to_code(self):
        """그린 그림과 가장 비슷한 발로란트 조준선을 찾아서 코드로"""
        pixels = raster_to_pixels(self.raster)
        if not pixels:
            self.set_status("먼저 그림을 그려 주세요.", ok=False)
            return
        self.set_status("바꾸는 중...")
        self.root.update_idletasks()
        self.cfg, match = pixels_to_cfg(pixels)
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
        if self.mode == "draw" and not self.has_drawing():
            self.set_status("판에 조준선을 그려 보세요.")

    def redraw(self):
        if not hasattr(self, "mode"):
            return  # 아직 창을 만드는 중
        if self.redraw_job:
            self.root.after_cancel(self.redraw_job)
            self.redraw_job = None
        scale = self.scale_var.get()
        if self.mode == "draw":
            side, rgba = render_raster(self.raster, scale)
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
            "drawing": base64.b64encode(zlib.compress(bytes(self.raster))).decode(),
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
        if self.overlay.hotkey:
            pressed = self.overlay.take_hotkey()
        else:
            down = bool(self.overlay.user32.GetAsyncKeyState(0x77) & 0x8000)  # F8
            pressed = down and not self.f8_down
            self.f8_down = down
        if pressed:
            self.show_var.set(not self.show_var.get())
            self.update_visible()
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

    # 이상한 숫자: 오류 메시지로 거절하거나 발로란트 범위로 맞추기 (멈추거나 너무 커지면 안 됨)
    for code in ["0;P;0o;inf", "0;P;0o;nan", "0;P;0l;-inf"]:
        try:
            parse_code(code)
            raise AssertionError(code + " should be rejected")
        except ValueError:
            pass
    for code in ["0;P;0l;1e9", "0;P;0o;1e3;1o;1e3;0t;-5", "0;P;t;99;z;99;0a;5"]:
        side, _ = render(parse_code(code), 3.0)
        assert side <= 400, (code, side)
    print("bad numbers: OK")

    if IS_WINDOWS:  # 이미 켜진 프로그램이 있으면 새로 켤 때 닫혀야 함
        import subprocess

        first = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--selftest-child"])
        u = ctypes.WinDLL("user32")
        u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        u.FindWindowW.restype = ctypes.c_void_p
        for _ in range(150):
            if u.FindWindowW(None, APP_TITLE) and u.FindWindowW(OVERLAY_CLASS, None):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("first copy did not start")
        close_other_instances()
        assert first.wait(timeout=10) == 0
        assert not u.FindWindowW(OVERLAY_CLASS, None)
        print("starting again closes the first copy: OK")

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
        check_range(name, expected, expected)

    def check_range(name, lo, hi):
        pump()
        red = red_at_center()
        print("%s: red pixels at screen center = %s (expected %d..%d)" % (name, red, lo, hi))
        assert red is None or lo <= red <= hi, name

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

    class Mouse:  # 그리기 칸 좌표로 마우스 위치 흉내
        def __init__(self, x, y, shift=False):
            self.x, self.y, self.state = x * app.CELL, y * app.CELL, 1 if shift else 0

    def drag(points, erase=False):
        app.stroke_start(Mouse(*points[0]), erase)
        for pt in points[1:]:
            app.stroke_move(Mouse(*pt))
        app.stroke_end()

    def drawn():
        return len(raster_to_pixels(app.raster))

    mid = GRID // 2
    app.set_brush("FF0000")
    for x in range(mid + 2, mid + 10):
        drag([(x + 0.5, mid + 0.5)])
    assert drawn() == 64, drawn()
    check("draw tab", 64)
    drag([(mid + 9.5, mid + 0.5)], erase=True)  # 끝 칸 지우기 -> 대칭으로 8칸 지워짐
    assert drawn() == 56, drawn()
    check("draw tab after erase", 56)

    # 부드러운 붓: 대칭 없이 굵기 2 가로선 (칸 6개 x 2줄 + 둥근 끝) -> 되돌리기
    app.tool_var.set("brush")
    app.on_tool()
    app.sym_var.set("1")
    app.width_var.set(2)
    drag([(24 + k, 8) for k in range(7)])
    print("brush stroke cells:", drawn() - 56)
    assert 12 <= drawn() - 56 <= 16, drawn()
    check_range("brush stroke", 56 + 12, 56 + 16)
    app.undo()
    assert drawn() == 56, drawn()

    # 도형: 채운 사각형 4x3 칸, 테두리 원, Shift 직선 -> 모두 되돌리기
    app.tool_var.set("rect")
    app.fill_var.set(True)
    drag([(26, 4), (28, 6), (30, 7)])
    assert drawn() - 56 == 12, drawn()
    check("filled rect", 56 + 12)
    app.tool_var.set("ellipse")
    app.fill_var.set(False)
    app.width_var.set(1)
    drag([(4, 4), (14, 14)])
    print("circle cells:", drawn() - 68)
    assert 20 <= drawn() - 68 <= 40, drawn()
    app.tool_var.set("line")
    app.stroke_start(Mouse(4, 30), False)
    app.stroke_move(Mouse(12, 31, shift=True))  # Shift: 수평으로 맞춤
    app.stroke_end()
    print("line cells:", drawn() - 68)
    for _ in range(3):
        app.undo()
    assert drawn() == 56, drawn()
    app.tool_var.set("pixel")
    app.on_tool()
    check("after undo", 56)

    # 가운데로: 구석에 그린 사각형이 정중앙으로 옮겨지고, 되돌리면 원래대로
    app.tool_var.set("rect")
    app.fill_var.set(True)
    app.sym_var.set("1")
    drag([(26, 4), (30, 7)])
    before = drawn()
    app.center_drawing()  # 칸 56개짜리 + 모양 + 사각형 전체가 가운데로
    x0, y0, x1, y1 = _content_box(app.raster)
    print("centered box:", (x0, y0, x1, y1), "center", HI / 2)
    assert abs((x0 + x1) / 2 - HI / 2) <= SS / 2 and abs((y0 + y1) / 2 - HI / 2) <= SS / 2
    assert drawn() == before
    app.undo()
    app.undo()
    assert drawn() == 56, drawn()
    steps = len(app.undo_stack)
    app.center_drawing()  # 이미 가운데인 + 모양은 그대로 (되돌리기 목록도 그대로)
    assert drawn() == 56 and len(app.undo_stack) == steps
    app.tool_var.set("pixel")
    app.on_tool()

    # 3) 그림 -> 코드: 그린 + 모양이 똑같은 코드로 바뀌어야 함
    match = app.drawing_to_code()
    print("drawing -> code:", app.code_var.get(), "match", match)
    assert match == 1.0 and app.mode == "make", match
    assert root.clipboard_get() == make_code(app.cfg) == make_code(parse_code(root.clipboard_get()))
    check("converted code", 56)

    if IS_WINDOWS:  # F8 단축키로 끄고 켜기
        assert app.overlay.hotkey, "F8 hotkey not registered"
        u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        u.PostMessageW(app.overlay.hwnd, 0x0312, 1, 0)  # WM_HOTKEY
        check("F8 off", 0)
        assert not app.show_var.get()
        u.PostMessageW(app.overlay.hwnd, 0x0312, 1, 0)
        check("F8 on", 56)
        assert app.show_var.get()
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
    if "--selftest-child" in sys.argv:  # 셀프테스트용 '먼저 켜져 있던 프로그램'
        global SETTINGS_PATH
        SETTINGS_PATH = os.devnull
    elif IS_WINDOWS:
        close_other_instances()
    import tkinter as tk

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
