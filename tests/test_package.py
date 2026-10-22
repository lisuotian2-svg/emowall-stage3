"""包级别冒烟测试：骨架可导入、版本号规范、核心层不拉起 Qt。"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

import emowall

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEAF_LAYERS = ("ai", "config", "storage", "emotion")


def test_version_format() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.\-+][0-9A-Za-z.\-]+)?", emowall.__version__), (
        f"版本号格式不符合 PEP 440 风格：{emowall.__version__}"
    )


def test_app_name() -> None:
    assert emowall.APP_NAME == "EmoWall AI"


@pytest.mark.parametrize("layer", LEAF_LAYERS)
def test_leaf_layer_importable(layer: str) -> None:
    module = importlib.import_module(f"emowall.{layer}")
    assert module.__doc__, f"emowall.{layer} 缺少模块职责说明"


def test_importing_core_does_not_load_qt() -> None:
    """在子进程中验证：只导入四层核心包时，PySide6 不应出现在 sys.modules。"""
    code = (
        "import sys\n"
        "import emowall.ai, emowall.config, emowall.storage, emowall.emotion\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in {'PySide6', 'PyQt6', 'PyQt5'})\n"
        "assert not loaded, loaded\n"
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


def test_gui_layer_importable_when_qt_installed() -> None:
    pytest.importorskip("PySide6", reason="PySide6 未安装时跳过（安装 requirements.txt 后自动启用）")
    importlib.import_module("emowall.gui")
