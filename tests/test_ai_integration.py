"""真实 Ollama 集成测试（默认跳过，手动 `-m integration` 运行）。

验收重点是协议、事件顺序、状态与资源释放，而不是具体回复文字。
运行前需确保本机 Ollama 已启动且默认模型可用。
完整运行还要求确认无其他模型任务并卸载模型；冷启动测试只检查、不自动卸载。
资源验收会只读检查当前 httpx/httpcore 的连接池内部状态，升级依赖时需复核。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from emowall.ai import (
    AIError,
    CancelledError,
    CancelToken,
    ChatChunk,
    ChatMessage,
    ModelNotFoundError,
    OllamaClient,
)
from emowall.config import AppSettings, default_settings
from scripts.check_env import _http_json

pytestmark = pytest.mark.integration
logger = logging.getLogger("emowall.tests.integration")


@pytest.fixture(scope="module")
def settings() -> AppSettings:
    return default_settings()


@pytest.fixture(scope="module")
def client(settings: AppSettings) -> Iterator[OllamaClient]:
    ollama = settings.ollama
    instance = OllamaClient(
        ollama.base_url,
        connect_timeout=ollama.connect_timeout_seconds,
        read_timeout=ollama.read_timeout_seconds,
    )
    try:
        instance.version()
    except AIError as exc:  # Ollama 未启动时跳过，保持集成测试可重复
        instance.close()
        pytest.skip(f"Ollama 不可用：{exc}")
    try:
        yield instance
    finally:
        instance.close()
        assert instance.is_closed
        assert not instance._client._transport._pool.connections
        assert not instance._client._transport._pool._requests


def _collect(client: OllamaClient, messages: list[ChatMessage], *, model: str) -> str:
    parts: list[str] = []
    for chunk in client.stream_chat(
        model=model,
        messages=messages,
        options={"num_ctx": 4096, "temperature": 0.0},
    ):
        parts.append(chunk.text)
    return "".join(parts)


def test_version_is_reachable(client: OllamaClient) -> None:
    assert client.version()


def test_configured_model_is_installed(client: OllamaClient, settings: AppSettings) -> None:
    models = client.list_models()
    assert settings.ollama.model in models, f"本机未安装 {settings.ollama.model}：{models}"


def test_cold_start_cancel_before_headers_within_one_second(
    client: OllamaClient, settings: AppSettings,
    record_property: Callable[[str, object], None],
) -> None:
    """须先人工确认模型独占且未驻留；本测试不会卸载其他任务的模型。"""
    status, running = _http_json(f"{settings.ollama.base_url}/api/ps", timeout=5.0)
    assert status == 200 and isinstance(running, dict)
    assert not running["models"], "冷启动前置条件不满足；确认无其他任务后再卸载模型重跑"
    token = CancelToken()
    waiting_headers = threading.Event()
    got_headers = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    chunks: list[ChatChunk] = []
    exited_at: list[float] = []
    headers_completed_at: list[float] = []
    trace_events: list[tuple[str, float]] = []
    http_client = client._client

    def trace(name: str, info: dict[str, Any]) -> None:
        trace_events.append((name, time.perf_counter()))
        if name == "http11.receive_response_headers.started":
            waiting_headers.set()
        if name == "http11.receive_response_headers.complete":
            headers_completed_at.append(time.perf_counter())

    def on_request(request: Any) -> None:
        request.extensions["trace"] = trace

    def on_response(response: Any) -> None:
        got_headers.set()

    def consume() -> None:
        try:
            chunks.extend(client.stream_chat(
                model=settings.ollama.model,
                messages=[ChatMessage("user", "请写一篇关于春天的长文章。")],
                options={"num_ctx": 4096, "num_predict": 128}, cancel=token,
            ))
        except BaseException as exc:
            errors.append(exc)
        finally:
            exited_at.append(time.perf_counter())
            finished.set()

    http_client.event_hooks["request"].append(on_request)
    http_client.event_hooks["response"].append(on_response)
    thread = threading.Thread(target=consume, name="ollama-cold-cancel", daemon=True)
    thread.start()
    try:
        assert waiting_headers.wait(10), "请求未到达等待响应头阶段"
        assert not finished.wait(0.25), "冷启动请求在取消前已经结束"
        assert not got_headers.is_set(), "已收到响应头，不能作为响应头前取消证据"
        old_connections = list(http_client._transport._pool.connections)
        assert old_connections, "等待响应头时没有可检查的活动连接"
        started = time.perf_counter()
        token.cancel()
        cancel_returned = time.perf_counter() - started
        thread.join(settings.ollama.read_timeout_seconds + 10)
        worker_elapsed = exited_at[0] - started if exited_at else float("inf")
        elapsed = max(worker_elapsed, cancel_returned)
        record_property("cold_cancel_seconds", elapsed)
        record_property("worker_exit_seconds", worker_elapsed)
        record_property("cancel_call_seconds", cancel_returned)
        logger.info("cold_cancel_seconds=%.6f cancel_call_seconds=%.6f chunks=%d",
                    elapsed, cancel_returned, len(chunks))
        logger.info("cold_trace_offsets=%s error_types=%s",
                    [(name, round(at - started, 6)) for name, at in trace_events],
                    [(type(exc).__name__, type(exc.__cause__).__name__) for exc in errors])
        assert not thread.is_alive(), "取消后消费线程未退出"
        assert all(at >= started for at in headers_completed_at)
        assert len(errors) == 1 and isinstance(errors[0], CancelledError), errors
        assert chunks == []
        assert http_client.is_closed
        assert not http_client._transport._pool.connections
        assert not http_client._transport._pool._requests
        assert all(connection.is_closed() for connection in old_connections)
        token.reset()
        assert elapsed < 1.0, f"冷启动取消超过 1 秒目标：{elapsed:.6f}s"
    finally:
        token.cancel()
        thread.join(settings.ollama.read_timeout_seconds + 10)
        http_client.event_hooks["request"].remove(on_request)
        http_client.event_hooks["response"].remove(on_response)
        assert not thread.is_alive(), "冷启动测试清理后仍有活动消费线程"


def test_simple_chat_returns_text_and_stats(client: OllamaClient, settings: AppSettings) -> None:
    chunks: list[ChatChunk] = list(
        client.stream_chat(
            model=settings.ollama.model,
            messages=[ChatMessage("user", "请只回复：你好")],
            options={"num_ctx": 4096, "temperature": 0.0},
        )
    )

    assert chunks, "没有收到任何流式事件"
    assert chunks[-1].done is True
    assert chunks[-1].stats is not None
    text = "".join(chunk.text for chunk in chunks)
    assert text.strip(), "模型返回了空文本"
    if chunks[-1].stats.eval_count is not None:
        assert chunks[-1].stats.eval_count > 0


def test_streaming_events_are_ordered(client: OllamaClient, settings: AppSettings) -> None:
    chunks = list(
        client.stream_chat(
            model=settings.ollama.model,
            messages=[ChatMessage("user", "数到三，只输出 1 2 3")],
            options={"num_ctx": 4096, "temperature": 0.0},
        )
    )
    assert chunks, "没有收到任何流式事件"
    assert chunks[-1].done is True
    assert all(not chunk.done for chunk in chunks[:-1]), "done 只能出现在最后一个事件"


def test_two_turn_conversation_keeps_context(client: OllamaClient, settings: AppSettings) -> None:
    first_user = ChatMessage("user", "请记住数字 42，只回复：好的")
    first_reply = _collect(client, [first_user], model=settings.ollama.model)
    assert first_reply.strip()

    history = [
        first_user,
        ChatMessage("assistant", first_reply),
        ChatMessage("user", "我刚才让你记住的数字是多少？只回复数字。"),
    ]
    second_reply = _collect(client, history, model=settings.ollama.model)
    assert any(token in second_reply for token in ("42", "四十二", "四二", "forty-two", "forty two")), (
        f"第二轮没有体现上下文：{second_reply!r}"
    )


def test_cancel_stops_generation_and_next_turn_works(
    client: OllamaClient, settings: AppSettings
) -> None:
    token = CancelToken()
    generator = client.stream_chat(
        model=settings.ollama.model,
        messages=[ChatMessage("user", "请写一篇 800 字左右的文章，主题是自律。")],
        options={"num_ctx": 4096, "temperature": 0.7},
        cancel=token,
    )
    try:
        first = next(generator, None)
        assert first is not None and not first.done, "没有收到可取消的增量块"

        started = time.perf_counter()
        token.cancel()
        with pytest.raises(CancelledError):
            next(generator)
        assert time.perf_counter() - started < 1.0
    finally:
        generator.close()

    # 取消后新令牌、新请求必须正常，不受上一轮影响
    reply = _collect(
        client,
        [ChatMessage("user", "只回复：恢复成功")],
        model=settings.ollama.model,
    )
    assert reply.strip()


def test_unknown_model_is_classified(client: OllamaClient, settings: AppSettings) -> None:
    with pytest.raises(ModelNotFoundError):
        list(
            client.stream_chat(
                model="this-model-does-not-exist:0b",
                messages=[ChatMessage("user", "hi")],
            )
        )


def test_repeated_cancel_and_recovery_release_http_resources(
    client: OllamaClient, settings: AppSettings,
    record_property: Callable[[str, object], None],
) -> None:
    for index in range(3):
        token = CancelToken()
        responses: list[Any] = []
        # 上轮取消后 _collect 已触发默认 HTTP 客户端重建。
        http_client = client._client
        http_client.event_hooks["response"].append(responses.append)
        generator = client.stream_chat(
            model=settings.ollama.model,
            messages=[ChatMessage("user", "请详细介绍太阳系，至少列举八颗行星。")],
            options={"num_ctx": 4096, "num_predict": 256}, cancel=token,
        )
        try:
            assert not next(generator).done
            old_connections = list(http_client._transport._pool.connections)
            started = time.perf_counter()
            token.cancel()
            with pytest.raises(CancelledError):
                next(generator)
            elapsed = time.perf_counter() - started
            record_property(f"repeat_cancel_{index + 1}_seconds", elapsed)
            logger.info("repeat_cancel_%d_seconds=%.6f", index + 1, elapsed)
            assert elapsed < 1.0
            assert http_client.is_closed
            assert responses and all(response.is_closed for response in responses)
            assert not http_client._transport._pool.connections
            assert not http_client._transport._pool._requests
            assert old_connections and all(connection.is_closed() for connection in old_connections)
            token.reset()
        finally:
            generator.close()
            http_client.event_hooks["response"].remove(responses.append)
        assert _collect(client, [ChatMessage("user", "只回复：恢复成功")],
                        model=settings.ollama.model).strip()
        assert client._client is not http_client
        assert not client.is_closed
        # 默认池可保留一个空闲 keep-alive 连接；不能逐轮累积活动连接。
        connections = client._client._transport._pool.connections
        assert len(connections) <= 1
        assert all(connection.is_idle() for connection in connections)


def test_generator_early_close_releases_real_response(
    client: OllamaClient, settings: AppSettings,
) -> None:
    token = CancelToken()
    responses: list[Any] = []
    http_client = client._client
    http_client.event_hooks["response"].append(responses.append)
    generator = client.stream_chat(
        model=settings.ollama.model,
        messages=[ChatMessage("user", "请详细介绍太阳系。")],
        options={"num_ctx": 4096, "num_predict": 128}, cancel=token,
    )
    try:
        assert not next(generator).done
    finally:
        generator.close()
        http_client.event_hooks["response"].remove(responses.append)
    assert responses and all(response.is_closed for response in responses)
    assert not http_client._transport._pool.connections
    assert not http_client._transport._pool._requests
    assert not client.is_closed
    token.reset()
    assert _collect(client, [ChatMessage("user", "只回复：好的")],
                    model=settings.ollama.model).strip()
