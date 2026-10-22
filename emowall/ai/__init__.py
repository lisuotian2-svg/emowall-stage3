"""AI 核心层（Stage 2 实现）。

职责：
    * Ollama HTTP 传输（`POST /api/chat`，NDJSON 流式）
    * 增量文本解析与生成统计
    * 多轮上下文裁剪
    * 可取消的生成（`CancelToken`）
    * 错误分类（连接失败 / 模型缺失 / 协议错误 / 已取消）

依赖约束：仅标准库 + httpx。
禁止：import PySide6，禁止 import 其他 emowall 层（gui / storage / config / emotion / app）。
"""
