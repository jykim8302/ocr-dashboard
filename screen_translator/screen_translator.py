"""
화면 번역기 (Windows)

  Ctrl + Shift + T : 지금 보고 있는 창의 영어를 한국어로 번역
  Ctrl + Shift + R : 마우스로 드래그한 영역만 번역

화면을 찍어서 글자를 읽고(OCR), 구글 번역으로 한국어로 바꿔 작은 창에 보여줍니다.
"""

# ───────────── 여기만 바꾸면 됩니다 ─────────────
HOTKEY_WINDOW = "ctrl+shift+t"   # 현재 창 번역
HOTKEY_AREA = "ctrl+shift+r"     # 영역 선택 번역
TARGET_LANG = "ko"               # 번역할 언어 (ko=한국어, ja=일본어, zh-CN=중국어)
FONT_SIZE = 13                   # 번역 글자 크기
# ───────────────────────────────────────────────

import ctypes
import json
import os
import queue
import re
import sys
import threading
import traceback
import urllib.parse
import urllib.request

import tkinter as tk
from tkinter import messagebox

APP_NAME = "화면 번역기"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "오류기록.txt")

# pythonw 로 실행하면 콘솔이 없어서 print 가 에러날 수 있으므로 막아 둡니다.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def log_error(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


# ═══════════════════════ 1. 글자 묶기 (줄 → 문단) ═══════════════════════

_LETTERS = re.compile(r"[A-Za-z]")


def is_english(text):
    """영어 글자가 절반 이상인 줄만 번역 대상으로 봅니다."""
    chars = [c for c in text if not c.isspace()]
    letters = len(_LETTERS.findall(text))
    return letters >= 2 and letters / max(len(chars), 1) >= 0.5


def group_paragraphs(ocr_lines):
    """
    OCR 결과 줄들을 문단으로 묶습니다.
    ocr_lines: [(box, text, score), ...]  box = 네 꼭짓점 [[x,y], ...]
    반환: ["문단1 문장", "문단2 문장", ...] (위→아래, 왼→오 순서)
    """
    lines = []
    for box, text, score in ocr_lines:
        text = text.strip()
        if float(score) < 0.5 or not is_english(text):
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
                      "h": max(ys) - min(ys), "text": text})

    lines.sort(key=lambda l: (l["y0"], l["x0"]))
    paras = []
    for ln in lines:
        best, best_gap = None, None
        for p in paras:
            last = p[-1]
            h = max(last["h"], ln["h"], 1)
            gap = ln["y0"] - last["y1"]
            same_size = max(last["h"], ln["h"]) / max(min(last["h"], ln["h"]), 1) < 1.5
            left_aligned = abs(ln["x0"] - last["x0"]) < 1.5 * h
            if not (-0.3 * h < gap < 0.9 * h and same_size and left_aligned):
                continue
            # 메뉴처럼 짧은 단어 목록은 합치지 않고, 이어지는 문장만 합칩니다.
            prose = len(last["text"].split()) >= 6
            if last["text"].endswith((".", "!", "?", ":")):
                prose = prose and len(ln["text"].split()) >= 3   # 문장 끝 + 짧은 줄 = 다른 항목
            continues = (
                ln["text"][:1].islower() or ln["text"][:1].isdigit()
                or last["text"].endswith((",", "-", ";", "–"))
                or prose
            )
            if continues and (best_gap is None or gap < best_gap):
                best, best_gap = p, gap
        if best is not None:
            best.append(ln)
        else:
            paras.append([ln])

    paras = _reading_order(paras)
    result = []
    for p in paras:
        text = ""
        for ln in p:
            if text.endswith("-") and ln["text"][:1].islower():
                text = text[:-1] + ln["text"]       # 줄 끝 하이픈 이어 붙이기
            else:
                text = (text + " " + ln["text"]).strip()
        result.append(text)
    return result


def _reading_order(paras):
    """같은 높이(한 줄)에 있는 것은 왼쪽부터, 그다음 아래 줄로."""
    paras = sorted(paras, key=lambda p: p[0]["y0"])
    rows, out = [], []
    for p in paras:
        top = p[0]
        if rows and top["y0"] - rows[-1][0][0]["y0"] < 0.5 * max(top["h"], 1):
            rows[-1].append(p)
        else:
            rows.append([p])
    for row in rows:
        out.extend(sorted(row, key=lambda p: p[0]["x0"]))
    return out


# ═══════════════════════ 2. 번역 ═══════════════════════

def _translate_chunk(text):
    data = urllib.parse.urlencode({
        "client": "gtx", "sl": "auto", "tl": TARGET_LANG, "dt": "t", "q": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single",
        data=data, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in res[0] if seg and seg[0])


def translate_paragraphs(paras):
    """문단 목록을 번역해서 같은 개수의 목록으로 돌려줍니다."""
    out = []
    chunk = []

    def flush():
        if not chunk:
            return
        translated = _translate_chunk("\n".join(chunk)).split("\n")
        if len(translated) == len(chunk):
            out.extend(t.strip() for t in translated)
        else:   # 줄 수가 어긋나면 하나씩 다시 번역
            out.extend(_translate_chunk(p).strip() for p in chunk)
        chunk.clear()

    for p in paras:
        if sum(len(c) + 1 for c in chunk) + len(p) > 3500:
            flush()
        chunk.append(p)
    flush()
    return out


# ═══════════════════════ 3. 화면 / 창 (Windows) ═══════════════════════

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
if user32:
    user32.GetForegroundWindow.restype = ctypes.c_void_p


def make_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def window_rect(hwnd):
    """창의 화면 위치 (그림자 테두리 제외)."""
    rect = RECT()
    ok = False
    try:
        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
    except Exception:
        pass
    if not ok:
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def window_pid(hwnd):
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    return pid.value


def virtual_screen():
    """모니터 여러 대를 합친 전체 화면 영역 (x, y, 너비, 높이)."""
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))


def grab(bbox):
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=bbox, all_screens=True)


# ═══════════════════════ 4. 단축키 (Windows RegisterHotKey) ═══════════════════════

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(s):
    mods, vk = 0x4000, None          # 0x4000 = 꾹 누르고 있어도 한 번만
    for part in s.lower().replace(" ", "").split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif re.fullmatch(r"f([1-9]|1[0-2])", part):
            vk = 0x70 + int(part[1:]) - 1
        else:
            raise ValueError(f"알 수 없는 키: {part}")
    if vk is None:
        raise ValueError(f"키가 없습니다: {s}")
    return mods, vk


class HotkeyThread(threading.Thread):
    def __init__(self, hotkeys, out_queue):
        super().__init__(daemon=True)
        self.hotkeys = hotkeys          # {id: "ctrl+shift+t"}
        self.q = out_queue
        self.failed = []
        self.ready = threading.Event()

    def run(self):
        for hid, s in self.hotkeys.items():
            mods, vk = parse_hotkey(s)
            if not user32.RegisterHotKey(None, hid, mods, vk):
                self.failed.append(s)
        self.ready.set()
        from ctypes import wintypes
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:            # WM_HOTKEY
                self.q.put(("hotkey", int(msg.wParam)))


# ═══════════════════════ 5. 화면 (tkinter) ═══════════════════════

ID_WINDOW, ID_AREA = 1, 2
BG = "#ffffff"
FG = "#1f2328"
SUB = "#8c959f"
ACCENT = "#2f6feb"


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.q = queue.Queue()
        self.engine = None
        self.engine_ready = threading.Event()
        self.busy = False
        self.last_hwnd = None
        self.popup = None
        self.overlay = None
        self.show_original = tk.BooleanVar(value=True)
        self.result = []      # [(원문, 번역), ...]
        self.build_main()
        threading.Thread(target=self.load_engine, daemon=True).start()

    # ── 시작 창 ──
    def build_main(self):
        r = self.root
        r.title(APP_NAME)
        r.configure(bg=BG)
        r.resizable(False, False)
        pad = {"bg": BG, "anchor": "w", "justify": "left"}
        tk.Label(r, text="화면 번역기", font=("Malgun Gothic", 16, "bold"),
                 fg=FG, **pad).pack(fill="x", padx=20, pady=(18, 8))
        for key, desc in ((HOTKEY_WINDOW, "지금 보고 있는 창 번역"),
                          (HOTKEY_AREA, "드래그한 영역만 번역")):
            row = tk.Frame(r, bg=BG)
            row.pack(fill="x", padx=20, pady=3)
            tk.Label(row, text=" " + key.upper().replace("+", " + ") + " ",
                     font=("Malgun Gothic", 11, "bold"), bg="#eaeef2", fg=FG,
                     width=18).pack(side="left")
            tk.Label(row, text="  " + desc, font=("Malgun Gothic", 11), fg=FG,
                     **pad).pack(side="left")
        self.status = tk.Label(r, text="⏳ 글자 인식 준비 중...", font=("Malgun Gothic", 10),
                               fg=SUB, **pad)
        self.status.pack(fill="x", padx=20, pady=(12, 2))
        tk.Label(r, text="이 창은 내려 두셔도 됩니다. 닫으면 프로그램이 꺼져요.",
                 font=("Malgun Gothic", 9), fg=SUB, **pad).pack(fill="x", padx=20, pady=(0, 16))
        r.protocol("WM_DELETE_WINDOW", self.quit)

    def load_engine(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR()
            self.q.put(("status", "✅ 준비 완료! 영어가 있는 창에서 단축키를 눌러 보세요."))
        except Exception:
            log_error(traceback.format_exc())
            self.q.put(("status", "❌ 글자 인식 엔진을 불러오지 못했어요. 실행.bat 을 다시 실행해 주세요."))
        self.engine_ready.set()

    # ── 이벤트 처리 ──
    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "hotkey":
                    self.on_hotkey(val)
                elif kind == "status":
                    self.status.config(text=val)
                elif kind == "result":
                    self.busy = False
                    self.show_result(*val)
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def on_hotkey(self, hid):
        if self.busy or self.overlay is not None:
            return
        if hid == ID_AREA:
            self.start_area_select()
            return
        hwnd = user32.GetForegroundWindow()
        if not hwnd or window_pid(hwnd) == os.getpid():
            # 번역 창을 보고 있을 때 누르면 → 직전 창을 다시 번역
            hwnd = self.last_hwnd
        if not hwnd or not user32.IsWindow(ctypes.c_void_p(hwnd)) or user32.IsIconic(ctypes.c_void_p(hwnd)):
            self.open_popup_message("번역할 창을 먼저 클릭한 뒤 단축키를 눌러 주세요.", None)
            return
        self.last_hwnd = hwnd
        self.capture_and_run(window_rect(hwnd))

    def capture_and_run(self, bbox):
        """번역 창이 사진에 찍히지 않도록 잠깐 숨긴 뒤 화면을 찍습니다."""
        self.busy = True
        hidden = self.popup is not None and self.popup.winfo_viewable()
        if hidden:
            self.popup.withdraw()
        self.root.after(180 if hidden else 10, lambda: self._capture(bbox))

    def _capture(self, bbox):
        try:
            img = grab(bbox)
        except Exception:
            log_error(traceback.format_exc())
            self.busy = False
            self.open_popup_message("화면을 찍지 못했어요. 다시 시도해 주세요.", bbox)
            return
        self.open_popup_message("⏳ 읽고 번역하는 중...", bbox)
        threading.Thread(target=self.work, args=(img, bbox), daemon=True).start()

    def work(self, img, bbox):
        try:
            self.engine_ready.wait()
            if self.engine is None:
                raise RuntimeError("글자 인식 엔진이 없어요. 실행.bat 을 다시 실행해 주세요.")
            import numpy as np
            arr = np.array(img.convert("RGB"))[:, :, ::-1]   # RGB → BGR
            if arr.shape[0] < 60 or arr.shape[1] < 60:      # 아주 작은 영역은 키워서 읽기
                from PIL import Image
                img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
                arr = np.array(img.convert("RGB"))[:, :, ::-1]
            ocr, _ = self.engine(arr)
            paras = group_paragraphs(ocr or [])
            if not paras:
                self.q.put(("result", ([], "영어 글자를 찾지 못했어요.", bbox)))
                return
            try:
                trans = translate_paragraphs(paras)
                self.q.put(("result", (list(zip(paras, trans)), None, bbox)))
            except Exception:
                log_error(traceback.format_exc())
                self.q.put(("result", ([(p, "") for p in paras],
                                       "번역에 실패했어요. 인터넷 연결을 확인해 주세요. (원문만 보여드려요)", bbox)))
        except Exception as e:
            log_error(traceback.format_exc())
            self.q.put(("result", ([], f"오류가 났어요: {e}", bbox)))

    # ── 영역 선택 ──
    def start_area_select(self):
        x, y, w, h = virtual_screen()
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.3)
        ov.geometry(f"{w}x{h}+{x}+{y}")
        cv = tk.Canvas(ov, bg="black", highlightthickness=0, cursor="cross")
        cv.pack(fill="both", expand=True)
        cv.create_text(user32.GetSystemMetrics(0) // 2 - x, 60 - y, fill="white",
                       font=("Malgun Gothic", 20, "bold"),
                       text="번역할 영역을 마우스로 드래그하세요  (취소: Esc)")
        start = {}

        def down(e):
            start["x"], start["y"] = e.x, e.y
            start["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#4da3ff", width=3,
                                                fill="white")

        def move(e):
            if "rect" in start:
                cv.coords(start["rect"], start["x"], start["y"], e.x, e.y)

        def up(e):
            if "x" not in start:
                return
            x0, x1 = sorted((start["x"], e.x))
            y0, y1 = sorted((start["y"], e.y))
            close()
            if x1 - x0 > 10 and y1 - y0 > 10:
                self.busy = True
                self.root.after(150, lambda: self._capture((x0 + x, y0 + y, x1 + x, y1 + y)))

        def close(_=None):
            ov.destroy()
            self.overlay = None

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        ov.bind("<Escape>", close)
        ov.bind("<Button-3>", close)
        self.overlay = ov
        if self.popup is not None:
            self.popup.withdraw()
        ov.after(50, ov.focus_force)

    # ── 번역 결과 창 ──
    def ensure_popup(self):
        if self.popup is not None:
            return
        p = tk.Toplevel(self.root)
        p.title("번역")
        p.configure(bg=BG)
        p.attributes("-topmost", True)
        p.protocol("WM_DELETE_WINDOW", self.hide_popup)
        p.bind("<Escape>", lambda e: self.hide_popup())

        bar = tk.Frame(p, bg="#f6f8fa")
        bar.pack(side="bottom", fill="x")
        btn = {"font": ("Malgun Gothic", 10), "relief": "flat", "bg": "#f6f8fa",
               "activebackground": "#eaeef2", "cursor": "hand2", "padx": 10, "pady": 6}
        tk.Checkbutton(bar, text="원문 같이 보기", variable=self.show_original,
                       command=self.render, bg="#f6f8fa", activebackground="#f6f8fa",
                       font=("Malgun Gothic", 10)).pack(side="left", padx=8)
        tk.Button(bar, text="닫기 (Esc)", command=self.hide_popup, **btn).pack(side="right", padx=(0, 8))
        self.copy_btn = tk.Button(bar, text="번역 복사", command=self.copy, **btn)
        self.copy_btn.pack(side="right")

        frame = tk.Frame(p, bg=BG)
        frame.pack(fill="both", expand=True)
        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")
        t = tk.Text(frame, wrap="word", bg=BG, fg=FG, relief="flat", padx=18, pady=14,
                    font=("Malgun Gothic", FONT_SIZE), yscrollcommand=sb.set, cursor="arrow")
        t.pack(side="left", fill="both", expand=True)
        sb.config(command=t.yview)
        t.tag_config("tr", font=("Malgun Gothic", FONT_SIZE), foreground=FG, spacing1=4, spacing3=2)
        t.tag_config("en", font=("Segoe UI", max(FONT_SIZE - 3, 8)), foreground=SUB, spacing3=14)
        t.tag_config("gap", spacing3=10)
        t.tag_config("msg", font=("Malgun Gothic", FONT_SIZE), foreground=ACCENT, spacing3=12)
        self.text = t
        self.popup = p
        self.message = None

    def place_popup(self, bbox):
        """번역 대상 창 오른쪽(자리가 없으면 왼쪽/가운데)에 번역 창을 띄웁니다."""
        p = self.popup
        sx, sy, sw, sh = virtual_screen()
        scale = max(self.root.winfo_fpixels("1i") / 96, 1)   # 화면 배율(125%, 150%...)
        w = min(int(560 * scale), sw - 40)
        h = min(int(640 * scale), sh - 120)
        if bbox:
            l, t, r, b = bbox
            if r + w + 10 <= sx + sw:
                x = r + 10
            elif l - w - 10 >= sx:
                x = l - w - 10
            else:
                x = r - w - 20
            y = max(t, sy + 10)
            y = min(y, sy + sh - h - 60)
        else:
            x, y = sx + (sw - w) // 2, sy + (sh - h) // 2
        p.geometry(f"{w}x{h}+{int(x)}+{int(y)}")

    def open_popup_message(self, msg, bbox):
        self.ensure_popup()
        self.result, self.message = [], msg
        self.place_popup(bbox)
        self.render()
        self.popup.deiconify()
        self.popup.lift()

    def show_result(self, pairs, msg, bbox):
        self.ensure_popup()
        self.result, self.message = pairs, msg
        self.render()
        self.popup.deiconify()
        self.popup.lift()
        self.popup.focus_force()

    def render(self):
        if self.popup is None:
            return
        t = self.text
        t.config(state="normal")
        t.delete("1.0", "end")
        if self.message:
            t.insert("end", self.message + "\n", "msg")
        for orig, tr in self.result:
            if tr:
                t.insert("end", tr + "\n", "tr")
            if self.show_original.get() or not tr:
                t.insert("end", orig + "\n", "en")
            else:
                t.insert("end", "\n", "gap")
        t.config(state="disabled")
        t.yview_moveto(0)

    def copy(self):
        text = "\n\n".join(tr or orig for orig, tr in self.result)
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.copy_btn.config(text="✔ 복사됨")
        self.root.after(1200, lambda: self.copy_btn.config(text="번역 복사"))

    def hide_popup(self):
        if self.popup is not None:
            self.popup.withdraw()

    def quit(self):
        self.root.destroy()

    # ── 시작 ──
    def run(self):
        hk = HotkeyThread({ID_WINDOW: HOTKEY_WINDOW, ID_AREA: HOTKEY_AREA}, self.q)
        hk.start()
        hk.ready.wait(3)
        if hk.failed:
            messagebox.showwarning(
                APP_NAME,
                "이 단축키를 쓸 수 없어요: " + ", ".join(hk.failed) +
                "\n\n프로그램이 이미 켜져 있거나, 다른 프로그램이 같은 단축키를 쓰고 있어요.\n"
                "screen_translator.py 맨 위의 HOTKEY 값을 바꿔 보세요.")
            if len(hk.failed) == 2:
                self.root.destroy()
                return
        self.root.after(80, self.poll)
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        print("이 프로그램은 Windows 에서만 동작합니다.")
        return
    make_dpi_aware()
    try:
        App().run()
    except Exception:
        log_error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
