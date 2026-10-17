"""화면 가운데 1픽셀 색이 바뀌면 딱 한 번 클릭하는 프로그램 (창 버전).

- 단축키(기본 F8)를 누르면 그 순간 가운데 색을 기억하고 감시 시작
- 색이 바뀌면 한 번 클릭하고 감시 꺼짐
- 감시 중에 단축키를 또 누르면 클릭 없이 감시 꺼짐
- [단축키 설정] 버튼으로 키를 바꾸고, 모든 설정은 자동 저장

사용법:
    python pixel_clicker.py
"""

import json
import time
import tkinter as tk
from pathlib import Path

import mss
import pyautogui
from pynput import keyboard

SETTINGS_FILE = Path(__file__).with_name("hotkey_settings.json")
DEFAULTS = {"hotkey": "f8", "tolerance": 10, "button": "left", "window": ""}
MODIFIERS = ["ctrl", "alt", "shift", "cmd"]
TICK_MS = 10  # 몇 ms마다 픽셀을 검사할지


# ---------- 설정 저장/불러오기 ----------

def load_settings():
    """저장된 설정을 읽는다. 없거나 깨졌으면 기본값."""
    settings = dict(DEFAULTS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        saved.setdefault("hotkey", saved.get("start_key"))  # 예전 버전 설정 이어받기
        settings.update({k: saved[k] for k in DEFAULTS if saved.get(k) is not None})
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ---------- 키 처리 ----------

def key_name(key):
    """눌린 키를 'ctrl', 'f8', 's' 같은 이름으로 바꾼다. 모르는 키는 None."""
    if isinstance(key, keyboard.Key):
        name = key.name
        for side in ("_l", "_r", "_gr"):
            if name.endswith(side):
                name = name[: -len(side)]
        return name
    vk = getattr(key, "vk", None)
    if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()  # Ctrl을 눌러도 글자 키를 제대로 읽기 위해
    if key.char and key.char.isprintable() and not key.char.isspace():
        return key.char.lower()
    return None


def make_combo(pressed):
    """누른 키 목록을 'ctrl+alt+s' 형태로. 일반 키가 정확히 1개가 아니면 None."""
    mods = [m for m in MODIFIERS if m in pressed]
    others = [k for k in pressed if k not in MODIFIERS]
    return "+".join(mods + others) if len(others) == 1 else None


def split_combo(combo):
    """'ctrl+alt+s' -> ({'ctrl', 'alt'}, 's')"""
    keys = combo.split("+")
    return {k for k in keys if k in MODIFIERS}, next(k for k in keys if k not in MODIFIERS)


# ---------- 화면 처리 ----------

def screen_center(sct):
    """주 모니터의 가운데 좌표(x, y)."""
    mon = sct.monitors[1]
    return mon["left"] + mon["width"] // 2, mon["top"] + mon["height"] // 2


def read_pixel(sct, x, y):
    """(x, y) 위치 1픽셀의 색 (R, G, B)."""
    return sct.grab({"left": x, "top": y, "width": 1, "height": 1}).pixel(0, 0)


def is_changed(a, b, tolerance):
    """두 색의 RGB 차이가 허용치보다 크면 True."""
    return max(abs(a[i] - b[i]) for i in range(3)) > tolerance


# ---------- 창 ----------

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.sct = getattr(mss, "MSS", mss.mss)()  # 새 버전 mss는 MSS 이름 사용
        self.x, self.y = screen_center(self.sct)
        self.watching = False
        self.base = None
        self.clicks = 0
        self.toggle_pressed = False  # 단축키 신호 (키보드 스레드 -> 창)
        self.hotkeys = None
        self.capturing = None        # 단축키 입력 중일 때의 키보드 리스너
        self.captured = None         # 입력 결과: 조합 문자열 또는 "" (잘못된 입력)

        pyautogui.FAILSAFE = True    # 마우스를 왼쪽 위 모서리로 옮기면 클릭 안 함
        pyautogui.PAUSE = 0

        self.build_ui()
        self.start_hotkeys()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(TICK_MS, self.tick)

    def build_ui(self):
        r = self.root
        r.title("픽셀 클릭기")
        r.resizable(False, False)
        r.attributes("-topmost", True)  # 항상 위에 (화면 가운데는 가리지 않게 오른쪽 위에 배치)
        pad = {"padx": 10, "pady": 4}

        self.status = tk.Label(r, font=("맑은 고딕", 16, "bold"), width=16)
        self.status.grid(row=0, column=0, columnspan=3, **pad)

        self.toggle_btn = tk.Button(r, text="감시 켜기 / 끄기", command=self.toggle, height=2)
        self.toggle_btn.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)

        tk.Label(r, text="단축키").grid(row=2, column=0, sticky="w", **pad)
        self.key_label = tk.Label(r, font=("맑은 고딕", 11, "bold"))
        self.key_label.grid(row=2, column=1, sticky="w")
        self.key_btn = tk.Button(r, text="단축키 설정", command=self.begin_capture)
        self.key_btn.grid(row=2, column=2, sticky="e", **pad)

        tk.Label(r, text="색 차이 허용치").grid(row=3, column=0, sticky="w", **pad)
        self.tol = tk.IntVar(value=self.settings["tolerance"])
        tk.Spinbox(r, from_=0, to=255, width=5, textvariable=self.tol,
                   command=self.save_options).grid(row=3, column=1, sticky="w")
        self.tol.trace_add("write", lambda *_: self.save_options())

        tk.Label(r, text="클릭 버튼").grid(row=4, column=0, sticky="w", **pad)
        self.button = tk.StringVar(value=self.settings["button"])
        box = tk.Frame(r)
        box.grid(row=4, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(box, text="왼쪽", value="left", variable=self.button,
                       command=self.save_options).pack(side="left")
        tk.Radiobutton(box, text="오른쪽", value="right", variable=self.button,
                       command=self.save_options).pack(side="left")

        self.log = tk.Label(r, fg="gray", anchor="w", justify="left")
        self.log.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)

        r.update_idletasks()
        r.geometry(f"+{r.winfo_screenwidth() - r.winfo_width() - 40}+40")
        try:
            wx, wy = (int(v) for v in self.settings["window"].lstrip("+").split("+"))
            if 0 <= wx < r.winfo_screenwidth() - 50 and 0 <= wy < r.winfo_screenheight() - 50:
                r.geometry(f"+{wx}+{wy}")  # 지난번 창 위치 (화면 안일 때만)
        except ValueError:
            pass
        self.refresh(f"감시 위치: 화면 가운데 ({self.x}, {self.y})")

    def refresh(self, message=None):
        key = self.settings["hotkey"].upper()
        self.key_label.config(text=key)
        if self.capturing:
            self.status.config(text="키를 누르세요...", fg="#d97706")
        elif self.watching:
            self.status.config(text="● 감시 중", fg="#16a34a")
        else:
            self.status.config(text="○ 꺼짐", fg="#6b7280")
        if message:
            self.log.config(text=message)

    # --- 단축키 ---

    def start_hotkeys(self):
        # 글자가 아니라 키 자체로 비교해서 한글 입력 상태에서도 동작
        mods, main_key = split_combo(self.settings["hotkey"])
        held = set()

        def on_press(key):
            name = key_name(key)
            if not name or name in held:  # 꾹 누르고 있을 때 반복 입력 무시
                return
            held.add(name)
            if name == main_key and held & set(MODIFIERS) == mods:
                self.toggle_pressed = True  # 키보드 스레드에서는 신호만 남김

        def on_release(key):
            held.discard(key_name(key))

        self.hotkeys = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.hotkeys.start()

    def begin_capture(self):
        """[단축키 설정] 버튼: 다음에 누르는 키 조합을 새 단축키로."""
        if self.capturing:
            return
        self.hotkeys.stop()
        self.watching = False
        pressed, held = [], set()

        def on_press(key):
            name = key_name(key)
            if name:
                if name not in pressed:
                    pressed.append(name)
                held.add(name)

        def on_release(key):
            held.discard(key_name(key))
            if pressed and not held:  # 모든 키를 떼면 입력 끝
                self.captured = make_combo(pressed) or ""
                return False

        self.capturing = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.capturing.start()
        self.key_btn.config(state="disabled")
        self.refresh("원하는 키를 누르세요 (예: F8, Ctrl+Alt+S)")

    def finish_capture(self):
        combo, self.captured, self.capturing = self.captured, None, None
        self.key_btn.config(state="normal")
        if combo:
            self.settings["hotkey"] = combo
            save_settings(self.settings)
            message = f"단축키가 {combo.upper()}(으)로 저장됐어요"
        else:
            message = "Ctrl/Alt/Shift 말고 다른 키를 1개 포함해서 눌러 주세요"
        self.start_hotkeys()
        self.refresh(message)

    # --- 감시 ---

    def toggle(self):
        if self.capturing:
            return
        self.watching = not self.watching
        if self.watching:
            self.x, self.y = screen_center(self.sct)
            self.base = read_pixel(self.sct, self.x, self.y)  # 누른 순간의 색이 기준
            self.refresh(f"기준 색 RGB{self.base}")
        else:
            self.refresh("감시를 껐어요")

    def tick(self):
        try:
            self.check()
        except Exception as e:  # 잠금 화면 등으로 화면을 못 읽어도 계속 동작
            self.watching = False
            self.refresh(f"오류로 감시를 껐어요: {e}")
        self.root.after(TICK_MS, self.tick)

    def check(self):
        if self.captured is not None:
            self.finish_capture()
        if self.toggle_pressed:
            self.toggle_pressed = False
            self.toggle()
        if self.watching:
            now = read_pixel(self.sct, self.x, self.y)
            if is_changed(self.base, now, self.safe_tolerance()):
                self.watching = False  # 한 번 클릭하면 감시 끄기
                try:
                    pyautogui.click(self.x, self.y, button=self.settings["button"])
                    self.clicks += 1
                    self.refresh(f"{time.strftime('%H:%M:%S')} 클릭! (총 {self.clicks}회)\n"
                                 f"RGB{self.base} → RGB{now}")
                except pyautogui.FailSafeException:
                    self.refresh("마우스가 왼쪽 위 모서리에 있어서 클릭을 멈췄어요")

    # --- 옵션 ---

    def safe_tolerance(self):
        try:
            return max(0, min(255, int(self.tol.get())))
        except (tk.TclError, ValueError):
            return self.settings["tolerance"]

    def save_options(self):
        self.settings["tolerance"] = self.safe_tolerance()
        self.settings["button"] = self.button.get()
        save_settings(self.settings)

    def close(self):
        self.settings["window"] = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
        self.save_options()
        self.hotkeys.stop()
        if self.capturing:
            self.capturing.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
