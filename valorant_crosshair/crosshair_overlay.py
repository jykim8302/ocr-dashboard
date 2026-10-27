"""
발로란트 조준선 오버레이

발로란트 조준선 코드를 붙여넣으면 화면 정중앙에 똑같은 조준선을 띄워 줍니다.
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

    primary = {}
    section = None
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("P", "A", "S"):  # 주무기 / 정조준 / 저격총 구간 시작
            section = tok
            i += 1
            continue
        if i + 1 < len(tokens) and section == "P":
            primary[tok] = tokens[i + 1]
        i += 2

    cfg = {}
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


class App:
    PREVIEW = 220
    PREVIEW_BG = (70, 76, 82)

    def __init__(self, root):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.overlay = Overlay() if IS_WINDOWS else None
        self.cfg = None
        self.f8_down = False

        settings = load_settings()
        font = ("Malgun Gothic", 10)
        root.title("발로란트 조준선 오버레이")
        root.resizable(False, False)
        root.configure(padx=14, pady=12)

        tk.Label(root, text="조준선 코드", font=(font[0], 11, "bold")).pack(anchor="w")
        row = tk.Frame(root)
        row.pack(fill="x", pady=(4, 6))
        self.code_var = tk.StringVar(value=settings.get("code", EXAMPLE_CODE))
        entry = tk.Entry(row, textvariable=self.code_var, width=46, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=3)
        entry.bind("<Return>", lambda e: self.apply())
        tk.Button(row, text="적용", width=6, command=self.apply).pack(side="left", padx=(6, 0))

        tk.Button(root, text="📋 복사한 코드 붙여넣고 바로 적용", font=font,
                  command=self.paste_and_apply).pack(fill="x")

        self.canvas = tk.Canvas(root, width=self.PREVIEW, height=self.PREVIEW,
                                bg="#%02x%02x%02x" % self.PREVIEW_BG, highlightthickness=0)
        self.canvas.pack(pady=10)

        opts = tk.Frame(root)
        opts.pack(fill="x")
        self.show_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="조준선 표시  (F8 로 켜기/끄기)", font=font,
                       variable=self.show_var, command=self.update_visible).pack(anchor="w")
        size_row = tk.Frame(opts)
        size_row.pack(fill="x")
        tk.Label(size_row, text="크기", font=font).pack(side="left")
        self.scale_var = tk.DoubleVar(value=settings.get("scale", 1.0))
        tk.Scale(size_row, from_=0.5, to=3.0, resolution=0.1, orient="horizontal",
                 variable=self.scale_var, showvalue=True, length=230,
                 command=lambda v: self.redraw()).pack(side="left", padx=6)

        self.status = tk.Label(root, text="", font=font)
        self.status.pack(anchor="w", pady=(6, 0))
        tip = ("※ 발로란트 설정 > 비디오 > 화면 모드를 '창 전체화면'으로 해야\n"
               "   게임 위에 조준선이 보여요. (전체화면 모드에선 가려짐)")
        if not IS_WINDOWS:
            tip = "※ Windows 가 아니라서 미리보기만 동작해요."
        tk.Label(root, text=tip, font=(font[0], 9), fg="#777", justify="left").pack(anchor="w")

        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.apply()
        if self.overlay:
            self.tick_hotkey()
            self.tick_top()

    def set_status(self, text, ok=True):
        self.status.configure(text=text, fg="#1a7f37" if ok else "#c62828")

    def paste_and_apply(self):
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            self.set_status("클립보드가 비어 있어요.", ok=False)
            return
        self.code_var.set(text.strip())
        self.apply()

    def apply(self):
        try:
            self.cfg = parse_code(self.code_var.get())
        except ValueError as e:
            self.set_status(str(e), ok=False)
            return
        self.redraw()
        self.set_status("✔ 적용됐어요! 화면 가운데를 확인하세요.")

    def redraw(self):
        if not self.cfg:
            return
        scale = self.scale_var.get()
        side, rgba = render(self.cfg, scale)
        if self.overlay:
            self.overlay.draw(side, rgba)
        self.draw_preview(side, rgba)
        save_settings({"code": self.code_var.get(), "scale": scale})

    def draw_preview(self, side, rgba):
        # 회색 배경 위에 합성해서 3배 확대로 보여주기
        br, bg, bb = self.PREVIEW_BG
        rows = []
        for y in range(side):
            row = []
            for x in range(side):
                i = (y * side + x) * 4
                a = rgba[i + 3] / 255
                row.append("#%02x%02x%02x" % (round(rgba[i] * a + br * (1 - a)),
                                              round(rgba[i + 1] * a + bg * (1 - a)),
                                              round(rgba[i + 2] * a + bb * (1 - a))))
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
    """CI 확인용: 빨간 조준선을 띄우고 화면 중앙에 실제로 그려졌는지 검사."""
    import tkinter as tk

    global SETTINGS_PATH
    SETTINGS_PATH = os.devnull
    root = tk.Tk()
    app = App(root)
    app.code_var.set("0;P;c;7;h;0;0t;4;0l;10;0o;2;0a;1;1b;0")
    app.apply()
    for _ in range(20):
        root.update()
        time.sleep(0.05)
    assert app.cfg["rgb"] == (255, 0, 0), app.cfg
    print("overlay window created and drawn: OK")

    if IS_WINDOWS:
        try:
            from PIL import ImageGrab
        except ImportError:
            print("Pillow not installed, skipping screen check")
        else:
            sw = app.overlay.user32.GetSystemMetrics(0)
            sh = app.overlay.user32.GetSystemMetrics(1)
            shot = ImageGrab.grab(bbox=(sw // 2 - 20, sh // 2 - 20, sw // 2 + 20, sh // 2 + 20))
            red = sum(1 for p in shot.getdata() if p[0] > 200 and p[1] < 60 and p[2] < 60)
            print("red pixels at screen center:", red)
            assert red >= 4 * 10 * 4 * 0.9, "crosshair not visible on screen"
            app.show_var.set(False)
            app.update_visible()
            root.update()
            time.sleep(0.3)
            shot = ImageGrab.grab(bbox=(sw // 2 - 20, sh // 2 - 20, sw // 2 + 20, sh // 2 + 20))
            red = sum(1 for p in shot.getdata() if p[0] > 200 and p[1] < 60 and p[2] < 60)
            print("red pixels after hiding:", red)
            assert red == 0, "crosshair still visible after hiding"
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
