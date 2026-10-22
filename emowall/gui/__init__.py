"""PySide6 界面层（Stage 5 实现）。

职责：
    * 主窗口、消息气泡、会话列表、设置对话框、表情指示器
    * 工作线程编排（QThread + worker），把流式结果用信号回传主线程

依赖约束：可以 import PySide6，以及向下使用 ai / storage / config / emotion 的公共类型；
禁止被上述各层反向 import；禁止在这里写 SQL 语句或拼装 HTTP 请求。
"""
