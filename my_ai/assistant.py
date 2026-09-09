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
from pathlib import Path
from typing import Iterator

import anthropic

CONFIG_PATH = Path(__file__).parent / "config.json"

# 선택할 수 있는 모델 (이름: 모델 ID)
MODELS = {
    "Claude Opus 5 (가장 똑똑함, 기본값)": "claude-opus-5",
    "Claude Sonnet 5 (빠르고 저렴)": "claude-sonnet-5",
    "Claude Haiku 4.5 (가장 빠름)": "claude-haiku-4-5",
}

# 생각 깊이 (effort) 단계 - Opus/Sonnet 에서만 동작
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]

ANSWER_LENGTHS = {
    "짧게": "답변은 2~3문장으로 아주 짧게 합니다.",
    "보통": "답변은 핵심만 담아 적당한 길이로 합니다.",
    "길게": "답변은 배경 설명과 예시까지 포함해 자세히 합니다.",
}

DEFAULT_CONFIG = {
    "name": "나의 AI",
    "greeting": "안녕하세요! 무엇을 도와드릴까요?",
    "persona": "당신은 친절하고 똑똑한 AI 비서입니다.",
    "tone": "친근하고 편안한 말투",
    "language": "한국어",
    "answer_length": "보통",
    "use_emoji": False,
    "rules": [],
    "extra_instructions": "",
    "model": "claude-opus-5",
    "effort": "medium",
    "max_tokens": 4096,
    "show_thinking": False,
    "fallback_on_refusal": True,
    "memory_turns": 20,
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    """config.json 을 읽어서 설정 dict 로 돌려줍니다. 빠진 항목은 기본값으로 채웁니다."""
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    """설정을 config.json 에 저장합니다."""
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def build_system_prompt(cfg: dict) -> str:
    """설정 항목들을 하나의 시스템 프롬프트(AI 의 성격 설명서)로 합칩니다."""
    parts = [
        f"당신의 이름은 '{cfg['name']}' 입니다.",
        cfg["persona"].strip(),
        f"말투: {cfg['tone']}.",
        f"항상 {cfg['language']}로 답합니다.",
        ANSWER_LENGTHS.get(cfg["answer_length"], ANSWER_LENGTHS["보통"]),
        "이모지를 적절히 사용합니다." if cfg["use_emoji"] else "이모지는 사용하지 않습니다.",
    ]
    rules = [r.strip() for r in cfg.get("rules", []) if r.strip()]
    if rules:
        parts.append("반드시 지켜야 할 규칙:\n" + "\n".join(f"- {r}" for r in rules))
    if cfg.get("extra_instructions", "").strip():
        parts.append(cfg["extra_instructions"].strip())
    return "\n\n".join(parts)


class Assistant:
    """대화 기록을 기억하는 AI 비서."""

    def __init__(self, cfg: dict | None = None, client: anthropic.Anthropic | None = None):
        self.cfg = cfg or load_config()
        self._client = client
        self.messages: list[dict] = []
        self.last_thinking: str = ""

    @property
    def client(self) -> anthropic.Anthropic:
        """API 키(ANTHROPIC_API_KEY 환경변수)는 처음 대화할 때 읽습니다."""
        if self._client is None:
            try:
                self._client = anthropic.Anthropic()
            except TypeError:
                raise RuntimeError("API 키가 없습니다. ANTHROPIC_API_KEY 환경변수를 설정하세요.")
        return self._client

    # ---------- 설정 ----------
    def update_config(self, **changes) -> None:
        """설정 일부를 바꿉니다. 예: ai.update_config(tone="딱딱한 말투")"""
        self.cfg.update(changes)

    def reset(self) -> None:
        """대화 기록을 지우고 처음부터 시작합니다."""
        self.messages.clear()
        self.last_thinking = ""

    # ---------- 요청 만들기 ----------
    def _request_params(self) -> dict:
        cfg = self.cfg
        model = cfg["model"]
        params: dict = {
            "model": model,
            "max_tokens": int(cfg["max_tokens"]),
            # 시스템 프롬프트는 매번 같으므로 캐시해서 비용을 아낍니다.
            "system": [{
                "type": "text",
                "text": build_system_prompt(cfg),
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": self._recent_messages(),
        }
        # Haiku 4.5 는 effort / adaptive thinking 을 지원하지 않습니다.
        if not model.startswith("claude-haiku"):
            params["output_config"] = {"effort": cfg["effort"]}
            params["thinking"] = {
                "type": "adaptive",
                "display": "summarized" if cfg["show_thinking"] else "omitted",
            }
        if cfg.get("fallback_on_refusal"):
            # 안전 정책으로 답변이 거절되면 다른 모델이 이어서 답하도록 합니다.
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def _recent_messages(self) -> list[dict]:
        """memory_turns 만큼의 최근 대화만 보냅니다 (비용/속도 절약)."""
        keep = int(self.cfg.get("memory_turns", 20)) * 2  # 질문+답변 = 1턴
        msgs = self.messages[-keep:] if keep > 0 else self.messages
        # 첫 메시지는 반드시 user 여야 합니다.
        while msgs and msgs[0]["role"] != "user":
            msgs = msgs[1:]
        return msgs

    # ---------- 대화 ----------
    def chat(self, user_text: str) -> Iterator[str]:
        """질문을 보내고 답변 조각(str)을 순서대로 돌려줍니다 (스트리밍)."""
        client = self.client  # 키가 없으면 여기서 친절한 오류가 납니다.
        self.messages.append({"role": "user", "content": user_text})
        params = self._request_params()
        answer_parts: list[str] = []
        self.last_thinking = ""

        try:
            with client.beta.messages.stream(**params) as stream:
                for text in stream.text_stream:
                    answer_parts.append(text)
                    yield text
                final = stream.get_final_message()
        except TypeError:  # SDK 가 API 키를 못 찾으면 TypeError 를 냅니다.
            self.messages.pop()
            raise RuntimeError("API 키가 없습니다. ANTHROPIC_API_KEY 환경변수를 설정하세요.")
        except anthropic.AuthenticationError:
            self.messages.pop()
            raise RuntimeError("API 키가 올바르지 않습니다. ANTHROPIC_API_KEY 환경변수를 확인하세요.")
        except anthropic.RateLimitError:
            self.messages.pop()
            raise RuntimeError("요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
        except anthropic.APIConnectionError:
            self.messages.pop()
            raise RuntimeError("네트워크 연결에 실패했습니다. 인터넷 상태를 확인하세요.")
        except anthropic.APIStatusError as e:
            self.messages.pop()
            raise RuntimeError(f"API 오류 ({e.status_code}): {e.message}")

        for block in final.content:
            if block.type == "thinking" and block.thinking:
                self.last_thinking = block.thinking

        if final.stop_reason == "refusal":
            reason = final.stop_details.explanation if final.stop_details else "안전 정책"
            notice = f"\n\n(이 요청은 답변할 수 없습니다: {reason})"
            answer_parts.append(notice)
            yield notice

        # 답변 원문(thinking 포함)을 그대로 기록해야 같은 모델에서 대화가 자연스럽게 이어집니다.
        self.messages.append({"role": "assistant", "content": final.content})

    def ask(self, user_text: str) -> str:
        """스트리밍 없이 답변 전체를 한 번에 문자열로 받습니다."""
        return "".join(self.chat(user_text))
