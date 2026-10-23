"""共享测试夹具。

所有测试临时目录都放在工作区 `.tmp/` 下：受限环境的系统临时目录可能不可写。
"""

from __future__ import annotations

import shutil
import socket
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def block_real_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """离线测试不得建立真实网络连接；integration 用例例外。

    MockTransport / 自定义假客户端不会触碰 socket，因此默认用例必须保持零真实网络。
    这是对架构守护测试的运行时补充（静态规则见 test_architecture.py）。
    """
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker(
        "local_network"
    ):
        return

    def _deny(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "离线测试禁止真实网络连接（integration / local_network 用例请加对应标记）"
        )

    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny)


@pytest.fixture()
def workdir() -> Iterator[Path]:
    base = PROJECT_ROOT / ".tmp" / "pytest" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)
