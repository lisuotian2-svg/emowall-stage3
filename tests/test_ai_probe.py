"""chat_probe 命令行工具的离线测试：参数、模型列表、错误码（不连接 Ollama）。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from emowall.ai import OllamaUnavailableError
from emowall.config import default_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "chat_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("emowall_chat_probe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def probe():
    return _load_probe()


def test_parser_supports_multiple_prompts_and_overrides(probe) -> None:
    args = probe.build_parser().parse_args(
        ["--prompt", "第一轮", "--prompt", "第二轮", "--model", "m:1b", "--num-ctx", "2048"]
    )
    assert args.prompt == ["第一轮", "第二轮"]
    assert args.model == "m:1b"
    assert args.num_ctx == 2048


def test_list_models_offline(probe, monkeypatch, capsys) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            self.closed = False

        def list_models(self) -> list[str]:
            return ["qwen3:8b", "llama3:8b"]

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(probe, "OllamaClient", FakeClient)
    monkeypatch.setattr(probe.ConfigStore, "load", lambda self: default_settings())

    assert probe.main(["--list-models"]) == 0
    assert capsys.readouterr().out.splitlines() == ["qwen3:8b", "llama3:8b"]


def test_ai_error_returns_code_two(probe, monkeypatch, capsys) -> None:
    class FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_models(self) -> list[str]:
            raise OllamaUnavailableError("服务未启动")

        def close(self) -> None:
            pass

    monkeypatch.setattr(probe, "OllamaClient", FailingClient)
    monkeypatch.setattr(probe.ConfigStore, "load", lambda self: default_settings())

    assert probe.main(["--list-models"]) == 2
    captured = capsys.readouterr()
    assert "服务未启动" in captured.err
