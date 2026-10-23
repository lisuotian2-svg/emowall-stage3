"""架构守护测试：分层解耦规则一旦被破坏，这里必须失败。

规则（详见 AGENTS.md 第 2 节）：
    1. ai / config / storage / emotion 四层互不 import，也不 import gui / app；
    2. 只有 `emowall/gui/**` 与组合根 `emowall/app.py` 允许 import Qt 绑定库；
    3. 四层只允许标准库 + 白名单第三方库（ai 仅 httpx，其余为空）；
    4. `emowall/__init__.py` 不得拉起 GUI。

检查对象是**项目源码里的直接 import 语句**；第三方库自身的传递依赖（如 httpx 依赖的
h11/httpcore）不扫描、也不算违规。
"""

from __future__ import annotations

import ast
import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "emowall"

LEAF_LAYERS = ("ai", "config", "storage", "emotion")
QT_MODULES = ("PySide6", "PySide2", "PyQt6", "PyQt5", "shiboken6", "shiboken2")
FORBIDDEN_TARGETS = ("gui", "app")

# 各层允许的第三方依赖（标准库始终允许）
THIRD_PARTY_ALLOWLIST: dict[str, frozenset[str]] = {
    "ai": frozenset({"httpx"}),
    "config": frozenset(),
    "storage": frozenset(),
    "emotion": frozenset(),
}

# 单元测试不允许直接引入网络客户端（真实联调放 integration 用例）。
# httpx 是 AI 层唯一允许的依赖，因此仅在 AI 传输层测试中放行，且必须使用
# httpx.MockTransport（离线）；其他测试文件仍禁止 import httpx。
NETWORK_CLIENTS = frozenset({"requests", "aiohttp", "urllib3", "websockets"})
HTTPX_ALLOWED_TEST_FILES = frozenset({"test_ai_client.py"})
# ai 是同步核心：额外禁止事件循环与数据库（见 ARCHITECTURE §2）
AI_FORBIDDEN_STDLIB = frozenset({"sqlite3", "asyncio"})


def scan_imports(path: Path, project_root: Path) -> set[str]:
    """返回文件里所有被 import 的绝对模块名（相对 import 会展开成完整路径）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package_parts = list(path.relative_to(project_root).with_suffix("").parts[:-1])

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level=1 表示当前包，level=2 表示上一级
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


def top_level(module: str) -> str:
    return module.split(".", 1)[0]


def python_files(package_root: Path) -> list[Path]:
    return sorted(package_root.rglob("*.py"))


def is_qt_allowed(path: Path, package_root: Path) -> bool:
    """只有 gui 目录与组合根 app.py 允许出现 Qt。"""
    return (package_root / "gui") in path.parents or path == package_root / "app.py"


def layer_modules(project_root: Path, layer: str) -> Iterator[tuple[Path, str]]:
    package_root = project_root / "emowall"
    for path in sorted((package_root / layer).rglob("*.py")):
        for module in sorted(scan_imports(path, project_root)):
            yield path, module


def find_qt_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    package_root = project_root / "emowall"
    violations: list[str] = []
    for path in python_files(package_root):
        if is_qt_allowed(path, package_root):
            continue
        for module in sorted(scan_imports(path, project_root)):
            if top_level(module) in QT_MODULES:
                relative = path.relative_to(project_root).as_posix()
                violations.append(f"{relative} → {module}")
    return violations


def find_layer_dependency_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    violations: list[str] = []
    for layer in LEAF_LAYERS:
        others = [name for name in LEAF_LAYERS if name != layer]
        forbidden = [f"emowall.{name}" for name in others + list(FORBIDDEN_TARGETS)]
        for path, module in layer_modules(project_root, layer):
            if any(module == target or module.startswith(f"{target}.") for target in forbidden):
                relative = path.relative_to(project_root).as_posix()
                violations.append(f"{relative} → {module}")
    return violations


def find_third_party_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    standard_library = set(sys.stdlib_module_names)
    violations: list[str] = []
    for layer, allowed in THIRD_PARTY_ALLOWLIST.items():
        for path, module in layer_modules(project_root, layer):
            top = top_level(module)
            if top == "emowall" or top in standard_library or top in allowed:
                continue
            if top in QT_MODULES:
                continue  # 由 find_qt_violations 单独报告
            relative = path.relative_to(project_root).as_posix()
            violations.append(f"{relative} → {module}（层：{layer}）")
    return violations


@pytest.fixture()
def workdir() -> Iterator[Path]:
    """在工作区内创建临时目录（受限环境的系统临时目录可能不可写）。"""
    base = PROJECT_ROOT / ".tmp" / "arch-tests" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# 真实仓库的守护
# ---------------------------------------------------------------------------


def test_all_layers_exist() -> None:
    for layer in (*LEAF_LAYERS, "gui"):
        layer_dir = PACKAGE_ROOT / layer
        assert layer_dir.is_dir(), f"缺少层目录：{layer_dir}"
        assert (layer_dir / "__init__.py").is_file(), f"缺少 {layer}/__init__.py"


def test_root_package_does_not_import_qt_or_gui() -> None:
    init_file = PACKAGE_ROOT / "__init__.py"
    for module in scan_imports(init_file, PROJECT_ROOT):
        assert top_level(module) not in QT_MODULES, f"emowall/__init__.py 不允许 import {module}"
        assert not module.startswith(("emowall.gui", "emowall.app")), (
            f"emowall/__init__.py 不允许 import {module}"
        )


def test_only_gui_and_composition_root_import_qt() -> None:
    assert find_qt_violations() == []


def test_leaf_layers_do_not_import_qt() -> None:
    leaf_prefixes = tuple(f"emowall/{layer}/" for layer in LEAF_LAYERS)
    offenders = [item for item in find_qt_violations() if item.startswith(leaf_prefixes)]
    assert offenders == []


def test_leaf_layers_are_mutually_independent() -> None:
    assert find_layer_dependency_violations() == []


def test_leaf_layers_use_stdlib_and_allowlisted_third_party_only() -> None:
    assert find_third_party_violations() == []


def test_ai_layer_does_not_use_sqlite_or_asyncio() -> None:
    assert find_ai_forbidden_stdlib() == []


def find_ai_forbidden_stdlib(project_root: Path = PROJECT_ROOT) -> list[str]:
    """ai 层禁止 import sqlite3 / asyncio（同步核心，不叠加事件循环/数据库）。"""
    violations: list[str] = []
    for path in sorted((project_root / "emowall" / "ai").rglob("*.py")):
        for module in sorted(scan_imports(path, project_root)):
            if top_level(module) in AI_FORBIDDEN_STDLIB:
                relative = path.relative_to(project_root).as_posix()
                violations.append(f"{relative} → {module}")
    return violations


def find_test_network_violations(project_root: Path = PROJECT_ROOT) -> list[str]:
    """测试代码里的网络客户端导入规则。

    * requests / aiohttp / urllib3 / websockets / urllib.request：任何测试都禁止；
    * httpx：只允许在 AI 传输层测试里使用 MockTransport，其他测试文件禁止。
    """
    tests_root = project_root / "tests"
    if not tests_root.is_dir():
        return []
    offenders: list[str] = []
    for path in sorted(tests_root.rglob("*.py")):
        allow_httpx = path.name in HTTPX_ALLOWED_TEST_FILES
        for module in sorted(scan_imports(path, project_root)):
            top = top_level(module)
            relative = path.relative_to(project_root).as_posix()
            if top in NETWORK_CLIENTS or module.startswith("urllib.request"):
                offenders.append(f"{relative} → {module}")
            elif top == "httpx" and not allow_httpx:
                offenders.append(f"{relative} → {module}（httpx 仅允许在 AI 传输层测试中使用 MockTransport）")
    return offenders


def test_unit_tests_do_not_import_network_clients() -> None:
    offenders = find_test_network_violations()
    assert offenders == [], "单元测试不得直接访问网络：" + "; ".join(offenders)


# ---------------------------------------------------------------------------
# 负向用例：证明规则被违反时测试真的会失败
# ---------------------------------------------------------------------------


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


_BASE_TREE = {
    "emowall/__init__.py": '__version__ = "0.0.0"\n',
    "emowall/ai/__init__.py": "",
    "emowall/config/__init__.py": "",
    "emowall/storage/__init__.py": "",
    "emowall/emotion/__init__.py": "",
    "emowall/gui/__init__.py": "",
}


def _fake_project(workdir: Path, extra: dict[str, str]) -> Path:
    files = dict(_BASE_TREE)
    files.update(extra)
    _write_tree(workdir, files)
    return workdir


def test_guard_flags_qt_in_core_layer(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/ai/bad.py": "import PySide6\n"})
    violations = find_qt_violations(root)
    assert len(violations) == 1
    assert "emowall/ai/bad.py" in violations[0]


def test_guard_flags_qt_imported_with_from(workdir: Path) -> None:
    root = _fake_project(
        workdir, {"emowall/emotion/bad.py": "from PySide6.QtCore import QObject\n"}
    )
    assert find_qt_violations(root), "from PySide6.X import Y 必须被识别"


def test_guard_flags_qt_outside_gui_and_app(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/utils/helper.py": "import PySide6\n"})
    assert find_qt_violations(root), "非 gui/app 位置出现 Qt 必须被识别"


def test_guard_allows_qt_in_gui_and_app(workdir: Path) -> None:
    root = _fake_project(
        workdir,
        {
            "emowall/gui/widget.py": "from PySide6.QtWidgets import QWidget\n",
            "emowall/app.py": "import PySide6\n",
        },
    )
    assert find_qt_violations(root) == []


def test_guard_flags_layer_importing_other_layer(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/storage/bad.py": "from emowall.ai import models\n"})
    violations = find_layer_dependency_violations(root)
    assert violations and "emowall/storage/bad.py" in violations[0]


def test_guard_flags_relative_layer_import(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/storage/bad.py": "from .. import ai\n"})
    assert find_layer_dependency_violations(root), "相对 import 也必须被识别"


def test_guard_flags_layer_importing_gui_or_app(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/config/bad.py": "import emowall.gui\n"})
    assert find_layer_dependency_violations(root)


def test_guard_flags_unlisted_third_party_dependency(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/ai/bad.py": "import requests\n"})
    violations = find_third_party_violations(root)
    assert violations and "requests" in violations[0]


def test_guard_flags_httpx_outside_ai_layer(workdir: Path) -> None:
    root = _fake_project(workdir, {"emowall/config/bad.py": "import httpx\n"})
    assert find_third_party_violations(root)


def test_guard_allows_httpx_in_ai_layer(workdir: Path) -> None:
    """ai 允许直接 import httpx；httpx 内部的 h11/httpcore 不属于项目直接依赖，不扫描。"""
    root = _fake_project(workdir, {"emowall/ai/client.py": "import httpx\n"})
    assert find_third_party_violations(root) == []


def test_guard_flags_httpx_in_non_ai_test_file(workdir: Path) -> None:
    root = _fake_project(workdir, {"tests/test_other.py": "import httpx\n"})
    violations = find_test_network_violations(root)
    assert violations and "test_other.py" in violations[0]


def test_guard_allows_httpx_only_in_ai_client_test_file(workdir: Path) -> None:
    root = _fake_project(workdir, {"tests/test_ai_client.py": "import httpx\n"})
    assert find_test_network_violations(root) == []


def test_guard_still_flags_other_network_clients_in_ai_client_test_file(workdir: Path) -> None:
    root = _fake_project(workdir, {"tests/test_ai_client.py": "import requests\n"})
    assert find_test_network_violations(root)


def test_guard_flags_ai_importing_sqlite_or_asyncio(workdir: Path) -> None:
    root = _fake_project(
        workdir,
        {"emowall/ai/bad.py": "import sqlite3\nimport asyncio\n"},
    )
    violations = find_ai_forbidden_stdlib(root)
    assert violations
    assert any("sqlite3" in item for item in violations)
    assert any("asyncio" in item for item in violations)
