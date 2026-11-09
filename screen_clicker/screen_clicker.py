"""
화면 이미지 자동 클릭기
------------------------------------------------------------
1) 화면에서 '감시할 박스(영역)'를 드래그로 정합니다.
2) 찾을 그림(버튼 등)을 화면에서 캡처하거나 파일로 올립니다.
3) [시작]을 누르면, 박스 안에 그 그림이 보일 때마다 자동으로 클릭합니다.
   - 항목은 여러 개 만들 수 있습니다.
   - F9 = 시작, F10 = 멈춤 (pynput 설치 시)
   - 비상 정지: 마우스를 화면 왼쪽 위 구석으로 밀면 멈춥니다.
"""

import ctypes
import json
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

# Windows 화면 배율(125%, 150% 등)에서도 좌표가 어긋나지 않도록 가장 먼저 설정
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_missing = []
try:
    import numpy as np
except ImportError:
    _missing.append("numpy")
try:
    import cv2
except ImportError:
    _missing.append("opencv-python")
try:
    import mss

    new_mss = getattr(mss, "MSS", None) or mss.mss  # 새/옛 버전 모두 지원
except ImportError:
    _missing.append("mss")
try:
    from PIL import Image, ImageTk
except ImportError:
    _missing.append("pillow")
try:
    import pyautogui

    pyautogui.FAILSAFE = True  # 마우스를 왼쪽 위 구석으로 밀면 비상 정지
    pyautogui.PAUSE = 0.03
except Exception:  # 화면이 없는 환경 등
    pyautogui = None
    _missing.append("pyautogui")
try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None  # 단축키만 안 될 뿐, 프로그램은 동작

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
IMAGE_DIR = BASE_DIR / "images"

CLICK_TYPES = {"왼쪽 클릭": "left", "더블 클릭": "double", "오른쪽 클릭": "right"}
CLICK_NAMES = {v: k for k, v in CLICK_TYPES.items()}


# ============================================================
# 이미지 / 화면 도우미
# ============================================================
def read_image(path):
    """한글 경로에서도 읽히도록 imdecode 사용. 실패하면 None."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def save_image(path, img_bgr):
    ok, buf = cv2.imencode(".png", img_bgr)
    if ok:
        buf.tofile(str(path))
    return ok


def grab_area(sct, x, y, w, h):
    """화면 일부를 BGR 이미지로 가져옴."""
    shot = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
    return np.ascontiguousarray(np.array(shot)[:, :, :3])


def grab_whole_screen():
    """모든 모니터를 합친 전체 화면. (이미지, 왼쪽, 위, 화면폭, 화면높이)"""
    with new_mss() as sct:
        mon = sct.monitors[0]
        img = grab_area(sct, mon["left"], mon["top"], mon["width"], mon["height"])
    return img, mon["left"], mon["top"], mon["width"], mon["height"]


def find_image(screen_bgr, template_bgr):
    """screen 안에서 template를 찾음 → (일치율 0~1, (중심x, 중심y), (폭, 높이)) / 못 찾으면 None"""
    if screen_bgr is None or template_bgr is None:
        return None
    sh, sw = screen_bgr.shape[:2]
    th, tw = template_bgr.shape[:2]
    if th > sh or tw > sw:
        return None
    screen = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tpl = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    if tpl.std() < 3:  # 거의 단색인 그림은 다른 방식으로 비교
        res = cv2.matchTemplate(screen, tpl, cv2.TM_SQDIFF_NORMED)
        min_v, _, min_loc, _ = cv2.minMaxLoc(res)
        score, loc = 1.0 - min_v, min_loc
    else:
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        _, max_v, _, max_loc = cv2.minMaxLoc(res)
        score, loc = max_v, max_loc
    center = (loc[0] + tw // 2, loc[1] + th // 2)
    return float(score), center, (tw, th)


def do_click(x, y, kind, return_mouse):
    old = pyautogui.position() if return_mouse else None
    if kind == "double":
        pyautogui.doubleClick(x, y)
    elif kind == "right":
        pyautogui.rightClick(x, y)
    else:
        pyautogui.click(x, y)
    if old is not None:
        pyautogui.moveTo(old[0], old[1])


# ============================================================
# 설정 저장 / 불러오기
# ============================================================
def new_rule():
    return {
        "id": uuid.uuid4().hex[:8],
        "name": "",
        "enabled": True,
        "region": None,  # [x, y, w, h]
        "image": "",  # images/ 폴더 안의 파일 이름
        "threshold": 0.85,
        "click": "left",
        "cooldown": 2.0,
    }


def load_settings():
    data = {"interval": 0.5, "return_mouse": True, "rules": []}
    if SETTINGS_FILE.exists():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    for r in data["rules"]:
        base = new_rule()
        base.update(r)
        r.update(base)
    return data


def save_settings(data):
    # 임시 파일에 먼저 쓰고 바꿔치기 → 저장 중 꺼져도 설정이 깨지지 않음
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)


def next_name(rules):
    """아직 안 쓴 가장 작은 번호 → '1번', '2번', '3번' ..."""
    used = {r["name"] for r in rules}
    n = 1
    while f"{n}번" in used:
        n += 1
    return f"{n}번"


# ============================================================
# 감시(백그라운드) 작업
# ============================================================
class Watcher(threading.Thread):
    def __init__(self, rules, interval, return_mouse, out_q):
        super().__init__(daemon=True)
        self.rules = [dict(r) for r in rules if r["enabled"] and r["region"] and r["image"]]
        self.interval = max(0.05, float(interval))
        self.return_mouse = return_mouse
        self.out_q = out_q
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        templates = {}
        for r in self.rules:
            img = read_image(IMAGE_DIR / r["image"])
            if img is None:
                self.out_q.put(("log", f"[{r['name']}] 그림 파일을 못 읽어서 건너뜁니다."))
            else:
                templates[r["id"]] = img
        rules = [r for r in self.rules if r["id"] in templates]
        if not rules:
            self.out_q.put(("log", "감시할 항목이 없어요. (사용 체크 / 박스 / 그림 확인)"))
            self.out_q.put(("stopped", self))
            return

        last_click = {}
        counts = {}
        try:
            with new_mss() as sct:
                while not self.stop_event.is_set():
                    for r in rules:
                        if self.stop_event.is_set():
                            break
                        x, y, w, h = r["region"]
                        shot = grab_area(sct, x, y, w, h)
                        scale = shot.shape[1] / float(w)  # Mac 레티나 대비
                        found = find_image(shot, templates[r["id"]])
                        if found is None:
                            self.out_q.put(("status", r["id"], "박스가 그림보다 작아요"))
                            continue
                        score, (cx, cy), _ = found
                        now = time.time()
                        if score >= r["threshold"]:
                            if now - last_click.get(r["id"], 0) >= r["cooldown"]:
                                sx = x + cx / scale
                                sy = y + cy / scale
                                do_click(sx, sy, r["click"], self.return_mouse)
                                last_click[r["id"]] = time.time()
                                counts[r["id"]] = counts.get(r["id"], 0) + 1
                                self.out_q.put(("log", f"[{r['name']}] 클릭! (일치 {score:.0%}, 위치 {int(sx)},{int(sy)})"))
                            self.out_q.put(("status", r["id"], f"찾음 {score:.0%} · 클릭 {counts.get(r['id'], 0)}회"))
                        else:
                            self.out_q.put(("status", r["id"], f"대기 중 ({score:.0%}) · 클릭 {counts.get(r['id'], 0)}회"))
                    self.stop_event.wait(self.interval)
        except Exception as e:
            if pyautogui is not None and isinstance(e, pyautogui.FailSafeException):
                self.out_q.put(("log", "비상 정지: 마우스가 화면 구석으로 가서 멈췄어요."))
            else:
                self.out_q.put(("log", f"오류로 멈췄어요: {e}"))
        self.out_q.put(("stopped", self))


# ============================================================
# 화면 위에서 드래그로 박스 고르기
# ============================================================
def select_on_screen(root, hide_windows, message, hint_region=None):
    """
    잠깐 창을 숨기고 전체 화면을 찍은 뒤, 그 위에서 드래그로 박스를 고릅니다.
    반환: (x, y, w, h, 잘라낸이미지BGR) 또는 None(취소)
    """
    for win in hide_windows:
        win.withdraw()
    root.update()
    time.sleep(0.35)  # 창이 사라질 시간
    try:
        full, left, top, mw, mh = grab_whole_screen()
    except Exception as e:
        for win in hide_windows:
            win.deiconify()
        messagebox.showerror("오류", f"화면을 찍지 못했어요.\n{e}")
        return None
    scale = full.shape[1] / float(mw)

    top_win = tk.Toplevel(root)
    top_win.overrideredirect(True)
    top_win.geometry(f"{mw}x{mh}+{left}+{top}")  # 보조 모니터가 왼쪽이면 left가 음수
    top_win.attributes("-topmost", True)
    top_win.configure(cursor="crosshair")

    rgb = cv2.cvtColor(full, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    if scale != 1.0:
        pil = pil.resize((mw, mh))
    # 살짝 어둡게 해서 '선택 모드'임을 알 수 있게
    dark = Image.eval(pil, lambda v: int(v * 0.75))
    photo = ImageTk.PhotoImage(dark)

    canvas = tk.Canvas(top_win, width=mw, height=mh, highlightthickness=0)
    canvas.pack()
    canvas.create_image(0, 0, image=photo, anchor="nw")

    # 이미 정한 감시 박스가 있으면 파란 점선으로 보여주기
    if hint_region:
        hx, hy, hw, hh = hint_region
        canvas.create_rectangle(hx - left, hy - top, hx - left + hw, hy - top + hh,
                                outline="#3B82F6", width=2, dash=(6, 4))

    # 안내 문구 (주 모니터 상단 가운데)
    gx = -left + 20
    gy = -top + 20
    canvas.create_rectangle(gx, gy, gx + 620, gy + 54, fill="#111827", outline="#FACC15", width=2)
    canvas.create_text(gx + 310, gy + 27, text=f"{message}   (취소: ESC)",
                       fill="white", font=("Malgun Gothic", 14, "bold"))

    state = {"start": None, "rect": None, "result": None, "label": None}

    def on_down(e):
        state["start"] = (e.x, e.y)
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#EF4444", width=3)

    def on_move(e):
        if state["start"]:
            x0, y0 = state["start"]
            canvas.coords(state["rect"], x0, y0, e.x, e.y)
            if state["label"]:
                canvas.delete(state["label"])
            state["label"] = canvas.create_text(e.x + 12, e.y + 18, anchor="nw",
                                                text=f"{abs(e.x - x0)} × {abs(e.y - y0)}",
                                                fill="#FACC15", font=("Malgun Gothic", 11, "bold"))

    def on_up(e):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = min(x0, e.x), min(y0, e.y)
        x2, y2 = max(x0, e.x), max(y0, e.y)
        if x2 - x1 < 5 or y2 - y1 < 5:
            state["start"] = None
            return
        crop = full[int(y1 * scale):int(y2 * scale), int(x1 * scale):int(x2 * scale)].copy()
        state["result"] = (x1 + left, y1 + top, x2 - x1, y2 - y1, crop)
        top_win.destroy()

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_move)
    canvas.bind("<ButtonRelease-1>", on_up)
    top_win.bind("<Escape>", lambda e: top_win.destroy())
    canvas.bind("<Button-3>", lambda e: top_win.destroy())  # 오른쪽 클릭도 취소
    top_win.focus_force()
    top_win.grab_set()
    top_win.wait_window()

    for win in hide_windows:
        win.deiconify()
    return state["result"]


def to_photo(img_bgr, max_w, max_h):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    pil.thumbnail((max_w, max_h))
    return ImageTk.PhotoImage(pil)


# ============================================================
# 항목 만들기 / 고치기 창
# ============================================================
class RuleDialog(tk.Toplevel):
    def __init__(self, app, rule):
        super().__init__(app.root)
        self.app = app
        self.rule = dict(rule)
        self.template = read_image(IMAGE_DIR / rule["image"]) if rule["image"] else None
        self.new_image = False
        self.saved = False
        self.photo = None

        self.title("항목 설정")
        self.resizable(False, False)
        self.transient(app.root)
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        # 이름
        ttk.Label(frm, text="이름").grid(row=0, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value=rule["name"])
        ttk.Entry(frm, textvariable=self.name_var, width=34).grid(row=0, column=1, columnspan=2, sticky="we", **pad)

        # ① 감시 박스
        ttk.Label(frm, text="① 감시할 박스", font=("Malgun Gothic", 10, "bold")).grid(row=1, column=0, sticky="w", **pad)
        reg_box = ttk.Frame(frm)
        reg_box.grid(row=1, column=1, sticky="w", **pad)
        self.reg_vars = []
        for i, t in enumerate(("X", "Y", "폭", "높이")):
            ttk.Label(reg_box, text=t).grid(row=0, column=i * 2, padx=(0 if i == 0 else 6, 2))
            v = tk.IntVar(value=0)
            ttk.Spinbox(reg_box, from_=-20000, to=20000, textvariable=v, width=5).grid(row=0, column=i * 2 + 1)
            self.reg_vars.append(v)
        ttk.Button(frm, text="📐 화면에서 박스 그리기", command=self.pick_region).grid(row=1, column=2, sticky="we", **pad)

        # 다른 번호에 저장된 박스/사진 가져오기
        others = [r for r in app.data["rules"] if r["id"] != rule["id"]]
        self.others = {r["name"]: r for r in others}
        if others:
            imp = ttk.Frame(frm)
            imp.grid(row=10, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 4))
            ttk.Label(imp, text="📋 저장된 것 가져오기:").pack(side="left")
            self.import_var = tk.StringVar()
            ttk.Combobox(imp, textvariable=self.import_var, values=list(self.others), state="readonly",
                         width=12).pack(side="left", padx=6)
            ttk.Button(imp, text="박스만", command=lambda: self.import_from("region")).pack(side="left")
            ttk.Button(imp, text="사진만", command=lambda: self.import_from("image")).pack(side="left", padx=4)
            ttk.Button(imp, text="둘 다", command=lambda: self.import_from("both")).pack(side="left")

        # ② 찾을 그림
        ttk.Label(frm, text="② 찾을 사진", font=("Malgun Gothic", 10, "bold")).grid(row=2, column=0, sticky="nw", **pad)
        self.preview = tk.Label(frm, text="(아직 없음)", width=28, height=6, relief="groove", bg="#F3F4F6")
        self.preview.grid(row=2, column=1, rowspan=2, sticky="w", **pad)
        ttk.Button(frm, text="✂ 화면에서 캡처", command=self.capture_image).grid(row=2, column=2, sticky="we", **pad)
        ttk.Button(frm, text="📂 그림 파일 올리기", command=self.upload_image).grid(row=3, column=2, sticky="nwe", **pad)

        ttk.Separator(frm).grid(row=4, column=0, columnspan=3, sticky="we", pady=8)

        # 정확도
        ttk.Label(frm, text="얼마나 똑같아야 클릭?").grid(row=5, column=0, sticky="w", **pad)
        self.th_var = tk.IntVar(value=int(round(rule["threshold"] * 100)))
        th_box = ttk.Frame(frm)
        th_box.grid(row=5, column=1, columnspan=2, sticky="we", **pad)
        self.th_label = ttk.Label(th_box, width=5)
        ttk.Scale(th_box, from_=50, to=99, variable=self.th_var, length=220,
                  command=lambda v: self.th_label.config(text=f"{int(float(v))}%")).pack(side="left")
        self.th_label.pack(side="left", padx=6)
        self.th_label.config(text=f"{self.th_var.get()}%")
        ttk.Label(th_box, text="(보통 85%)", foreground="gray").pack(side="left")

        # 클릭 방법
        ttk.Label(frm, text="클릭 방법").grid(row=6, column=0, sticky="w", **pad)
        self.click_var = tk.StringVar(value=CLICK_NAMES.get(rule["click"], "왼쪽 클릭"))
        ttk.Combobox(frm, textvariable=self.click_var, values=list(CLICK_TYPES), state="readonly",
                     width=12).grid(row=6, column=1, sticky="w", **pad)

        # 대기 시간
        ttk.Label(frm, text="한 번 클릭 후 쉬는 시간").grid(row=7, column=0, sticky="w", **pad)
        cd_box = ttk.Frame(frm)
        cd_box.grid(row=7, column=1, sticky="w", **pad)
        self.cd_var = tk.DoubleVar(value=rule["cooldown"])
        ttk.Spinbox(cd_box, from_=0, to=3600, increment=0.5, textvariable=self.cd_var, width=7).pack(side="left")
        ttk.Label(cd_box, text="초").pack(side="left", padx=4)

        ttk.Separator(frm).grid(row=8, column=0, columnspan=3, sticky="we", pady=8)

        btns = ttk.Frame(frm)
        btns.grid(row=11, column=0, columnspan=3, sticky="we", pady=(6, 0))
        ttk.Button(btns, text="🔍 지금 찾아보기(테스트)", command=self.test).pack(side="left")
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="💾 저장", command=self.save).pack(side="right", padx=6)

        self.set_region(rule["region"])
        self.refresh()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

    # ---- 화면 갱신
    def get_region(self):
        try:
            x, y, w, h = (int(v.get()) for v in self.reg_vars)
        except Exception:
            return None
        return [x, y, w, h] if w > 0 and h > 0 else None

    def set_region(self, r):
        for v, n in zip(self.reg_vars, r or (0, 0, 0, 0)):
            v.set(int(n))

    def import_from(self, what):
        src = self.others.get(self.import_var.get())
        if not src:
            messagebox.showinfo("알림", "가져올 번호를 먼저 골라주세요.", parent=self)
            return
        if what in ("region", "both"):
            if src["region"]:
                self.set_region(src["region"])
            else:
                messagebox.showinfo("알림", f"'{src['name']}'에는 박스가 없어요.", parent=self)
        if what in ("image", "both"):
            img = read_image(IMAGE_DIR / src["image"]) if src["image"] else None
            if img is not None:
                self.template = img
                self.new_image = True
                self.refresh()
            else:
                messagebox.showinfo("알림", f"'{src['name']}'에는 사진이 없어요.", parent=self)

    def refresh(self):
        if self.template is not None:
            self.photo = to_photo(self.template, 200, 90)
            self.preview.config(image=self.photo, text="", width=200, height=90)
        else:
            self.preview.config(image="", text="(아직 없음)", width=28, height=6)

    # ---- 버튼 동작
    def pick_region(self):
        res = select_on_screen(self.app.root, [self, self.app.root],
                               "① 감시할 박스를 드래그하세요 (조금 넉넉하게)")
        self.grab_set()
        if res:
            x, y, w, h, crop = res
            self.set_region([x, y, w, h])

    def capture_image(self):
        res = select_on_screen(self.app.root, [self, self.app.root],
                               "② 찾을 그림(버튼 등)만 딱 맞게 드래그하세요",
                               hint_region=self.get_region())
        self.grab_set()
        if res:
            x, y, w, h, crop = res
            self.template = crop
            self.new_image = True
            if not self.get_region():
                # 박스를 안 정했으면 그림 주변을 넉넉하게 박스로 잡아줌
                m = 40
                self.set_region([x - m, y - m, w + 2 * m, h + 2 * m])
            self.refresh()

    def upload_image(self):
        path = filedialog.askopenfilename(
            parent=self, title="찾을 그림 고르기",
            filetypes=[("그림 파일", "*.png *.jpg *.jpeg *.bmp"), ("모든 파일", "*.*")])
        if not path:
            return
        img = read_image(path)
        if img is None:
            messagebox.showerror("오류", "그림 파일을 읽지 못했어요.", parent=self)
            return
        self.template = img
        self.new_image = True
        self.refresh()

    def test(self):
        if not self.get_region() or self.template is None:
            messagebox.showinfo("알림", "① 박스와 ② 그림을 먼저 정해주세요.", parent=self)
            return
        x, y, w, h = self.get_region()
        self.withdraw()
        self.app.root.withdraw()
        self.app.root.update()
        time.sleep(0.35)
        try:
            with new_mss() as sct:
                shot = grab_area(sct, x, y, w, h)
        finally:
            self.app.root.deiconify()
            self.deiconify()
            self.grab_set()
        found = find_image(shot, self.template)
        th = self.th_var.get() / 100
        if found is None:
            messagebox.showwarning("결과", "박스가 그림보다 작아요.\n박스를 더 크게 그려주세요.", parent=self)
            return
        score, (cx, cy), (tw, th_px) = found
        ok = score >= th
        view = shot.copy()
        color = (80, 200, 0) if ok else (0, 0, 255)
        cv2.rectangle(view, (cx - tw // 2, cy - th_px // 2), (cx + tw // 2, cy + th_px // 2), color, 2)
        msg = (f"✅ 찾았어요!  일치율 {score:.0%}  (기준 {th:.0%})\n시작하면 빨간/초록 상자 가운데를 클릭합니다."
               if ok else
               f"❌ 못 찾았어요.  가장 비슷한 곳 {score:.0%}  (기준 {th:.0%})\n그림이 지금 화면 박스 안에 보이는지 확인하세요.")
        win = tk.Toplevel(self)
        win.title("테스트 결과")
        win.transient(self)
        ttk.Label(win, text=msg, padding=10, foreground="#15803D" if ok else "#B91C1C",
                  font=("Malgun Gothic", 10, "bold")).pack()
        ph = to_photo(view, 640, 420)
        lbl = tk.Label(win, image=ph)
        lbl.image = ph
        lbl.pack(padx=10, pady=(0, 10))
        ttk.Button(win, text="확인", command=win.destroy).pack(pady=(0, 10))
        win.grab_set()

    def save(self):
        region = self.get_region()
        if not region and self.template is None:
            messagebox.showinfo("알림", "① 박스나 ② 사진 중 하나는 정해주세요.", parent=self)
            return
        if region and self.template is not None:
            th_px, tw = self.template.shape[:2]
            if tw > region[2] or th_px > region[3]:
                if not messagebox.askyesno("확인", "사진이 박스보다 커서 찾을 수 없어요.\n그래도 저장할까요?", parent=self):
                    return
        others = [r for r in self.app.data["rules"] if r["id"] != self.rule["id"]]
        name = self.name_var.get().strip() or next_name(others)
        self.rule["region"] = region
        self.rule["name"] = name
        self.rule["threshold"] = self.th_var.get() / 100
        self.rule["click"] = CLICK_TYPES.get(self.click_var.get(), "left")
        try:
            self.rule["cooldown"] = max(0.0, float(self.cd_var.get()))
        except Exception:
            self.rule["cooldown"] = 2.0
        if self.new_image:
            IMAGE_DIR.mkdir(exist_ok=True)
            fname = f"{self.rule['id']}_{int(time.time())}.png"
            save_image(IMAGE_DIR / fname, self.template)
            self.rule["image"] = fname
        self.saved = True
        self.destroy()


# ============================================================
# 메인 창
# ============================================================
class App:
    def __init__(self, root):
        self.root = root
        self.data = load_settings()
        self.watcher = None
        self.q = queue.Queue()
        self.status = {}
        self.thumbs = {}  # 목록에 보이는 작은 사진들

        root.title("화면 이미지 자동 클릭기")
        root.geometry("860x560")
        root.minsize(640, 420)
        try:
            style = ttk.Style()
            if "vista" in style.theme_names():
                style.theme_use("vista")
            style.configure("Treeview", rowheight=46, font=("Malgun Gothic", 10))
            style.configure("Treeview.Heading", font=("Malgun Gothic", 10, "bold"))
            style.configure("Big.TButton", font=("Malgun Gothic", 11, "bold"), padding=8)
        except Exception:
            pass

        # 위쪽 버튼
        top = ttk.Frame(root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Button(top, text="➕ 새 항목", command=self.add).pack(side="left")
        ttk.Button(top, text="✏ 고치기", command=self.edit).pack(side="left", padx=4)
        ttk.Button(top, text="🏷 이름 바꾸기 (F2)", command=self.rename).pack(side="left")
        ttk.Button(top, text="📄 복사", command=self.copy).pack(side="left", padx=4)
        ttk.Button(top, text="🗑 지우기", command=self.delete).pack(side="left")
        ttk.Label(top, text="이름 두 번 클릭 = 이름 바꾸기 · 다른 칸 두 번 클릭 = 고치기",
                  foreground="gray").pack(side="right")

        # 목록
        mid = ttk.Frame(root, padding=(10, 4))
        mid.pack(fill="both", expand=True)
        cols = ("on", "name", "region", "th", "click", "status")
        self.tree = ttk.Treeview(mid, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="사진")
        self.tree.column("#0", width=100, stretch=False, anchor="center")
        for c, t, w, a in [("on", "사용", 50, "center"), ("name", "이름", 140, "w"),
                           ("region", "박스 위치", 150, "w"), ("th", "정확도", 60, "center"),
                           ("click", "클릭", 80, "center"), ("status", "상태", 220, "w")]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c in ("name", "status")))
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_tree_double)
        self.tree.bind("<F2>", lambda e: self.rename())
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Delete>", lambda e: self.delete())

        # 아래 조작부
        bottom = ttk.Frame(root, padding=(10, 6))
        bottom.pack(fill="x")
        self.start_btn = ttk.Button(bottom, text="▶ 시작 (F9)", style="Big.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bottom, text="■ 멈춤 (F10)", style="Big.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        ttk.Label(bottom, text="  검사 간격").pack(side="left")
        self.interval_var = tk.DoubleVar(value=self.data["interval"])
        ttk.Spinbox(bottom, from_=0.1, to=60, increment=0.1, textvariable=self.interval_var, width=5,
                    command=self.save_options).pack(side="left", padx=4)
        ttk.Label(bottom, text="초").pack(side="left")
        self.return_var = tk.BooleanVar(value=self.data["return_mouse"])
        ttk.Checkbutton(bottom, text="클릭 후 마우스 제자리로", variable=self.return_var,
                        command=self.save_options).pack(side="left", padx=12)

        self.state_var = tk.StringVar(value="⏸ 멈춤")
        ttk.Label(bottom, textvariable=self.state_var, font=("Malgun Gothic", 11, "bold")).pack(side="right")

        # 기록
        logf = ttk.Frame(root, padding=(10, 0, 10, 10))
        logf.pack(fill="x")
        self.log_box = tk.Text(logf, height=6, state="disabled", bg="#F9FAFB", relief="solid", bd=1,
                               font=("Malgun Gothic", 9))
        self.log_box.pack(fill="x")

        self.refresh_list()
        hk = "F9 시작 / F10 멈춤" if pynput_keyboard else "단축키를 쓰려면 pynput 설치 필요"
        self.log(f"준비 완료. ({hk} · 비상 정지: 마우스를 화면 왼쪽 위 구석으로)")
        self.setup_hotkeys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(150, self.poll)

    # ---- 단축키 (F9 / F10)
    def setup_hotkeys(self):
        self.hotkeys = None
        if not pynput_keyboard:
            return
        try:
            self.hotkeys = pynput_keyboard.GlobalHotKeys({
                "<f9>": lambda: self.q.put(("hotkey", "start")),
                "<f10>": lambda: self.q.put(("hotkey", "stop")),
            })
            self.hotkeys.daemon = True
            self.hotkeys.start()
        except Exception as e:
            self.log(f"단축키 사용 불가: {e}")

    # ---- 목록
    def refresh_list(self):
        sel = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        for r in self.data["rules"]:
            reg = r["region"]
            thumb = self.make_thumb(r)
            status = self.status.get(r["id"], "")
            if not reg and not r["image"]:
                status = "⚠ 박스·사진 없음"
            elif not reg:
                status = "⚠ 박스 없음 (고치기에서 정하세요)"
            elif not r["image"]:
                status = "⚠ 사진 없음 (고치기에서 정하세요)"
            self.tree.insert("", "end", iid=r["id"], image=thumb or "", text="" if thumb else "(없음)", values=(
                "☑" if r["enabled"] else "☐",
                r["name"],
                f"{reg[0]},{reg[1]} ({reg[2]}×{reg[3]})" if reg else "-",
                f"{r['threshold']:.0%}",
                CLICK_NAMES.get(r["click"], ""),
                status,
            ))
        if sel and self.tree.exists(sel):
            self.tree.selection_set(sel)

    def make_thumb(self, r):
        """목록용 작은 사진 (파일이 바뀌었을 때만 새로 만듦)"""
        if not r["image"]:
            return None
        key = (r["id"], r["image"])
        if key not in self.thumbs:
            img = read_image(IMAGE_DIR / r["image"])
            self.thumbs[key] = to_photo(img, 90, 40) if img is not None else None
        return self.thumbs[key]

    def on_tree_double(self, e):
        rid = self.tree.identify_row(e.y)
        if not rid:
            return
        self.tree.selection_set(rid)
        if self.tree.identify_column(e.x) == "#2":  # 이름 칸
            self.rename()
        elif self.tree.identify_column(e.x) != "#1":
            self.edit()
        return "break"

    def rename(self):
        """목록에서 바로 이름 바꾸기 (Enter = 저장, Esc = 취소)"""
        rid = self.selected_id()
        r = self.find_rule(rid)
        if not r:
            messagebox.showinfo("알림", "이름을 바꿀 항목을 먼저 골라주세요.")
            return
        self.tree.see(rid)
        self.tree.update_idletasks()
        box = self.tree.bbox(rid, "name")
        if not box:
            return
        x, y, w, h = box
        var = tk.StringVar(value=r["name"])
        ent = ttk.Entry(self.tree, textvariable=var, font=("Malgun Gothic", 10))
        ent.place(x=x, y=y + (h - 28) // 2, width=max(w, 140), height=28)
        ent.focus_set()
        ent.select_range(0, "end")
        done = {"v": False}

        def finish(save):
            if done["v"]:
                return
            done["v"] = True
            new = var.get().strip()
            ent.destroy()
            if save and new and new != r["name"]:
                if any(o["name"] == new for o in self.data["rules"] if o is not r):
                    messagebox.showwarning("알림", f"'{new}' 이름은 이미 있어요. 다른 이름을 써주세요.")
                    return
                self.log(f"이름 변경: '{r['name']}' → '{new}' (저장됨)")
                r["name"] = new
                self.changed()

        ent.bind("<Return>", lambda e: finish(True))
        ent.bind("<KP_Enter>", lambda e: finish(True))
        ent.bind("<Escape>", lambda e: finish(False))
        ent.bind("<FocusOut>", lambda e: finish(True))

    def selected_id(self):
        s = self.tree.selection()
        return s[0] if s else None

    def find_rule(self, rid):
        return next((r for r in self.data["rules"] if r["id"] == rid), None)

    def on_tree_click(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            rid = self.tree.identify_row(e.y)
            r = self.find_rule(rid)
            if r:
                r["enabled"] = not r["enabled"]
                self.changed()
                return "break"

    def changed(self):
        save_settings(self.data)
        self.refresh_list()
        if self.watcher:  # 감시 중이면 바뀐 내용으로 다시 시작
            self.restart()

    # ---- 항목 버튼
    def add(self):
        rule = new_rule()
        rule["name"] = next_name(self.data["rules"])
        dlg = RuleDialog(self, rule)
        self.root.wait_window(dlg)
        if dlg.saved:
            self.data["rules"].append(dlg.rule)
            self.changed()
            self.tree.selection_set(dlg.rule["id"])
            self.log(f"💾 '{dlg.rule['name']}' 저장했어요. (박스 위치 + 사진)")

    def edit(self):
        r = self.find_rule(self.selected_id())
        if not r:
            messagebox.showinfo("알림", "고칠 항목을 먼저 골라주세요.")
            return
        dlg = RuleDialog(self, r)
        self.root.wait_window(dlg)
        if dlg.saved:
            old_img = r["image"]
            r.update(dlg.rule)
            if dlg.new_image and old_img and old_img != r["image"]:
                (IMAGE_DIR / old_img).unlink(missing_ok=True)
            self.changed()
            self.log(f"💾 '{r['name']}' 저장했어요.")

    def copy(self):
        r = self.find_rule(self.selected_id())
        if not r:
            messagebox.showinfo("알림", "복사할 항목을 먼저 골라주세요.")
            return
        c = dict(r)
        c["id"] = uuid.uuid4().hex[:8]
        c["name"] = next_name(self.data["rules"])
        if r["image"]:
            img = read_image(IMAGE_DIR / r["image"])
            if img is not None:
                c["image"] = f"{c['id']}_{int(time.time())}.png"
                save_image(IMAGE_DIR / c["image"], img)
        self.data["rules"].append(c)
        self.changed()

    def delete(self):
        r = self.find_rule(self.selected_id())
        if not r:
            return
        if not messagebox.askyesno("지우기", f"'{r['name']}' 항목을 지울까요?"):
            return
        self.data["rules"].remove(r)
        if r["image"]:
            (IMAGE_DIR / r["image"]).unlink(missing_ok=True)
        self.status.pop(r["id"], None)
        self.changed()

    def save_options(self):
        try:
            self.data["interval"] = max(0.1, float(self.interval_var.get()))
        except Exception:
            pass
        self.data["return_mouse"] = bool(self.return_var.get())
        save_settings(self.data)

    # ---- 시작 / 멈춤
    def start(self):
        if self.watcher:
            return
        if pyautogui is None:
            messagebox.showerror("오류", "pyautogui가 설치되지 않아 클릭할 수 없어요.")
            return
        self.save_options()
        active = [r for r in self.data["rules"] if r["enabled"]]
        if not active:
            messagebox.showinfo("알림", "켜진 항목이 없어요.\n➕ 새 항목을 만들거나 '사용' 칸을 체크하세요.")
            return
        self.watcher = Watcher(self.data["rules"], self.data["interval"], self.data["return_mouse"], self.q)
        self.watcher.start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.state_var.set("🟢 감시 중")
        self.log(f"시작! 항목 {len(active)}개 감시 중 (이 창이 박스를 가리면 못 찾아요)")

    def stop(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
            self.log("멈췄어요.")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.state_var.set("⏸ 멈춤")

    def restart(self):
        self.watcher.stop()
        self.watcher = Watcher(self.data["rules"], self.data["interval"], self.data["return_mouse"], self.q)
        self.watcher.start()

    # ---- 백그라운드 소식 받기
    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status[msg[1]] = msg[2]
                    if self.tree.exists(msg[1]):
                        self.tree.set(msg[1], "status", msg[2])
                elif kind == "log":
                    self.log(msg[1])
                elif kind == "stopped":
                    # 지금 돌고 있는 watcher가 스스로 멈춘 경우만 화면 정리
                    if msg[1] is self.watcher:
                        self.watcher = None
                        self.stop()
                elif kind == "hotkey":
                    self.start() if msg[1] == "start" else self.stop()
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 300:
            self.log_box.delete("1.0", f"{lines - 300}.0")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def on_close(self):
        if self.watcher:
            self.watcher.stop()
        if self.hotkeys:
            try:
                self.hotkeys.stop()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    if _missing:
        root.withdraw()
        messagebox.showerror(
            "설치 필요",
            "필요한 프로그램이 없어요:\n  " + ", ".join(_missing) +
            "\n\n명령창에서 아래를 실행하세요:\n  pip install -r requirements.txt")
        return
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
