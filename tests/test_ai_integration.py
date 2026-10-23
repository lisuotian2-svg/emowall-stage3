"""真实 Ollama 集成测试（默认跳过，手动 `-m integration` 运行）。

验收重点是协议、事件顺序、状态与资源释放，而不是具体回复文字。
运行前需确保本机 Ollama 已启动且默认模型可用。
"""

from __future__ import annotations

import time

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

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> AppSettings:
    return default_settings()


@pytest.fixture(scope="module")
def client(settings: AppSettings):
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
    yield instance
    instance.close()


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
    first = next(generator, None)
    assert first is not None and not first.done, "没有收到可取消的增量块"

    started = time.monotonic()
    token.cancel()
    with pytest.raises(CancelledError):
        next(generator)
    assert time.monotonic() - started < 1.0

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


def test_close_releases_owned_client(settings: AppSettings) -> None:
    instance = OllamaClient(settings.ollama.base_url)
    assert instance.is_closed is False
    instance.close()
    assert instance.is_closed is True
    instance.close()
