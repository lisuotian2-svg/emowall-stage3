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


def test_integration_selection_collects_nothing_by_default() -> None:
    """当前没有 integration 用例：显式选择应为空（pytest 返回 5），而不是误跑离线用例。"""
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
    assert result.returncode == 5, combined
    assert "test_" not in combined, f"不应收集到任何用例，实际输出：{combined!r}"
