# EmoWall Stage 3 接口契约 v1

> 版本：v1.2 最终草案（独立审查二轮 CONDITIONAL PASS 后修订 + 项目负责人确认）
> 日期：2026-10-23
> 状态：**待最终复审**（未冻结）
> 作者：Lead Software Architect
> 审核者：独立审查 Agent（首轮 CONDITIONAL PASS → 二轮 CONDITIONAL PASS）
> 批准者：项目负责人（已确认 5 项设计假设）

---

## 前言

本文档定义 EmoWall AI V0.1 Stage 3（SQLite 存储层）的**公共接口契约**。

契约的目标是：
1. **冻结** Stage 3 的公共接口，使多个 Agent 可以并行开发后续阶段
2. **保护** Stage 1（config）和 Stage 2（ai）的已有稳定接口
3. **明确** 模块间的依赖方向、数据模型、线程约束和错误语义
4. **支持** 长期可审计、可维护的接口演进

**冻结后，所有公共接口的变更必须经过架构审批流程。**

---

## 目录

1. [契约范围](#1-契约范围)
2. [已冻结接口（不可修改）](#2-已冻结接口不可修改)
3. [Stage 3 拟定接口](#3-stage-3-拟定接口)
4. [跨模块通信约定](#4-跨模块通信约定)
5. [错误处理约定](#5-错误处理约定)
6. [兼容性要求](#6-兼容性要求)
7. [冻结验收清单](#7-冻结验收清单)
8. [阻塞问题与下一步建议](#8-阻塞问题与下一步建议)

---

## 1. 契约范围

### 1.1 本文档覆盖的接口

| 层 | 状态 | 说明 |
|----|------|------|
| `emowall/ai` | ✅ 已冻结（Stage 2） | 见 ARCHITECTURE.md §3.1 和 ADR-0002 |
| `emowall/config` | ✅ 已冻结（Stage 1） | 见 ARCHITECTURE.md §3.2 和 ADR-0001 |
| `emowall/storage` | 🔲 拟定（Stage 3） | 本文档 §3 定义 |
| `emowall/emotion` | 🔲 待设计（Stage 4） | 不在本文档范围 |
| `emowall/gui` | 🔲 待设计（Stage 5） | 不在本文档范围 |

### 1.2 不在本文档覆盖范围

- Stage 3 的**内部实现**（私有方法、内部类）
- 性能优化细节
- 日志格式（但日志命名空间 `emowall.storage` 已约定）
- 数据库文件的具体路径（由 `config.default_app_data_dir()` 决定）

### 1.3 关联文档

| 文档 | 关系 |
|------|------|
| `docs/ARCHITECTURE.md` | 架构设计（契约的权威来源） |
| `AGENTS.md` | 长期开发规则（约束来源） |
| `docs/adr/0001-configuration-store.md` | 配置层设计决策 |
| `docs/adr/0002-ai-core-boundaries-and-cancellation.md` | AI 层设计决策 |
| `docs/contracts/data-models.md` | 数据模型详细约定 |
| `docs/contracts/threading-model.md` | 线程模型详细约定 |
| `docs/contracts/module-ownership.md` | 模块所有权与并行开发 |
| `docs/contracts/investigation-report.md` | 调查报告（事实依据） |

---

## 2. 已冻结接口（不可修改）

### 2.1 AI 层公共 API

**定义位置**：`emowall/ai/__init__.py`（`__all__`）

以下符号在 Stage 2 已冻结，Stage 3 **不得**修改：

```python
# 数据模型
ChatMessage, ChatChunk, GenerationStats, Role

# 传输客户端
OllamaClient, DEFAULT_BASE_URL

# 对话引擎
ChatEngine

# 取消令牌
CancelToken

# 异常层级
AIError, OllamaUnavailableError, OllamaConnectionError, OllamaTimeoutError,
OllamaHTTPError, ModelNotFoundError, ProtocolError, StreamInterruptedError,
CancelledError
```

完整签名见 `docs/ARCHITECTURE.md` §3.1 和 `docs/contracts/investigation-report.md` §2.1。

### 2.2 配置层公共 API

**定义位置**：`emowall/config/__init__.py`（`__all__`）

以下符号在 Stage 1 已冻结，Stage 3 **不得**修改：

```python
# 数据模型
OllamaSettings, ChatSettings, AppSettings

# 存储
ConfigStore

# 路径
config_path, default_app_data_dir, APP_DIR_NAME, CONFIG_FILENAME, ENV_HOME

# 默认值
DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT, CURRENT_CONFIG_VERSION

# 异常
ConfigError, ConfigIOError, ConfigValidationError

# 工厂函数
default_settings
```

完整签名见 `docs/ARCHITECTURE.md` §3.2 和 `docs/contracts/investigation-report.md` §2.2。

---

## 3. Stage 3 拟定接口

### 3.1 异常层级

**定义位置**：`emowall/storage/errors.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/gui`（Stage 5）、`emowall/app.py`（Stage 5）

```python
class StorageError(Exception):
    """存储层异常基类。"""

class StorageConnectionError(StorageError):
    """数据库连接失败（文件不可写、权限不足等）。"""

class StorageIntegrityError(StorageError):
    """数据完整性违规（外键约束、唯一约束等）。"""

class StorageIOError(StorageError):
    """磁盘读写失败。"""
```

**设计原则**：
- 与 `AIError`、`ConfigError` 平级，不继承彼此
- 调用方可只捕获 `StorageError` 兜住所有存储问题
- `StorageIntegrityError` 用于外键违规（如 `conversation_id` 不存在）
- `StorageConnectionError` 用于连接阶段的错误
- `StorageIOError` 用于磁盘读写错误

**兼容性要求**：
- Stage 4/5 不得修改异常层级
- 未来新增子类必须继承 `StorageError`

### 3.2 数据模型

**定义位置**：`emowall/storage/models.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/gui`（Stage 5）、`emowall/app.py`（Stage 5）

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Conversation:
    """一个对话会话的元数据。"""
    id: str              # UUID v4 字符串
    title: str           # 会话标题（保证非空，≤ 20 字符；规则见 §3.4 create()）
    model: str           # 使用的模型名
    created_at: str      # ISO-8601 UTC
    updated_at: str      # ISO-8601 UTC

@dataclass(frozen=True)
class MessageRecord:
    """一条持久化的消息记录。"""
    id: int | None                       # 行 ID（传入时为 None；Repository 返回时保证非 None）
    conversation_id: str                 # 所属会话 UUID
    role: str                            # "system" | "user" | "assistant"；Repository 负责校验合法值
    content: str                         # 消息文本
    emotion: str | None                  # 情绪标签名称
    emotion_intensity: float | None      # 情绪强度 [0.0, 1.0]
    created_at: str                      # ISO-8601 UTC
```

详细约束见 `docs/contracts/data-models.md` §3。

### 3.3 数据库连接管理

**定义位置**：`emowall/storage/database.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/storage/repository.py`（内部）、`emowall/gui`（Stage 5）

```python
class Database:
    """SQLite 数据库连接管理器。

    构造时打开连接、设置 PRAGMA、执行建表和迁移。
    close() 关闭连接。
    支持上下文管理器（with 语句）。

    线程契约：
        连接在构造线程上使用。check_same_thread=True（默认）。
        Stage 5 由 StorageService（QThread）独占使用。
    """

    def __init__(self, path: Path) -> None:
        """打开数据库连接，执行建表和迁移。

        Args:
            path: 数据库文件路径。目录不存在时自动创建。

        Raises:
            StorageConnectionError: 连接失败（目录不可创建、权限不足等）
            StorageIOError: 磁盘读写失败
        """

    def close(self) -> None:
        """关闭数据库连接。幂等：多次调用无副作用。"""

    @property
    def schema_version(self) -> int:
        """当前 schema 版本（PRAGMA user_version）。"""

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
```

**输入约束**：
- `path`：`pathlib.Path`，指向 `.db` 文件
- 目录不存在时自动创建（`parents=True`）
- 文件不存在时自动创建数据库并建表

**输出约束**：
- 构造成功后，`schema_version` 返回当前版本号（初始为 1）
- `close()` 后调用任何方法抛 `sqlite3.ProgrammingError`

**PRAGMA 设置**：
- `journal_mode = WAL`
- `foreign_keys = ON`
- `busy_timeout = 2000`

**生命周期**：
- `__init__` → 使用 → `close()`
- 或 `with Database(path) as db:` → 使用 → 自动 `close()`

### 3.4 仓库接口

**定义位置**：`emowall/storage/repository.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/gui`（Stage 5，通过 StorageService）

```python
class ConversationRepository:
    """会话与消息的 CRUD 仓库。

    线程契约：继承 Database 的线程绑定约束。
    每次操作是一个短事务。
    """

    def __init__(self, db: Database) -> None:
        """绑定到已打开的数据库。

        Args:
            db: 已打开的 Database 实例

        Raises:
            TypeError: db 不是 Database 实例
        """

    def create(self, *, title: str, model: str) -> Conversation:
        """创建新会话。

        标题规则（与 append_message 自动标题共享同一截断函数）：
            1. 先 strip() 去除首尾空白；
            2. 空串或纯空白 → 标题设为 "新会话"；
            3. len(title) > 20 → 截断为 title[:17] + "..."（总计 20 个 Python 字符）；
            4. "字符"统一使用 Python len()（代码点计数），不做 Unicode 字素簇拆分。

        Args:
            title: 会话标题（任意字符串；空/空白回退为"新会话"，超长截断）
            model: 使用的模型名（非空字符串）

        Returns:
            新创建的 Conversation（含生成的 UUID 和时间戳；id 为新 UUID v4）

        Raises:
            ValueError: model 为空串或纯空白
            StorageIOError: 写入失败
        """

    def list_recent(self, limit: int = 50) -> list[Conversation]:
        """按 updated_at 倒序列出最近会话。

        Args:
            limit: 最大返回数（默认 50，必须 > 0）

        Returns:
            Conversation 列表（可能为空）

        Raises:
            ValueError: limit ≤ 0
        """

    def get(self, conversation_id: str) -> Conversation | None:
        """按 ID 查找会话。

        Returns:
            Conversation 或 None（不存在时）
        """

    def rename(self, conversation_id: str, title: str) -> None:
        """重命名会话。

        标题规则与 create() 一致：strip → 空/空白回退 "新会话" → 超长截断。

        Raises:
            StorageIntegrityError: conversation_id 不存在
            StorageIOError: 写入失败
        """

    def delete(self, conversation_id: str) -> None:
        """删除会话及其级联删除消息。

        会话不存在时静默（幂等）。
        """

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        emotion: str | None = None,
        emotion_intensity: float | None = None,
    ) -> MessageRecord:
        """追加一条消息到会话。

        副作用：
            - 更新会话的 updated_at 为当前 UTC 时间；
            - 自动标题生成：当 role == "user" 且该会话尚无 user 消息时，
              用 content 生成会话标题，规则与 create() 一致：
                1. strip() → 空/空白 → "新会话"
                2. len > 20 → content[:17] + "..."
                3. 否则原样使用
              此操作与消息写入在同一事务内。

        Args:
            conversation_id: 会话 UUID（必须已存在）
            role: "system" | "user" | "assistant"（必须校验，不在集合中抛 ValueError）
            content: 消息文本（可为空串）
            emotion: 情绪标签名称（可选；Stage 4 产出，Stage 3 仅存储）
            emotion_intensity: 情绪强度（可选；非 None 时 ∈ [0.0, 1.0]）

        Returns:
            新创建的 MessageRecord；**id 保证非 None**（由 SQLite AUTOINCREMENT 生成）

        Raises:
            StorageIntegrityError: conversation_id 不存在（外键违规）
            ValueError: role 不在 {"system", "user", "assistant"} 中；
                        或 emotion_intensity 非 None 且不在 [0.0, 1.0] 内
            StorageIOError: 写入失败
        """

    def list_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        """列出会话消息（按 id 正序，即插入顺序）。

        Args:
            conversation_id: 会话 UUID
            limit: 最大返回数；None 表示返回全部消息。
                   **注意**：limit=None 时，超长会话（数千条消息）会一次性加载全部记录到内存。
                   Stage 5 的 StorageService 应结合 AI 引擎的上下文窗口（`qwen3:8b` 当前 8192 tokens）
                   使用合适的 limit 值。

        Returns:
            MessageRecord 列表（可能为空；会话不存在时也返回空列表）

        Raises:
            ValueError: limit 不是 None 且 limit <= 0
        """
```

### 3.5 预留接口：`update_message_emotion()` — 拟定契约（Stage 3 实现，Stage 4 消费）

> **状态**：拟定契约 — 尚未实现。Stage 3 必须实现此方法；Stage 4（情绪系统）是其主要消费者。
> 标记为"预留"是因为当前没有调用方，但预留可避免 Stage 4 时再修改公共接口。

**定义位置**：`emowall/storage/repository.py`（待创建）
**负责模块**：`emowall/storage`（Stage 3 实现 + 维护）
**消费模块**：`emowall/emotion`（Stage 4，通过组合根调用）

```python
    def update_message_emotion(
        self,
        message_id: int,
        *,
        emotion: str,
        emotion_intensity: float,
    ) -> MessageRecord:
        """更新已有消息的情绪分析结果。

        状态：拟定契约（Stage 3 实现，Stage 4 消费）。

        事务：单条 UPDATE 语句，自动提交。
        成功后返回更新后的完整 MessageRecord（新 frozen 实例）。

        Args:
            message_id: 消息行 ID（必须 > 0）
            emotion: 情绪标签名称（非空字符串；如 "happy"、"calm"）
            emotion_intensity: 情绪强度，必须在 [0.0, 1.0] 内

        Returns:
            更新后的 MessageRecord（frozen 新实例；id 保证非 None）

        Raises:
            StorageIntegrityError: message_id 不存在于 messages 表
            ValueError: emotion 为空串/纯空白；
                        emotion_intensity 不在 [0.0, 1.0]；
                        message_id <= 0
            StorageIOError: 写入失败

        异常链：
            所有 StorageError 保留原始 sqlite3 异常作为 __cause__（见 §5.2）。
        """
```

**设计决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| 参数是 `message_id` 而非 `MessageRecord` | `int` | 避免要求调用方持有完整记录；最小化接口耦合 |
| 返回 `MessageRecord` 而非 `None` | 返回完整记录 | 调用方可直接使用更新后的数据，无需再次查询 |
| 消息不存在时抛异常而非返回 `None` | `StorageIntegrityError` | 与 `rename()` 一致；调用方需要明确知道数据不存在 |
| `emotion` 用 `str` 而非枚举 | `str` | storage 不 import emotion 层；组合根负责 `Emotion.value` → `str` 映射 |
| Stage 3 实现还是 Stage 4 实现 | Stage 3 | 存储操作属于 storage 层职责；Stage 4 只需调用 |
| 不支持将 emotion 重置为 `None` | V0.1 不做 | 参数非空；如需清除，未来可新增 `clear_message_emotion()` 或将参数改为 `Optional[str]` |

### 3.6 公共 API 导出

**定义位置**：`emowall/storage/__init__.py`（修改）
**负责模块**：`emowall/storage`

```python
"""SQLite 存储层（Stage 3）。

职责：
    * 数据库连接、PRAGMA、建表与版本迁移
    * 会话（conversations）与消息（messages）的仓库接口

依赖约束：仅标准库（sqlite3）。
禁止：import PySide6、httpx，禁止 import 其他 emowall 层。
"""

from __future__ import annotations

from .database import Database
from .errors import StorageConnectionError, StorageError, StorageIntegrityError, StorageIOError
from .models import Conversation, MessageRecord
from .repository import ConversationRepository

__all__ = [
    "Conversation",
    "ConversationRepository",
    "Database",
    "MessageRecord",
    "StorageConnectionError",
    "StorageError",
    "StorageIntegrityError",
    "StorageIOError",
]
```

---

## 4. 跨模块通信约定

### 4.1 依赖方向（不可违反）

```
emowall/gui  ──►  emowall/{ai, storage, emotion, config}   （只允许向下）
emowall/app.py ──►  emowall/{gui, ai, storage, emotion, config}（组合根）
emowall/{ai, storage, emotion, config} ──►  互不 import
```

`emowall/storage` 是叶子层：
- **不 import** `emowall/ai`
- **不 import** `emowall/config`
- **不 import** `emowall/emotion`
- **不 import** `emowall/gui`
- **不 import** `emowall/app`

### 4.2 数据流方向

```
用户输入
  │
  ▼
GUI (main thread)
  │ signal: 用户消息
  ▼
ChatWorker (QThread)
  │ 调用: ChatEngine.stream_reply()
  ▼
AI 层 (同步)
  │ 返回: Iterator[ChatChunk]
  ▼
ChatWorker (QThread)
  │ signal: 完成回复 + emotion 分析
  ▼
StorageService (QThread)
  │ 调用: ConversationRepository.append_message()
  ▼
Storage 层 (同步)
  │ 写入 SQLite
  ▼
信号回传 GUI
```

### 4.3 配置注入方式

```python
# 伪代码 — app.py 组合根（Stage 5 实现）
def main():
    # 1. 加载配置
    settings = ConfigStore().load()

    # 2. 构造 AI 层
    client = OllamaClient(
        settings.ollama.base_url,
        connect_timeout=settings.ollama.connect_timeout_seconds,
        read_timeout=settings.ollama.read_timeout_seconds,
    )
    engine = ChatEngine(
        client,
        model=settings.ollama.model,
        max_context_messages=settings.chat.max_context_messages,
        max_context_chars=settings.chat.max_context_chars,
        system_prompt=settings.chat.system_prompt,
        options={"num_ctx": settings.ollama.num_ctx, "temperature": settings.ollama.temperature},
        think=settings.ollama.think,
    )

    # 3. 构造 Storage 层
    db_path = default_app_data_dir() / "emowall.db"
    db = Database(db_path)
    repo = ConversationRepository(db)

    # 4. 注入到 GUI
    app = QApplication(...)
    window = MainWindow(engine=engine, repo=repo, settings=settings)
    window.show()
    app.exec()

    # 5. 清理
    client.close()
    db.close()
```

---

## 5. 错误处理约定

### 5.1 异常层级总览

```
Exception
├── AIError                          # Stage 2 (frozen)
│   ├── OllamaUnavailableError
│   │   ├── OllamaConnectionError
│   │   ├── OllamaTimeoutError
│   │   └── OllamaHTTPError
│   ├── ModelNotFoundError
│   ├── ProtocolError
│   │   └── StreamInterruptedError
│   └── CancelledError
├── ConfigError                      # Stage 1 (frozen)
│   ├── ConfigValidationError
│   └── ConfigIOError
├── StorageError                     # Stage 3 (proposed)
│   ├── StorageConnectionError
│   ├── StorageIntegrityError
│   └── StorageIOError
└── EmotionError                     # Stage 4 (future, TBD)
```

### 5.2 错误映射

异常映射按**发生阶段**区分。同一种 `sqlite3` 异常在不同阶段映射为不同的 `StorageError` 子类。

#### 5.2.1 连接阶段（`Database.__init__`）

`Database.__init__` 期间发生的所有 SQLite 错误统一映射为 `StorageConnectionError`：

| SQLite 原始异常 | Storage 异常 | 典型场景 |
|-----------------|-------------|----------|
| `sqlite3.OperationalError` | `StorageConnectionError` | 目录不可创建、文件被锁定、权限不足 |
| `sqlite3.DatabaseError` | `StorageConnectionError` | 数据库文件损坏、格式不兼容 |
| `OSError`（文件系统层） | `StorageConnectionError` | 路径无效、磁盘不可达 |

#### 5.2.2 操作阶段（`ConversationRepository` 方法）

Repository 方法运行期间的 SQLite 错误按类型映射：

| SQLite 原始异常 | Storage 异常 | 典型场景 |
|-----------------|-------------|----------|
| `sqlite3.IntegrityError` | `StorageIntegrityError` | 外键约束（conversation_id 不存在）、唯一约束 |
| `sqlite3.OperationalError` | `StorageIOError` | 磁盘满、WAL 写失败、busy_timeout 超时 |
| `sqlite3.DatabaseError` | `StorageIOError` | 通用数据库错误 |
| `OSError`（文件系统层） | `StorageIOError` | 运行时磁盘满（`ENOSPC`）、文件系统 I/O 错误（区别于 `sqlite3.OperationalError`） |

#### 5.2.3 不捕获的异常

以下异常**不做映射**，直接向上抛出（属于编程错误，不应被吞掉）：

| 异常 | 场景 | 说明 |
|------|------|------|
| `sqlite3.ProgrammingError` | 关闭后使用连接、跨线程使用 | 调用方修复线程归属或生命周期 |
| `sqlite3.InterfaceError` | 连接内部状态损坏、参数绑定失败 | 与 `ProgrammingError` 同属编程错误，调用方修复 API 用法 |
| `ValueError` / `TypeError` | 参数校验失败 | 调用方修复参数 |

#### 5.2.4 异常链保留

**所有 `StorageError` 子类必须保留原始异常作为 `__cause__`。**

```python
# 示例：Repository 中的映射模式
try:
    cursor.execute(sql, params)
except sqlite3.IntegrityError as exc:
    raise StorageIntegrityError(f"外键约束失败：{conversation_id}") from exc
except sqlite3.OperationalError as exc:
    raise StorageIOError(f"数据库操作失败：{exc}") from exc
```

调用方可通过 `exc.__cause__` 访问原始 SQLite 异常，便于调试和日志记录。

#### 5.2.5 可测试性

以上映射规则均可通过自动化测试验证：

| 测试场景 | 预期 |
|----------|------|
| `Database("/不存在的路径/abc/db.sqlite")` | 抛 `StorageConnectionError`，`__cause__` 是 `sqlite3.OperationalError` |
| `repo.append_message("不存在的UUID", ...)` | 抛 `StorageIntegrityError`，`__cause__` 是 `sqlite3.IntegrityError` |
| 磁盘满时写入 | 抛 `StorageIOError`，`__cause__` 是 `sqlite3.OperationalError` |
| `db.close()` 后再调用 `repo.create(...)` | 抛 `sqlite3.ProgrammingError`（不映射） |

### 5.3 错误传播规则

1. `emowall/storage` **不**捕获 `AIError` 或 `ConfigError`
2. `emowall/storage` 只抛出 `StorageError` 及其子类
3. 组合根（`app.py`）负责决定如何展示不同类型的错误
4. 日志使用 `emowall.storage` 命名空间

---

## 6. 兼容性要求

### 6.1 向后兼容

Stage 3 冻结后，后续阶段必须保证：

1. 不删除 `__all__` 中已有的导出符号
2. 不重命名已有符号
3. 不改变已有方法的签名（参数名、参数顺序、返回类型）
4. 不改变已有数据模型的字段名或类型
5. 不改变异常层级的继承关系

### 6.2 向前兼容

为未来阶段预留的扩展点：

1. `MessageRecord.emotion` 和 `emotion_intensity` 字段（为 Stage 4 预留）
2. `Database.schema_version` 属性（为未来迁移预留）
3. `StorageError` 基类（为未来新增子类预留）
4. `Conversation` 和 `MessageRecord` 的 `frozen=True`（保证不可变性）

### 6.3 版本迁移

- 当前 schema 版本：`1`
- 迁移函数表：暂为空
- 升级路径：按 `PRAGMA user_version` 逐级迁移

---

## 7. 冻结验收清单

### 7.1 架构兼容性

- [ ] `emowall/storage` 不 import `emowall/ai`
- [ ] `emowall/storage` 不 import `emowall/config`
- [ ] `emowall/storage` 不 import `emowall/emotion`
- [ ] `emowall/storage` 不 import `emowall/gui`
- [ ] `emowall/storage` 不 import `emowall/app`
- [ ] `emowall/storage` 不 import `PySide6`
- [ ] `emowall/storage` 不 import `httpx`
- [ ] `tests/test_architecture.py` 全部通过

### 7.2 接口完整性

- [ ] `Database.__init__`, `.close()`, `.schema_version` 已定义
- [ ] `Database` 支持上下文管理器
- [ ] `ConversationRepository` 的所有 8 个方法已定义（含 1 个预留接口 `update_message_emotion`）
- [ ] `Conversation` 和 `MessageRecord` 已定义为 `frozen=True` dataclass
- [ ] `StorageError` 异常层级已定义（含 3 个子类）
- [ ] `__init__.py` 的 `__all__` 包含所有公共符号

### 7.3 类型安全

- [ ] 所有公共方法有完整类型标注
- [ ] `from __future__ import annotations` 在每个文件头部
- [ ] 参数约束有文档字符串说明
- [ ] 返回值类型明确

### 7.4 线程安全

- [ ] `Database` 不创建线程
- [ ] `Database` 不加锁
- [ ] `check_same_thread=True` 保留（默认）
- [ ] `ConversationRepository` 不创建线程
- [ ] `ConversationRepository` 不加锁
- [ ] 跨线程使用抛 `ProgrammingError` 的测试通过

### 7.5 测试覆盖

- [ ] `tests/test_storage.py` ≥ 15 个用例
- [ ] 首次打开自动建库建表
- [ ] 会话 CRUD 往返测试
- [ ] 消息追加与读取测试
- [ ] 级联删除测试
- [ ] 标题自动生成测试
- [ ] emotion 字段 NULL 往返测试
- [ ] list_recent 排序测试
- [ ] 并发测试（两个连接交替读写）
- [ ] 跨线程检测测试

#### 7.5.1 标题截断策略测试（M1）

- [ ] `create(title="")` → 标题为 "新会话"
- [ ] `create(title="   ")` → 标题为 "新会话"（纯空白）
- [ ] `create(title="短标题")` → 标题为 "短标题"
- [ ] `create(title="a" * 20)` → 标题为 "a" * 20（恰好 20 字符）
- [ ] `create(title="a" * 21)` → 标题为 "a" * 17 + "..."
- [ ] `append_message()` 第一条用户消息自动生成标题（≤ 20 字符）
- [ ] `append_message()` 非第一条用户消息不触发自动标题
- [ ] `rename()` 使用相同的截断规则

#### 7.5.2 异常映射测试（M2）

- [ ] `Database("/无效路径/abc/db.sqlite")` 抛 `StorageConnectionError`，`__cause__` 是 `sqlite3.OperationalError`
- [ ] `repo.append_message("不存在的uuid", ...)` 抛 `StorageIntegrityError`，`__cause__` 是 `sqlite3.IntegrityError`
- [ ] 磁盘满模拟写入抛 `StorageIOError`，`__cause__` 是 `sqlite3.OperationalError`
- [ ] `db.close()` 后再调用 `repo.create(...)` 抛 `sqlite3.ProgrammingError`（不映射）

#### 7.5.3 预留接口测试（M3）

- [ ] `update_message_emotion(message_id, emotion="happy", emotion_intensity=0.8)` 返回更新后的 `MessageRecord`
- [ ] `update_message_emotion(999999, ...)` 抛 `StorageIntegrityError`（消息不存在）
- [ ] `update_message_emotion(1, emotion="", ...)` 抛 `ValueError`
- [ ] `update_message_emotion(1, emotion="   ", ...)` 抛 `ValueError`（纯空白）
- [ ] `update_message_emotion(1, emotion="happy", emotion_intensity=1.5)` 抛 `ValueError`
- [ ] 更新后再次 `list_messages()` 验证 emotion 字段已更新

#### 7.5.4 边界条件测试（Minor issues）

- [ ] `list_messages(conv_id, limit=0)` 抛 `ValueError`
- [ ] `list_messages(conv_id, limit=-1)` 抛 `ValueError`
- [ ] `append_message()` 返回的 `MessageRecord.id` 非 None
- [ ] `list_messages()` 对不存在的 conversation_id 返回空列表（不抛异常）

### 7.6 兼容性

- [ ] Stage 1 测试未减少
- [ ] Stage 2 测试未减少
- [ ] 架构守护测试未减少
- [ ] `$PY -m pytest` 全绿
- [ ] 已冻结的 AI/Config 接口未修改

### 7.7 文档

- [ ] 所有公共接口有 docstring
- [ ] 异常层级有设计说明
- [ ] 线程约束有明确说明
- [ ] 契约文档已同步

---

## 8. 阻塞问题与下一步建议

### 8.1 是否具备冻结条件

**初步评估：基本具备冻结条件，但有以下待确认事项。**

### 8.2 待确认事项

**已解决（独立审查后修订 v1.1）**：

| # | 事项 | 决定 | 文档位置 |
|---|------|------|----------|
| 3 | 标题自动生成时机 | `append_message()` 内，当 role == "user" 且该会话尚无 user 消息时触发 | §3.4 |
| 7 | `update_message_emotion()` | 预留接口，Stage 3 实现，Stage 4 消费 | §3.5 |
| — | 标题截断策略 | ≤ 20 字符；超长 → 前 17 + "..."；空/空白 → "新会话" | §3.4 |
| — | 异常映射规则 | 按阶段区分：连接阶段 → `StorageConnectionError`；操作阶段按类型映射 | §5.2 |
| — | `list_messages(limit <= 0)` | 抛 `ValueError` | §3.4 |
| — | `append_message()` 返回 id | 保证非 None | §3.4 |

**已由项目负责人确认**（2026-10-23）：

| # | 事项 | 决定 | 备注 |
|---|------|------|------|
| 1 | `Conversation.id` 使用 UUID v4 字符串 | ✅ 确认 | ARCHITECTURE.md §3.3 指定 |
| 2 | `MessageRecord.role` 使用 `str` 而非 `Role` | ✅ 确认 | storage 不 import ai；**Repository 必须校验合法角色值**（`ValueError`） |
| 4 | `Database` 支持上下文管理器 | ✅ 确认 | 良好实践 |
| 5 | `emotion` 字段存储枚举值还是名称 | ✅ 确认 | 存储 `.value`（如 `"happy"`） |
| 6 | `list_messages(limit=None)` 表示全部 | ✅ 确认 | ARCHITECTURE.md §3.3；**调用方应注意超长会话的内存风险**（见 §3.4 docstring） |

### 8.3 阻塞冻结的问题

**当前无硬性阻塞问题。**

所有待确认事项均为"可接受假设"，即使后续微调也不会影响：
- 依赖方向
- 线程模型
- 数据模型的核心字段
- 异常层级结构

### 8.4 下一步建议

1. **项目负责人审查**本文档和关联文档
2. **确认待确认事项**（§8.2 的 7 项）
3. **批准冻结**后，Storage Agent 开始实现
4. 实现过程中如需微调签名，按**接口变更申请流程**处理
5. 实现完成后，按**冻结验收清单**（§7）逐条验证

---

## 附录 A：签名速查表

### A.1 已冻结签名

```python
# --- emowall/ai ---
Role = Literal["system", "user", "assistant"]
ChatMessage(role: Role, content: str)
GenerationStats(eval_count, prompt_eval_count, total_duration_ms, load_duration_ms, done_reason)
ChatChunk(text: str, done: bool = False, stats: GenerationStats | None = None)
CancelToken(): cancel(), reset(), is_cancelled, raise_if_cancelled()
OllamaClient(base_url, *, connect_timeout, read_timeout, ...): version(), list_models(), stream_chat(), close()
ChatEngine(client, *, model, max_context_messages, ...): build_context(), stream_reply()

# --- emowall/config ---
OllamaSettings(base_url, model, connect_timeout_seconds, read_timeout_seconds, num_ctx, temperature, think)
ChatSettings(max_context_messages, max_context_chars, system_prompt)
AppSettings(ollama, chat)
ConfigStore(path): load(), save()
```

### A.2 拟定签名

```python
# --- emowall/storage ---
Conversation(id: str, title: str, model: str, created_at: str, updated_at: str)
MessageRecord(id: int | None, conversation_id: str, role: str, content: str,
              emotion: str | None, emotion_intensity: float | None, created_at: str)
Database(path: Path): close(), schema_version, __enter__(), __exit__()
ConversationRepository(db: Database):
    create(*, title, model) -> Conversation
    list_recent(limit=50) -> list[Conversation]
    get(conversation_id) -> Conversation | None
    rename(conversation_id, title) -> None
    delete(conversation_id) -> None
    append_message(conversation_id, *, role, content, emotion, emotion_intensity) -> MessageRecord
    list_messages(conversation_id, limit=None) -> list[MessageRecord]
    update_message_emotion(message_id, *, emotion, emotion_intensity) -> MessageRecord  # 预留

# 标题规则（create / rename / append_message 自动标题共用）
MAX_TITLE_CHARS = 20
def _normalize_title(raw: str) -> str:
    t = raw.strip()
    if not t: return "新会话"
    return t[:17] + "..." if len(t) > MAX_TITLE_CHARS else t

# Exceptions（所有 StorageError 保留 __cause__）
StorageError, StorageConnectionError, StorageIntegrityError, StorageIOError
```
