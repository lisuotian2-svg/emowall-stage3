"""共享测试夹具。

所有测试临时目录都放在工作区 `.tmp/` 下：受限环境的系统临时目录可能不可写。
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir() -> Iterator[Path]:
    base = PROJECT_ROOT / ".tmp" / "pytest" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)
