"""文档一致性测试：链接有效、目录描述与实际一致、无个人绝对路径与过期表述。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
AGENTS = PROJECT_ROOT / "AGENTS.md"
DOC_FILES = [README, AGENTS, *sorted((PROJECT_ROOT / "docs").glob("*.md"))]
LAYER_DIRS = ("ai", "config", "storage", "emotion", "gui")

LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
PERSONAL_PATH_PATTERN = re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9]")


def _relative_links() -> list[tuple[Path, str]]:
    links: list[tuple[Path, str]] = []
    for doc in DOC_FILES:
        for match in LINK_PATTERN.finditer(doc.read_text(encoding="utf-8")):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            links.append((doc, target))
    return links


@pytest.mark.parametrize(
    ("doc", "target"),
    _relative_links(),
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_relative_links_resolve(doc: Path, target: str) -> None:
    path = target.split("#", 1)[0]
    assert (doc.parent / path).resolve().exists(), f"{doc.name} 中的链接不存在：{target}"


@pytest.mark.parametrize("doc", DOC_FILES, ids=lambda path: path.name)
def test_docs_have_no_personal_absolute_paths(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    matches = PERSONAL_PATH_PATTERN.findall(text)
    assert not matches, f"{doc.name} 含个人绝对路径：{matches[:3]}（请改用占位符）"


def test_readme_documents_actual_package_structure() -> None:
    text = README.read_text(encoding="utf-8")
    assert "6 个包目录" in text
    for layer in LAYER_DIRS:
        assert f"{layer}/" in text, f"README 目录树缺少 {layer}/"
        assert (PROJECT_ROOT / "emowall" / layer).is_dir(), f"实际缺少 emowall/{layer}/"


def test_docs_agree_on_dedicated_database_thread() -> None:
    """P1-3 的架构决定必须在三份文档中一致出现。"""
    for doc in (AGENTS, PROJECT_ROOT / "docs" / "ARCHITECTURE.md", PROJECT_ROOT / "docs" / "DEVELOPMENT_PLAN.md"):
        assert "数据库工作线程" in doc.read_text(encoding="utf-8"), f"{doc.name} 未写明数据库独立线程"


def test_docs_have_no_stale_statements() -> None:
    stale = (
        "主线程仅做单条短读",          # 旧的主线程读库方案
        "check_same_thread=False",     # 旧方案：关闭线程检查
        "五项结论",                    # 旧：check_env 只输出五项
        "7 个包目录",                  # 旧：包目录数量写错
        "ENVIRONMENT_AUDIT.md#问题-2", # 旧：失效锚点
    )
    for doc in DOC_FILES:
        text = doc.read_text(encoding="utf-8")
        for phrase in stale:
            assert phrase not in text, f"{doc.name} 仍包含过期表述：{phrase}"
