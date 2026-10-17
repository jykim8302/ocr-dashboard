# 픽셀 변화 자동 클릭기

**단축키를 누르면**, 그 순간 화면 **정가운데 1픽셀** 색을 기억해요.
그 색이 바뀌면 그 자리를 자동으로 **클릭**해요.

## 실행 방법 (Windows)

1. [Python](https://www.python.org/downloads/) 설치 (설치 시 **"Add Python to PATH"** 체크)
2. 파일 4개를 한 폴더에 넣고 `run_windows.bat` 더블클릭

(다른 OS: `pip install -r requirements.txt` 후 `python pixel_clicker.py`)

## 사용 순서

1. 프로그램을 켜 두면 **대기** 상태예요
2. 원하는 화면에서 **F8** → 지금 가운데 색을 기억하고 감시 시작
3. 색이 바뀌면 → **클릭 1번** → 다시 대기
4. 또 하고 싶으면 다시 **F8**

## 단축키

| 키 | 기능 |
|---|---|
| **F8** | 감시 시작 / 취소 |
| **F12** | 프로그램 종료 |

마우스를 화면 **왼쪽 위 모서리**로 옮겨도 바로 멈춰요.

## 옵션 (필요할 때만)

| 옵션 | 뜻 | 기본값 |
|---|---|---|
| `--key ctrl+alt+s` | 감시 시작 키 바꾸기 | f8 |
| `--quit-key esc` | 종료 키 바꾸기 | f12 |
| `--repeat` | 클릭 후에도 계속 감시 | 꺼짐 |
| `--tolerance 30` | 이만큼 이상 색이 달라야 "바뀜"으로 인정 (0~255) | 10 |
| `--button right` | 오른쪽 클릭 | left |

예: `python pixel_clicker.py --key f6 --tolerance 30`

`run_windows.bat`에 옵션을 넣고 싶으면 메모장으로 열어서
`python pixel_clicker.py` 뒤에 적으면 돼요.
