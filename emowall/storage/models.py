"""存储层数据模型：会话与消息记录。

设计原则：
    * 使用 ``@dataclass(frozen=True)`` 保证不可变性；
    * 与 ``emowall/ai`` 的数据模型解耦（storage 不 import ai）；
    * 跨层映射由组合根 ``emowall/app.py`` 负责；
    * 标题规范化逻辑由 ``_normalize_title()`` 统一处理，
      ``create()`` / ``rename()`` / ``append_message()`` 自动标题共用。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 合法消息角色集合（与 ``emowall.ai.models.VALID_ROLES`` 保持一致）。
VALID_ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})

#: 会话标题最大字符数（Python ``len()`` 计数，代码点级别）。
MAX_TITLE_CHARS: int = 20


@dataclass(frozen=True)
class Conversation:
    """一个对话会话的元数据。

    Attributes:
        id: UUID v4 字符串，由 ``ConversationRepository.create()`` 内部生成。
        title: 会话标题，保证非空且 ≤ 20 个 Python 字符。
        model: 使用的模型名（如 ``"qwen3:8b"``）。
        created_at: ISO-8601 UTC 创建时间。
        updated_at: ISO-8601 UTC 最后更新时间。
    """

    id: str
    title: str
    model: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MessageRecord:
    """一条持久化的消息记录。

    Attributes:
        id: 行 ID（新建时为 None；``ConversationRepository`` 返回时保证非 None）。
        conversation_id: 所属会话 UUID。
        role: ``"system"`` | ``"user"`` | ``"assistant"``；
              Repository 负责校验合法值。
        content: 消息文本（可为空串）。
        emotion: 情绪标签名称（如 ``"happy"``），Stage 4 产出；
                 ``None`` 表示尚未分析。
        emotion_intensity: 情绪强度 ``[0.0, 1.0]``，Stage 4 产出；
                           ``None`` 表示尚未分析。
        created_at: ISO-8601 UTC 创建时间。
    """

    id: int | None
    conversation_id: str
    role: str
    content: str
    emotion: str | None
    emotion_intensity: float | None
    created_at: str


def _normalize_title(raw: str) -> str:
    """规范化会话标题。

    规则：
        1. ``strip()`` 去除首尾空白；
        2. 空串或纯空白 → ``"新会话"``；
        3. ``len(title) > 20`` → ``title[:17] + "..."``（总计 20 个 Python 字符）；
        4. 否则原样使用。

    "字符"统一使用 Python ``len()``（代码点计数），不做 Unicode 字素簇拆分。

    Args:
        raw: 原始标题字符串。

    Returns:
        规范化后的标题。
    """
    t = raw.strip()
    if not t:
        return "新会话"
    if len(t) > MAX_TITLE_CHARS:
        return t[:17] + "..."
    return t


__all__ = [
    "Conversation",
    "MAX_TITLE_CHARS",
    "MessageRecord",
    "VALID_ROLES",
]
