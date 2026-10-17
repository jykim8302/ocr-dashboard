"""Windows 실제 동작 테스트 (GitHub Actions의 Windows 컴퓨터에서 실행).

진짜 키 입력과 진짜 마우스 클릭으로 아래를 확인한다.
- 단축키로 감시 켜기 -> 색이 바뀌면 한 번 클릭 -> 꺼짐
- 단축키로 켰다 끄면 색이 바뀌어도 클릭 안 함
- 단축키를 꾹 눌러도 한 번만 켜짐
- [단축키 설정] 버튼으로 Ctrl+Alt+S 지정 -> 파일에 저장 -> 그 키로만 동작
- 창을 닫으면 창 위치까지 저장
"""

import json
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path

import mss
import mss.tools
from pynput import keyboard, mouse

sys.path.insert(0, str(Path(__file__).parent))
import pixel_clicker as pc  # noqa: E402

OUT = Path(__file__).parent / "test_output"
OUT.mkdir(exist_ok=True)
pc.SETTINGS_FILE = Path(tempfile.mkdtemp()) / "hotkey_settings.json"
pc.SETTINGS_FILE.write_text(json.dumps({"hotkey": "f8"}), encoding="utf-8")

root = tk.Tk()
app = pc.App(root)

# 화면 가운데에 색이 바뀌는 사각형 (클릭되면 기록)
clicks = []
target = tk.Toplevel(root)
target.overrideredirect(True)
target.attributes("-topmost", True)
target.geometry(f"300x300+{app.x - 150}+{app.y - 150}")
canvas = tk.Canvas(target, bg="blue", highlightthickness=0)
canvas.pack(fill="both", expand=True)
canvas.bind("<Button-1>", lambda e: clicks.append(time.time()))

# 테스트 스레드 -> 창(메인 스레드)에 일 시키기
jobs = queue.Queue()


def poll():
    while not jobs.empty():
        fn, box, done = jobs.get()
        box.append(fn())
        done.set()
    try:
        root.after(20, poll)
    except tk.TclError:  # 창이 이미 닫힘
        pass


def ui(fn):
    box, done = [], threading.Event()
    jobs.put((fn, box, done))
    done.wait(5)
    return box[0] if box else None


results = []


def check(name, ok):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}", flush=True)


def shot(name):
    with mss.mss() as s:
        img = s.grab(s.monitors[1])
        mss.tools.to_png(img.rgb, img.size, output=str(OUT / f"{name}.png"))


kb = keyboard.Controller()
K = keyboard.Key


def tap(key, wait=0.6):
    kb.press(key)
    kb.release(key)
    time.sleep(wait)


def set_color(color, wait=0.8):
    ui(lambda: canvas.config(bg=color))
    time.sleep(wait)


closed = []


def scenario():
    try:
        time.sleep(2)
        mouse.Controller().position = (200, 300)  # 왼쪽 위 모서리(안전장치) 피하기
        print(f"화면 가운데: ({app.x}, {app.y})", flush=True)

        tap(K.f8)
        check("F8 -> 감시 켜짐", app.watching)
        shot("1_watching")
        set_color("red")
        check("색 바뀜 -> 1번 클릭", len(clicks) == 1)
        check("클릭 후 감시 꺼짐", not app.watching)

        tap(K.f8)
        tap(K.f8)
        check("F8 두 번 -> 꺼짐", not app.watching)
        set_color("green")
        check("꺼진 상태에선 클릭 안 함", len(clicks) == 1)

        kb.press(K.f8)
        time.sleep(1.5)
        kb.release(K.f8)
        time.sleep(0.5)
        check("F8 꾹 눌러도 한 번만 -> 켜짐", app.watching)
        tap(K.f8)

        # [단축키 설정] 버튼을 진짜 마우스로 클릭
        bx, by = ui(lambda: (app.key_btn.winfo_rootx() + app.key_btn.winfo_width() // 2,
                             app.key_btn.winfo_rooty() + app.key_btn.winfo_height() // 2))
        m = mouse.Controller()
        m.position = (bx, by)
        time.sleep(0.2)
        m.click(mouse.Button.left)
        time.sleep(0.6)
        check("[단축키 설정] 버튼 -> 키 입력 대기", app.capturing is not None)
        shot("2_capturing")
        with kb.pressed(K.ctrl, K.alt):
            tap("s", 0.1)
        time.sleep(0.8)
        saved = json.loads(pc.SETTINGS_FILE.read_text(encoding="utf-8"))
        check(f"Ctrl+Alt+S 저장됨 (저장값: {saved.get('hotkey')})", saved.get("hotkey") == "ctrl+alt+s")
        shot("3_saved")

        m.position = (200, 300)
        tap(K.f8)
        tap("s")
        with kb.pressed(K.alt):
            tap("s", 0.1)
        time.sleep(0.5)
        check("F8 / S / Alt+S 에는 반응 안 함", not app.watching)
        with kb.pressed(K.ctrl, K.alt):
            tap("s", 0.1)
        time.sleep(0.6)
        check("Ctrl+Alt+S -> 감시 켜짐", app.watching)
        set_color("yellow")
        check("색 바뀜 -> 2번째 클릭", len(clicks) == 2)
        shot("4_clicked")

        closed.append(True)
        ui(app.close)  # 창 닫기 (위치 저장 확인은 아래 메인 스레드에서)
    except Exception as e:
        check(f"테스트 중 오류: {e!r}", False)
        try:
            ui(root.destroy)
        except Exception:
            pass


root.after(20, poll)
threading.Thread(target=scenario, daemon=True).start()
root.after(60000, root.destroy)  # 혹시 멈추면 60초 뒤 끝내기
root.mainloop()

if closed:
    saved = json.loads(pc.SETTINGS_FILE.read_text(encoding="utf-8"))
    check(f"창 닫으면 위치 저장 ({saved.get('window')})", bool(saved.get("window")))
else:
    check("시나리오가 끝까지 실행됨", False)

passed = sum(results)
print(f"\n결과: {passed}/{len(results)} 통과", flush=True)
sys.exit(0 if results and all(results) else 1)
