# Stage 3 接口冻结 — 代码与架构调查报告

> 调查日期：2026-10-23
> 修订：v1.2 最终草案（独立审查 PASS；含标题策略、异常映射、预留接口、role 校验、list_messages 内存风险）
> 调查者：Lead Software Architect
> 调查范围：EmoWall AI V0.1 全部已实现代码、文档与测试
> 目的：为 Stage 3（SQLite 存储层）接口冻结提供事实依据

---

## 1. 项目当前状态总览

### 1.1 已实现模块

| 模块 | 阶段 | 状态 | 文件数 | 测试覆盖 |
|------|------|------|--------|----------|
| `emowall/config` | Stage 1 | ✅ 已完成 | 4 文件 | `test_config.py` + `test_ai_config.py` |
| `emowall/ai` | Stage 2 | ✅ 已完成（G1–G4 整改已复验） | 5 文件 | `test_ai_client.py` + `test_ai_engine.py` + `test_ai_config.py` + `test_ai_probe.py` + `test_ai_integration.py` |
| `emowall/storage` | Stage 3 | 🔲 仅骨架 `__init__.py` | 0 | 无 |
| `emowall/emotion` | Stage 4 | 🔲 仅骨架 `__init__.py` | 0 | 无 |
| `emowall/gui` | Stage 5 | 🔲 仅骨架 `__init__.py` | 0 | 无 |
| `emowall/app.py` | Stage 5 | ❌ 不存在 | — | — |

### 1.2 支撑设施

| 设施 | 状态 |
|------|------|
| `tests/conftest.py` | ✅ socket 守卫 + workdir fixture |
| `tests/test_architecture.py` | ✅ 分层/依赖/Qt 守护（22 例） |
| `tests/test_docs.py` | ✅ 文档一致性（34 例） |
| `scripts/chat_probe.py` | ✅ 命令行联调工具 |
| `scripts/check_env.py` | ✅ 环境检查脚本 |
| `AGENTS.md` | ✅ 长期开发规则 |
| `docs/ARCHITECTURE.md` | ✅ 架构设计（Stage 2 已定稿） |
| `docs/DEVELOPMENT_PLAN.md` | ✅ 分阶段计划（Stage 2 已复验） |
| ADR-0001 | ✅ 配置存储设计 |
| ADR-0002 | ✅ AI 核心边界与取消机制 |

---

## 2. 已实现的公共接口清单

### 2.1 `emowall/ai` — AI 核心层

**已实现，STABLE（Stage 2 整改已复验，不可修改）**

#### 数据模型 (`emowall/ai/models.py`)

| 类型 | 签名 | 约束 |
|------|------|------|
| `Role` | `Literal["system", "user", "assistant"]` | 类型别名 |
| `VALID_ROLES` | `frozenset[str]` | 常量 |
| `ChatMessage` | `@dataclass(frozen=True)` | `role: Role`, `content: str`；构造即校验 |
| `GenerationStats` | `@dataclass(frozen=True)` | 全 `Optional` 字段（毫秒统一） |
| `ChatChunk` | `@dataclass(frozen=True)` | `text: str`, `done: bool`, `stats: GenerationStats \| None` |

#### 传输客户端 (`emowall/ai/client.py`)

| 方法 | 签名 | 说明 |
|------|------|------|
| `OllamaClient.__init__` | `(base_url, *, connect_timeout, read_timeout, write_timeout, pool_timeout, client, transport)` | 自有或注入两种模式 |
| `OllamaClient.version()` | `→ str` | 同步 |
| `OllamaClient.list_models()` | `→ list[str]` | 同步 |
| `OllamaClient.stream_chat()` | `(*, model, messages, options, think, cancel) → Iterator[ChatChunk]` | 同步生成器 |
| `OllamaClient.close()` | `→ None` | 释放资源 |
| `DEFAULT_BASE_URL` | `str` | 常量 |

#### 对话引擎 (`emowall/ai/engine.py`)

| 方法 | 签名 | 说明 |
|------|------|------|
| `ChatEngine.__init__` | `(client, *, model, max_context_messages, max_context_chars, system_prompt, options, think)` | 无状态 |
| `ChatEngine.build_context()` | `(history) → list[ChatMessage]` | 确定性裁剪 |
| `ChatEngine.stream_reply()` | `(history, *, cancel) → Iterator[ChatChunk]` | 裁剪后调用客户端 |

#### 取消令牌 (`emowall/ai/cancel.py`)

| 方法 | 签名 | 说明 |
|------|------|------|
| `CancelToken.__init__` | `()` | 线程安全 |
| `CancelToken.cancel()` | `→ None` | 幂等 |
| `CancelToken.reset()` | `→ None` | 活动态禁止 |
| `CancelToken.is_cancelled` | `→ bool` | 属性 |
| `CancelToken.raise_if_cancelled()` | `→ None` | 或抛 `CancelledError` |

#### 异常层级 (`emowall/ai/errors.py`)

```
AIError
├── OllamaUnavailableError
│   ├── OllamaConnectionError
│   ├── OllamaTimeoutError
│   └── OllamaHTTPError（status_code）
├── ModelNotFoundError
├── ProtocolError
│   └── StreamInterruptedError
└── CancelledError
```

### 2.2 `emowall/config` — 配置系统层

**已实现，STABLE（Stage 1 已完成，不可修改）**

#### 数据模型 (`emowall/config/settings.py`)

| 类型 | 字段 | 默认值 |
|------|------|--------|
| `OllamaSettings` | `base_url, model, connect_timeout_seconds, read_timeout_seconds, num_ctx, temperature, think` | `"http://127.0.0.1:11434"`, `"qwen3:8b"`, 5.0, 120.0, 8192, 0.7, False |
| `ChatSettings` | `max_context_messages, max_context_chars, system_prompt` | 20, 6000, 默认提示 |
| `AppSettings` | `ollama, chat` | `OllamaSettings()`, `ChatSettings()` |

#### 存储 (`emowall/config/store.py`)

| 方法 | 签名 | 说明 |
|------|------|------|
| `ConfigStore.__init__` | `(path: Path \| None)` | 默认 `config_path()` |
| `ConfigStore.load()` | `→ AppSettings` | 缺失/损坏均降级默认值 |
| `ConfigStore.save()` | `(settings) → None` | 原子写入 |

#### 路径 (`emowall/config/paths.py`)

| 函数 | 签名 | 说明 |
|------|------|------|
| `default_app_data_dir()` | `→ Path` | `%APPDATA%\EmoWall` 或 `EMOWALL_HOME` |
| `config_path()` | `(base_dir: Path \| None) → Path` | 配置文件路径 |

#### 异常层级 (`emowall/config/errors.py`)

```
ConfigError
├── ConfigValidationError
└── ConfigIOError
```

### 2.3 已实现接口兼容性约束

Stage 3 **不得**修改上述任何公共接口。具体而言：

1. 不得在 `emowall/ai/__init__.py` 的 `__all__` 中删除或重命名任何导出。
2. 不得在 `emowall/config/__init__.py` 的 `__all__` 中删除或重命名任何导出。
3. 不得修改 `ChatMessage`、`ChatChunk`、`GenerationStats` 的字段或类型。
4. 不得修改 `OllamaSettings`、`ChatSettings`、`AppSettings` 的字段或类型。
5. 不得修改异常层级的继承关系或类名。

---

## 3. Stage 3 计划实现的模块

根据 `docs/DEVELOPMENT_PLAN.md` Stage 3 的描述：

### 3.1 计划交付物

| 文件 | 职责 |
|------|------|
| `emowall/storage/database.py` | 连接、PRAGMA、建表、`user_version` 迁移 |
| `emowall/storage/models.py` | `Conversation`, `MessageRecord` 数据类 |
| `emowall/storage/repository.py` | `ConversationRepository` CRUD 操作 |
| `tests/test_storage.py` | ≥ 15 个用例，临时目录 DB |

### 3.2 架构契约草案（来自 ARCHITECTURE.md §3.3）

```python
@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    model: str
    created_at: str   # ISO-8601 UTC
    updated_at: str

@dataclass(frozen=True)
class MessageRecord:
    id: int | None
    conversation_id: str
    role: str
    content: str
    emotion: str | None
    emotion_intensity: float | None
    created_at: str

class Database:
    def __init__(self, path: Path) -> None: ...
    def close(self) -> None: ...
    @property
    def schema_version(self) -> int: ...

class ConversationRepository:
    def create(self, *, title: str, model: str) -> Conversation: ...
    def list_recent(self, limit: int = 50) -> list[Conversation]: ...
    def get(self, conversation_id: str) -> Conversation | None: ...
    def rename(self, conversation_id: str, title: str) -> None: ...
    def delete(self, conversation_id: str) -> None: ...
    def append_message(self, conversation_id: str, *, role: str, content: str,
                       emotion: str | None = None,
                       emotion_intensity: float | None = None) -> MessageRecord: ...
    def list_messages(self, conversation_id: str,
                      limit: int | None = None) -> list[MessageRecord]: ...
```

### 3.3 技术要点（来自 DEVELOPMENT_PLAN.md）

- `storage` 同步、线程无关：不建线程、不加锁、不依赖 Qt
- 每次操作短事务，`busy_timeout=2000`
- 保留 `check_same_thread=True`：连接只在其所属线程使用
- WAL + `foreign_keys=ON`
- 时间 UTC ISO-8601；会话 `updated_at` 在追加消息时更新
- 删除会话级联删除消息；`list_messages` 按 `id` 正序
- 同一会话第 1 条用户消息自动生成标题（≤ 20 字），空内容回退为「新会话」

### 3.4 Stage 3 产生的跨模块调用

Stage 3 本身只实现 `emowall/storage`，**不会**直接调用其他层。但会产生以下跨模块依赖：

| 方向 | 接口 | 说明 |
|------|------|------|
| 组合根 → storage | `Database(path)`, `ConversationRepository(db)` | 构造与注入 |
| gui → storage | 通过 `StorageService`（QThread）间接调用 | Stage 5 实现 |
| storage ← emotion | `MessageRecord.emotion` 字段存储情绪名称 | Stage 4 产出，Stage 3 预留字段 |
| storage ← ai | `MessageRecord.role` 与 `ChatMessage.role` 对应 | 组合根做映射 |

---

## 4. 已有线程与异步约束

### 4.1 当前线程模型

| 层 | 线程约束 | 来源 |
|---|---|---|
| `ai` | 同步核心，不创建线程，不使用 asyncio | AGENTS.md §2.2, ADR-0002 |
| `config` | 单线程使用（调用方保证），不加锁 | ADR-0001 |
| `storage`（计划） | 同步、线程无关；连接由 DB 工作线程独占 | AGENTS.md §2.2, ARCHITECTURE.md §5.1 |
| `gui`（计划） | 主线程 UI + ChatWorker（QThread）+ StorageService（QThread） | ARCHITECTURE.md §5 |

### 4.2 CancelToken 线程安全

`CancelToken` 已经是线程安全的：
- 使用 `threading.Event` + `threading.Lock`
- 支持跨线程取消
- `reset()` 在生成器未退出时抛 `RuntimeError`

### 4.3 未来 DB 工作线程（Stage 5）

- SQLite 连接由 `StorageService`（QThread）的 `run()` 方法内创建
- 保留 `check_same_thread=True`
- 主线程通过信号投递读写请求，不直接调用 repository

---

## 5. 已经存在的测试契约

### 5.1 架构守护测试 (`tests/test_architecture.py`)

守护的规则（22 例）：
1. ai / config / storage / emotion 四层互不 import
2. 四层不 import gui / app
3. 只有 gui 和 app.py 可 import PySide6
4. ai 层只依赖标准库 + httpx（禁止 sqlite3、asyncio）
5. config / storage / emotion 层只依赖标准库
6. `__init__.py` 不拉起 GUI

**Stage 3 影响**：新增 storage 代码必须通过这些测试。`test_architecture.py` 中已包含对 `emowall/storage` 的扫描规则。

### 5.2 网络隔离 (`tests/conftest.py`)

- `block_real_network` fixture 默认拦截所有 socket 连接
- `integration` / `local_network` 标记的用例例外
- Stage 3 测试**不需要**网络，全部离线

### 5.3 已有测试数量

| 测试文件 | 用例数（约） | 说明 |
|----------|------------|------|
| `test_config.py` | ~30 | 配置系统 |
| `test_ai_client.py` | ~79 | AI 传输层 |
| `test_ai_engine.py` | ~35 | 对话引擎 |
| `test_ai_config.py` | ~6 | AI-配置交叉 |
| `test_ai_probe.py` | ~3 | 探针测试 |
| `test_ai_integration.py` | ~10 | 真实 Ollama（integration 标记） |
| `test_architecture.py` | ~22 | 架构守护 |
| `test_docs.py` | ~34 | 文档一致性 |
| `test_package.py` | ~2 | 包基础 |
| `test_pytest_config.py` | ~3 | pytest 配置 |
| `test_check_env.py` | ~4 | 环境检查 |
| **总计** | **~228** | 默认离线 ~244 passed / 1 skipped / 10 deselected |

---

## 6. 待确认事项

### 6.1 已解决（v1.1 修订）

| # | 事项 | 决定 | 文档位置 |
|---|------|------|----------|
| 3 | 标题自动生成时机 | `append_message()` 内，当 role=="user" 且会话尚无 user 消息时触发 | stage3-contract §3.4 |
| 7 | `update_message_emotion()` | 预留接口，Stage 3 实现、Stage 4 消费 | stage3-contract §3.5 |

### 6.2 仍待确认

| # | 事项 | 当前假设 | 待谁确认 |
|---|------|----------|----------|
| 1 | `Conversation.id` 使用 `str`（UUID）而非 `int` | ARCHITECTURE.md §3.3 指定为 `str` | 项目负责人 |
| 2 | `MessageRecord.role` 使用 `str` 而非 `Role` 类型别名 | ARCHITECTURE.md §3.3 指定为 `str`；storage 不 import ai | 项目负责人 |
| 4 | `Database` 是否需要 `__enter__`/`__exit__` 上下文管理器 | 已纳入契约（§3.3） | 项目负责人 |
| 5 | `emotion` 字段值的来源约定（Stage 4 的 `Emotion.value` 还是 `Emotion.name`） | 预留 `str \| None`，Stage 4 定义后由组合根映射 | Stage 4 实现时确认 |
| 6 | `list_messages` 的 `limit` 语义：None 表示全部 | 已纳入契约（§3.4） | 项目负责人 |

---

## 7. 权限问题诊断报告

### 7.1 问题现象

运行 `pwsh` 命令时出现错误：
```
Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\emowall-stage3\featurestage3)
```

### 7.2 分析

- Win32 错误码 5 = `ERROR_ACCESS_DENIED`
- 发生在 DSH 沙箱尝试对工作区授予写权限时（`SetNamedSecurityInfoW`）
- 这是沙箱初始化阶段的问题，不是具体文件操作的问题
- 可能的原因：
  1. 工作区位于 OneDrive 同步目录，ACL 被 OneDrive 修改
  2. 父目录的权限继承链中有缺失的 `WRITE_DAC` 或 `WRITE_OWNER` 权限
  3. 存在 AppContainer 包 ACE（`S-1-15-2-*`）冲突

### 7.3 最小修复方案

使用 `diagnose-windows-sandbox-acl` 技能中的诊断脚本修复 ACL 问题。该脚本会：
1. 检查 `D:\emowall-stage3\featurestage3` 及其所有父目录
2. 在缺少必要权限的目录上为当前用户添加完全控制权限
3. 移除可能导致冲突的 AppContainer 包 ACE
4. 每次修改前备份，修改后验证

**此修复不修改 Git 仓库配置、不修改任何文件内容、不修改文件所有权。**

### 7.4 当前工作状态

尽管 pwsh 命令受限，但文件系统工具（`read`、`write`、`glob`、`grep`）工作正常。
本次架构调查**全部使用只读文件系统工具完成**，未受权限问题影响。
契约文档创建使用 `write` 工具，预计不受影响（沙箱对 workspace 内写入允许）。

---

## 8. 结论

1. **Stage 1（config）和 Stage 2（ai）的公共接口已稳定**，经过整改复验，有完善的测试守护。
2. **Stage 3（storage）的接口设计已在 ARCHITECTURE.md §3.3 中有草案**，可作为冻结基础。
3. **storage 层是叶子层**，不 import 其他层，也不被其他已实现层 import。冻结其接口的风险较低。
4. **Stage 3 的冻结主要影响 Stage 5（GUI）和组合根**，它们是 storage 的消费者。
5. **已有架构守护测试会自动检测 storage 层的依赖违规**，为冻结提供运行时保障。
