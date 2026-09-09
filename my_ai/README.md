# 🤖 나만의 AI 비서 (my_ai)

Claude 를 기반으로 만든, **온갖 세부 설정을 내 마음대로 만질 수 있는** AI 비서입니다.

---

## 1. 실행 방법 (가장 쉬운 방법)

| 운영체제 | 방법 |
|---|---|
| **Windows** | `AI실행.bat` **더블클릭** |
| **Mac** | `AI실행.command` **더블클릭** (처음 한 번만 터미널에서 `chmod +x AI실행.command`) |

더블클릭하면 필요한 프로그램을 알아서 설치하고 브라우저가 자동으로 열립니다.
검은 창(터미널)은 끄지 마세요. 그 창을 닫으면 AI도 꺼집니다.

**API 키**는 처음 실행할 때 화면 왼쪽에 입력하면 됩니다.
키는 https://console.anthropic.com 에서 발급받습니다.
"이 컴퓨터에 저장"을 체크하면 `my_ai/api_key.txt` 에 저장되어 다음부터는 입력하지 않아도 됩니다.
(이 파일은 깃허브에 올라가지 않습니다.)

### 명령어로 실행하기

```bash
pip install anthropic streamlit
streamlit run my_ai/app.py     # 웹 채팅 화면
python my_ai/cli.py            # 터미널에서 바로 대화
```

---

## 2. 바꿀 수 있는 것 (사이드바 1~8번)

바꾼 뒤 **💾 설정 저장**을 누르면 `my_ai/config.json` 에 기록됩니다. 파일을 직접 고쳐도 됩니다.

### 🎭 1. 성격 / 역할
| 항목 | 설명 |
|---|---|
| `name` | AI 이름 |
| `avatar` | AI 아이콘 이모지 |
| `greeting` | 첫 인사말 |
| `persona` | 역할과 성격 (예: "20년차 한식 요리사") |
| `expertise` | 전문 분야 |

### 💬 2. 말하기 방식
| 항목 | 설명 |
|---|---|
| `tone` | 말투 분위기 |
| `formality` | 존댓말 / 반말 / 상황에 맞게 |
| `self_reference` | 자기를 부르는 말 (저, 나, 본 AI …) |
| `language` | 한국어 / English / 日本語 / 中文 / Español / 사용자와 같은 언어 |
| `answer_length` | 아주 짧게 ~ 아주 길게 (5단계) |
| `explain_level` | 어린이 / 일반인 / 전문가 |
| `format_style` | 자유 / 마크다운 / 글머리표 / 순수 텍스트 |
| `use_emoji` | 이모지 사용 여부 |
| `humor` | 유머 정도 0~10 |
| `creativity` | 창의성 0~10 (0 = 사실만, 10 = 자유 발상) |
| `ask_back` | 모호할 때 되물을지 |
| `signature` | 답변 끝에 붙일 서명 문구 |

### 📏 3. 규칙 / 제한
| 항목 | 설명 |
|---|---|
| `rules` | 반드시 지킬 규칙 목록 |
| `forbidden_topics` | 다루지 않을 주제 |
| `forbidden_words` | 쓰지 않을 단어/표현 |
| `examples` | 답변 스타일 예시 |
| `extra_instructions` | 자유로운 추가 지시 |

### 🙋 4. 나에 대한 정보
| 항목 | 설명 |
|---|---|
| `user_name` | 내 이름 / 호칭 (AI가 불러줍니다) |
| `user_avatar` | 내 아이콘 이모지 |
| `user_info` | AI가 기억할 내 정보 (직업, 관심사 등) |

### 🧠 5. 두뇌 (모델)
| 항목 | 설명 |
|---|---|
| `model` | Opus 5 (똑똑함) / Sonnet 5 (빠름) / Haiku 4.5 (가장 빠름) / 직접 입력 |
| `custom_model` | 모델 ID 직접 입력 |
| `effort` | 생각 깊이 low ~ max |
| `show_thinking` | 생각 과정을 펼쳐 볼지 |
| `temperature` | 무작위성 (Haiku 전용) |
| `max_tokens` | 한 번에 답할 최대 길이 |
| `memory_turns` | 몇 턴까지 기억할지 |
| `fallback_on_refusal` | 거절되면 다른 모델이 대신 답할지 |

### 🔧 6. 도구
| 항목 | 설명 |
|---|---|
| `web_search` | 인터넷 검색 허용 (최신 정보가 필요할 때 AI가 스스로 검색) |
| `web_search_max_uses` | 답변 1회당 최대 검색 횟수 |

### 🛠️ 7. 고급
| 항목 | 설명 |
|---|---|
| `streaming` | 글자 단위로 흘려 보여줄지 |
| `use_cache` | 프롬프트 캐시 (반복 대화 비용 절약) |
| `stop_sequences` | 이 문구가 나오면 답변 중단 |
| `timeout` / `max_retries` | 대기 시간, 재시도 횟수 |
| `system_prompt_override` | **완전 수동 모드.** 여기에 쓰면 1~4번 설정을 무시하고 이 내용만 AI에게 전달합니다 |

### 🖥️ 8. 화면
| 항목 | 설명 |
|---|---|
| `show_usage` | 토큰 사용량과 예상 비용을 답변 아래에 표시 |

---

## 3. 프리셋 (캐릭터 저장/불러오기)

사이드바 맨 위 **📁 프리셋**에서 현재 설정을 이름 붙여 저장하고, 언제든 불러올 수 있습니다.
기본으로 4개가 들어 있습니다.

- **기본 비서** 친절하고 똑똑한 만능 비서
- **영어 선생님** 영어 문장을 고쳐주고 이유를 설명
- **코딩 도우미** 시니어 개발자 스타일, 바로 쓸 수 있는 코드
- **요리사** 반말로 집밥 레시피를 알려주는 셰프

프리셋은 `my_ai/presets/*.json` 파일입니다. 직접 만들어 넣어도 됩니다.

---

## 4. 코드에서 쓰기

```python
from my_ai.assistant import Assistant

ai = Assistant()
ai.update_config(name="요리봇", persona="당신은 한식 요리사입니다.", formality="반말")
print(ai.ask("김치찌개 맛있게 끓이는 법?"))

for chunk in ai.chat("그럼 돼지고기 대신 참치는?"):   # 스트리밍
    print(chunk, end="", flush=True)
```
