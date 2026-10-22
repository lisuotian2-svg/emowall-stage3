"""架构守护测试：分层解耦规则一旦被破坏，这里必须失败。

规则（详见 AGENTS.md 第 2 节）：
    1. ai / config / storage / emotion 四层互不 import，也不 import gui / app；
    2. 只有 `emowall/gui/**` 与组合根 `emowall/app.py` 允许 import Qt 绑定库；
    3. 四层只允许标准库 + 白名单第三方库（ai 仅 httpx，其余为空）；
    4. `emowall/__init__.py` 不得拉起 GUI。
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "emowall"

LEAF_LAYERS = ("ai", "config", "storage", "emotion")
QT_MODULES = ("PySide6", "PySide2", "PyQt6", "PyQt5", "shiboken6", "shiboken2")
FORBIDDEN_TARGETS = ("gui", "app")

# 唯一允许 import Qt 的位置：界面层目录 与 组合根模块
QT_ALLOWED_DIRS = (PACKAGE_ROOT / "gui",)
QT_ALLOWED_FILES = (PACKAGE_ROOT / "app.py",)

# 各层允许的第三方依赖（标准库始终允许）
THIRD_PARTY_ALLOWLIST: dict[str, frozenset[str]] = {
    "ai": frozenset({"httpx"}),
    "config": frozenset(),
    "storage": frozenset(),
    "emotion": frozenset(),
}


def _layer_files(layer: str) -> list[Path]:
    layer_dir = PACKAGE_ROOT / layer
    assert layer_dir.is_dir(), f"缺少层目录：{layer_dir}"
    return sorted(layer_dir.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    """返回文件中所有被 import 的绝对模块名（相对 import 会展开成完整路径）。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    relative_to_project = path.relative_to(PROJECT_ROOT).with_suffix("")
    package_parts = list(relative_to_project.parts[:-1])

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level=1 表示当前包，level=2 表示上一级
                base = package_parts[: len(package_parts) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if prefix:
                modules.add(prefix)
                for alias in node.names:
                    modules.add(f"{prefix}.{alias.name}")
            else:
                for alias in node.names:
                    modules.add(alias.name)
    return modules


def _top_level(module: str) -> str:
    return module.split(".", 1)[0]


def _iter_layer_modules(layer: str) -> Iterator[tuple[Path, str]]:
    for path in _layer_files(layer):
        for module in sorted(_imported_modules(path)):
            yield path, module


def _qt_allowed(path: Path) -> bool:
    if any(allowed_dir in path.parents for allowed_dir in QT_ALLOWED_DIRS):
        return True
    return path in QT_ALLOWED_FILES


def test_all_layers_exist() -> None:
    for layer in (*LEAF_LAYERS, "gui"):
        layer_dir = PACKAGE_ROOT / layer
        assert layer_dir.is_dir(), f"缺少层目录：{layer_dir}"
        assert (layer_dir / "__init__.py").is_file(), f"缺少 {layer}/__init__.py"


def test_root_package_does_not_import_qt_or_gui() -> None:
    """导入 emowall 不能顺带加载 Qt 或界面代码。"""
    init_file = PACKAGE_ROOT / "__init__.py"
    for module in _imported_modules(init_file):
        assert _top_level(module) not in QT_MODULES, f"emowall/__init__.py 不允许 import {module}"
        assert not module.startswith(("emowall.gui", "emowall.app")), (
            f"emowall/__init__.py 不允许 import {module}"
        )


def test_only_gui_and_composition_root_import_qt() -> None:
    """Qt 只允许出现在界面层与组合根，其他位置出现即视为分层被破坏。"""
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} → {module}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if not _qt_allowed(path)
        for module in _imported_modules(path)
        if _top_level(module) in QT_MODULES
    ]
    assert not offenders, "Qt 只能出现在 emowall/gui 与 emowall/app.py：" + "; ".join(offenders)


def test_leaf_layers_do_not_import_qt() -> None:
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)} → {module}"
        for layer in LEAF_LAYERS
        for path, module in _iter_layer_modules(layer)
        if _top_level(module) in QT_MODULES
    ]
    assert not offenders, "核心层禁止依赖 Qt：" + "; ".join(offenders)


def test_leaf_layers_are_mutually_independent() -> None:
    offenders = []
    for layer in LEAF_LAYERS:
        others = [name for name in LEAF_LAYERS if name != layer]
        forbidden = [f"emowall.{name}" for name in others + list(FORBIDDEN_TARGETS)]
        for path, module in _iter_layer_modules(layer):
            if any(module == target or module.startswith(f"{target}.") for target in forbidden):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} → {module}")
    assert not offenders, (
        "四层必须互不依赖，跨层数据由组合根（emowall/app.py）映射：" + "; ".join(offenders)
    )


def test_leaf_layers_use_stdlib_and_allowlisted_third_party_only() -> None:
    """四层只允许标准库 + 白名单第三方库，保证可迁移、可离线测试。"""
    standard_library = set(sys.stdlib_module_names)
    offenders = []
    for layer, allowed in THIRD_PARTY_ALLOWLIST.items():
        for path, module in _iter_layer_modules(layer):
            top = _top_level(module)
            if top == "emowall" or top in standard_library or top in allowed:
                continue
            if top in QT_MODULES:
                continue  # 由 test_leaf_layers_do_not_import_qt 单独报告
            offenders.append(f"{path.relative_to(PROJECT_ROOT)} → {module}（层：{layer}）")
    assert not offenders, "出现白名单外的依赖：" + "; ".join(offenders)
