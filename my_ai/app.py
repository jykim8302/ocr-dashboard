"""나만의 AI 비서 - 채팅 화면 (Streamlit)

실행:  streamlit run my_ai/app.py   (또는 AI실행.bat 더블클릭)
왼쪽 사이드바에서 AI 의 이름, 성격, 말투, 모델 등 모든 것을 바꿀 수 있습니다.
"""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from assistant import (  # noqa: E402
    ANSWER_LENGTHS, EFFORT_LEVELS, EXPLAIN_LEVELS, FORMALITY, FORMAT_STYLES,
    LANGUAGES, MODELS, Assistant, build_system_prompt, delete_preset,
    list_presets, load_api_key, load_config, load_preset, save_api_key,
    save_config, save_preset,
)

st.set_page_config(page_title="나만의 AI", page_icon="🤖", layout="wide")

# ---------- 상태 초기화 ----------
if "cfg" not in st.session_state:
    st.session_state.cfg = load_config()
if "ai" not in st.session_state:
    st.session_state.ai = Assistant(st.session_state.cfg)
if "history" not in st.session_state:
    st.session_state.history = []  # 화면 표시용 [(role, text)]

cfg: dict = st.session_state.cfg
ai: Assistant = st.session_state.ai


def chat_bubble(role: str, avatar: str | None):
    """아이콘이 이상해도 앱이 죽지 않게 감싸줍니다."""
    try:
        return st.chat_message(role, avatar=avatar or None)
    except Exception:
        return st.chat_message(role)


def _index(options, value, default=0):
    options = list(options)
    return options.index(value) if value in options else default


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def apply_cfg(new_cfg: dict) -> None:
    """프리셋 등을 불러와 설정 전체를 바꿉니다."""
    st.session_state.cfg = new_cfg
    ai.cfg = new_cfg
    ai.reconnect()
    st.rerun()


# ---------- 사이드바: 모든 설정 ----------
with st.sidebar:
    st.title("⚙️ AI 설정")

    # --- API 키 ---
    if not load_api_key():
        st.warning("API 키가 없습니다. 아래에 입력하세요.")
        key = st.text_input("Anthropic API 키", type="password",
                            help="https://console.anthropic.com 에서 발급받을 수 있습니다.")
        remember = st.checkbox("이 컴퓨터에 저장 (다음부터 자동 입력)", True)
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key.strip()
            if remember:
                save_api_key(key)
            ai.reconnect()
            st.rerun()

    # --- 프리셋 ---
    with st.expander("📁 프리셋 (캐릭터 저장/불러오기)", expanded=False):
        presets = list_presets()
        if presets:
            chosen = st.selectbox("저장된 프리셋", presets)
            c1, c2 = st.columns(2)
            if c1.button("불러오기", use_container_width=True):
                apply_cfg(load_preset(chosen))
            if c2.button("삭제", use_container_width=True):
                delete_preset(chosen)
                st.rerun()
        new_name = st.text_input("현재 설정을 프리셋으로 저장", placeholder="예: 영어 선생님")
        if st.button("프리셋 저장", use_container_width=True) and new_name.strip():
            save_preset(new_name.strip(), cfg)
            st.success(f"'{new_name.strip()}' 프리셋을 저장했습니다.")
            st.rerun()

    # --- 1. 성격 ---
    with st.expander("🎭 1. 성격 / 역할", expanded=True):
        cfg["name"] = st.text_input("이름", cfg["name"])
        cfg["avatar"] = st.text_input("AI 아이콘 (이모지)", cfg["avatar"],
                                      help="👨‍🍳 처럼 조합된 이모지도 됩니다. 비워두면 기본 아이콘을 씁니다.")
        cfg["greeting"] = st.text_input("첫 인사말", cfg["greeting"])
        cfg["persona"] = st.text_area("역할 / 성격", cfg["persona"], height=100,
                                      help="예: 당신은 10년차 한식 요리사입니다. / 당신은 냉철한 투자 분석가입니다.")
        cfg["expertise"] = st.text_input("전문 분야", cfg["expertise"],
                                         placeholder="예: 파이썬, 데이터 분석, 영어 회화")

    # --- 2. 말하기 방식 ---
    with st.expander("💬 2. 말하기 방식"):
        cfg["tone"] = st.text_input("말투 분위기", cfg["tone"], placeholder="예: 차분하고 논리적인, 장난스러운")
        cfg["formality"] = st.radio("존댓말 / 반말", FORMALITY, horizontal=True,
                                    index=_index(FORMALITY, cfg["formality"]))
        cfg["self_reference"] = st.text_input("자기 호칭", cfg["self_reference"], placeholder="예: 저, 나, 본 AI")
        cfg["language"] = st.selectbox("답변 언어", LANGUAGES, index=_index(LANGUAGES, cfg["language"]))
        cfg["answer_length"] = st.select_slider("답변 길이", list(ANSWER_LENGTHS),
                                                cfg["answer_length"] if cfg["answer_length"] in ANSWER_LENGTHS else "보통")
        cfg["explain_level"] = st.radio("설명 수준", list(EXPLAIN_LEVELS), horizontal=True,
                                        index=_index(EXPLAIN_LEVELS, cfg["explain_level"], 1))
        cfg["format_style"] = st.selectbox("답변 형식", list(FORMAT_STYLES),
                                           index=_index(FORMAT_STYLES, cfg["format_style"]))
        cfg["use_emoji"] = st.toggle("이모지 사용", cfg["use_emoji"])
        cfg["humor"] = st.slider("유머 정도", 0, 10, int(cfg["humor"]), help="0 = 진지함, 10 = 매우 유쾌함")
        cfg["creativity"] = st.slider("창의성", 0, 10, int(cfg["creativity"]),
                                      help="0 = 사실만 정확히, 10 = 자유로운 발상")
        cfg["ask_back"] = st.toggle("모호하면 되묻기", cfg["ask_back"])
        cfg["signature"] = st.text_input("답변 끝 서명 문구", cfg["signature"], placeholder="예: - 나의 AI 드림")

    # --- 3. 규칙 / 제한 ---
    with st.expander("📏 3. 규칙 / 제한"):
        cfg["rules"] = _lines(st.text_area("반드시 지킬 규칙 (한 줄에 하나)", "\n".join(cfg["rules"]), height=100))
        cfg["forbidden_topics"] = _lines(st.text_area("다루지 않을 주제 (한 줄에 하나)",
                                                      "\n".join(cfg["forbidden_topics"]), height=70))
        cfg["forbidden_words"] = _lines(st.text_area("쓰지 않을 단어/표현 (한 줄에 하나)",
                                                     "\n".join(cfg["forbidden_words"]), height=70))
        cfg["examples"] = st.text_area("답변 예시 (스타일 학습용)", cfg["examples"], height=100,
                                       placeholder="질문: 오늘 날씨 어때?\n답변: 저는 실시간 날씨는 몰라요. 기상청 앱을 확인해 보세요!")
        cfg["extra_instructions"] = st.text_area("추가 지시사항 (자유롭게)", cfg["extra_instructions"], height=80)

    # --- 4. 사용자 정보 ---
    with st.expander("🙋 4. 나에 대한 정보"):
        cfg["user_name"] = st.text_input("내 이름 / 호칭", cfg["user_name"], placeholder="예: 김대리, 준영")
        cfg["user_avatar"] = st.text_input("내 아이콘 (이모지)", cfg["user_avatar"])
        cfg["user_info"] = st.text_area("AI가 알아둘 내 정보", cfg["user_info"], height=100,
                                        placeholder="예: 데이터 분석 공부 중인 대학생. 파이썬 초보. 주말엔 등산.")

    # --- 5. 두뇌 (모델) ---
    with st.expander("🧠 5. 두뇌 (모델)"):
        model_names = list(MODELS)
        current = next((n for n, m in MODELS.items() if m == cfg["model"]), model_names[0])
        cfg["model"] = MODELS[st.selectbox("모델", model_names, index=model_names.index(current))]
        if cfg["model"] == "custom":
            cfg["custom_model"] = st.text_input("모델 ID 직접 입력", cfg["custom_model"],
                                                placeholder="예: claude-opus-4-8")
        is_haiku = ai.model_id.startswith("claude-haiku")
        cfg["effort"] = st.select_slider("생각 깊이 (effort)", EFFORT_LEVELS,
                                         cfg["effort"] if cfg["effort"] in EFFORT_LEVELS else "medium",
                                         disabled=is_haiku, help="높을수록 더 깊이 생각하지만 느리고 비용이 늘어납니다.")
        cfg["show_thinking"] = st.toggle("생각 과정 보기", cfg["show_thinking"], disabled=is_haiku)
        cfg["temperature"] = st.slider("무작위성 (temperature, Haiku 전용)", 0.0, 1.0,
                                       float(cfg["temperature"]), 0.1, disabled=not is_haiku,
                                       help="Opus/Sonnet 5 는 temperature 대신 '창의성'과 '생각 깊이'로 조절합니다.")
        cfg["max_tokens"] = st.slider("최대 답변 길이 (토큰)", 256, 32000, int(cfg["max_tokens"]), 256)
        cfg["memory_turns"] = st.slider("기억할 대화 수 (턴)", 1, 100, int(cfg["memory_turns"]))
        cfg["fallback_on_refusal"] = st.toggle("거절 시 다른 모델로 대체", cfg["fallback_on_refusal"],
                                               help="안전 정책으로 답변이 거절되면 자동으로 다른 모델이 답합니다.")

    # --- 6. 도구 ---
    with st.expander("🔧 6. 도구"):
        cfg["web_search"] = st.toggle("인터넷 검색 허용", cfg["web_search"],
                                      help="최신 정보가 필요하면 AI가 스스로 웹을 검색합니다. (검색 1회당 소액 과금)")
        cfg["web_search_max_uses"] = st.slider("답변 1회당 최대 검색 횟수", 1, 10,
                                               int(cfg["web_search_max_uses"]), disabled=not cfg["web_search"])

    # --- 7. 고급 ---
    with st.expander("🛠️ 7. 고급"):
        cfg["streaming"] = st.toggle("글자 단위 스트리밍", cfg["streaming"])
        cfg["use_cache"] = st.toggle("프롬프트 캐시 (비용 절약)", cfg["use_cache"])
        cfg["stop_sequences"] = _lines(st.text_area("이 문구가 나오면 답변 중단 (한 줄에 하나)",
                                                    "\n".join(cfg["stop_sequences"]), height=60))
        new_timeout = st.number_input("타임아웃 (초)", 10, 3600, int(cfg["timeout"]), 10)
        new_retries = st.number_input("실패 시 재시도 횟수", 0, 10, int(cfg["max_retries"]))
        if new_timeout != cfg["timeout"] or new_retries != cfg["max_retries"]:
            cfg["timeout"], cfg["max_retries"] = new_timeout, new_retries
            ai.reconnect()
        cfg["system_prompt_override"] = st.text_area(
            "시스템 프롬프트 직접 작성 (완전 수동 모드)", cfg["system_prompt_override"], height=120,
            help="여기에 내용을 쓰면 위의 1~4번 설정은 무시되고 이 내용이 그대로 AI 에게 전달됩니다.")
        if st.button("저장된 API 키 지우기", use_container_width=True):
            from assistant import API_KEY_PATH
            API_KEY_PATH.unlink(missing_ok=True)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            ai.reconnect()
            st.rerun()

    # --- 8. 화면 ---
    with st.expander("🖥️ 8. 화면"):
        cfg["show_usage"] = st.toggle("토큰 사용량 / 예상 비용 표시", cfg["show_usage"])

    ai.cfg = cfg  # 바뀐 설정을 즉시 반영

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("💾 설정 저장", use_container_width=True, type="primary"):
        save_config(cfg)
        st.success("config.json 에 저장했습니다.")
    if c2.button("🗑️ 대화 초기화", use_container_width=True):
        ai.reset()
        st.session_state.history = []
        st.rerun()

    with st.expander("실제로 AI 에게 전달되는 성격 설명서 보기"):
        st.code(build_system_prompt(cfg), language="text")

# ---------- 채팅 화면 ----------
st.title(f"{cfg['avatar']} {cfg['name']}")

with chat_bubble("assistant", cfg["avatar"]):
    st.write(cfg["greeting"])

for role, text in st.session_state.history:
    avatar = cfg["avatar"] if role == "assistant" else cfg["user_avatar"]
    with chat_bubble(role, avatar):
        st.markdown(text)

if prompt := st.chat_input("메시지를 입력하세요..."):
    st.session_state.history.append(("user", prompt))
    with chat_bubble("user", cfg["user_avatar"]):
        st.markdown(prompt)

    with chat_bubble("assistant", cfg["avatar"]):
        try:
            answer = st.write_stream(ai.chat(prompt))
        except RuntimeError as e:
            st.error(str(e))
            st.session_state.history.pop()
        else:
            if cfg["show_thinking"] and ai.last_thinking:
                with st.expander("🧠 생각 과정"):
                    st.markdown(ai.last_thinking)
            if cfg["show_usage"] and ai.last_usage:
                u, cost = ai.last_usage, ai.estimated_cost()
                cost_text = f" · 누적 비용 약 ${cost:.4f}" if cost is not None else ""
                st.caption(f"입력 {u['input']:,} 토큰 (캐시 {u['cache_read']:,}) · 출력 {u['output']:,} 토큰{cost_text}")
            st.session_state.history.append(("assistant", answer))
