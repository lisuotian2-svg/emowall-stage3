"""AI 对话引擎离线测试：上下文裁剪、系统提示、多轮顺序、模型切换与配置注入。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pytest

from emowall.ai import (
    CancelledError,
    CancelToken,
    ChatChunk,
    ChatEngine,
    ChatMessage,
    GenerationStats,
)


class StubClient:
    """记录调用参数的最小流式客户端替身（不依赖 httpx / 网络）。"""

    def __init__(self, chunks: Sequence[ChatChunk] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._chunks = list(
            chunks
            if chunks is not None
            else [ChatChunk("ok"), ChatChunk("", done=True, stats=GenerationStats(eval_count=1))]
        )

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        options: Mapping[str, object] | None = None,
        think: bool = False,
        cancel: CancelToken | None = None,
    ) -> Iterator[ChatChunk]:
        self.calls.append(
            {
                "model": model,
                "messages": list(messages),
                "options": dict(options) if options is not None else None,
                "think": think,
                "cancel": cancel,
            }
        )
        yield from self._chunks


def _engine(**kwargs: Any) -> tuple[ChatEngine, StubClient]:
    stub = StubClient()
    kwargs.setdefault("model", "qwen3:8b")
    return ChatEngine(stub, **kwargs), stub


# ---------------------------------------------------------------------------
# 系统提示与顺序
# ---------------------------------------------------------------------------


def test_system_prompt_is_first_and_order_is_preserved() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=20, max_context_chars=1000)
    user1 = ChatMessage("user", "u1")
    assistant1 = ChatMessage("assistant", "a1")
    user2 = ChatMessage("user", "u2")

    context = engine.build_context([user1, assistant1, user2])

    assert context == [ChatMessage("system", "SYS"), user1, assistant1, user2]


def test_history_system_message_is_used_when_engine_has_no_prompt() -> None:
    engine, _ = _engine(system_prompt=None)
    system0 = ChatMessage("system", "S0")
    system1 = ChatMessage("system", "S1")
    history = [system0, ChatMessage("user", "u"), system1, ChatMessage("assistant", "a")]

    context = engine.build_context(history)

    assert context == [system0, ChatMessage("user", "u"), ChatMessage("assistant", "a")]


def test_engine_system_prompt_overrides_history_system_messages() -> None:
    engine, _ = _engine(system_prompt="ENGINE")
    context = engine.build_context(
        [ChatMessage("system", "OLD"), ChatMessage("user", "u")]
    )
    assert context == [ChatMessage("system", "ENGINE"), ChatMessage("user", "u")]


def test_no_system_prompt_means_no_system_message() -> None:
    engine, _ = _engine(system_prompt=None)
    context = engine.build_context([ChatMessage("user", "u")])
    assert context == [ChatMessage("user", "u")]


def test_empty_string_system_prompt_is_treated_as_absent() -> None:
    engine, _ = _engine(system_prompt="   ")
    context = engine.build_context([ChatMessage("user", "u")])
    assert context == [ChatMessage("user", "u")]


def test_empty_history_returns_empty_context() -> None:
    engine, _ = _engine()
    assert engine.build_context([]) == []


def test_empty_history_with_system_prompt_returns_system_only() -> None:
    engine, _ = _engine(system_prompt="SYS")
    assert engine.build_context([]) == [ChatMessage("system", "SYS")]


# ---------------------------------------------------------------------------
# 上下文裁剪
# ---------------------------------------------------------------------------


def _turn(index: int, *, size: int = 1) -> list[ChatMessage]:
    return [
        ChatMessage("user", f"u{index}" * size),
        ChatMessage("assistant", f"a{index}" * size),
    ]


def test_message_limit_trims_oldest_complete_turns() -> None:
    engine, _ = _engine(
        system_prompt="SYS",
        max_context_messages=20,
        max_context_chars=100_000,
    )
    history = [message for index in range(30) for message in _turn(index)]

    context = engine.build_context(history)

    assert len(context) == 19  # 1 条 system + 9 个完整轮次
    assert context[0] == ChatMessage("system", "SYS")
    assert context[1:] == history[-18:]
    assert context[-1] == history[-1]


def test_char_budget_trims_oldest_complete_turns() -> None:
    engine, _ = _engine(
        system_prompt="S" * 10,
        max_context_messages=40,
        max_context_chars=100,
    )
    history = [message for index in range(10) for message in _turn(index, size=5)]

    context = engine.build_context(history)

    assert len(context) == 9  # 10 字符 system + 4 个轮次（80 字符）
    assert context[1:] == history[-8:]
    assert sum(len(message.content) for message in context) <= 100


def test_last_user_message_is_never_dropped_even_over_budget() -> None:
    engine, _ = _engine(system_prompt="S", max_context_messages=2, max_context_chars=10)
    history = [ChatMessage("user", "u" * 50), ChatMessage("assistant", "a" * 50)]

    context = engine.build_context(history)

    assert ChatMessage("user", "u" * 50) in context
    assert context[-2] == ChatMessage("user", "u" * 50)
    assert context[-1] == ChatMessage("assistant", "a" * 50)


def test_system_prompt_is_never_dropped_even_over_budget() -> None:
    engine, _ = _engine(system_prompt="S" * 50, max_context_messages=2, max_context_chars=10)
    context = engine.build_context([ChatMessage("user", "u")])
    assert context == [ChatMessage("system", "S" * 50), ChatMessage("user", "u")]


def test_message_limit_counts_system_prompt() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=5, max_context_chars=1000)
    history = [message for index in range(10) for message in _turn(index)]

    context = engine.build_context(history)

    assert len(context) == 5
    assert context[1:] == history[-4:]


def test_selected_context_keeps_complete_turns() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=7, max_context_chars=1000)
    history = [message for index in range(10) for message in _turn(index)]

    context = engine.build_context(history)

    non_system = context[1:]
    assert len(non_system) % 2 == 0
    for user, assistant in zip(non_system[::2], non_system[1::2]):
        assert user.role == "user"
        assert assistant.role == "assistant"
        assert user.content[1:] == assistant.content[1:]


def test_consecutive_user_messages_are_preserved_in_order() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=10, max_context_chars=1000)
    history = [
        ChatMessage("user", "u1"),
        ChatMessage("user", "u2"),
        ChatMessage("assistant", "a2"),
    ]
    assert engine.build_context(history) == [ChatMessage("system", "SYS"), *history]


def test_leading_assistant_messages_are_kept_as_a_group() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=10, max_context_chars=1000)
    history = [
        ChatMessage("assistant", "a0"),
        ChatMessage("user", "u1"),
        ChatMessage("assistant", "a1"),
    ]
    assert engine.build_context(history) == [ChatMessage("system", "SYS"), *history]


def test_build_context_is_deterministic_and_does_not_mutate_input() -> None:
    engine, _ = _engine(system_prompt="SYS", max_context_messages=5, max_context_chars=40)
    history = [message for index in range(6) for message in _turn(index, size=3)]
    snapshot = list(history)

    first = engine.build_context(history)
    second = engine.build_context(history)

    assert first == second
    assert history == snapshot


def test_build_context_rejects_non_chat_message() -> None:
    engine, _ = _engine()
    with pytest.raises(TypeError):
        engine.build_context([ChatMessage("user", "u"), "not-a-message"])  # type: ignore[list-item]


def test_acceptance_context_60_messages_budget_6000() -> None:
    system = ChatMessage("system", "你是 EmoWall 的 AI 伙伴。")
    history = [
        message
        for index in range(30)
        for message in (
            ChatMessage("user", f"user-{index}-" + "x" * 20),
            ChatMessage("assistant", f"assistant-{index}-" + "y" * 20),
        )
    ]
    engine, _ = _engine(
        system_prompt=system.content,
        max_context_messages=20,
        max_context_chars=6000,
    )

    context = engine.build_context(history)

    assert len(context) <= 20
    assert sum(len(message.content) for message in context) <= 6000
    assert context[0] == system
    assert context[-1] == history[-1]
    last_user = next(message for message in reversed(history) if message.role == "user")
    assert last_user in context


# ---------------------------------------------------------------------------
# 调用客户端
# ---------------------------------------------------------------------------


def test_stream_reply_forwards_model_options_think_and_cancel() -> None:
    engine, stub = _engine(
        model="llama3:70b",
        system_prompt="SYS",
        options={"temperature": 0.1},
        think=True,
    )
    history = [ChatMessage("user", "你好")]
    token = CancelToken()

    chunks = list(engine.stream_reply(history, cancel=token))

    assert [chunk.text for chunk in chunks] == ["ok", ""]
    call = stub.calls[0]
    assert call["model"] == "llama3:70b"
    assert call["messages"] == [ChatMessage("system", "SYS"), ChatMessage("user", "你好")]
    assert call["options"] == {"temperature": 0.1}
    assert call["think"] is True
    assert call["cancel"] is token


def test_stream_reply_uses_no_options_when_empty() -> None:
    engine, stub = _engine(system_prompt="SYS")
    list(engine.stream_reply([ChatMessage("user", "hi")]))
    assert stub.calls[0]["options"] is None
    assert stub.calls[0]["think"] is False


def test_stream_reply_rejects_empty_context() -> None:
    engine, stub = _engine()
    with pytest.raises(ValueError):
        list(engine.stream_reply([]))
    assert stub.calls == []


def test_model_can_be_switched_by_building_a_new_engine() -> None:
    first, first_stub = _engine(model="qwen3:8b")
    second, second_stub = _engine(model="llama3:8b")

    list(first.stream_reply([ChatMessage("user", "hi")]))
    list(second.stream_reply([ChatMessage("user", "hi")]))

    assert first_stub.calls[0]["model"] == "qwen3:8b"
    assert second_stub.calls[0]["model"] == "llama3:8b"


def test_engine_copies_options_mapping() -> None:
    options = {"temperature": 0.5}
    engine, stub = _engine(options=options)
    options["temperature"] = 1.9

    list(engine.stream_reply([ChatMessage("user", "hi")]))

    assert stub.calls[0]["options"] == {"temperature": 0.5}


def test_engine_defaults() -> None:
    engine, _ = _engine()
    assert engine.max_context_messages == 20
    assert engine.max_context_chars == 6000
    assert engine.system_prompt is None
    assert engine.think is False


# ---------------------------------------------------------------------------
# 构造参数校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model": ""},
        {"model": "   "},
        {"model": "m", "max_context_messages": 0},
        {"model": "m", "max_context_messages": -1},
        {"model": "m", "max_context_chars": 0},
        {"model": "m", "max_context_chars": -5},
        {"model": "m", "system_prompt": 123},
        {"model": "m", "options": ["temperature"]},
        {"model": "m", "think": "yes"},
    ],
)
def test_invalid_engine_arguments_are_rejected(kwargs: dict[str, Any]) -> None:
    stub = StubClient()
    with pytest.raises((TypeError, ValueError)):
        ChatEngine(stub, **kwargs)

class CancellingClient:
    """第一次调用抛取消，第二次正常返回；用于验证状态恢复。"""

    def __init__(self) -> None:
        self.calls = 0

    def stream_chat(self, *, model, messages, options=None, think=False, cancel=None):
        self.calls += 1
        if self.calls == 1:
            raise CancelledError("cancelled")
        yield ChatChunk("ok")
        yield ChatChunk("", done=True, stats=GenerationStats())


def test_cancelled_stream_does_not_mutate_history_and_next_turn_works() -> None:
    client = CancellingClient()
    engine = ChatEngine(client, model="m", system_prompt="SYS")
    history = [ChatMessage("user", "hi")]
    snapshot = list(history)

    token = CancelToken()
    token.cancel()
    with pytest.raises(CancelledError):
        list(engine.stream_reply(history, cancel=token))
    assert history == snapshot

    chunks = list(engine.stream_reply(history, cancel=CancelToken()))
    assert [chunk.text for chunk in chunks] == ["ok", ""]
    assert history == snapshot
    assert client.calls == 2

def test_char_budget_actually_binds() -> None:
    engine, _ = _engine(
        system_prompt="S",
        max_context_messages=100,
        max_context_chars=500,
    )
    history = [
        message
        for _ in range(10)
        for message in (
            ChatMessage("user", "u" * 100),
            ChatMessage("assistant", "a" * 100),
        )
    ]

    context = engine.build_context(history)

    assert len(context) == 5  # system + 2 个完整轮次（401 字符）
    assert len(context) < 21
    assert sum(len(message.content) for message in context) <= 500
    assert context[1:] == history[-4:]
