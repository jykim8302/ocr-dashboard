"""
화면 이미지 자동 클릭기
------------------------------------------------------------
1) 화면에서 '감시할 박스(영역)'를 드래그로 정합니다.
2) 찾을 것을 정합니다: 사진(화면 캡처/파일) 또는 글자(예: "확인").
3) 클릭할 곳을 정합니다: 찾은 곳 가운데 / 거기서 옆으로 / 화면의 정해진 좌표.
4) [시작]을 누르면, 박스 안에서 찾을 때마다 자동으로 클릭합니다.
   - 항목은 여러 개 만들 수 있습니다.
   - F9 = 시작, F10 = 멈춤 (pynput 설치 시)
   - 비상 정지: 마우스를 화면 왼쪽 위 구석으로 밀면 멈춥니다.
"""

import asyncio
import ctypes
import difflib
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
# 글자 인식 (OCR)
#  - Windows: 윈도우에 들어있는 글자 인식 기능 사용 (따로 설치할 것 없음)
#  - 그 밖에: Tesseract(pytesseract)가 설치되어 있으면 사용
# ============================================================
def _import_winrt():
    """pywinrt(winrt) 또는 예전 이름(winsdk) 중 있는 것으로 불러오기"""
    for base in ("winrt", "winsdk"):
        try:
            ocr = __import__(f"{base}.windows.media.ocr", fromlist=["OcrEngine"])
            glob = __import__(f"{base}.windows.globalization", fromlist=["Language"])
            img = __import__(f"{base}.windows.graphics.imaging", fromlist=["SoftwareBitmap"])
            streams = __import__(f"{base}.windows.storage.streams", fromlist=["DataWriter"])
            return ocr, glob, img, streams
        except Exception:
            continue
    return None


class TextReader:
    """박스 화면에서 글자와 글자 위치를 읽어 줌."""

    def __init__(self):
        self.kind = None
        self.lang_name = ""
        self.error = ""
        self._local = threading.local()
        if sys.platform == "win32":
            mods = _import_winrt()
            if mods:
                self._ocr, self._glob, self._img, self._streams = mods
                try:
                    eng = self._make_engine()
                    if eng is not None:
                        self.kind = "windows"
                        self._local.engine = eng
                except Exception as e:
                    self.error = f"Windows 글자 인식 오류: {e}"
            else:
                self.error = "Windows 글자 인식 모듈(winrt)이 설치되지 않았어요."
        if self.kind is None:
            try:
                import pytesseract

                pytesseract.get_tesseract_version()
                langs = pytesseract.get_languages(config="")
                self._tess = pytesseract
                self._tess_lang = "+".join(l for l in ("kor", "eng") if l in langs) or "eng"
                self.kind = "tesseract"
                self.lang_name = self._tess_lang
            except Exception:
                if not self.error:
                    self.error = "글자 인식 기능을 찾지 못했어요."

    @property
    def ok(self):
        return self.kind is not None

    def describe(self):
        if self.kind == "windows":
            return f"Windows 글자 인식 ({self.lang_name})"
        if self.kind == "tesseract":
            return f"Tesseract ({self.lang_name})"
        return self.error

    # ---- Windows
    def _make_engine(self):
        OcrEngine = self._ocr.OcrEngine
        eng = None
        try:
            ko = self._glob.Language("ko")
            if OcrEngine.is_language_supported(ko):
                eng = OcrEngine.try_create_from_language(ko)
                self.lang_name = "한국어"
        except Exception:
            eng = None
        if eng is None:
            eng = OcrEngine.try_create_from_user_profile_languages()
            if eng is not None:
                try:
                    self.lang_name = eng.recognizer_language.display_name
                except Exception:
                    self.lang_name = "기본 언어"
        if eng is None:
            self.error = "Windows에 글자 인식 언어가 없어요. (설정 > 시간 및 언어 > 언어에서 한국어 추가)"
        return eng

    def _engine(self):
        eng = getattr(self._local, "engine", None)
        if eng is None:  # 다른 스레드에서는 새로 만들어 씀
            eng = self._make_engine()
            self._local.engine = eng
        return eng

    async def _win_recognize(self, bgra, w, h):
        img = self._img
        data = bgra.tobytes()
        bitmap = img.SoftwareBitmap(img.BitmapPixelFormat.BGRA8, w, h)
        try:
            bitmap.copy_from_buffer(data)  # winrt 3.x 이상: 바이트를 바로 넣을 수 있음
        except TypeError:  # 예전 버전: DataWriter로 버퍼를 만들어서 넣기
            writer = self._streams.DataWriter()
            try:
                writer.write_bytes(data)
            except TypeError:
                writer.write_bytes(list(data))
            bitmap.copy_from_buffer(writer.detach_buffer())
        return await self._engine().recognize_async(bitmap)

    def _read_windows(self, img_bgr):
        h, w = img_bgr.shape[:2]
        try:
            max_dim = int(self._ocr.OcrEngine.max_image_dimension)
        except Exception:
            max_dim = 2600
        # 작은 글자는 크게 키우면 더 잘 읽음
        scale = 1.0
        if max(w, h) * 2 <= max_dim and h < 400:
            scale = 2.0
        elif max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
        if scale != 1.0:
            img_bgr = cv2.resize(img_bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                                 interpolation=cv2.INTER_CUBIC)
        sh, sw = img_bgr.shape[:2]
        bgra = np.ascontiguousarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA))
        result = asyncio.run(self._win_recognize(bgra, sw, sh))
        lines = []
        for line in result.lines:
            words = []
            for word in line.words:
                r = word.bounding_rect
                words.append((word.text, r.x / scale, r.y / scale, r.width / scale, r.height / scale))
            if words:
                lines.append(words)
        return lines

    # ---- Tesseract
    def _read_tesseract(self, img_bgr):
        scale = 2.0 if img_bgr.shape[0] < 400 else 1.0
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)  # 흑백이 더 잘 읽힘
        if scale != 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        d = self._tess.image_to_data(gray, lang=self._tess_lang, config="--psm 11",  # 흩어진 글자(화면 버튼) 모드
                                     output_type=self._tess.Output.DICT)
        groups = {}
        for i, txt in enumerate(d["text"]):
            if not str(txt).strip():
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            groups.setdefault(key, []).append((str(txt), d["left"][i] / scale, d["top"][i] / scale,
                                               d["width"][i] / scale, d["height"][i] / scale))
        return list(groups.values())

    def read(self, img_bgr):
        """반환: 줄 목록. 줄 = [(글자, x, y, 폭, 높이), ...]"""
        if self.kind == "windows":
            return self._read_windows(img_bgr)
        if self.kind == "tesseract":
            return self._read_tesseract(img_bgr)
        return []


_reader = None
_reader_lock = threading.Lock()


def get_reader():
    """글자 인식기는 처음 쓸 때 한 번만 준비"""
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = TextReader()
        return _reader


def _norm(s):
    """띄어쓰기 없애고 소문자로 → 비교하기 쉽게"""
    return "".join(str(s).split()).lower()


def find_text(lines, target):
    """
    읽은 글자(lines) 안에서 target 글자를 찾음.
    반환: (비슷한 정도 0~1, (중심x, 중심y), (폭, 높이)) / 글자가 하나도 없으면 None
    띄어쓰기·대소문자는 무시하고, 한두 글자 틀린 것도 비슷한 정도로 계산.
    """
    t = _norm(target)
    if not t:
        return None
    best = None  # (점수, 줄번호, 시작, 끝)
    joined_lines = []
    for li, words in enumerate(lines):
        joined, owner = "", []
        for wi, w in enumerate(words):
            n = _norm(w[0])
            joined += n
            owner += [wi] * len(n)
        joined_lines.append((joined, owner))
        if not joined:
            continue
        pos = joined.find(t)
        if pos >= 0:
            best = (1.0, li, pos, pos + len(t))
            break
        # 정확히 없으면 비슷한 부분 찾기 (같은 길이, 한 글자 더 긴 것)
        sizes = {len(t), len(t) + 1} | ({len(t) - 1} if len(t) >= 4 else set())
        for size in sizes:
            for start in range(0, max(1, len(joined) - size + 1)):
                piece = joined[start:start + size]
                score = difflib.SequenceMatcher(None, t, piece).ratio()
                if best is None or score > best[0]:
                    best = (score, li, start, start + len(piece))
    if best is None:
        return None
    score, li, s, e = best
    words = lines[li]
    owner = joined_lines[li][1]
    idx = sorted(set(owner[s:e])) or [0]
    x1 = min(words[i][1] for i in idx)
    y1 = min(words[i][2] for i in idx)
    x2 = max(words[i][1] + words[i][3] for i in idx)
    y2 = max(words[i][2] + words[i][4] for i in idx)
    return float(score), (int((x1 + x2) / 2), int((y1 + y2) / 2)), (int(x2 - x1), int(y2 - y1))


def lines_to_text(lines):
    return "\n".join(" ".join(w[0] for w in words) for words in lines)


# ============================================================
# 설정 저장 / 불러오기
# ============================================================
def new_rule():
    return {
        "id": uuid.uuid4().hex[:8],
        "name": "",
        "enabled": True,
        "region": None,  # [x, y, w, h]
        "mode": "image",  # image = 사진 찾기, text = 글자 찾기
        "image": "",  # images/ 폴더 안의 파일 이름
        "text": "",  # 찾을 글자
        "threshold": 0.85,
        "click": "left",
        "cooldown": 2.0,
        "click_pos": "center",  # center = 찾은 곳 가운데, offset = 거기서 옆으로, fixed = 정해진 좌표
        "offset": [0, 0],
        "fixed": None,  # [x, y]
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
# 찾을 것 / 클릭할 곳
# ============================================================
CLICK_POS_NAMES = {"center": "찾은 곳 가운데", "offset": "찾은 곳에서 옆으로", "fixed": "화면의 정해진 곳"}


def has_target(r):
    """찾을 것(사진 또는 글자)이 정해졌는지"""
    return bool(r["text"].strip()) if r["mode"] == "text" else bool(r["image"])


def click_point(r, cx, cy):
    """찾은 곳 가운데(cx, cy) → 실제로 누를 화면 좌표"""
    if r["click_pos"] == "fixed" and r["fixed"]:
        return r["fixed"][0], r["fixed"][1]
    if r["click_pos"] == "offset":
        return cx + r["offset"][0], cy + r["offset"][1]
    return cx, cy


def click_desc(r):
    kind = CLICK_NAMES.get(r["click"], "")
    if r["click_pos"] == "fixed" and r["fixed"]:
        return f"{kind} · ({r['fixed'][0]},{r['fixed'][1]})"
    if r["click_pos"] == "offset":
        dx, dy = r["offset"]
        return f"{kind} · 옆으로 {dx:+d},{dy:+d}"
    return f"{kind} · 가운데"


def search_in(shot, r, template, reader):
    """박스 화면(shot)에서 찾기 → (점수, (중심x, 중심y), (폭, 높이), 읽은글자) / None"""
    if r["mode"] == "text":
        lines = reader.read(shot)
        found = find_text(lines, r["text"])
        if found is None:
            return 0.0, None, None, lines_to_text(lines)
        return found + (lines_to_text(lines),)
    found = find_image(shot, template)
    if found is None:
        return None
    return found + ("",)


# ============================================================
# 감시(백그라운드) 작업
# ============================================================
class Watcher(threading.Thread):
    def __init__(self, rules, interval, return_mouse, out_q):
        super().__init__(daemon=True)
        self.rules = [dict(r) for r in rules if r["enabled"] and r["region"] and has_target(r)]
        self.interval = max(0.05, float(interval))
        self.return_mouse = return_mouse
        self.out_q = out_q
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        templates = {}
        reader = None
        rules = []
        for r in self.rules:
            if r["mode"] == "text":
                if reader is None:
                    reader = get_reader()
                if not reader.ok:
                    self.out_q.put(("log", f"[{r['name']}] 글자 인식을 쓸 수 없어 건너뜁니다. ({reader.describe()})"))
                    continue
            else:
                img = read_image(IMAGE_DIR / r["image"])
                if img is None:
                    self.out_q.put(("log", f"[{r['name']}] 사진 파일을 못 읽어서 건너뜁니다."))
                    continue
                templates[r["id"]] = img
            rules.append(r)
        if not rules:
            self.out_q.put(("log", "감시할 항목이 없어요. (사용 체크 / 박스 / 찾을 것 확인)"))
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
                        found = search_in(shot, r, templates.get(r["id"]), reader)
                        n = counts.get(r["id"], 0)
                        if found is None:
                            self.out_q.put(("status", r["id"], "박스가 사진보다 작아요"))
                            continue
                        score, center = found[0], found[1]
                        if center is not None and score >= r["threshold"]:
                            if time.time() - last_click.get(r["id"], 0) >= r["cooldown"]:
                                px, py = click_point(r, x + center[0] / scale, y + center[1] / scale)
                                do_click(px, py, r["click"], self.return_mouse)
                                last_click[r["id"]] = time.time()
                                n = counts[r["id"]] = n + 1
                                self.out_q.put(("log", f"[{r['name']}] 클릭! (일치 {score:.0%}, 좌표 {int(px)},{int(py)})"))
                            self.out_q.put(("status", r["id"], f"찾음 {score:.0%} · 클릭 {n}회"))
                        else:
                            self.out_q.put(("status", r["id"], f"대기 중 ({score:.0%}) · 클릭 {n}회"))
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
def select_on_screen(root, hide_windows, message, hint_region=None, point=False):
    """
    잠깐 창을 숨기고 전체 화면을 찍은 뒤, 그 위에서 드래그로 박스를 고릅니다.
    반환: (x, y, w, h, 잘라낸이미지BGR) 또는 None(취소)
    point=True 이면 한 번 누른 곳의 좌표 (x, y)를 돌려줍니다.
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
        if point:
            state["result"] = (e.x + left, e.y + top)
            top_win.destroy()
            return
        state["start"] = (e.x, e.y)
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#EF4444", width=3)

    def on_move(e):
        if point:
            canvas.delete("pt")
            canvas.create_line(e.x - 14, e.y, e.x + 15, e.y, fill="#EF4444", width=2, tags="pt")
            canvas.create_line(e.x, e.y - 14, e.x, e.y + 15, fill="#EF4444", width=2, tags="pt")
            canvas.create_text(e.x + 14, e.y + 14, anchor="nw", text=f"{e.x + left}, {e.y + top}",
                               fill="#FACC15", font=("Malgun Gothic", 11, "bold"), tags="pt")
        elif state["start"]:
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
    canvas.bind("<Motion>", lambda e: on_move(e) if point else None)
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
        pad = {"padx": 10, "pady": 5}
        bold = ("Malgun Gothic", 10, "bold")

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        # 이름
        ttk.Label(frm, text="이름").grid(row=0, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value=rule["name"])
        ttk.Entry(frm, textvariable=self.name_var, width=34).grid(row=0, column=1, columnspan=2, sticky="we", **pad)

        # ① 감시 박스
        ttk.Label(frm, text="① 감시할 박스", font=bold).grid(row=1, column=0, sticky="w", **pad)
        reg_box = ttk.Frame(frm)
        reg_box.grid(row=1, column=1, sticky="w", **pad)
        self.reg_vars = []
        for i, t in enumerate(("X", "Y", "폭", "높이")):
            ttk.Label(reg_box, text=t).grid(row=0, column=i * 2, padx=(0 if i == 0 else 6, 2))
            v = tk.IntVar(value=0)
            ttk.Spinbox(reg_box, from_=-20000, to=20000, textvariable=v, width=5).grid(row=0, column=i * 2 + 1)
            self.reg_vars.append(v)
        ttk.Button(frm, text="📐 화면에서 박스 그리기", command=self.pick_region).grid(row=1, column=2, sticky="we", **pad)

        # ② 찾을 것: 사진 / 글자
        ttk.Label(frm, text="② 찾을 것", font=bold).grid(row=2, column=0, sticky="nw", **pad)
        self.mode_var = tk.StringVar(value=rule["mode"])
        mode_box = ttk.Frame(frm)
        mode_box.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        ttk.Radiobutton(mode_box, text="🖼 사진", value="image", variable=self.mode_var,
                        command=self.show_mode).pack(side="left")
        ttk.Radiobutton(mode_box, text="🔤 글자", value="text", variable=self.mode_var,
                        command=self.show_mode).pack(side="left", padx=14)

        # 사진 칸
        self.img_frame = ttk.Frame(frm)
        self.img_frame.grid(row=3, column=0, columnspan=3, sticky="we")
        self.img_frame.columnconfigure(1, weight=1)
        self.preview = tk.Label(self.img_frame, text="(아직 없음)", width=28, height=6, relief="groove", bg="#F3F4F6")
        self.preview.grid(row=0, column=1, rowspan=2, sticky="w", **pad)
        ttk.Button(self.img_frame, text="✂ 화면에서 캡처", command=self.capture_image).grid(row=0, column=2, sticky="we", **pad)
        ttk.Button(self.img_frame, text="📂 사진 파일 올리기", command=self.upload_image).grid(row=1, column=2, sticky="nwe", **pad)
        ttk.Label(self.img_frame, text="", width=14).grid(row=0, column=0)

        # 글자 칸
        self.txt_frame = ttk.Frame(frm)
        self.txt_frame.grid(row=3, column=0, columnspan=3, sticky="we")
        ttk.Label(self.txt_frame, text="", width=14).grid(row=0, column=0)
        self.text_var = tk.StringVar(value=rule["text"])
        ttk.Entry(self.txt_frame, textvariable=self.text_var, width=30,
                  font=("Malgun Gothic", 11)).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(self.txt_frame, text="이 글자가 박스 안에 보이면 클릭해요.\n띄어쓰기·대소문자는 무시해요.",
                  foreground="gray").grid(row=1, column=1, sticky="w", padx=10)
        self.engine_var = tk.StringVar(value="글자 인식: 확인 중…")
        ttk.Label(self.txt_frame, textvariable=self.engine_var, foreground="#2563EB").grid(
            row=2, column=1, sticky="w", padx=10, pady=(2, 4))

        ttk.Separator(frm).grid(row=4, column=0, columnspan=3, sticky="we", pady=6)

        # 정확도
        ttk.Label(frm, text="얼마나 똑같아야 클릭?").grid(row=5, column=0, sticky="w", **pad)
        self.th_var = tk.IntVar(value=int(round(rule["threshold"] * 100)))
        th_box = ttk.Frame(frm)
        th_box.grid(row=5, column=1, columnspan=2, sticky="we", **pad)
        self.th_label = ttk.Label(th_box, width=5)
        ttk.Scale(th_box, from_=50, to=100, variable=self.th_var, length=220,
                  command=lambda v: self.th_label.config(text=f"{int(float(v))}%")).pack(side="left")
        self.th_label.pack(side="left", padx=6)
        self.th_label.config(text=f"{self.th_var.get()}%")
        ttk.Label(th_box, text="(보통 85%)", foreground="gray").pack(side="left")

        # 클릭 방법
        ttk.Label(frm, text="클릭 방법").grid(row=6, column=0, sticky="w", **pad)
        self.click_var = tk.StringVar(value=CLICK_NAMES.get(rule["click"], "왼쪽 클릭"))
        ttk.Combobox(frm, textvariable=self.click_var, values=list(CLICK_TYPES), state="readonly",
                     width=12).grid(row=6, column=1, sticky="w", **pad)

        # ③ 클릭할 곳
        ttk.Label(frm, text="③ 클릭할 곳", font=bold).grid(row=7, column=0, sticky="nw", **pad)
        pos_box = ttk.Frame(frm)
        pos_box.grid(row=7, column=1, columnspan=2, sticky="w", **pad)
        self.pos_var = tk.StringVar(value=rule["click_pos"])
        ttk.Radiobutton(pos_box, text="찾은 곳 가운데", value="center", variable=self.pos_var,
                        command=self.show_pos).grid(row=0, column=0, sticky="w")

        ttk.Radiobutton(pos_box, text="찾은 곳에서 옆으로", value="offset", variable=self.pos_var,
                        command=self.show_pos).grid(row=1, column=0, sticky="w", pady=3)
        off = ttk.Frame(pos_box)
        off.grid(row=1, column=1, sticky="w", padx=6)
        self.off_vars = [tk.IntVar(value=rule["offset"][0]), tk.IntVar(value=rule["offset"][1])]
        self.off_widgets = []
        for i, t in enumerate(("오른쪽", "아래")):
            ttk.Label(off, text=t).pack(side="left", padx=(0 if i == 0 else 6, 2))
            sp = ttk.Spinbox(off, from_=-5000, to=5000, textvariable=self.off_vars[i], width=5)
            sp.pack(side="left")
            self.off_widgets.append(sp)
        ttk.Label(off, text="픽셀 (반대쪽은 -)", foreground="gray").pack(side="left", padx=4)

        ttk.Radiobutton(pos_box, text="화면의 정해진 곳", value="fixed", variable=self.pos_var,
                        command=self.show_pos).grid(row=2, column=0, sticky="w")
        fix = ttk.Frame(pos_box)
        fix.grid(row=2, column=1, sticky="w", padx=6)
        fx, fy = rule["fixed"] or (0, 0)
        self.fix_vars = [tk.IntVar(value=fx), tk.IntVar(value=fy)]
        self.fix_widgets = []
        for i, t in enumerate(("X", "Y")):
            ttk.Label(fix, text=t).pack(side="left", padx=(0 if i == 0 else 6, 2))
            sp = ttk.Spinbox(fix, from_=-20000, to=20000, textvariable=self.fix_vars[i], width=6)
            sp.pack(side="left")
            self.fix_widgets.append(sp)
        self.fix_btn = ttk.Button(fix, text="📍 화면에서 찍기", command=self.pick_point)
        self.fix_btn.pack(side="left", padx=6)

        # 쉬는 시간
        ttk.Label(frm, text="한 번 클릭 후 쉬는 시간").grid(row=8, column=0, sticky="w", **pad)
        cd_box = ttk.Frame(frm)
        cd_box.grid(row=8, column=1, sticky="w", **pad)
        self.cd_var = tk.DoubleVar(value=rule["cooldown"])
        ttk.Spinbox(cd_box, from_=0, to=3600, increment=0.5, textvariable=self.cd_var, width=7).pack(side="left")
        ttk.Label(cd_box, text="초").pack(side="left", padx=4)

        ttk.Separator(frm).grid(row=9, column=0, columnspan=3, sticky="we", pady=6)

        # 다른 번호에 저장된 것 가져오기
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
            ttk.Button(imp, text="찾을 것만", command=lambda: self.import_from("target")).pack(side="left", padx=4)
            ttk.Button(imp, text="클릭할 곳만", command=lambda: self.import_from("click")).pack(side="left")
            ttk.Button(imp, text="전부", command=lambda: self.import_from("all")).pack(side="left", padx=4)

        btns = ttk.Frame(frm)
        btns.grid(row=11, column=0, columnspan=3, sticky="we", pady=(6, 0))
        ttk.Button(btns, text="🔍 지금 찾아보기(테스트)", command=self.test).pack(side="left")
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="💾 저장", command=self.save).pack(side="right", padx=6)

        self.set_region(rule["region"])
        self.refresh()
        self.show_mode()
        self.show_pos()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

    # ---- 화면 갱신
    def show_mode(self):
        if self.mode_var.get() == "text":
            self.img_frame.grid_remove()
            self.txt_frame.grid()
            reader = get_reader()
            self.engine_var.set(("✅ 글자 인식: " if reader.ok else "⚠ ") + reader.describe())
        else:
            self.txt_frame.grid_remove()
            self.img_frame.grid()

    def show_pos(self):
        p = self.pos_var.get()
        for wdg in self.off_widgets:
            wdg.config(state="normal" if p == "offset" else "disabled")
        for wdg in self.fix_widgets + [self.fix_btn]:
            wdg.config(state="normal" if p == "fixed" else "disabled")

    def get_region(self):
        try:
            x, y, w, h = (int(v.get()) for v in self.reg_vars)
        except Exception:
            return None
        return [x, y, w, h] if w > 0 and h > 0 else None

    def set_region(self, r):
        for v, n in zip(self.reg_vars, r or (0, 0, 0, 0)):
            v.set(int(n))

    def get_ints(self, vars_, default=0):
        out = []
        for v in vars_:
            try:
                out.append(int(v.get()))
            except Exception:
                out.append(default)
        return out

    def refresh(self):
        if self.template is not None:
            self.photo = to_photo(self.template, 200, 90)
            self.preview.config(image=self.photo, text="", width=200, height=90)
        else:
            self.preview.config(image="", text="(아직 없음)", width=28, height=6)

    def import_from(self, what):
        src = self.others.get(self.import_var.get())
        if not src:
            messagebox.showinfo("알림", "가져올 번호를 먼저 골라주세요.", parent=self)
            return
        if what in ("region", "all") and src["region"]:
            self.set_region(src["region"])
        if what in ("target", "all"):
            self.mode_var.set(src["mode"])
            self.text_var.set(src["text"])
            img = read_image(IMAGE_DIR / src["image"]) if src["image"] else None
            if img is not None:
                self.template = img
                self.new_image = True
                self.refresh()
            self.show_mode()
        if what in ("click", "all"):
            self.pos_var.set(src["click_pos"])
            for v, n in zip(self.off_vars, src["offset"]):
                v.set(n)
            if src["fixed"]:
                for v, n in zip(self.fix_vars, src["fixed"]):
                    v.set(n)
            self.click_var.set(CLICK_NAMES.get(src["click"], "왼쪽 클릭"))
            self.show_pos()

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
                               "② 찾을 사진(버튼 등)만 딱 맞게 드래그하세요",
                               hint_region=self.get_region())
        self.grab_set()
        if res:
            x, y, w, h, crop = res
            self.template = crop
            self.new_image = True
            if not self.get_region():
                # 박스를 안 정했으면 사진 주변을 넉넉하게 박스로 잡아줌
                m = 40
                self.set_region([x - m, y - m, w + 2 * m, h + 2 * m])
            self.refresh()

    def pick_point(self):
        res = select_on_screen(self.app.root, [self, self.app.root],
                               "③ 클릭할 곳을 한 번 누르세요", hint_region=self.get_region(), point=True)
        self.grab_set()
        if res:
            self.fix_vars[0].set(int(res[0]))
            self.fix_vars[1].set(int(res[1]))

    def upload_image(self):
        path = filedialog.askopenfilename(
            parent=self, title="찾을 사진 고르기",
            filetypes=[("사진 파일", "*.png *.jpg *.jpeg *.bmp"), ("모든 파일", "*.*")])
        if not path:
            return
        img = read_image(path)
        if img is None:
            messagebox.showerror("오류", "사진 파일을 읽지 못했어요.", parent=self)
            return
        self.template = img
        self.new_image = True
        self.refresh()

    def collect(self):
        """창에 입력한 값으로 항목 내용 채우기"""
        r = self.rule
        r["region"] = self.get_region()
        r["mode"] = self.mode_var.get()
        r["text"] = self.text_var.get().strip()
        r["threshold"] = self.th_var.get() / 100
        r["click"] = CLICK_TYPES.get(self.click_var.get(), "left")
        r["click_pos"] = self.pos_var.get()
        r["offset"] = self.get_ints(self.off_vars)
        fixed = self.get_ints(self.fix_vars)
        r["fixed"] = fixed if (r["click_pos"] == "fixed" or r["fixed"]) else None
        try:
            r["cooldown"] = max(0.0, float(self.cd_var.get()))
        except Exception:
            r["cooldown"] = 2.0
        return r

    def test(self):
        r = dict(self.collect())
        is_text = r["mode"] == "text"
        if not r["region"] or (is_text and not r["text"]) or (not is_text and self.template is None):
            messagebox.showinfo("알림", "① 박스와 ② 찾을 것(사진 또는 글자)을 먼저 정해주세요.", parent=self)
            return
        reader = get_reader() if is_text else None
        if is_text and not reader.ok:
            messagebox.showwarning("알림", reader.describe(), parent=self)
            return
        x, y, w, h = r["region"]
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
        try:
            found = search_in(shot, r, self.template, reader)
        except Exception as e:
            messagebox.showerror("오류", f"찾는 중 오류가 났어요.\n{e}", parent=self)
            return
        if found is None:
            messagebox.showwarning("결과", "박스가 사진보다 작아요.\n박스를 더 크게 그려주세요.", parent=self)
            return
        score, center, size, read_text = found
        th = r["threshold"]
        ok = center is not None and score >= th
        scale = shot.shape[1] / float(w)
        view = shot.copy()
        click_msg = ""
        if center is not None:
            cx, cy = center
            tw, th_px = size
            color = (80, 200, 0) if ok else (0, 0, 255)
            cv2.rectangle(view, (cx - tw // 2, cy - th_px // 2), (cx + tw // 2, cy + th_px // 2), color, 2)
            px, py = click_point(r, x + cx / scale, y + cy / scale)
            click_msg = f"\n누를 좌표: {int(px)}, {int(py)}"
            # 누를 곳을 빨간 십자로 표시 (박스 안일 때)
            vx, vy = int((px - x) * scale), int((py - y) * scale)
            if 0 <= vx < view.shape[1] and 0 <= vy < view.shape[0]:
                cv2.drawMarker(view, (vx, vy), (0, 0, 255), cv2.MARKER_CROSS, 18, 2)
            else:
                click_msg += " (박스 밖)"
        if ok:
            msg = f"✅ 찾았어요!  일치 {score:.0%}  (기준 {th:.0%}){click_msg}"
        elif center is None:
            msg = "❌ 박스 안에서 글자를 하나도 못 읽었어요."
        else:
            msg = f"❌ 못 찾았어요.  가장 비슷한 곳 {score:.0%}  (기준 {th:.0%})"
        win = tk.Toplevel(self)
        win.title("테스트 결과")
        win.transient(self)
        ttk.Label(win, text=msg, padding=10, foreground="#15803D" if ok else "#B91C1C",
                  font=("Malgun Gothic", 10, "bold")).pack()
        ph = to_photo(view, 640, 380)
        lbl = tk.Label(win, image=ph)
        lbl.image = ph
        lbl.pack(padx=10)
        if is_text:
            ttk.Label(win, text="읽은 글자:", padding=(10, 6, 10, 0)).pack(anchor="w")
            box = tk.Text(win, height=4, width=70, font=("Malgun Gothic", 9), bg="#F9FAFB")
            box.insert("1.0", read_text or "(없음)")
            box.config(state="disabled")
            box.pack(padx=10)
        ttk.Button(win, text="확인", command=win.destroy).pack(pady=10)
        win.grab_set()

    def save(self):
        r = self.collect()
        is_text = r["mode"] == "text"
        target_ok = bool(r["text"]) if is_text else self.template is not None
        if not r["region"] and not target_ok:
            messagebox.showinfo("알림", "① 박스나 ② 찾을 것 중 하나는 정해주세요.", parent=self)
            return
        if r["region"] and target_ok and not is_text:
            th_px, tw = self.template.shape[:2]
            if tw > r["region"][2] or th_px > r["region"][3]:
                if not messagebox.askyesno("확인", "사진이 박스보다 커서 찾을 수 없어요.\n그래도 저장할까요?", parent=self):
                    return
        if r["click_pos"] == "fixed" and r["fixed"] == [0, 0]:
            if not messagebox.askyesno("확인", "클릭할 곳이 (0, 0)이에요.\n📍 화면에서 찍기로 정하는 걸 추천해요.\n그래도 저장할까요?", parent=self):
                return
        others = [o for o in self.app.data["rules"] if o["id"] != r["id"]]
        r["name"] = self.name_var.get().strip() or next_name(others)
        if self.new_image and self.template is not None:
            IMAGE_DIR.mkdir(exist_ok=True)
            fname = f"{r['id']}_{int(time.time())}.png"
            save_image(IMAGE_DIR / fname, self.template)
            r["image"] = fname
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
        root.geometry("920x580")
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
        self.tree.heading("#0", text="찾을 것")
        self.tree.column("#0", width=100, stretch=False, anchor="center")
        for c, t, w, a in [("on", "사용", 50, "center"), ("name", "이름", 140, "w"),
                           ("region", "박스 위치", 150, "w"), ("th", "정확도", 60, "center"),
                           ("click", "클릭", 150, "w"), ("status", "상태", 220, "w")]:
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
            thumb = self.make_thumb(r) if r["mode"] == "image" else None
            if r["mode"] == "text":
                label = f"🔤 {r['text']}" if r["text"] else "(없음)"
            else:
                label = "" if thumb else "(없음)"
            status = self.status.get(r["id"], "")
            if not reg and not has_target(r):
                status = "⚠ 박스·찾을 것 없음"
            elif not reg:
                status = "⚠ 박스 없음 (고치기에서 정하세요)"
            elif not has_target(r):
                status = "⚠ 찾을 것 없음 (고치기에서 정하세요)"
            self.tree.insert("", "end", iid=r["id"], image=thumb or "", text=label, values=(
                "☑" if r["enabled"] else "☐",
                r["name"],
                f"{reg[0]},{reg[1]} ({reg[2]}×{reg[3]})" if reg else "-",
                f"{r['threshold']:.0%}",
                click_desc(r),
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
            self.log(f"💾 '{dlg.rule['name']}' 저장했어요.")

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
