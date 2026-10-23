# Stage 3 接口契约 — 线程模型约定

> 版本：v1.2 最终草案（独立审查 PASS）
> 日期：2026-10-23
> 状态：**已通过审查**（待项目负责人宣布冻结）
> 依赖：AGENTS.md §2.2、`docs/ARCHITECTURE.md` §5、ADR-0002

---

## 1. 线程模型总览

```
┌──────────────────────────────────────────────────────────────┐
│                      主线程 (GUI Thread)                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ UI 事件循环   │  │ 信号/槽连接   │  │ UI 更新（追加文本、│  │
│  │              │  │              │  │ 滚动、按钮状态）   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
│        ▲                 ▲                    ▲              │
│        │ signal          │ signal             │ signal       │
│  ┌─────┴─────┐    ┌──────┴──────┐    ┌───────┴───────┐     │
│  │ChatWorker │    │StorageService│    │ 其他 Worker   │     │
│  │(QThread)  │    │ (QThread)    │    │ (未来扩展)    │     │
│  └─────┬─────┘    └──────┬──────┘    └───────────────┘     │
└────────┼──────────────────┼──────────────────────────────────┘
         │                  │
    ┌────┴────┐       ┌─────┴──────┐
    │ AI 层   │       │ Storage 层 │
    │ (同步)  │       │  (同步)    │
    │ OllamaC.│       │ Database   │
    │ ChatEng.│       │ Repository │
    └─────────┘       └────────────┘
```

---

## 2. 各层线程约束

### 2.1 `emowall/ai` — 同步核心（已实现，STABLE）

| 属性 | 约束 | 来源 |
|------|------|------|
| 线程创建 | **禁止** | AGENTS.md §2.2 |
| asyncio | **禁止** | AGENTS.md §2.1 |
| 锁 | 仅 `CancelToken` 内部使用 `threading.Lock` | 实现细节 |
| 阻塞操作 | 在调用线程上阻塞（HTTP 读取） | ADR-0002 §3 |
| 线程安全 | `CancelToken` 线程安全；`OllamaClient` 单路使用 | ADR-0002 §3 |
| 使用方式 | 由 GUI 工作线程（`QThread`）调用 | AGENTS.md §2.2 |

**Stage 3 不得改变这些约束。**

### 2.2 `emowall/config` — 单线程（已实现，STABLE）

| 属性 | 约束 | 来源 |
|------|------|------|
| 线程创建 | **禁止** | ADR-0001 |
| 锁 | **无** | 调用方保证单线程 |
| 使用方式 | 应用启动和保存时使用 | ADR-0001 |

**Stage 3 不得改变这些约束。**

### 2.3 `emowall/storage` — 同步、线程无关（Stage 3 拟定）

| 属性 | 约束 | 来源 |
|------|------|------|
| 线程创建 | **禁止** | AGENTS.md §2.2, ARCHITECTURE.md §5.1 |
| 锁 | **禁止**（线程归属由调用方保证） | AGENTS.md §3 |
| asyncio | **禁止** | 架构原则 |
| Qt | **禁止** | 架构原则 |
| `check_same_thread` | **保留默认 `True`** | AGENTS.md §2.2 |
| SQLite 连接 | 由调用方（DB 工作线程）独占使用 | AGENTS.md §2.2 |
| 事务 | 每次操作为短事务 | DEVELOPMENT_PLAN Stage 3 |
| `busy_timeout` | 2000 ms | DEVELOPMENT_PLAN Stage 3 |

**关键约束说明**：

1. **`storage` 层不创建线程**：线程封装在 GUI 层（`StorageService`，QThread）。
2. **`storage` 层不加锁**：SQLite 连接只在其所属线程使用，由 `check_same_thread=True` 保证。
3. **`storage` 层不知道 Qt**：不 import PySide6，不依赖信号/槽。
4. **跨线程使用**：主线程通过信号投递请求到 DB 工作线程，不直接调用 repository。

### 2.4 `emowall/emotion` — 纯函数（Stage 4 拟定）

| 属性 | 约束 | 来源 |
|------|------|------|
| 线程创建 | **禁止** | AGENTS.md §3 |
| I/O | **禁止** | AGENTS.md §3 |
| 锁 | **不需要**（纯函数，无状态） | 架构原则 |
| 确定性 | 同输入必同输出 | DEVELOPMENT_PLAN Stage 4 |

### 2.5 `emowall/gui` — 多线程编排（Stage 5 拟定）

| 属性 | 约束 | 来源 |
|------|------|------|
| 主线程 | 只做 UI 更新和事件处理 | AGENTS.md §2.2 |
| ChatWorker | `QThread`，执行 AI 生成 | ARCHITECTURE.md §5 |
| StorageService | `QThread`，独占 DB 连接 | ARCHITECTURE.md §5.1 |
| 信号/槽 | 跨线程通信的唯一方式 | Qt 线程模型 |

---

## 3. Stage 3 线程安全契约

### 3.1 `Database` 类

```python
class Database:
    """SQLite 数据库连接管理器。

    线程契约：
        - 连接在构造时创建，在 close() 时关闭
        - 连接只应在创建它的线程上使用（check_same_thread=True）
        - 多线程场景下，每个线程应创建自己的 Database 实例
        - Stage 5 由 StorageService（QThread）独占使用
    """
    def __init__(self, path: Path) -> None: ...
    def close(self) -> None: ...
    @property
    def schema_version(self) -> int: ...
```

**线程安全级别**：**线程绑定**（thread-confined）
- 连接不可跨线程共享
- 同一连接上的操作不需要额外同步
- 不同连接之间的并发由 SQLite WAL 模式 + `busy_timeout` 保证

### 3.2 `ConversationRepository` 类

```python
class ConversationRepository:
    """会话与消息的 CRUD 仓库。

    线程契约：
        - 继承 Database 的线程绑定约束
        - 不创建线程、不加锁
        - 每次操作是一个短事务（BEGIN ... COMMIT）
        - 调用方保证同一 Database 实例不并发使用
    """
    def __init__(self, db: Database) -> None: ...
```

**线程安全级别**：**线程绑定**（继承自 Database）

### 3.3 并发场景

| 场景 | 是否允许 | 说明 |
|------|----------|------|
| 同一连接，同一线程，顺序操作 | ✅ | 正常使用模式 |
| 同一连接，不同线程 | ❌ | `check_same_thread=True` 会抛 `ProgrammingError` |
| 不同连接，同一文件，不同线程 | ✅ | WAL 模式 + busy_timeout 保证 |
| 不同连接，同一文件，同一线程 | ✅ | 但通常不需要 |

### 3.4 错误处理与线程

| 错误 | 线程影响 | 处理方式 |
|------|----------|----------|
| `sqlite3.OperationalError`（busy） | 自动重试（busy_timeout） | 由 SQLite 处理 |
| `sqlite3.IntegrityError` | 事务回滚 | Repository 抛自定义异常 |
| `sqlite3.DatabaseError` | 连接可能不可用 | 需要重建连接 |
| `ProgrammingError`（跨线程） | 立即抛出 | 调用方修复线程归属 |

---

## 4. Stage 5 线程编排预览（不影响 Stage 3 契约）

以下描述 Stage 5 的预期使用方式，供 Stage 3 设计参考：

```python
# 伪代码 — Stage 5 的 StorageService
class StorageService(QObject):
    """DB 工作线程服务。"""

    # 信号定义
    conversation_created = Signal(Conversation)
    messages_loaded = Signal(list)  # list[MessageRecord]
    error_occurred = Signal(str)

    def __init__(self, db_path: Path):
        super().__init__()
        self._db_path = db_path
        self._db: Database | None = None
        self._repo: ConversationRepository | None = None

    @Slot()
    def initialize(self) -> None:
        """在 DB 线程的 run() 内调用。"""
        self._db = Database(self._db_path)
        self._repo = ConversationRepository(self._db)

    @Slot(str, str)  # title, model
    def create_conversation(self, title: str, model: str) -> None:
        """在 DB 线程上执行。"""
        try:
            conv = self._repo.create(title=title, model=model)
            self.conversation_created.emit(conv)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    @Slot()
    def shutdown(self) -> None:
        """在 DB 线程退出前调用。"""
        if self._db:
            self._db.close()
```

**关键点**：
- `Database` 在 DB 线程内创建和关闭
- 主线程从不直接调用 `_repo` 方法
- 所有交互通过信号/槽

---

## 5. CancelToken 与 DB 操作的交互

当前 `CancelToken` 仅用于取消 AI 生成。Stage 3 的 DB 操作**不受 CancelToken 影响**。

**取消生成后的 DB 行为**（Stage 5 实现）：
1. 用户点击取消 → `CancelToken.cancel()`
2. AI 生成器抛 `CancelledError`
3. ChatWorker 拼接已收到的部分内容
4. ChatWorker 通过信号投递到 StorageService
5. StorageService 把部分内容作为 `MessageRecord` 写入

**Stage 3 不需要实现上述逻辑**，只需保证：
- `append_message()` 可以在任何时刻被调用（无前置条件）
- 部分内容（甚至空串）可以正常存储

---

## 6. 测试方案

### 6.1 线程安全测试

| 测试项 | 预期 | 方法 |
|--------|------|------|
| `check_same_thread=True` | 跨线程使用抛 `ProgrammingError` | 构造连接后在另一线程调用 |
| WAL 并发 | 两个连接交替读写不报 `database is locked` | 两个线程各持一个连接 |
| `busy_timeout` | 2000 ms 等待 | 验证 PRAGMA 设置 |
| 短事务 | 操作完成后不持有锁 | 检查 WAL 状态 |

### 6.2 生命周期测试

| 测试项 | 预期 |
|--------|------|
| `Database(path)` → `close()` → 再次 `Database(path)` | 正常重开 |
| `close()` 后调用 repository | 抛 `ProgrammingError` 或自定义异常 |
| 未 `close()` 进程退出 | WAL 模式自动恢复 |
