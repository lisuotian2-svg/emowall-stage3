"""配置系统异常层级。

调用方只需捕获 `ConfigError` 即可兜住所有配置问题；
需要区分「用户输入非法」与「磁盘读写失败」时再用子类。
"""

from __future__ import annotations


class ConfigError(Exception):
    """配置系统异常基类。"""


class ConfigValidationError(ConfigError):
    """配置字段值非法（类型、范围或格式不符合约定）。"""


class ConfigIOError(ConfigError):
    """配置文件的磁盘读写失败。"""
