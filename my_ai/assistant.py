"""나만의 AI 비서 - 핵심 엔진

config.json 의 설정을 읽어서 Claude 에게 보낼 시스템 프롬프트를 만들고,
대화 기록을 유지하면서 답변을 스트리밍으로 받아옵니다.

사용 예시:
    from assistant import Assistant
    ai = Assistant()                 # config.json 자동 로드
    for chunk in ai.chat("안녕?"):   # 글자가 생성되는 대로 출력
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

import anthropic

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
API_KEY_PATH = HERE / "api_key.txt"      # 여기에 키를 저장해 두면 자동으로 읽습니다 (git 에는 안 올라감)
PRESETS_DIR = HERE / "presets"

# ---------------------------------------------------------------------------
# 선택지 목록 (화면과 엔진이 같이 씁니다)
# ---------------------------------------------------------------------------
MODELS = {
    "Claude Opus 5 (가장 똑똑함, 기본값)": "claude-opus-5",
    "Claude Sonnet 5 (빠르고 저렴)": "claude-sonnet-5",
    "Claude Haiku 4.5 (가장 빠름)": "claude-haiku-4-5",
    "직접 입력": "custom",
}
# 100만 토큰당 가격 (입력, 출력) - 비용 표시용
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]
LANGUAGES = ["한국어", "English", "日本語", "中文", "Español", "사용자와 같은 언어"]
FORMALITY = ["존댓말", "반말", "상황에 맞게"]
ANSWER_LENGTHS = {
    "아주 짧게": "답변은 한두 문장으로 아주 짧게 합니다.",
    "짧게": "답변은 2~3문장으로 짧게 합니다.",
    "보통": "답변은 핵심만 담아 적당한 길이로 합니다.",
    "길게": "답변은 배경 설명과 예시까지 포함해 자세히 합니다.",
    "아주 길게": "답변은 가능한 한 상세하고 빠짐없이, 단계별로 깊이 있게 합니다.",
}
EXPLAIN_LEVELS = {
    "어린이": "초등학생도 이해할 수 있게 아주 쉬운 말과 비유로 설명합니다.",
    "일반인": "전문 지식이 없는 일반인이 이해할 수 있게 설명합니다.",
    "전문가": "전문가를 대상으로 정확한 용어를 써서 깊이 있게 설명합니다.",
}
FORMAT_STYLES = {
    "자유": "",
    "마크다운 적극 활용": "제목, 굵은 글씨, 표, 코드 블록 등 마크다운을 적극적으로 사용해 보기 좋게 정리합니다.",
    "글머리표 위주": "가능하면 글머리표(불릿)로 요점을 정리해서 답합니다.",
    "순수 텍스트": "마크다운 기호(#, *, - 등)를 쓰지 않고 순수한 문장으로만 답합니다.",
}

DEFAULT_CONFIG: dict = {
    "name": "나의 AI", "avatar": "🤖", "user_avatar": "🙂",
    "greeting": "안녕하세요! 무엇을 도와드릴까요?",
    "persona": "당신은 친절하고 똑똑한 AI 비서입니다.",
    "expertise": "", "tone": "친근하고 편안한 말투", "formality": "존댓말",
    "self_reference": "저", "language": "한국어", "answer_length": "보통",
    "explain_level": "일반인", "format_style": "자유", "use_emoji": False,
    "humor": 3, "creativity": 5, "ask_back": True, "signature": "",
    "rules": [], "forbidden_topics": [], "forbidden_words": [],
    "extra_instructions": "", "examples": "",
    "user_name": "", "user_info": "",
    "system_prompt_override": "",
    "model": "claude-opus-5", "custom_model": "", "effort": "medium",
    "max_tokens": 4096, "temperature": 1.0, "show_thinking": False,
    "fallback_on_refusal": True, "memory_turns": 20, "stop_sequences": [],
    "streaming": True, "use_cache": True, "timeout": 600, "max_retries": 2,
    "web_search": False, "web_search_max_uses": 3,
    "show_usage": True,
}


# ---------------------------------------------------------------------------
# 설정 파일 / 프리셋
# ---------------------------------------------------------------------------
def load_config(path: Path = CONFIG_PATH) -> dict:
    """config.json 을 읽어서 설정 dict 로 돌려줍니다. 빠진 항목은 기본값으로 채웁니다."""
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    """설정을 JSON 파일로 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def list_presets() -> list[str]:
    """presets/ 폴더에 저장된 프리셋 이름 목록."""
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def load_preset(name: str) -> dict:
    return load_config(PRESETS_DIR / f"{name}.json")


def save_preset(name: str, cfg: dict) -> None:
    save_config(cfg, PRESETS_DIR / f"{name}.json")


def delete_preset(name: str) -> None:
    p = PRESETS_DIR / f"{name}.json"
    if p.exists():
        p.unlink()


def load_api_key() -> str | None:
    """환경변수 -> api_key.txt 순서로 API 키를 찾습니다."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and API_KEY_PATH.exists():
        key = API_KEY_PATH.read_text(encoding="utf-8").strip()
    return key or None


def save_api_key(key: str) -> None:
    API_KEY_PATH.write_text(key.strip(), encoding="utf-8")


# ---------------------------------------------------------------------------
# 시스템 프롬프트 만들기
# ---------------------------------------------------------------------------
def _scale_text(value: int, low: str, mid: str, high: str) -> str:
    """0~10 슬라이더 값을 문장으로 바꿉니다."""
    if value <= 2:
        return low
    if value >= 8:
        return high
    return mid


def build_system_prompt(cfg: dict) -> str:
    """설정 항목들을 하나의 시스템 프롬프트(AI 의 성격 설명서)로 합칩니다.

    system_prompt_override 가 있으면 그 내용을 그대로 씁니다 (완전 수동 모드).
    """
    if cfg.get("system_prompt_override", "").strip():
        return cfg["system_prompt_override"].strip()

    parts = [f"당신의 이름은 '{cfg['name']}' 입니다.", cfg["persona"].strip()]

    if cfg.get("expertise", "").strip():
        parts.append(f"특히 다음 분야에 전문성이 있습니다: {cfg['expertise'].strip()}")

    # --- 말하기 방식 ---
    speak = [f"말투: {cfg['tone']}."]
    if cfg["formality"] == "존댓말":
        speak.append("항상 존댓말을 씁니다.")
    elif cfg["formality"] == "반말":
        speak.append("항상 친한 사이처럼 반말을 씁니다.")
    if cfg.get("self_reference"):
        speak.append(f"자신을 가리킬 때는 '{cfg['self_reference']}'라고 합니다.")
    if cfg["language"] == "사용자와 같은 언어":
        speak.append("사용자가 쓴 언어와 같은 언어로 답합니다.")
    else:
        speak.append(f"항상 {cfg['language']}로 답합니다.")
    speak.append(ANSWER_LENGTHS.get(cfg["answer_length"], ANSWER_LENGTHS["보통"]))
    speak.append(EXPLAIN_LEVELS.get(cfg["explain_level"], EXPLAIN_LEVELS["일반인"]))
    if FORMAT_STYLES.get(cfg["format_style"]):
        speak.append(FORMAT_STYLES[cfg["format_style"]])
    speak.append("이모지를 적절히 사용합니다." if cfg["use_emoji"] else "이모지는 사용하지 않습니다.")
    speak.append(_scale_text(int(cfg["humor"]),
                             "농담이나 유머는 쓰지 않고 진지하게 답합니다.",
                             "가끔 가벼운 유머를 섞습니다.",
                             "유머와 재치를 적극적으로 섞어 재미있게 답합니다."))
    speak.append(_scale_text(int(cfg["creativity"]),
                             "사실에 근거해 보수적이고 정확하게만 답하고, 추측이나 창의적 확장은 하지 않습니다.",
                             "정확성을 지키되 필요하면 새로운 아이디어도 제안합니다.",
                             "자유롭고 창의적으로 발상하며 다양한 아이디어와 관점을 적극 제안합니다."))
    if cfg.get("ask_back"):
        speak.append("질문이 모호하면 추측하지 말고 되물어서 확인합니다.")
    else:
        speak.append("질문이 모호해도 되묻지 않고 가장 그럴듯한 해석으로 바로 답합니다.")
    parts.append("\n".join(speak))

    # --- 규칙 / 금지 ---
    rules = [r.strip() for r in cfg.get("rules", []) if r.strip()]
    if rules:
        parts.append("반드시 지켜야 할 규칙:\n" + "\n".join(f"- {r}" for r in rules))
    topics = [t.strip() for t in cfg.get("forbidden_topics", []) if t.strip()]
    if topics:
        parts.append("다음 주제는 다루지 않고 정중히 거절합니다: " + ", ".join(topics))
    words = [w.strip() for w in cfg.get("forbidden_words", []) if w.strip()]
    if words:
        parts.append("다음 단어/표현은 절대 쓰지 않습니다: " + ", ".join(words))

    # --- 사용자 정보 ---
    user = []
    if cfg.get("user_name", "").strip():
        user.append(f"사용자의 이름은 '{cfg['user_name'].strip()}' 입니다. 필요하면 이름을 불러줍니다.")
    if cfg.get("user_info", "").strip():
        user.append("사용자에 대해 알아둘 정보:\n" + cfg["user_info"].strip())
    if user:
        parts.append("\n".join(user))

    # --- 예시 대화 / 서명 / 기타 ---
    if cfg.get("examples", "").strip():
        parts.append("답변 스타일 예시 (이런 식으로 답합니다):\n" + cfg["examples"].strip())
    if cfg.get("signature", "").strip():
        parts.append(f"모든 답변의 맨 마지막 줄에 다음 문구를 붙입니다: {cfg['signature'].strip()}")
    if cfg.get("extra_instructions", "").strip():
        parts.append(cfg["extra_instructions"].strip())

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# AI 비서
# ---------------------------------------------------------------------------
class Assistant:
    """대화 기록을 기억하는 AI 비서."""

    def __init__(self, cfg: dict | None = None, client: anthropic.Anthropic | None = None):
        self.cfg = cfg or load_config()
        self._client = client
        self.messages: list[dict] = []
        self.last_thinking: str = ""
        self.last_usage: dict = {}          # 마지막 답변의 토큰 사용량
        self.total_usage = {"input": 0, "output": 0, "cache_read": 0}

    # ---------- 클라이언트 ----------
    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=load_api_key(),
                timeout=float(self.cfg.get("timeout", 600)),
                max_retries=int(self.cfg.get("max_retries", 2)),
            )
        return self._client

    def reconnect(self) -> None:
        """API 키나 타임아웃 설정을 바꾼 뒤 호출하면 새로 연결합니다."""
        self._client = None

    # ---------- 설정 ----------
    @property
    def model_id(self) -> str:
        if self.cfg["model"] == "custom":
            return self.cfg.get("custom_model", "").strip() or "claude-opus-5"
        return self.cfg["model"]

    def update_config(self, **changes) -> None:
        """설정 일부를 바꿉니다. 예: ai.update_config(tone="딱딱한 말투")"""
        self.cfg.update(changes)

    def reset(self) -> None:
        """대화 기록을 지우고 처음부터 시작합니다."""
        self.messages.clear()
        self.last_thinking = ""
        self.last_usage = {}
        self.total_usage = {"input": 0, "output": 0, "cache_read": 0}

    # ---------- 요청 만들기 ----------
    def _request_params(self) -> dict:
        cfg = self.cfg
        model = self.model_id
        is_haiku = model.startswith("claude-haiku")

        system_block: dict = {"type": "text", "text": build_system_prompt(cfg)}
        if cfg.get("use_cache", True):
            # 시스템 프롬프트는 매번 같으므로 캐시해서 비용을 아낍니다.
            system_block["cache_control"] = {"type": "ephemeral"}

        params: dict = {
            "model": model,
            "max_tokens": int(cfg["max_tokens"]),
            "system": [system_block],
            "messages": self._recent_messages(),
        }

        if is_haiku:
            # Haiku 4.5 는 effort / adaptive thinking 이 없고 temperature 를 씁니다.
            params["temperature"] = float(cfg.get("temperature", 1.0))
        else:
            params["output_config"] = {"effort": cfg["effort"]}
            params["thinking"] = {
                "type": "adaptive",
                "display": "summarized" if cfg["show_thinking"] else "omitted",
            }

        stops = [s for s in cfg.get("stop_sequences", []) if s.strip()]
        if stops:
            params["stop_sequences"] = stops

        if cfg.get("web_search"):
            params["tools"] = [{
                "type": "web_search_20250305" if is_haiku else "web_search_20260209",
                "name": "web_search",
                "max_uses": int(cfg.get("web_search_max_uses", 3)),
            }]

        if cfg.get("fallback_on_refusal"):
            # 안전 정책으로 답변이 거절되면 다른 모델이 이어서 답하도록 합니다.
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def _recent_messages(self) -> list[dict]:
        """memory_turns 만큼의 최근 대화만 보냅니다 (비용/속도 절약)."""
        keep = int(self.cfg.get("memory_turns", 20)) * 2  # 질문+답변 = 1턴
        msgs = self.messages[-keep:] if keep > 0 else list(self.messages)
        while msgs and msgs[0]["role"] != "user":  # 첫 메시지는 반드시 user
            msgs = msgs[1:]
        return msgs

    # ---------- 대화 ----------
    def chat(self, user_text: str) -> Iterator[str]:
        """질문을 보내고 답변 조각(str)을 순서대로 돌려줍니다 (스트리밍)."""
        self.messages.append({"role": "user", "content": user_text})
        self.last_thinking = ""
        try:
            for _ in range(5):  # 웹 검색이 길어지면(pause_turn) 이어서 요청
                final, produced = yield from self._one_request()
                self.messages.append({"role": "assistant", "content": final.content})
                self._record_usage(final)
                if final.stop_reason != "pause_turn":
                    break
        except TypeError:  # SDK 가 API 키를 못 찾으면 TypeError 를 냅니다.
            self._rollback()
            raise RuntimeError("API 키가 없습니다. 화면 왼쪽에 키를 입력하거나 my_ai/api_key.txt 파일에 저장하세요.")
        except anthropic.AuthenticationError:
            self._rollback()
            raise RuntimeError("API 키가 올바르지 않습니다. 키를 다시 확인하세요.")
        except anthropic.RateLimitError:
            self._rollback()
            raise RuntimeError("요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
        except anthropic.APIConnectionError:
            self._rollback()
            raise RuntimeError("네트워크 연결에 실패했습니다. 인터넷 상태를 확인하세요.")
        except anthropic.APIStatusError as e:
            self._rollback()
            raise RuntimeError(f"API 오류 ({e.status_code}): {e.message}")

        for block in final.content:
            if block.type == "thinking" and getattr(block, "thinking", ""):
                self.last_thinking = block.thinking

        if final.stop_reason == "refusal":
            reason = final.stop_details.explanation if final.stop_details else "안전 정책"
            yield f"\n\n(이 요청은 답변할 수 없습니다: {reason})"
        elif final.stop_reason == "max_tokens":
            yield "\n\n(최대 답변 길이에 도달해 잘렸습니다. '최대 답변 길이' 설정을 늘려보세요.)"

    def _one_request(self):
        """API 를 한 번 호출하고 (최종 메시지, 텍스트를 냈는지) 를 돌려줍니다."""
        params = self._request_params()
        produced = False
        if self.cfg.get("streaming", True):
            with self.client.beta.messages.stream(**params) as stream:
                for text in stream.text_stream:
                    produced = True
                    yield text
                final = stream.get_final_message()
        else:
            final = self.client.beta.messages.create(**params)
            for block in final.content:
                if block.type == "text":
                    produced = True
                    yield block.text
        return final, produced

    def _rollback(self) -> None:
        """실패한 요청의 질문을 기록에서 지웁니다."""
        while self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()

    def _record_usage(self, final) -> None:
        u = final.usage
        self.last_usage = {
            "input": u.input_tokens,
            "output": u.output_tokens,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        }
        for k in self.total_usage:
            self.total_usage[k] += self.last_usage[k]

    def estimated_cost(self) -> float | None:
        """지금까지 대화의 대략적인 비용(달러). 가격을 모르는 모델이면 None."""
        price = PRICES.get(self.model_id)
        if not price:
            return None
        t = self.total_usage
        return (t["input"] * price[0] + t["cache_read"] * price[0] * 0.1 + t["output"] * price[1]) / 1_000_000

    def ask(self, user_text: str) -> str:
        """스트리밍 없이 답변 전체를 한 번에 문자열로 받습니다."""
        return "".join(self.chat(user_text))
