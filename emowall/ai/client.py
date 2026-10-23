"""Ollama HTTP 传输层（同步、流式、可取消）。

只依赖标准库 + httpx，不依赖 Qt / 配置层 / 存储层。
对外暴露：
    * `version()`：读取 Ollama 版本；
    * `list_models()`：读取已安装模型名；
    * `stream_chat()`：发送 `/api/chat` 并逐块产出 `ChatChunk`。

所有网络故障都会转换为 `emowall.ai.errors` 中的明确异常，调用方不需要解析
httpx 异常，也不需要直接解析 Ollama 原始 JSON。
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import httpx

from .cancel import CancelToken
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
from .models import ChatChunk, ChatMessage, GenerationStats

logger = logging.getLogger("emowall.ai.client")

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 120.0
DEFAULT_WRITE_TIMEOUT = 30.0
DEFAULT_POOL_TIMEOUT = 5.0


def _positive_seconds(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} 必须是数值，收到 {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} 必须是大于 0 的有限数值，收到 {value!r}")
    return number


def _validate_base_url(base_url: object) -> str:
    if not isinstance(base_url, str):
        raise TypeError(f"base_url 必须是 str，收到 {type(base_url).__name__}")
    text = base_url.strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"base_url 必须是 http/https 地址，收到 {base_url!r}")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"base_url 端口非法，收到 {base_url!r}") from exc
    if parsed.query or parsed.fragment:
        raise ValueError(f"base_url 不能包含查询参数或片段，收到 {base_url!r}")
    # 允许 path 作为反向代理前缀，例如 http://host/ollama -> /ollama/api/chat
    return text


class OllamaClient:
    """Ollama 传输客户端。

    线程模型：同步、阻塞；由调用方（GUI 工作线程）负责不在主线程调用。
    资源：默认自己创建并关闭 `httpx.Client`；若注入外部 client，则只使用不关闭。
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        write_timeout: float = DEFAULT_WRITE_TIMEOUT,
        pool_timeout: float = DEFAULT_POOL_TIMEOUT,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("client 与 transport 只能提供一个")
        self._base_url = _validate_base_url(base_url)
        self._timeout = httpx.Timeout(
            connect=_positive_seconds("connect_timeout", connect_timeout),
            read=_positive_seconds("read_timeout", read_timeout),
            write=_positive_seconds("write_timeout", write_timeout),
            pool=_positive_seconds("pool_timeout", pool_timeout),
        )
        self._owns_client = client is None
        self._transport = transport
        self._closed = False
        self._client = client if client is not None else self._make_http_client()

    # ------------------------------------------------------------------
    # 生命周期与只读属性
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout(self) -> httpx.Timeout:
        return self._timeout

    @property
    def is_closed(self) -> bool:
        return self._closed or self._client.is_closed

    def close(self) -> None:
        if not self._owns_client:
            return
        self._closed = True
        if not self._client.is_closed:
            self._client.close()

    def _make_http_client(self) -> httpx.Client:
        # 本地 Ollama 默认不走系统代理；同时避免代理环境变量（如畸形 NO_PROXY）
        # 影响客户端构造。显式配置的远程地址仍可工作，只是不自动继承代理。
        return httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        )

    def _ensure_open(self) -> None:
        """取消会关闭底层 client；这里按需重建，使用户取消后仍能继续下一轮。"""
        if self._closed:
            raise OllamaUnavailableError("Ollama 客户端已关闭")
        if not self._client.is_closed:
            return
        if not self._owns_client:
            raise OllamaUnavailableError("注入的 HTTP 客户端已关闭")
        self._client = self._make_http_client()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 简单端点
    # ------------------------------------------------------------------

    def version(self) -> str:
        data = self._get_json("/api/version")
        if not isinstance(data, dict):
            raise ProtocolError("Ollama /api/version 响应必须是 JSON 对象")
        version = data.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ProtocolError("Ollama /api/version 响应缺少 version 字段")
        return version.strip()

    def list_models(self) -> list[str]:
        data = self._get_json("/api/tags")
        if not isinstance(data, dict):
            raise ProtocolError("Ollama /api/tags 响应必须是 JSON 对象")
        models = data.get("models")
        if not isinstance(models, list):
            raise ProtocolError("Ollama /api/tags 响应缺少 models 数组")

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                logger.warning("忽略 /api/tags 中非对象模型条目：%r", item)
                continue
            name = item.get("name", item.get("model"))
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
            else:
                logger.warning("忽略 /api/tags 中缺少模型名的条目：%r", item)
        return names

    # ------------------------------------------------------------------
    # 流式聊天
    # ------------------------------------------------------------------

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        options: Mapping[str, object] | None = None,
        think: bool = False,
        cancel: CancelToken | None = None,
    ) -> Iterator[ChatChunk]:
        """发送聊天请求，逐行解析 NDJSON 并产出 `ChatChunk`。

        生成器在迭代时才真正发请求；调用方必须消费完或显式关闭生成器，
        以便 `with` 块及时释放连接。
        """
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model 不能为空")
        if not isinstance(think, bool):
            raise TypeError(f"think 必须是 bool，收到 {type(think).__name__}")

        payload_messages = self._serialize_messages(messages)
        if not payload_messages:
            raise ValueError("messages 不能为空")

        payload: dict[str, Any] = {
            "model": model.strip(),
            "messages": payload_messages,
            "stream": True,
            "think": think,
        }
        if options is not None:
            if not isinstance(options, Mapping):
                raise TypeError(f"options 必须是 Mapping，收到 {type(options).__name__}")
            if options:
                payload["options"] = dict(options)

        if cancel is not None:
            cancel.raise_if_cancelled()
        self._ensure_open()
        http_client = self._client

        try:
            # 连接/等待响应头阶段也需要可关闭资源：取消时关闭底层 client，
            # 可立即中断阻塞的 send()；随后由 _ensure_open() 重建。
            owned_client_closer = http_client.close if self._owns_client else None
            with self._track_closer(cancel, owned_client_closer):
                with http_client.stream(
                    "POST",
                    self._url("/api/chat"),
                    json=payload,
                    timeout=self._timeout,
                    headers={"Accept": "application/x-ndjson"},
                ) as response:
                    with self._track_closer(cancel, response.close):
                        if cancel is not None:
                            cancel.raise_if_cancelled()
                        if not (200 <= response.status_code < 300):
                            self._raise_for_status(response, model_not_found=True)
                        yield from self._iter_chunks(response, cancel)
        except CancelledError:
            raise
        except AIError:
            raise
        except httpx.InvalidURL as exc:
            raise ProtocolError(f"Ollama 地址无效：{exc}") from exc
        except httpx.TimeoutException as exc:
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise OllamaTimeoutError(f"Ollama 请求超时：{exc}") from exc
        except httpx.ConnectError as exc:
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise OllamaConnectionError(
                f"无法连接 Ollama（{self._base_url}）：{exc}"
            ) from exc
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.StreamClosed) as exc:
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise StreamInterruptedError(f"流式响应中断：{exc}") from exc
        except httpx.DecodingError as exc:
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise ProtocolError(f"Ollama 响应编码无法解析：{exc}") from exc
        except httpx.HTTPError as exc:
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise OllamaUnavailableError(f"Ollama 请求失败：{exc}") from exc
        except RuntimeError as exc:
            # httpx.Client 已关闭 / 流已关闭；取消场景优先识别为用户取消
            if cancel is not None and cancel.is_cancelled:
                raise CancelledError("生成已取消") from exc
            raise StreamInterruptedError(f"流式响应已关闭：{exc}") from exc

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    @staticmethod
    @contextmanager
    def _track_closer(
        cancel: CancelToken | None, closer: Callable[[], None] | None
    ) -> Iterator[None]:
        if cancel is None or closer is None:
            yield
            return
        cancel._register(closer)
        try:
            yield
        finally:
            cancel._unregister(closer)

    def _get_json(self, path: str) -> Any:
        self._ensure_open()
        try:
            response = self._client.get(
                self._url(path),
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        except httpx.InvalidURL as exc:
            raise ProtocolError(f"Ollama 地址无效：{exc}") from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(f"Ollama 请求超时：{exc}") from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"无法连接 Ollama（{self._base_url}）：{exc}"
            ) from exc
        except httpx.DecodingError as exc:
            raise ProtocolError(f"Ollama 响应编码无法解析：{exc}") from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(f"Ollama 请求失败：{exc}") from exc
        except RuntimeError as exc:
            raise OllamaUnavailableError(f"Ollama 客户端不可用：{exc}") from exc

        try:
            self._raise_for_status(response)
            try:
                return response.json()
            except ValueError as exc:
                raise ProtocolError(f"Ollama 响应不是合法 JSON：{exc}") from exc
        finally:
            response.close()

    def _raise_for_status(
        self, response: httpx.Response, *, model_not_found: bool = False
    ) -> None:
        if 200 <= response.status_code < 300:
            return
        message = self._error_message(response)
        if model_not_found and response.status_code == 404:
            raise ModelNotFoundError(message or "模型不存在（HTTP 404）")
        raise OllamaHTTPError(
            message or f"Ollama 返回 HTTP {response.status_code}",
            status_code=response.status_code,
        )

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.read()
        except Exception:  # 读取错误正文失败时保留状态码信息
            logger.warning("读取 Ollama 错误响应正文失败", exc_info=True)
            return ""
        if not body:
            return ""
        text = body.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(text)
        except ValueError:
            return text[:500]
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()[:500]
        return text[:500]

    @staticmethod
    def _serialize_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
        if isinstance(messages, (str, bytes)):
            raise TypeError("messages 必须是 ChatMessage 序列，不能是字符串")
        try:
            iterator = iter(messages)
        except TypeError as exc:
            raise TypeError("messages 必须是 ChatMessage 序列") from exc

        payload: list[dict[str, str]] = []
        for message in iterator:
            if not isinstance(message, ChatMessage):
                raise TypeError(
                    f"messages 只能包含 ChatMessage，收到 {type(message).__name__}"
                )
            payload.append({"role": message.role, "content": message.content})
        return payload

    def _iter_chunks(
        self, response: httpx.Response, cancel: CancelToken | None
    ) -> Iterator[ChatChunk]:
        valid_events = 0
        saw_done = False

        for line in response.iter_lines():
            if cancel is not None:
                cancel.raise_if_cancelled()
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except ValueError:
                logger.warning("跳过无法解析的 NDJSON 行（长度 %d）", len(line))
                continue

            if not isinstance(data, dict):
                logger.warning("跳过非对象 NDJSON 行（长度 %d）", len(line))
                continue

            if "error" in data:
                error = data.get("error")
                message = error.strip() if isinstance(error, str) and error.strip() else "Ollama 返回未知错误"
                raise self._error_for_message(message)

            message = data.get("message")
            text = ""
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    text = content
                elif content is not None:
                    logger.warning("跳过 message.content 非字符串的 NDJSON 行")
                    continue
            elif message is not None:
                logger.warning("跳过 message 非对象的 NDJSON 行")
                continue

            if data.get("done") is True:
                valid_events += 1
                saw_done = True
                yield ChatChunk(text=text, done=True, stats=self._parse_stats(data))
                return

            if text:
                valid_events += 1
                yield ChatChunk(text=text, done=False)

        if valid_events == 0:
            raise ProtocolError("Ollama 响应中没有可解析的 NDJSON 数据")
        if not saw_done:
            raise StreamInterruptedError("流式响应在 done 标记之前中断")

    @staticmethod
    def _error_for_message(message: str) -> AIError:
        lowered = message.lower()
        model_related = "model" in lowered and (
            "not found" in lowered
            or "does not exist" in lowered
            or "unknown" in lowered
            or "no such" in lowered
        )
        if model_related:
            return ModelNotFoundError(message)
        return OllamaUnavailableError(message)

    @classmethod
    def _parse_stats(cls, data: Mapping[str, Any]) -> GenerationStats:
        done_reason = data.get("done_reason")
        return GenerationStats(
            eval_count=cls._non_negative_int(data.get("eval_count")),
            prompt_eval_count=cls._non_negative_int(data.get("prompt_eval_count")),
            total_duration_ms=cls._ns_to_ms(data.get("total_duration")),
            load_duration_ms=cls._ns_to_ms(data.get("load_duration")),
            done_reason=done_reason if isinstance(done_reason, str) else None,
        )

    @staticmethod
    def _non_negative_int(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @staticmethod
    def _ns_to_ms(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return round(value / 1_000_000)
