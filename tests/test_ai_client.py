"""AI 传输层离线测试：MockTransport 模拟 Ollama，全部不触碰真实网络。

覆盖：普通响应、NDJSON 分块、流式取消、超时、连接失败、模型缺失、协议错误、
资源释放、客户端关闭，以及「无 Qt 依赖 / 无真实网络」的守护。
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from emowall.ai import (
    AIError,
    CancelledError,
    CancelToken,
    ChatEngine,
    ChatMessage,
    ModelNotFoundError,
    OllamaClient,
    OllamaConnectionError,
    OllamaHTTPError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ProtocolError,
    StreamInterruptedError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NDJSON_HEADERS = {"content-type": "application/x-ndjson"}


class ChunkStream(httpx.SyncByteStream):
    """按给定字节块输出响应体，用于模拟任意网络分块。"""

    def __init__(self, chunks: Iterable[bytes]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class BlockingStream(httpx.SyncByteStream):
    """先产出一个块，然后阻塞；close() 负责唤醒并模拟连接中断。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.released = threading.Event()
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield _line({"message": {"role": "assistant", "content": "first"}, "done": False})
        self.started.set()
        self.released.wait(5)
        raise httpx.ReadError("stream closed by cancel")

    def close(self) -> None:
        self.closed = True
        self.released.set()


def _line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


class HeaderBlockingTransport(httpx.BaseTransport):
    """第一次请求在返回响应头前阻塞，close() 会释放；第二次正常返回。

    用于覆盖「冷启动 / 等待响应头」阶段的取消，而不是只覆盖读流阶段。
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            self.released.wait(5)
            raise httpx.ReadError("aborted while waiting for headers", request=request)
        body = _line({"message": {"content": "ok"}, "done": False}) + _line(_done())
        return httpx.Response(200, content=body, headers=NDJSON_HEADERS)

    def close(self) -> None:
        self.released.set()


def _ndjson(
    lines: Iterable[dict[str, Any]],
    *,
    chunks: Iterable[bytes] | None = None,
    status: int = 200,
) -> httpx.Response:
    body = b"".join(_line(line) for line in lines)
    if chunks is None:
        return httpx.Response(status, content=body, headers=NDJSON_HEADERS)
    return httpx.Response(status, stream=ChunkStream(chunks), headers=NDJSON_HEADERS)


def _done(**extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": {"role": "assistant", "content": ""}, "done": True}
    payload.update(extra)
    return payload


@pytest.fixture()
def client_factory() -> Iterator[Any]:
    created: list[httpx.Client] = []

    def factory(handler: Any) -> tuple[OllamaClient, httpx.Client]:
        http = httpx.Client(transport=httpx.MockTransport(handler))
        created.append(http)
        return OllamaClient("http://mock", client=http), http

    yield factory
    for http in created:
        http.close()


# ---------------------------------------------------------------------------
# 基础端点
# ---------------------------------------------------------------------------


def test_version_reads_ollama_version(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"version": "0.40.6"})

    client, _ = client_factory(handler)
    assert client.version() == "0.40.6"


def test_version_rejects_malformed_json(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: httpx.Response(200, text="not-json"))
    with pytest.raises(ProtocolError):
        client.version()


def test_version_rejects_non_object_json(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: httpx.Response(200, json=["0.40.6"]))
    with pytest.raises(ProtocolError):
        client.version()


def test_version_rejects_missing_field(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ProtocolError):
        client.version()


def test_list_models_returns_names(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:8b"},
                    {"model": "llama3:8b"},
                    {"name": ""},
                    {"bad": True},
                ]
            },
        )

    client, _ = client_factory(handler)
    assert client.list_models() == ["qwen3:8b", "llama3:8b"]


def test_list_models_rejects_non_list_models(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: httpx.Response(200, json={"models": "nope"}))
    with pytest.raises(ProtocolError):
        client.list_models()


def test_list_models_rejects_missing_models(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: httpx.Response(200, json={"other": []}))
    with pytest.raises(ProtocolError):
        client.list_models()


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------


def test_http_500_is_service_error(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(500, json={"error": "internal boom"})
    )
    with pytest.raises(OllamaHTTPError) as excinfo:
        client.list_models()
    assert excinfo.value.status_code == 500
    assert "boom" in str(excinfo.value)


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_failure_preserves_http_status(client_factory: Any, status_code: int) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(status_code, json={"error": "access denied"})
    )
    with pytest.raises(OllamaHTTPError) as excinfo:
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert excinfo.value.status_code == status_code


def test_http_redirect_is_error(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(302, json={"version": "9.9.9"})
    )
    with pytest.raises(OllamaHTTPError) as excinfo:
        client.version()
    assert excinfo.value.status_code == 302


def test_http_404_on_chat_is_model_not_found(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(404, json={"error": "model 'nope' not found"})
    )
    with pytest.raises(ModelNotFoundError):
        list(client.stream_chat(model="nope", messages=[ChatMessage("user", "hi")]))


def test_http_404_on_tags_is_http_error(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(404, json={"error": "page not found"})
    )
    with pytest.raises(OllamaHTTPError) as excinfo:
        client.list_models()
    assert excinfo.value.status_code == 404


def test_connection_refused_is_connection_error(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, _ = client_factory(handler)
    with pytest.raises(OllamaConnectionError):
        client.version()


def test_connect_timeout_is_timeout_error(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout", request=request)

    client, _ = client_factory(handler)
    with pytest.raises(OllamaTimeoutError):
        client.version()


def test_read_timeout_is_timeout_error(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout", request=request)

    client, _ = client_factory(handler)
    with pytest.raises(OllamaTimeoutError):
        client.list_models()


def test_timeout_during_stream_is_timeout_error(client_factory: Any) -> None:
    class TimeoutStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield _line({"message": {"role": "assistant", "content": "a"}, "done": False})
            raise httpx.ReadTimeout("stream read timeout")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=TimeoutStream(), headers=NDJSON_HEADERS)

    client, _ = client_factory(handler)
    chunks: list[Any] = []
    with pytest.raises(OllamaTimeoutError):
        for chunk in client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]):
            chunks.append(chunk)
    assert [chunk.text for chunk in chunks] == ["a"]


# ---------------------------------------------------------------------------
# 流式 NDJSON
# ---------------------------------------------------------------------------


def test_stream_chat_assembles_text_and_stats(client_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return _ndjson(
            [
                {"message": {"role": "assistant", "content": "你"}, "done": False},
                {"message": {"role": "assistant", "content": "好"}, "done": False},
                _done(
                    done_reason="stop",
                    eval_count=7,
                    prompt_eval_count=3,
                    total_duration=1_500_000_000,
                    load_duration=250_000_000,
                ),
            ]
        )

    client, _ = client_factory(handler)
    chunks = list(client.stream_chat(model="qwen3:8b", messages=[ChatMessage("user", "hi")]))

    assert [chunk.text for chunk in chunks] == ["你", "好", ""]
    assert chunks[-1].done is True
    stats = chunks[-1].stats
    assert stats is not None
    assert stats.eval_count == 7
    assert stats.prompt_eval_count == 3
    assert stats.total_duration_ms == 1500
    assert stats.load_duration_ms == 250
    assert stats.done_reason == "stop"


def test_stream_chat_handles_chunk_boundaries_inside_json_and_utf8(
    client_factory: Any,
) -> None:
    body = (
        _line({"message": {"role": "assistant", "content": "你"}, "done": False})
        + _line({"message": {"role": "assistant", "content": "好"}, "done": False})
        + _line(_done())
    )
    # 故意在 JSON 中间、以及「你」的 UTF-8 字节序列中间切开
    utf8_index = body.index("你".encode("utf-8")) + 1
    boundaries = [0, 3, utf8_index, utf8_index + 2, len(body) // 2, len(body) - 1, len(body)]
    chunks = [body[boundaries[i] : boundaries[i + 1]] for i in range(len(boundaries) - 1)]

    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=ChunkStream(chunks), headers=NDJSON_HEADERS)
    )
    received = list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert [chunk.text for chunk in received] == ["你", "好", ""]
    assert received[-1].done is True


def test_stream_chat_skips_blank_lines_and_bad_lines(
    client_factory: Any, caplog: pytest.LogCaptureFixture
) -> None:
    body = (
        b"\n"
        + _line({"message": {"role": "assistant", "content": "a"}, "done": False})
        + b"not-json\n"
        + _line(_done())
    )

    client, _ = client_factory(
        lambda request: httpx.Response(200, content=body, headers=NDJSON_HEADERS)
    )
    with caplog.at_level(logging.WARNING, logger="emowall.ai.client"):
        chunks = list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert [chunk.text for chunk in chunks] == ["a", ""]
    assert any("NDJSON" in record.message for record in caplog.records)


def test_stream_chat_all_bad_lines_is_protocol_error(client_factory: Any) -> None:
    body = b"not-json\n{bad}\n"
    client, _ = client_factory(
        lambda request: httpx.Response(200, content=body, headers=NDJSON_HEADERS)
    )
    with pytest.raises(ProtocolError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_empty_body_is_protocol_error(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: httpx.Response(200, content=b"", headers=NDJSON_HEADERS)
    )
    with pytest.raises(ProtocolError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_eof_before_done_is_interrupted(client_factory: Any) -> None:
    body = _line({"message": {"role": "assistant", "content": "partial"}, "done": False})
    client, _ = client_factory(
        lambda request: httpx.Response(200, content=body, headers=NDJSON_HEADERS)
    )
    with pytest.raises(StreamInterruptedError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_error_event_model_not_found(client_factory: Any) -> None:
    client, _ = client_factory(
        lambda request: _ndjson([{"error": "model 'nope' not found"}])
    )
    with pytest.raises(ModelNotFoundError):
        list(client.stream_chat(model="nope", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_error_event_service_error(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: _ndjson([{"error": "out of memory"}]))
    with pytest.raises(OllamaUnavailableError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_error_event_route_not_found_is_not_model_error(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: _ndjson([{"error": "route not found"}]))
    with pytest.raises(OllamaUnavailableError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_payload_is_correct(client_factory: Any) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _ndjson([_done()])

    client, _ = client_factory(handler)
    list(
        client.stream_chat(
            model="llama3:70b",
            messages=[
                ChatMessage("system", "sys"),
                ChatMessage("user", "你好"),
                ChatMessage("assistant", "hi"),
            ],
            options={"temperature": 0.2, "num_ctx": 4096},
            think=True,
        )
    )

    assert captured["model"] == "llama3:70b"
    assert captured["stream"] is True
    assert captured["think"] is True
    assert captured["options"] == {"temperature": 0.2, "num_ctx": 4096}
    assert captured["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "hi"},
    ]


def test_stream_chat_omits_options_when_none(client_factory: Any) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _ndjson([_done()])

    client, _ = client_factory(handler)
    list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert "options" not in captured
    assert captured["think"] is False


def test_stream_chat_rejects_empty_messages(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: _ndjson([_done()]))
    with pytest.raises(ValueError):
        list(client.stream_chat(model="m", messages=[]))


def test_stream_chat_rejects_empty_model(client_factory: Any) -> None:
    client, _ = client_factory(lambda request: _ndjson([_done()]))
    with pytest.raises(ValueError):
        list(client.stream_chat(model="  ", messages=[ChatMessage("user", "hi")]))


def test_stream_chat_closes_response_on_success(client_factory: Any) -> None:
    stream = ChunkStream([_line({"message": {"content": "a"}, "done": False}), _line(_done())])
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert stream.closed is True


def test_stream_chat_yields_first_chunk_before_body_completes(client_factory: Any) -> None:
    """首块必须在整个响应下载完成前产出（证明不是先缓冲全文再解析）。"""

    class GatedStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.release = threading.Event()

        def __iter__(self) -> Iterator[bytes]:
            yield _line({"message": {"content": "first"}, "done": False})
            self.release.wait(2)
            yield _line(_done())

        def close(self) -> None:
            self.release.set()

    stream = GatedStream()
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    generator = client.stream_chat(model="m", messages=[ChatMessage("user", "hi")])
    try:
        started = time.monotonic()
        assert next(generator).text == "first"
        assert time.monotonic() - started < 1.0, "客户端在收到首块前等待了完整响应"
        stream.release.set()
        assert next(generator).done is True
    finally:
        stream.release.set()
        generator.close()


def test_client_recovers_after_stream_error(client_factory: Any) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary boom"})
        return _ndjson([{"message": {"content": "ok"}, "done": False}, _done()])

    client, _ = client_factory(handler)
    with pytest.raises(OllamaHTTPError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))

    chunks = list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert [chunk.text for chunk in chunks] == ["ok", ""]
    assert calls == 2


# ---------------------------------------------------------------------------
# 取消
# ---------------------------------------------------------------------------


def test_cancel_before_start_sends_no_request(client_factory: Any) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _ndjson([_done()])

    client, _ = client_factory(handler)
    from emowall.ai import CancelToken

    token = CancelToken()
    token.cancel()
    with pytest.raises(CancelledError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")], cancel=token))
    assert requests == []


def test_cancel_after_two_chunks_raises_and_closes(client_factory: Any) -> None:
    from emowall.ai import CancelToken

    stream = ChunkStream(
        [
            _line({"message": {"content": "1"}, "done": False}),
            _line({"message": {"content": "2"}, "done": False}),
            _line({"message": {"content": "3"}, "done": False}),
            _line(_done()),
        ]
    )
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    token = CancelToken()
    generator = client.stream_chat(
        model="m", messages=[ChatMessage("user", "hi")], cancel=token
    )

    assert next(generator).text == "1"
    assert next(generator).text == "2"
    token.cancel()
    with pytest.raises(CancelledError):
        next(generator)
    assert stream.closed is True


def test_cancel_from_another_thread_stops_within_500ms(client_factory: Any) -> None:
    from emowall.ai import CancelToken

    stream = BlockingStream()
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    token = CancelToken()
    result: dict[str, Any] = {"chunks": []}

    def consume() -> None:
        try:
            for chunk in client.stream_chat(
                model="m", messages=[ChatMessage("user", "hi")], cancel=token
            ):
                result["chunks"].append(chunk)
        except CancelledError:
            result["cancelled"] = True
        except BaseException as exc:  # pragma: no cover - 失败时给出诊断
            result["error"] = repr(exc)

    thread = threading.Thread(target=consume, name="ai-cancel-test")
    thread.start()
    assert stream.started.wait(2), "流没有开始读取"

    started = time.monotonic()
    token.cancel()
    thread.join(2)
    elapsed = time.monotonic() - started

    assert not thread.is_alive(), "取消后读取线程没有退出"
    assert result.get("cancelled") is True, result
    assert stream.closed is True
    assert elapsed < 0.5, f"取消耗时过长：{elapsed:.3f}s"
    assert [chunk.text for chunk in result["chunks"]] == ["first"]


def test_reset_allows_next_generation_after_cancel(client_factory: Any) -> None:
    from emowall.ai import CancelToken

    stream_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal stream_count
        stream_count += 1
        return _ndjson([{"message": {"content": "ok"}, "done": False}, _done()])

    client, _ = client_factory(handler)
    token = CancelToken()
    token.cancel()
    with pytest.raises(CancelledError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")], cancel=token))

    token.reset()
    chunks = list(
        client.stream_chat(model="m", messages=[ChatMessage("user", "hi")], cancel=token)
    )
    assert [chunk.text for chunk in chunks] == ["ok", ""]
    assert token.is_cancelled is False
    assert stream_count == 1


# ---------------------------------------------------------------------------
# 客户端生命周期与输入校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owned", [True, False])
def test_reset_after_cancel_waits_for_generator_exit(owned: bool) -> None:
    streams: list[ChunkStream] = []

    def handler(request: httpx.Request) -> httpx.Response:
        stream = ChunkStream([
            _line({"message": {"content": "partial"}, "done": False}),
            _line(_done()),
        ])
        streams.append(stream)
        return httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as external:
        with OllamaClient("http://mock", **(
            {"transport": transport} if owned else {"client": external}
        )) as client:
            token = CancelToken()
            generator = client.stream_chat(
                model="m", messages=[ChatMessage("user", "hi")], cancel=token
            )
            try:
                assert next(generator).text == "partial"
                token.cancel()
                with pytest.raises(RuntimeError, match="活动生成"):
                    token.reset()
                assert token.is_cancelled
                with pytest.raises(CancelledError):
                    next(generator)
                assert streams[0].closed
                token.reset()
                chunks = list(client.stream_chat(
                    model="m", messages=[ChatMessage("user", "again")], cancel=token
                ))
                assert chunks[-1].done
                assert not token.is_cancelled
                assert streams[1].closed
            finally:
                generator.close()


def test_reset_is_blocked_until_exception_is_classified(
    client_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = BlockingStream()
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    token = CancelToken()
    unregister = token._unregister
    checked: list[bool] = []

    def unregister_then_try_reset(closer: Any) -> None:
        unregister(closer)
        # 确定性停在资源已反登记、外层 except 尚未识别 ReadError 的窗口。
        with pytest.raises(RuntimeError, match="活动生成"):
            token.reset()
        checked.append(True)

    monkeypatch.setattr(token, "_unregister", unregister_then_try_reset)
    generator = client.stream_chat(
        model="m", messages=[ChatMessage("user", "hi")], cancel=token
    )
    assert next(generator).text == "first"
    token.cancel()
    with pytest.raises(CancelledError):
        next(generator)
    assert checked
    token.reset()


@pytest.mark.parametrize("partial", [True, False])
def test_cancelled_eof_is_not_reported_as_network_interruption(
    client_factory: Any, partial: bool
) -> None:
    token = CancelToken()

    class CancelAtEOF(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            if partial:
                yield _line({"message": {"content": "partial"}, "done": False})
            token.cancel()
            return

    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=CancelAtEOF(), headers=NDJSON_HEADERS)
    )
    with pytest.raises(CancelledError):
        list(client.stream_chat(
            model="m", messages=[ChatMessage("user", "hi")], cancel=token
        ))
    token.reset()


def test_cancel_during_http_error_body_preserves_cancelled_error(client_factory: Any) -> None:
    token = CancelToken()

    class CancelErrorBody(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield from ()
            token.cancel()
            raise httpx.ReadError("cancelled error body")

    client, _ = client_factory(
        lambda request: httpx.Response(500, stream=CancelErrorBody())
    )
    with pytest.raises(CancelledError):
        list(client.stream_chat(
            model="m", messages=[ChatMessage("user", "hi")], cancel=token
        ))
    token.reset()


def test_cancelled_registration_remains_active_until_unregistered() -> None:
    token = CancelToken()
    closed: list[bool] = []

    def close() -> None:
        closed.append(True)

    token.cancel()
    token._register(close)
    assert closed == [True]
    with pytest.raises(RuntimeError, match="活动生成"):
        token.reset()
    token.cancel()
    assert closed == [True]
    token._unregister(close)
    token.reset()


def test_reset_waits_for_cancel_callbacks_to_finish() -> None:
    token = CancelToken()
    entered = threading.Event()
    release = threading.Event()

    def close() -> None:
        entered.set()
        release.wait(5)

    token._register(close)
    thread = threading.Thread(target=token.cancel)
    thread.start()
    try:
        assert entered.wait(2)
        token._unregister(close)
        with pytest.raises(RuntimeError, match="活动生成"):
            token.reset()
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()
    token.reset()


def test_injected_client_is_not_closed_by_ollama_client(client_factory: Any) -> None:
    client, http = client_factory(lambda request: httpx.Response(200, json={"version": "1"}))
    assert client.is_closed is False
    client.close()
    assert client.is_closed is False
    assert http.is_closed is False


def test_injected_client_waiting_for_headers_needs_external_release() -> None:
    transport = HeaderBlockingTransport()
    token = CancelToken()
    errors: list[BaseException] = []
    with httpx.Client(transport=transport) as external:
        client = OllamaClient("http://mock", client=external)

        def consume() -> None:
            try:
                list(client.stream_chat(
                    model="m", messages=[ChatMessage("user", "hi")], cancel=token
                ))
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=consume)
        thread.start()
        try:
            assert transport.entered.wait(2)
            token.cancel()
            client.close()
            assert not external.is_closed
            assert not transport.released.is_set()
            assert thread.is_alive(), "注入模式不能自行中断响应头等待"
            with pytest.raises(RuntimeError, match="活动生成"):
                token.reset()
        finally:
            transport.released.set()
            thread.join(2)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], CancelledError), errors
        token.reset()
        assert list(client.stream_chat(
            model="m", messages=[ChatMessage("user", "again")], cancel=token
        ))[-1].done
        assert not external.is_closed


def test_externally_closed_client_is_not_rebuilt(client_factory: Any) -> None:
    client, external = client_factory(lambda request: _ndjson([_done()]))
    external.close()
    token = CancelToken()
    with pytest.raises(OllamaUnavailableError, match="注入的 HTTP 客户端已关闭"):
        list(client.stream_chat(
            model="m", messages=[ChatMessage("user", "hi")], cancel=token
        ))
    token.reset()
    assert client.is_closed


def test_context_manager_leaves_injected_client_usable(client_factory: Any) -> None:
    client, external = client_factory(
        lambda request: httpx.Response(200, json={"version": "1"})
    )
    with client:
        assert client.version() == "1"
    assert not external.is_closed
    assert client.version() == "1"


@pytest.mark.parametrize("through_engine", [True, False])
@pytest.mark.parametrize("owned", [True, False])
def test_generator_close_releases_response_and_token(
    through_engine: bool, owned: bool
) -> None:
    streams: list[ChunkStream] = []

    def handler(request: httpx.Request) -> httpx.Response:
        stream = ChunkStream([
            _line({"message": {"content": "partial"}, "done": False}),
            _line(_done()),
        ])
        streams.append(stream)
        return httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as external:
        with OllamaClient("http://mock", **(
            {"transport": transport} if owned else {"client": external}
        )) as client:
            token = CancelToken()
            messages = [ChatMessage("user", "hi")]
            generator = (
                ChatEngine(client, model="m").stream_reply(messages, cancel=token)
                if through_engine else
                client.stream_chat(model="m", messages=messages, cancel=token)
            )
            try:
                assert next(generator).text == "partial"
                assert not streams[0].closed
            finally:
                generator.close()
            assert streams[0].closed
            token.reset()
            assert not client.is_closed
            assert not external.is_closed
            assert list(client.stream_chat(
                model="m", messages=messages, cancel=token
            ))[-1].done
            assert streams[1].closed


def test_owned_client_is_closed_and_close_is_idempotent() -> None:
    client = OllamaClient("http://127.0.0.1:11434")
    assert client.is_closed is False
    client.close()
    assert client.is_closed is True
    client.close()
    assert client.is_closed is True


def test_context_manager_closes_owned_client() -> None:
    with OllamaClient("http://127.0.0.1:11434") as client:
        assert client.is_closed is False
    assert client.is_closed is True


def test_close_releases_owned_client() -> None:
    """从 integration 迁移：仅构造和关闭客户端，不进行网络调用。"""
    instance = OllamaClient()
    assert instance.is_closed is False
    instance.close()
    assert instance.is_closed is True
    instance.close()


def test_base_url_and_timeouts_are_configurable() -> None:
    client = OllamaClient(
        "http://127.0.0.1:12345/",
        connect_timeout=1.5,
        read_timeout=7.0,
    )
    try:
        assert client.base_url == "http://127.0.0.1:12345"
        assert client.timeout.connect == 1.5
        assert client.timeout.read == 7.0
    finally:
        client.close()


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "   ",
        "127.0.0.1:11434",
        "ftp://127.0.0.1",
        "http://",
        "http://127.0.0.1:11434?x=1",
        "http://127.0.0.1:11434#frag",
    ],
)
def test_invalid_base_url_is_rejected(base_url: str) -> None:
    with pytest.raises(ValueError):
        OllamaClient(base_url)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_timeout": 0},
        {"connect_timeout": -1},
        {"read_timeout": 0},
        {"write_timeout": 0},
        {"pool_timeout": 0},
    ],
)
def test_invalid_timeouts_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        OllamaClient("http://127.0.0.1:11434", **kwargs)


def test_base_url_path_prefix_is_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/prefix/api/version"
        return httpx.Response(200, json={"version": "1.0"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        client = OllamaClient("http://mock/prefix", client=http)
        assert client.version() == "1.0"
    finally:
        http.close()


def test_transport_and_client_are_mutually_exclusive() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as http:
        with pytest.raises(ValueError):
            OllamaClient(
                "http://mock",
                client=http,
                transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            )


def test_cancel_while_waiting_for_response_headers_is_timely() -> None:
    transport = HeaderBlockingTransport()
    client = OllamaClient("http://mock", transport=transport)
    token = CancelToken()
    result: dict[str, Any] = {"chunks": []}

    def consume() -> None:
        try:
            for chunk in client.stream_chat(
                model="m", messages=[ChatMessage("user", "hi")], cancel=token
            ):
                result["chunks"].append(chunk)
        except CancelledError:
            result["cancelled"] = True
        except BaseException as exc:  # pragma: no cover - 失败时给出诊断
            result["error"] = repr(exc)

    thread = threading.Thread(target=consume, name="ai-header-cancel-test")
    thread.start()
    assert transport.entered.wait(2), "请求没有进入等待响应头阶段"

    started = time.monotonic()
    token.cancel()
    thread.join(2)
    elapsed = time.monotonic() - started

    assert not thread.is_alive(), "响应头前取消后线程仍在阻塞"
    assert result.get("cancelled") is True, result
    assert elapsed < 0.5, f"响应头前取消耗时过长：{elapsed:.3f}s"

    # 取消关闭了底层 client；同一 OllamaClient 必须能重建并继续下一轮
    chunks = list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))
    assert [chunk.text for chunk in chunks] == ["ok", ""]
    assert transport.calls == 2
    client.close()


def test_reset_during_active_stream_raises(client_factory: Any) -> None:
    stream = BlockingStream()
    client, _ = client_factory(
        lambda request: httpx.Response(200, stream=stream, headers=NDJSON_HEADERS)
    )
    token = CancelToken()
    generator = client.stream_chat(
        model="m", messages=[ChatMessage("user", "hi")], cancel=token
    )
    assert next(generator).text == "first"
    with pytest.raises(RuntimeError):
        token.reset()
    token.cancel()
    with pytest.raises(CancelledError):
        next(generator)
    assert stream.closed is True


# ---------------------------------------------------------------------------
# 架构守护：AI 核心不依赖 Qt，离线测试不触碰真实网络
# ---------------------------------------------------------------------------


def test_ai_core_imports_with_qt_blocked() -> None:
    code = "\n".join(
        [
            "import sys",
            "class Blocker:",
            "    def find_spec(self, fullname, path=None, target=None):",
            "        if fullname.split('.')[0] in {'PySide6', 'PyQt6', 'PyQt5'}:",
            "            raise ImportError('Qt import blocked by test')",
            "        return None",
            "sys.meta_path.insert(0, Blocker())",
            "import emowall.ai",
            "assert 'PySide6' not in sys.modules",
            "print('ok')",
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_offline_socket_guard_is_active() -> None:
    """证明 conftest 的运行时防线真的会拦截真实网络。"""

    with pytest.raises(AssertionError, match="离线测试禁止真实网络"):
        sock = socket.socket()
        try:
            sock.connect(("127.0.0.1", 9))
        finally:
            sock.close()


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:bad", "http://127.0.0.1:99999"])
def test_invalid_port_is_rejected(base_url: str) -> None:
    with pytest.raises(ValueError):
        OllamaClient(base_url)


def test_stream_chat_decoding_error_is_protocol_error(client_factory: Any) -> None:
    body = b'{"message":{"content":"\xff"},"done":false}\n'
    client, _ = client_factory(
        lambda request: httpx.Response(200, content=body, headers=NDJSON_HEADERS)
    )
    with pytest.raises(ProtocolError):
        list(client.stream_chat(model="m", messages=[ChatMessage("user", "hi")]))


def test_ai_errors_are_ai_error_subclasses() -> None:
    for error in (
        OllamaUnavailableError,
        OllamaConnectionError,
        OllamaTimeoutError,
        OllamaHTTPError,
        ModelNotFoundError,
        ProtocolError,
        StreamInterruptedError,
        CancelledError,
    ):
        assert issubclass(error, AIError)
