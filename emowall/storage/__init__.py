"""SQLite 存储层（Stage 3 实现）。

职责：
    * 数据库连接、PRAGMA、建表与版本迁移
    * 会话（conversations）与消息（messages）的仓库接口

依赖约束：仅标准库（sqlite3）。
禁止：import PySide6、httpx，禁止 import 其他 emowall 层。
"""
