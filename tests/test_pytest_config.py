"""pytest 配置守卫：默认不跑 integration，显式指定时才收集。"""

from __future__ import annotations

import configparser
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTEST_INI = PROJECT_ROOT / "pytest.ini"


def _pytest_section() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    return parser["pytest"]


def test_default_addopts_exclude_integration() -> None:
    addopts = _pytest_section()["addopts"]
    assert "-m" in addopts
    assert "not integration" in addopts, f"默认必须排除 integration，实际：{addopts}"


def test_pythonpath_is_project_root() -> None:
    assert _pytest_section()["pythonpath"].strip() == "."


def test_integration_marker_is_declared() -> None:
    assert "integration" in _pytest_section()["markers"]


def test_integration_selection_only_collects_integration_tests() -> None:
    """显式 `-m integration` 只收集真实 Ollama 用例，不误跑离线用例。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "integration", "--collect-only", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "test_ai_integration.py" in combined, combined
    assert "test_ai_client.py" not in combined, "integration 选择不应收集离线用例"
    assert "test_ai_engine.py" not in combined, "integration 选择不应收集离线用例"


def test_default_selection_excludes_integration_tests() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "test_ai_integration.py" not in combined, "默认选择不得收集 integration 用例"
    assert "test_ai_client.py" in combined, combined
