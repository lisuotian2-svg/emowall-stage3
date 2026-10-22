"""配置系统层（Stage 1）。

职责：
    * 应用数据目录定位（`%APPDATA%\\EmoWall`，可由 `EMOWALL_HOME` 覆盖）
    * 配置数据结构与字段校验（`OllamaSettings / ChatSettings / AppSettings`）
    * `config.json` 读写：默认值、损坏恢复、未知字段保留、版本兼容、原子写入

依赖约束：仅标准库。
禁止：import PySide6、httpx，禁止 import 其他 emowall 层。
"""

from __future__ import annotations

from .errors import ConfigError, ConfigIOError, ConfigValidationError
from .paths import APP_DIR_NAME, CONFIG_FILENAME, ENV_HOME, config_path, default_app_data_dir
from .settings import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    AppSettings,
    ChatSettings,
    OllamaSettings,
    default_settings,
)
from .store import ConfigStore

__all__ = [
    "APP_DIR_NAME",
    "CONFIG_FILENAME",
    "CURRENT_CONFIG_VERSION",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_SYSTEM_PROMPT",
    "ENV_HOME",
    "AppSettings",
    "ChatSettings",
    "ConfigError",
    "ConfigIOError",
    "ConfigStore",
    "ConfigValidationError",
    "OllamaSettings",
    "config_path",
    "default_app_data_dir",
    "default_settings",
]
