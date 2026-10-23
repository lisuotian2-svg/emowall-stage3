"""AI 通用数据模型：消息、流式事件、生成统计。

这些类型与 GUI / 存储 / Ollama 传输细节解耦：
    * `ChatMessage` 是标准对话消息（system / user / assistant）；
    * `ChatChunk` 是流式生成事件（增量文本 + 是否结束 + 结束统计）；
    * `GenerationStats` 是 done 事件的统计信息（时间为毫秒，便于跨提供者统一）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]

VALID_ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class ChatMessage:
    """一条对话消息。

    构造即校验：角色必须是 system / user / assistant，内容必须是字符串。
    `content` 允许为空串（例如失败时为空的 assistant 占位）；是否发送由引擎决定。
    """

    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"非法消息角色：{self.role!r}（只允许 system / user / assistant）")
        if not isinstance(self.content, str):
            raise TypeError(f"消息内容必须是 str，收到 {type(self.content).__name__}")


@dataclass(frozen=True)
class GenerationStats:
    """一次生成结束时的统计信息；字段缺失时为 None。"""

    eval_count: int | None = None
    prompt_eval_count: int | None = None
    total_duration_ms: int | None = None
    load_duration_ms: int | None = None
    done_reason: str | None = None


@dataclass(frozen=True)
class ChatChunk:
    """流式生成事件。

    * `text`：本次增量文本，可为空串（例如只带统计的 done 事件）；
    * `done`：是否为最后一块；
    * `stats`：仅 done 块通常携带。
    """

    text: str
    done: bool = False
    stats: GenerationStats | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError(f"text 必须是 str，收到 {type(self.text).__name__}")
        if not isinstance(self.done, bool):
            raise TypeError(f"done 必须是 bool，收到 {type(self.done).__name__}")
        if self.stats is not None and not isinstance(self.stats, GenerationStats):
            raise TypeError("stats 必须是 GenerationStats 或 None")

    @classmethod
    def final(cls, text: str = "", stats: GenerationStats | None = None) -> ChatChunk:
        """构造结束事件（便于调用方与测试统一表达）。"""
        return cls(text=text, done=True, stats=stats)
