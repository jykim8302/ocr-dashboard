# 픽셀 변화 자동 클릭기

화면 **정가운데 1픽셀**의 색이 바뀌면, 그 자리를 자동으로 클릭합니다.

## 실행 방법 (Windows)

1. [Python](https://www.python.org/downloads/) 설치 (설치 시 **"Add Python to PATH"** 체크)
2. `run_windows.bat` 더블클릭 → 끝!

(다른 OS: `pip install -r requirements.txt` 후 `python pixel_clicker.py`)

## 동작 순서

1. 실행하면 3초 기다림 → 이때 감시할 화면을 띄워 두세요
2. 그 순간 가운데 픽셀 색을 **기준 색**으로 기억
3. 색이 바뀌면 → **클릭** → 바뀐 색을 새 기준으로 다시 감시

## 멈추기

- `Ctrl + C`
- 또는 마우스를 화면 **왼쪽 위 모서리**로 이동

## 옵션 (필요할 때만)

| 옵션 | 뜻 | 기본값 |
|---|---|---|
| `--once` | 한 번만 클릭하고 종료 | 꺼짐 |
| `--tolerance 10` | 이만큼 이상 색이 달라야 "바뀜"으로 인정 (0~255) | 10 |
| `--interval 0.01` | 몇 초마다 검사할지 | 0.01 |
| `--cooldown 0.5` | 클릭 후 쉬는 시간(초) | 0.5 |
| `--delay 3` | 시작 전 대기 시간(초) | 3 |
| `--button right` | 오른쪽 클릭 | left |

예: `python pixel_clicker.py --once --tolerance 30`
