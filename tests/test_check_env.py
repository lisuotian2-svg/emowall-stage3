"""环境自检脚本的测试：正常/异常路径、中文输出、仅标准库依赖。

所有用例离线运行：不访问外网，真实 HTTP 只用本机回环端口。
"""

from __future__ import annotations

import ast
import importlib.util
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "check_env.py"

_spec = importlib.util.spec_from_file_location("emowall_check_env", SCRIPT)
assert _spec and _spec.loader
check_env = importlib.util.module_from_spec(_spec)
# dataclass 需要模块已注册到 sys.modules 才能解析前向引用
sys.modules[_spec.name] = check_env
_spec.loader.exec_module(check_env)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )


class _HtmlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        body = b"<html>not json</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # 静默
        return


def test_display_width_counts_cjk_as_two() -> None:
    assert check_env._display_width("Python") == 6
    assert check_env._display_width("同步模型") == 8


def test_validate_base_url_rejects_invalid() -> None:
    report = check_env.Report()
    assert check_env._validate_base_url(report, "not-a-url") is None
    assert report.count(check_env.FAIL) == 1


def test_validate_base_url_normalizes_trailing_slash() -> None:
    report = check_env.Report()
    assert check_env._validate_base_url(report, "http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert report.count(check_env.FAIL) == 0


def test_report_render_marks_strict_mode() -> None:
    report = check_env.Report()
    report.add("依赖", check_env.WARN, "缺失：httpx")
    text = report.render(strict=True)
    assert "WARN" in text
    assert "strict 模式：WARN 视为失败" in text
    assert "结果：" in text


@pytest.mark.local_network
def test_http_json_rejects_non_json_payload() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HtmlHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(ValueError):
            check_env._http_json(f"http://127.0.0.1:{server.server_port}/", timeout=3.0)
    finally:
        server.shutdown()
        server.server_close()


def test_script_help_exits_zero() -> None:
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "环境自检" in result.stdout


def test_invalid_base_url_exits_one_with_chinese_message() -> None:
    result = _run("--base-url", "not-a-url")
    assert result.returncode == 1
    assert "地址无效" in result.stdout


@pytest.mark.local_network
def test_unreachable_service_reports_fail() -> None:
    port = _free_port()
    result = _run("--base-url", f"http://127.0.0.1:{port}")
    assert result.returncode == 1
    assert "不可达" in result.stdout


def test_output_is_valid_utf8_without_replacement_chars() -> None:
    result = _run("--help")
    assert "\ufffd" not in result.stdout
    assert "EmoWall AI" in result.stdout


def test_script_depends_on_stdlib_only() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names)
    assert imported <= stdlib, f"check_env.py 引入了第三方依赖：{sorted(imported - stdlib)}"
