"""配置系统与 AI 核心的集成测试（组合根职责的最小验证）。

规则：
    * `emowall.ai` 不 import `emowall.config`；
    * `emowall.config` 不 import `emowall.ai`；
    * 由调用方（未来的 emowall/app.py）读取配置后构造客户端与引擎；
    * 配置变化时构造新的客户端实例，不共享旧连接。
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from emowall.ai import CancelToken, ChatChunk, ChatEngine, ChatMessage, GenerationStats, OllamaClient
from emowall.config import AppSettings, ChatSettings, ConfigStore, OllamaSettings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        options: Mapping[str, object] | None = None,
        think: bool = False,
        cancel: CancelToken | None = None,
    ) -> Iterator[ChatChunk]:
        self.calls.append({"model": model, "messages": list(messages), "options": options})
        yield ChatChunk("", done=True, stats=GenerationStats())


def _imports(path: Path) -> set[str]:
    """展开相对导入，返回绝对模块名（与 tests/test_architecture.py 的语义一致）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package_parts = list(path.relative_to(PROJECT_ROOT).with_suffix("").parts[:-1])
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if prefix:
                modules.add(prefix)
                modules.update(f"{prefix}.{alias.name}" for alias in node.names)
            else:
                modules.update(alias.name for alias in node.names)
    return modules


def test_settings_build_client_and_engine(workdir: Path) -> None:
    store = ConfigStore(workdir / "config.json")
    settings = store.load()

    client = OllamaClient(
        settings.ollama.base_url,
        connect_timeout=settings.ollama.connect_timeout_seconds,
        read_timeout=settings.ollama.read_timeout_seconds,
    )
    try:
        engine = ChatEngine(
            client,
            model=settings.ollama.model,
            max_context_messages=settings.chat.max_context_messages,
            max_context_chars=settings.chat.max_context_chars,
            system_prompt=settings.chat.system_prompt,
            options={
                "num_ctx": settings.ollama.num_ctx,
                "temperature": settings.ollama.temperature,
            },
            think=settings.ollama.think,
        )
        assert engine.model == settings.ollama.model
        assert client.base_url == settings.ollama.base_url
        assert engine.max_context_messages == settings.chat.max_context_messages
        assert engine.max_context_chars == settings.chat.max_context_chars
    finally:
        client.close()


def test_changed_config_creates_a_new_client_instance(workdir: Path) -> None:
    store = ConfigStore(workdir / "config.json")
    first = store.load()
    first_client = OllamaClient(first.ollama.base_url)
    try:
        store.save(
            AppSettings(
                ollama=OllamaSettings(base_url="http://127.0.0.1:11435", model="other:1b"),
                chat=ChatSettings(max_context_messages=10, max_context_chars=2000),
            )
        )
        second = store.load()
        second_client = OllamaClient(second.ollama.base_url)
        try:
            assert first_client.base_url == "http://127.0.0.1:11434"
            assert second_client.base_url == "http://127.0.0.1:11435"
            assert second_client is not first_client

            engine = ChatEngine(second_client, model=second.ollama.model)
            assert engine.model == "other:1b"
        finally:
            second_client.close()
    finally:
        first_client.close()


def test_config_model_is_used_by_engine(workdir: Path) -> None:
    store = ConfigStore(workdir / "config.json")
    store.save(AppSettings(ollama=OllamaSettings(model="configured:7b")))
    settings = store.load()
    stub = StubClient()

    engine = ChatEngine(stub, model=settings.ollama.model)
    list(engine.stream_reply([ChatMessage("user", "hi")]))

    assert stub.calls[0]["model"] == "configured:7b"


def test_ai_layer_does_not_import_config() -> None:
    for path in sorted((PROJECT_ROOT / "emowall" / "ai").rglob("*.py")):
        imports = _imports(path)
        assert not any(name == "emowall.config" or name.startswith("emowall.config.") for name in imports), (
            f"{path} 不得 import 配置层"
        )
        forbidden_layers = ("emowall.config", "emowall.storage", "emowall.emotion", "emowall.gui", "emowall.app")
        assert not any(name.startswith(forbidden_layers) for name in imports), (
            f"{path} 不得 import 其他 emowall 层：{imports}"
        )


def test_config_layer_does_not_import_ai() -> None:
    for path in sorted((PROJECT_ROOT / "emowall" / "config").rglob("*.py")):
        imports = _imports(path)
        assert not any(name == "emowall.ai" or name.startswith("emowall.ai.") for name in imports), (
            f"{path} 不得 import AI 层"
        )


def test_ai_does_not_create_extra_config_file(workdir: Path) -> None:
    store = ConfigStore(workdir / "config.json")
    settings = store.load()
    client = OllamaClient(settings.ollama.base_url)
    try:
        ChatEngine(client, model=settings.ollama.model)
    finally:
        client.close()

    assert sorted(path.name for path in workdir.iterdir()) == ["config.json"]
