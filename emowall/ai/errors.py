"""AI 核心异常层级。

设计原则：
    * 所有 AI 核心错误都继承 `AIError`，调用方可以只捕获基类；
    * 常见故障有独立子类，避免「一个 Exception 静默吞掉所有问题」；
    * `OllamaUnavailableError` 保留为「服务不可用」总类，连接失败 / 超时 /
      HTTP 服务错误是它的子类；`ModelNotFoundError`、`ProtocolError`、
      `CancelledError` 是平级的具体错误。
"""

from __future__ import annotations


class AIError(Exception):
    """AI 核心错误基类。"""


class OllamaUnavailableError(AIError):
    """Ollama 服务不可用（连接、超时、HTTP 服务错误的基类）。"""


class OllamaConnectionError(OllamaUnavailableError):
    """无法与 Ollama 建立连接（服务未启动、地址错误、网络不可达）。"""


class OllamaTimeoutError(OllamaUnavailableError):
    """请求超时（连接、读取、写入或连接池等待超时）。"""


class OllamaHTTPError(OllamaUnavailableError):
    """Ollama 返回非 2xx HTTP 状态（404 模型不存在除外）。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ModelNotFoundError(AIError):
    """请求的模型不存在。"""


class ProtocolError(AIError):
    """响应格式不符合 Ollama 协议（JSON 结构错误、无有效 NDJSON 等）。"""


class StreamInterruptedError(ProtocolError):
    """流式生成在收到 done 标记之前异常中断。"""


class CancelledError(AIError):
    """用户主动取消生成（不是网络错误）。"""


__all__ = [
    "AIError",
    "CancelledError",
    "ModelNotFoundError",
    "OllamaConnectionError",
    "OllamaHTTPError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "ProtocolError",
    "StreamInterruptedError",
]
