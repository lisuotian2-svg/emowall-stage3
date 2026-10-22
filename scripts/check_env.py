#!/usr/bin/env python
"""EmoWall 环境自检脚本。

只使用标准库，因此可以在安装第三方依赖之前运行。

用法::

    python scripts/check_env.py
    python scripts/check_env.py --base-url http://127.0.0.1:11434
    python scripts/check_env.py --strict        # WARN 也视为失败

退出码：0 = 无 FAIL（未加 --strict 时忽略 WARN）；1 = 存在 FAIL，或 --strict 下存在 WARN。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

MIN_PYTHON = (3, 12)
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
REQUIRED_MODULES = ("PySide6", "httpx", "pytest")

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Result:
    """一条检查结果。"""

    name: str
    status: str
    detail: str
    hint: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str, hint: str = "") -> None:
        self.results.append(Result(name, status, detail, hint))

    def count(self, status: str) -> int:
        return sum(1 for item in self.results if item.status == status)

    def render(self, *, strict: bool = False) -> str:
        name_width = max((_display_width(item.name) for item in self.results), default=0) + 2
        lines = []
        for item in self.results:
            padding = " " * max(0, name_width - _display_width(item.name))
            lines.append(f"[{item.status}] {item.name}{padding}{item.detail}")
            if item.hint and item.status != PASS:
                lines.append(" " * (name_width + 7) + f"→ {item.hint}")
        lines.append("")
        lines.append(
            f"结果：{self.count(PASS)} PASS / {self.count(WARN)} WARN / {self.count(FAIL)} FAIL"
        )
        if strict and self.count(WARN):
            lines.append("strict 模式：WARN 视为失败")
        return "\n".join(lines)


def _display_width(text: str) -> int:
    """按终端显示宽度计算（中日韩全角字符占 2 列），用于对齐输出。"""
    return sum(
        2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text
    )


def _run_command(args: list[str], timeout: float = 15.0) -> tuple[int, str]:
    """执行外部命令并返回 (returncode, 合并输出)；命令不存在/无法执行时返回 (127/126, 说明)。"""
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return 127, f"命令不存在：{args[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"命令超时：{' '.join(args)}"
    except OSError as exc:
        return 126, f"无法执行 {args[0]}：{exc}"
    output = f"{completed.stdout}{completed.stderr}".strip()
    return completed.returncode, output


def check_python(report: Report) -> None:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info[:2] >= MIN_PYTHON:
        report.add("Python", PASS, f"{version}（{sys.executable}）")
    else:
        required = ".".join(str(part) for part in MIN_PYTHON)
        report.add(
            "Python",
            FAIL,
            f"{version}，要求 >= {required}",
            "安装 Python 3.12 并重建 .venv",
        )


def check_modules(report: Report) -> None:
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        report.add("依赖", PASS, "PySide6 / httpx / pytest 均可导入")
        return
    report.add(
        "依赖",
        WARN,
        "缺失：" + ", ".join(missing),
        "在当前解释器执行 pip install -r requirements.txt",
    )


def check_cli(report: Report, name: str, args: list[str]) -> None:
    path = shutil.which(name)
    if path is None:
        report.add(name, WARN, "未在 PATH 中找到", f"安装 {name} 或将其加入 PATH")
        return
    code, output = _run_command(args)
    first_line = output.splitlines()[0] if output else ""
    if code == 0:
        report.add(name, PASS, first_line or path)
    else:
        report.add(name, WARN, output or f"退出码 {code}", f"检查 {name} 安装")


def _http_json(url: str, timeout: float) -> tuple[int, object]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
        status = response.status
    try:
        return status, json.loads(payload)
    except ValueError as exc:
        raise ValueError(f"响应不是合法 JSON：{payload[:120]!r}") from exc


def _validate_base_url(report: Report, base_url: str) -> str | None:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        report.add(
            "Ollama API",
            FAIL,
            f"地址无效：{base_url!r}",
            "示例：--base-url http://127.0.0.1:11434",
        )
        return None
    return base_url.rstrip("/")


def check_ollama(report: Report, base_url: str) -> None:
    base = _validate_base_url(report, base_url)
    if base is None:
        return

    try:
        status, body = _http_json(f"{base}/api/version", timeout=5.0)
    except urllib.error.HTTPError as exc:
        report.add("Ollama API", FAIL, f"HTTP {exc.code}（{base}）", "检查 Ollama 版本与服务状态")
        return
    except ValueError as exc:
        report.add("Ollama API", FAIL, f"{base} 响应异常：{exc}", "确认地址指向 Ollama 而非其他服务")
        return
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        report.add(
            "Ollama API",
            FAIL,
            f"{base} 不可达：{reason}",
            "启动 Ollama：开始菜单运行 Ollama，或执行 ollama serve",
        )
        return

    version = body.get("version") if isinstance(body, dict) else None
    report.add("Ollama API", PASS, f"{base}（version {version}，HTTP {status}）")

    try:
        _, tags = _http_json(f"{base}/api/tags", timeout=10.0)
    except urllib.error.HTTPError as exc:
        report.add("本地模型", WARN, f"HTTP {exc.code}", "稍后重试")
        return
    except ValueError as exc:
        report.add("本地模型", WARN, f"响应异常：{exc}", "稍后重试")
        return
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        report.add("本地模型", WARN, f"读取 /api/tags 失败：{exc}", "稍后重试")
        return

    models = tags.get("models", []) if isinstance(tags, dict) else []
    names = [
        str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")
    ]
    if names:
        report.add("本地模型", PASS, "、".join(names))
    else:
        report.add("本地模型", WARN, "没有本地模型", "执行 ollama pull qwen3:8b")

    models_dir = os.environ.get("OLLAMA_MODELS")
    if models_dir:
        exists = "存在" if os.path.isdir(models_dir) else "不存在"
        report.add("模型目录", PASS, f"OLLAMA_MODELS={models_dir}（{exists}）")


def check_app_data(report: Report) -> None:
    """报告将来应用数据目录的位置，不创建任何文件。"""
    override = os.environ.get("EMOWALL_HOME")
    if override:
        report.add("应用数据目录", PASS, f"{override}（来自 EMOWALL_HOME）")
        return
    appdata = os.environ.get("APPDATA")
    if not appdata:
        report.add("应用数据目录", WARN, "APPDATA 未设置", "配置与数据库将无法定位")
        return
    report.add("应用数据目录", PASS, os.path.join(appdata, "EmoWall"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EmoWall AI V0.1 环境自检")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Ollama 服务地址")
    parser.add_argument("--strict", action="store_true", help="WARN 也返回非零退出码")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    report = Report()
    check_python(report)
    check_modules(report)
    check_cli(report, "git", ["git", "--version"])
    check_cli(report, "ollama", ["ollama", "--version"])
    check_ollama(report, args.base_url)
    check_app_data(report)

    print("EmoWall AI · 环境自检")
    print("=" * 60)
    print(report.render(strict=args.strict))

    failed = report.count(FAIL) > 0 or (args.strict and report.count(WARN) > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
