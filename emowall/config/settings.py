"""配置数据结构与字段校验。

设计要点：
    * frozen dataclass：**构造即校验**，非法值立刻抛 `ConfigValidationError`；
    * 默认值集中在本模块，`store` 只负责序列化/容错，不在别处散落默认值；
    * 纯标准库，不依赖 Qt / httpx，也不关心 Ollama 的真实连接方式。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .errors import ConfigValidationError

CURRENT_CONFIG_VERSION = 1

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_SYSTEM_PROMPT = "你是 EmoWall 的 AI 伙伴，回答简洁、自然、有情绪温度。"

MIN_NUM_CTX = 1024
MAX_NUM_CTX = 1_048_576
MAX_TIMEOUT_SECONDS = 3600.0
MAX_MODEL_CHARS = 200
MAX_SYSTEM_PROMPT_CHARS = 8000
MIN_CONTEXT_MESSAGES = 1
MAX_CONTEXT_MESSAGES = 200
MIN_CONTEXT_CHARS = 200
MAX_CONTEXT_CHARS = 200_000


def _fail(field_name: str, message: str) -> ConfigValidationError:
    return ConfigValidationError(f"{field_name}: {message}")


def _require_number(
    field_name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(field_name, f"必须是数值，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise _fail(field_name, f"必须是有限数值，收到 {value!r}")
    if not minimum <= number <= maximum:
        raise _fail(field_name, f"必须在 [{minimum}, {maximum}] 之间，收到 {number}")
    return number


def _require_int(field_name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field_name, f"必须是整数，收到 {value!r}")
    if not minimum <= value <= maximum:
        raise _fail(field_name, f"必须在 [{minimum}, {maximum}] 之间，收到 {value}")
    return value


def _require_bool(field_name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise _fail(field_name, f"必须是布尔值，收到 {value!r}")
    return value


def _require_text(
    field_name: str,
    value: object,
    *,
    max_chars: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise _fail(field_name, f"必须是字符串，收到 {value!r}")
    text = value.strip()
    if not allow_empty and not text:
        raise _fail(field_name, "不能为空")
    if len(text) > max_chars:
        raise _fail(field_name, f"长度不能超过 {max_chars} 字符（当前 {len(text)}）")
    return text


def validate_base_url(value: object) -> str:
    """校验 Ollama 服务地址：http/https、有主机、无空白字符。"""
    text = _require_text("ollama.base_url", value, max_chars=2000)
    if any(char.isspace() for char in text):
        raise _fail("ollama.base_url", f"不能包含空白字符，收到 {text!r}")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise _fail("ollama.base_url", f"必须是 http/https 地址，收到 {text!r}")
    return text


def validate_model(value: object) -> str:
    return _require_text("ollama.model", value, max_chars=MAX_MODEL_CHARS)


def validate_connect_timeout(value: object) -> float:
    return _require_number(
        "ollama.connect_timeout_seconds", value, minimum=0.1, maximum=MAX_TIMEOUT_SECONDS
    )


def validate_read_timeout(value: object) -> float:
    return _require_number(
        "ollama.read_timeout_seconds", value, minimum=1.0, maximum=MAX_TIMEOUT_SECONDS
    )


def validate_num_ctx(value: object) -> int:
    return _require_int("ollama.num_ctx", value, minimum=MIN_NUM_CTX, maximum=MAX_NUM_CTX)


def validate_temperature(value: object) -> float:
    return _require_number("ollama.temperature", value, minimum=0.0, maximum=2.0)


def validate_think(value: object) -> bool:
    return _require_bool("ollama.think", value)


def validate_max_context_messages(value: object) -> int:
    return _require_int(
        "chat.max_context_messages",
        value,
        minimum=MIN_CONTEXT_MESSAGES,
        maximum=MAX_CONTEXT_MESSAGES,
    )


def validate_max_context_chars(value: object) -> int:
    return _require_int(
        "chat.max_context_chars",
        value,
        minimum=MIN_CONTEXT_CHARS,
        maximum=MAX_CONTEXT_CHARS,
    )


def validate_system_prompt(value: object) -> str:
    return _require_text(
        "chat.system_prompt", value, max_chars=MAX_SYSTEM_PROMPT_CHARS, allow_empty=True
    )


OLLAMA_FIELD_VALIDATORS: dict[str, Callable[[object], Any]] = {
    "base_url": validate_base_url,
    "model": validate_model,
    "connect_timeout_seconds": validate_connect_timeout,
    "read_timeout_seconds": validate_read_timeout,
    "num_ctx": validate_num_ctx,
    "temperature": validate_temperature,
    "think": validate_think,
}

CHAT_FIELD_VALIDATORS: dict[str, Callable[[object], Any]] = {
    "max_context_messages": validate_max_context_messages,
    "max_context_chars": validate_max_context_chars,
    "system_prompt": validate_system_prompt,
}


@dataclass(frozen=True)
class OllamaSettings:
    """Ollama 连接与推理参数。

    这些值只是配置，不代表连接成功；真正的探活由 AI 核心（Stage 2）负责。
    """

    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 120.0
    num_ctx: int = 8192
    temperature: float = 0.7
    think: bool = False

    def __post_init__(self) -> None:
        for name, validator in OLLAMA_FIELD_VALIDATORS.items():
            # frozen dataclass 允许用 object.__setattr__ 归一化（去首尾空白等）
            object.__setattr__(self, name, validator(getattr(self, name)))


@dataclass(frozen=True)
class ChatSettings:
    """对话上下文的裁剪与提示词。"""

    max_context_messages: int = 20
    max_context_chars: int = 6000
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def __post_init__(self) -> None:
        for name, validator in CHAT_FIELD_VALIDATORS.items():
            object.__setattr__(self, name, validator(getattr(self, name)))


@dataclass(frozen=True)
class AppSettings:
    """应用配置根对象。"""

    ollama: OllamaSettings = field(default_factory=OllamaSettings)
    chat: ChatSettings = field(default_factory=ChatSettings)

    def __post_init__(self) -> None:
        if not isinstance(self.ollama, OllamaSettings):
            raise _fail("ollama", f"必须是 OllamaSettings，收到 {type(self.ollama).__name__}")
        if not isinstance(self.chat, ChatSettings):
            raise _fail("chat", f"必须是 ChatSettings，收到 {type(self.chat).__name__}")


def default_settings() -> AppSettings:
    """返回全默认配置（集合了所有默认值的唯一入口）。"""
    return AppSettings()
