"""SQLite 存储层（Stage 3 实现）。

职责：
    * 数据库连接、PRAGMA、建表与版本迁移
    * 会话（conversations）与消息（messages）的仓库接口

依赖约束：仅标准库（sqlite3）。
禁止：导入界面框架、HTTP 客户端及其他 emowall 层。
"""

from __future__ import annotations

from .database import Database
from .errors import (
    StorageConnectionError,
    StorageError,
    StorageIntegrityError,
    StorageIOError,
    StorageTimestampError,
)
from .models import Conversation, MessageRecord
from .repository import ConversationRepository

__all__ = [
    "Conversation",
    "ConversationRepository",
    "Database",
    "MessageRecord",
    "StorageConnectionError",
    "StorageError",
    "StorageIntegrityError",
    "StorageIOError",
    "StorageTimestampError",
]
