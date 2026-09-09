"""나만의 AI 비서 - 채팅 화면 (Streamlit)

실행:  streamlit run my_ai/app.py
왼쪽 사이드바에서 AI 의 이름, 성격, 말투, 모델 등 모든 것을 바꿀 수 있습니다.
"""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from assistant import (  # noqa: E402
    ANSWER_LENGTHS, EFFORT_LEVELS, MODELS, Assistant, build_system_prompt,
    load_config, save_config,
)

st.set_page_config(page_title="나만의 AI", page_icon="🤖", layout="wide")

# ---------- 상태 초기화 ----------
if "cfg" not in st.session_state:
    st.session_state.cfg = load_config()
if "ai" not in st.session_state:
    st.session_state.ai = Assistant(st.session_state.cfg)
if "history" not in st.session_state:
    st.session_state.history = []  # 화면 표시용 [(role, text)]

cfg = st.session_state.cfg
ai: Assistant = st.session_state.ai

# ---------- 사이드바: 모든 설정 ----------
with st.sidebar:
    st.title("⚙️ AI 설정")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        key = st.text_input("Anthropic API 키", type="password",
                            help="환경변수 ANTHROPIC_API_KEY 로 넣어두면 매번 입력하지 않아도 됩니다.")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key

    st.subheader("1. 성격")
    cfg["name"] = st.text_input("이름", cfg["name"])
    cfg["greeting"] = st.text_input("첫 인사말", cfg["greeting"])
    cfg["persona"] = st.text_area("역할 / 성격", cfg["persona"], height=100)
    cfg["tone"] = st.text_input("말투", cfg["tone"])
    cfg["language"] = st.selectbox("언어", ["한국어", "English", "日本語", "中文"],
                                   index=["한국어", "English", "日本語", "中文"].index(cfg["language"])
                                   if cfg["language"] in ["한국어", "English", "日本語", "中文"] else 0)
    cfg["answer_length"] = st.radio("답변 길이", list(ANSWER_LENGTHS), horizontal=True,
                                    index=list(ANSWER_LENGTHS).index(cfg["answer_length"]))
    cfg["use_emoji"] = st.toggle("이모지 사용", cfg["use_emoji"])
    rules_text = st.text_area("지켜야 할 규칙 (한 줄에 하나)", "\n".join(cfg["rules"]), height=100)
    cfg["rules"] = [r for r in rules_text.splitlines() if r.strip()]
    cfg["extra_instructions"] = st.text_area("추가 지시사항 (자유롭게)", cfg["extra_instructions"], height=80)

    st.subheader("2. 두뇌")
    model_names = list(MODELS)
    current = next((n for n, m in MODELS.items() if m == cfg["model"]), model_names[0])
    cfg["model"] = MODELS[st.selectbox("모델", model_names, index=model_names.index(current))]
    is_haiku = cfg["model"].startswith("claude-haiku")
    cfg["effort"] = st.select_slider("생각 깊이 (effort)", EFFORT_LEVELS, cfg["effort"],
                                     disabled=is_haiku,
                                     help="높을수록 더 깊이 생각하지만 느리고 비용이 늘어납니다.")
    cfg["max_tokens"] = st.slider("최대 답변 길이 (토큰)", 256, 16000, int(cfg["max_tokens"]), 256)
    cfg["show_thinking"] = st.toggle("생각 과정 보기", cfg["show_thinking"], disabled=is_haiku)
    cfg["memory_turns"] = st.slider("기억할 대화 수 (턴)", 1, 100, int(cfg["memory_turns"]))
    cfg["fallback_on_refusal"] = st.toggle("거절 시 다른 모델로 대체", cfg["fallback_on_refusal"],
                                           help="안전 정책으로 답변이 거절되면 자동으로 다른 모델이 답합니다.")

    ai.cfg = cfg  # 바뀐 설정을 즉시 반영

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("💾 설정 저장", use_container_width=True):
        save_config(cfg)
        st.success("config.json 에 저장했습니다.")
    if c2.button("🗑️ 대화 초기화", use_container_width=True):
        ai.reset()
        st.session_state.history = []
        st.rerun()

    with st.expander("실제로 AI 에게 전달되는 성격 설명서 보기"):
        st.code(build_system_prompt(cfg), language="text")

# ---------- 채팅 화면 ----------
st.title(f"🤖 {cfg['name']}")

with st.chat_message("assistant"):
    st.write(cfg["greeting"])

for role, text in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)

if prompt := st.chat_input("메시지를 입력하세요..."):
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            answer = st.write_stream(ai.chat(prompt))
        except RuntimeError as e:
            st.error(str(e))
            st.session_state.history.pop()
        else:
            if cfg["show_thinking"] and ai.last_thinking:
                with st.expander("🧠 생각 과정"):
                    st.markdown(ai.last_thinking)
            st.session_state.history.append(("assistant", answer))
