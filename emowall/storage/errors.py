"""存储层异常层级。

设计原则：
    * 所有存储层错误都继承 ``StorageError``，调用方可以只捕获基类；
    * 常见故障有独立子类，避免「一个 Exception 静默吞掉所有问题」；
    * 与 ``AIError``、``ConfigError`` 平级，不继承彼此；
    * 有实际底层异常时保留原始 ``__cause__``；纯格式判定不伪造 cause。

异常层级::

    Exception
    └── StorageError
        ├── StorageConnectionError   # 连接阶段（Database.__init__）
        ├── StorageIntegrityError    # 数据完整性（外键、唯一约束等）
        ├── StorageIOError           # 磁盘读写失败
        └── StorageTimestampError    # 会话时间戳无法安全比较
"""

from __future__ import annotations


class StorageError(Exception):
    """存储层异常基类。"""


class StorageConnectionError(StorageError):
    """数据库连接失败（文件不可写、权限不足等）。

    发生在 ``Database.__init__`` 阶段的错误统一映射为本类。
    """


class StorageIntegrityError(StorageError):
    """数据完整性违规（外键约束、唯一约束等）。

    例如 ``conversation_id`` 不存在于 ``conversations`` 表。
    """


class StorageIOError(StorageError):
    """磁盘读写失败。

    发生在 ``ConversationRepository`` 操作阶段的磁盘 I/O 错误。
    """


class StorageTimestampError(StorageError):
    """At least one stored conversation timestamp cannot be safely compared.

    ``conversation_ids`` is the complete, immutable set of affected IDs from
    one ``list_recent`` read snapshot. User data is never placed in the message.
    """

    def __init__(self, message: str, *, conversation_ids: tuple[str, ...]) -> None:
        ids = tuple(sorted(set(conversation_ids)))
        if not ids:
            raise ValueError("conversation_ids must not be empty")
        if not all(isinstance(value, str) for value in ids):
            raise TypeError("conversation_ids must contain strings")
        super().__init__(message)
        self._conversation_ids = ids

    @property
    def conversation_ids(self) -> tuple[str, ...]:
        """All affected conversation IDs, deduplicated and sorted by ID."""
        return self._conversation_ids


__all__ = [
    "StorageConnectionError",
    "StorageError",
    "StorageIOError",
    "StorageIntegrityError",
    "StorageTimestampError",
]
