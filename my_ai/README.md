# 🤖 나만의 AI 비서 (my_ai)

Claude 를 기반으로 만든, **모든 세부 설정을 내 마음대로 바꿀 수 있는** AI 비서입니다.

## 1. 준비 (한 번만)

```bash
uv pip install -r requirements.txt        # 또는 pip install anthropic streamlit

# API 키 등록 (https://console.anthropic.com 에서 발급)
set ANTHROPIC_API_KEY=sk-ant-...          # Windows CMD
$env:ANTHROPIC_API_KEY="sk-ant-..."       # Windows PowerShell
export ANTHROPIC_API_KEY=sk-ant-...       # Mac / Linux
```

## 2. 실행

```bash
streamlit run my_ai/app.py     # 웹 채팅 화면 (추천)
python my_ai/cli.py            # 터미널에서 바로 대화
```

## 3. 바꿀 수 있는 것들

왼쪽 사이드바에서 바로 바꾸고, **💾 설정 저장**을 누르면 `my_ai/config.json` 에 저장됩니다.
파일을 직접 열어서 고쳐도 됩니다.

| 항목 | 설명 |
|---|---|
| `name` | AI 이름 |
| `greeting` | 첫 인사말 |
| `persona` | 역할과 성격 (예: "10년차 요리사", "냉철한 투자 분석가") |
| `tone` | 말투 (예: "존댓말", "반말", "장난스럽게") |
| `language` | 답변 언어 |
| `answer_length` | 짧게 / 보통 / 길게 |
| `use_emoji` | 이모지 사용 여부 |
| `rules` | 반드시 지킬 규칙 목록 |
| `extra_instructions` | 그 외 자유로운 지시사항 |
| `model` | `claude-opus-5` (똑똑함) / `claude-sonnet-5` (빠름) / `claude-haiku-4-5` (가장 빠름) |
| `effort` | 생각 깊이: low / medium / high / xhigh / max |
| `max_tokens` | 한 번에 답할 수 있는 최대 길이 |
| `show_thinking` | 생각 과정을 화면에 보여줄지 |
| `memory_turns` | 몇 턴까지 기억할지 |
| `fallback_on_refusal` | 답변이 거절되면 다른 모델이 대신 답하게 할지 |

## 4. 코드에서 쓰기

```python
from my_ai.assistant import Assistant

ai = Assistant()
ai.update_config(name="요리봇", persona="당신은 한식 전문 요리사입니다.", tone="반말")
print(ai.ask("김치찌개 맛있게 끓이는 법?"))
```
