"""配置系统层（Stage 1 实现）。

职责：
    * 应用数据目录定位（`%APPDATA%\\EmoWall`，可由 `EMOWALL_HOME` 覆盖）
    * `config.json` 读写：默认值、校验、原子写入、损坏文件备份回退

依赖约束：仅标准库。
禁止：import PySide6、httpx，禁止 import 其他 emowall 层。
"""
