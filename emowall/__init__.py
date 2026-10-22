"""EmoWall AI —— 面向 EmoWall 情绪壁纸的可复用 AI 对话核心（练习版 V0.1）。

本包只提供版本号与应用名。导入本包**不会**拉起 GUI，
因此 `emowall.ai` 等核心层可以在没有 PySide6 的环境中单独使用。
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"
APP_NAME = "EmoWall AI"

__all__ = ["APP_NAME", "__version__"]
