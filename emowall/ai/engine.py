"""与界面无关的对话引擎：上下文裁剪 + 提示组装 + 调用传输客户端。

上下文规则（确定、可测试）：
    1. `system` 提示始终位于最前，永不裁剪；
    2. 历史消息按时间正序；非 system 消息按「用户消息开启一个轮次」分组，
       从最新轮次向最旧轮次累加，保持完整轮次，避免出现孤立的 assistant 回复；
    3. 同时受 `max_context_messages`（条数，含 system）与 `max_context_chars`
       （字符预算，含 system）限制；
    4. 最新轮次（含最后一条用户消息）是硬底线，即使单轮超预算也保留；
    5. 字符数只是对 token 的保守近似，不是 tokenizer；裁剪只影响发送给模型的
       上下文，不修改调用方历史，也不影响持久化。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence

from .cancel import CancelToken
from .client import OllamaClient
from .models import ChatChunk, ChatMessage

logger = logging.getLogger("emowall.ai.engine")

DEFAULT_MAX_CONTEXT_MESSAGES = 20
DEFAULT_MAX_CONTEXT_CHARS = 6000


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} 必须是整数，收到 {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0，收到 {value}")
    return value


class ChatEngine:
    """对话引擎：不持有会话状态，历史由调用方传入。

    `options` 由组合根从配置映射而来（例如 temperature / num_ctx），
    引擎只负责原样传给客户端；`think` 同理。
    """

    def __init__(
        self,
        client: OllamaClient,
        *,
        model: str,
        max_context_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
        system_prompt: str | None = None,
        options: Mapping[str, object] | None = None,
        think: bool = False,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model 不能为空")
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise TypeError(f"system_prompt 必须是 str 或 None，收到 {type(system_prompt).__name__}")
        if options is not None and not isinstance(options, Mapping):
            raise TypeError(f"options 必须是 Mapping 或 None，收到 {type(options).__name__}")
        if not isinstance(think, bool):
            raise TypeError(f"think 必须是 bool，收到 {type(think).__name__}")

        self._client = client
        self._model = model.strip()
        self._max_context_messages = _positive_int(
            "max_context_messages", max_context_messages
        )
        self._max_context_chars = _positive_int("max_context_chars", max_context_chars)
        self._system_prompt = system_prompt if system_prompt and system_prompt.strip() else None
        self._options: dict[str, object] | None = dict(options) if options else None
        self._think = think

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_context_messages(self) -> int:
        return self._max_context_messages

    @property
    def max_context_chars(self) -> int:
        return self._max_context_chars

    @property
    def system_prompt(self) -> str | None:
        return self._system_prompt

    @property
    def options(self) -> Mapping[str, object] | None:
        return self._options

    @property
    def think(self) -> bool:
        return self._think

    # ------------------------------------------------------------------
    # 上下文
    # ------------------------------------------------------------------

    def build_context(self, history: Sequence[ChatMessage]) -> list[ChatMessage]:
        """按确定规则裁剪历史，返回发送给模型的完整消息列表。"""
        if isinstance(history, (str, bytes)):
            raise TypeError("history 必须是 ChatMessage 序列，不能是字符串")
        try:
            messages = list(history)
        except TypeError as exc:
            raise TypeError("history 必须是 ChatMessage 序列") from exc
        for message in messages:
            if not isinstance(message, ChatMessage):
                raise TypeError(
                    f"history 只能包含 ChatMessage，收到 {type(message).__name__}"
                )

        system_messages = [message for message in messages if message.role == "system"]
        non_system = [message for message in messages if message.role != "system"]

        system: ChatMessage | None
        if self._system_prompt is not None:
            system = ChatMessage("system", self._system_prompt)
        elif system_messages:
            system = system_messages[0]
        else:
            system = None

        groups = self._split_turns(non_system)
        if not groups:
            return [system] if system is not None else []

        selected: list[list[ChatMessage]] = []
        used_messages = 1 if system is not None else 0
        used_chars = len(system.content) if system is not None else 0

        for index, group in enumerate(reversed(groups)):
            group_chars = sum(len(message.content) for message in group)
            fits = (
                used_messages + len(group) <= self._max_context_messages
                and used_chars + group_chars <= self._max_context_chars
            )
            # index == 0：最新轮次是硬底线（保留最后一条用户消息）
            if index == 0 or fits:
                selected.append(group)
                used_messages += len(group)
                used_chars += group_chars
            else:
                break

        context: list[ChatMessage] = [system] if system is not None else []
        for group in reversed(selected):
            context.extend(group)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "context built: history=%d sent=%d chars=%d",
                len(messages),
                len(context),
                sum(len(message.content) for message in context),
            )
        return context

    @staticmethod
    def _split_turns(messages: Sequence[ChatMessage]) -> list[list[ChatMessage]]:
        """按「用户消息开启新轮次」分组；开头孤立的 assistant 成为独立组。"""
        groups: list[list[ChatMessage]] = []
        current: list[ChatMessage] = []
        for message in messages:
            if message.role == "user" and current:
                groups.append(current)
                current = []
            current.append(message)
        if current:
            groups.append(current)
        return groups

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def stream_reply(
        self,
        history: Sequence[ChatMessage],
        *,
        cancel: CancelToken | None = None,
    ) -> Iterator[ChatChunk]:
        """裁剪上下文后调用客户端；不修改历史、不写数据库、不更新 UI。"""
        context = self.build_context(history)
        if not context:
            raise ValueError("上下文为空：至少需要一条消息")
        yield from self._client.stream_chat(
            model=self._model,
            messages=context,
            options=self._options,
            think=self._think,
            cancel=cancel,
        )
