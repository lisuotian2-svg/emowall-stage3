"""应用数据目录定位。

优先级：
    1. 环境变量 `EMOWALL_HOME`（测试、便携模式、多实例隔离）
    2. Windows 的 `%APPDATA%\\EmoWall`
    3. 其他平台或缺少 APPDATA 时的 `~/.emowall`
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "EmoWall"
CONFIG_FILENAME = "config.json"
ENV_HOME = "EMOWALL_HOME"


def default_app_data_dir() -> Path:
    """返回配置/数据库所在目录（不创建目录，不写文件）。"""
    override = os.environ.get(ENV_HOME)
    if override:
        return Path(override).expanduser()

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME

    return Path.home() / ".emowall"


def config_path(base_dir: Path | None = None) -> Path:
    """返回配置文件路径；`base_dir` 用于显式注入（测试/便携模式）。"""
    directory = Path(base_dir) if base_dir is not None else default_app_data_dir()
    return directory / CONFIG_FILENAME
