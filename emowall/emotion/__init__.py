"""情绪系统层（Stage 4 实现）。

职责：
    * 把 AI 回复文本映射为 5 种基础表情：开心 / 平静 / 难过 / 生气 / 惊讶
    * 提供表情的名称、emoji 与主色等展示数据（不含 Qt 类型）

依赖约束：仅标准库；纯函数、确定性、无 I/O。
禁止：import PySide6、httpx、sqlite3，禁止 import 其他 emowall 层。
"""
