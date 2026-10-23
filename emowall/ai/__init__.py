"""AI 核心层（Stage 2）。

职责：
    * Ollama HTTP 传输（`POST /api/chat`，NDJSON 流式）
    * 增量文本解析与生成统计
    * 多轮上下文裁剪
    * 可取消的生成（`CancelToken`）
    * 错误分类（连接失败 / 超时 / 模型缺失 / HTTP 服务错误 / 协议错误 / 流中断 / 已取消）

依赖约束：仅标准库 + httpx。
禁止：import Qt 绑定库，禁止 import 其他 emowall 层（gui / storage / config / emotion / app）。
"""

from __future__ import annotations

from .cancel import CancelToken
from .client import DEFAULT_BASE_URL, OllamaClient
from .engine import ChatEngine
from .errors import (
    AIError,
    CancelledError,
    ModelNotFoundError,
    OllamaConnectionError,
    OllamaHTTPError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ProtocolError,
    StreamInterruptedError,
)
from .models import ChatChunk, ChatMessage, GenerationStats, Role

__all__ = [
    "AIError",
    "CancelledError",
    "CancelToken",
    "ChatChunk",
    "ChatEngine",
    "ChatMessage",
    "DEFAULT_BASE_URL",
    "GenerationStats",
    "ModelNotFoundError",
    "OllamaClient",
    "OllamaConnectionError",
    "OllamaHTTPError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "ProtocolError",
    "Role",
    "StreamInterruptedError",
]
