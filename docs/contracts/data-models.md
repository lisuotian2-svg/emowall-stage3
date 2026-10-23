# Stage 3 接口契约 — 数据模型约定

> 版本：v1.2 最终草案
> 日期：2026-10-23
> 状态：**待最终复审**（未冻结）
> 依赖：`docs/ARCHITECTURE.md` §3.1 / §3.3、ADR-0001、ADR-0002

---

## 1. 数据模型分层原则

### 1.1 核心原则

**每层使用自己的数据结构（dataclass），由组合根做映射。**

这条原则来自 AGENTS.md §3 和 ARCHITECTURE.md §2：
- `ai / config / storage / emotion` 四层互不 import
- 每层的数据模型只包含本层关心的概念
- 跨层数据转换由 `emowall/app.py`（组合根）负责

### 1.2 为什么不让 storage 依赖 ai 的数据类

| 理由 | 说明 |
|------|------|
| 架构隔离 | `storage` 不知道 AI 的存在，可以被替换或迁移 |
| 独立测试 | storage 测试不需要构造 AI 层对象 |
| 演进自由 | AI 层可以改变消息格式（如多模态），storage 只需调整映射 |
| 迁移友好 | 主项目可以直接复用 storage 而不需要 AI 层 |

---

## 2. 已冻结的数据模型（Stage 1 & Stage 2）

### 2.1 AI 层数据模型 — STABLE

**定义位置**：`emowall/ai/models.py`
**负责模块**：`emowall/ai`
**使用模块**：`emowall/gui`（Stage 5）、`emowall/app.py`（Stage 5）

```python
Role = Literal["system", "user", "assistant"]

@dataclass(frozen=True)
class ChatMessage:
    role: Role           # "system" | "user" | "assistant"
    content: str         # 消息文本，可为空串

@dataclass(frozen=True)
class GenerationStats:
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    total_duration_ms: int | None = None
    load_duration_ms: int | None = None
    done_reason: str | None = None

@dataclass(frozen=True)
class ChatChunk:
    text: str            # 增量文本
    done: bool = False   # 是否为最后一块
    stats: GenerationStats | None = None
```

**约束**：
- `ChatMessage.role` 只能是 `"system"` / `"user"` / `"assistant"`
- `ChatMessage.content` 必须是 `str`（含空串）
- `ChatChunk.text` 必须是 `str`
- 所有类型均为 `frozen=True`，构造后不可变

**兼容性**：Stage 3 不得修改这些类型。

### 2.2 配置层数据模型 — STABLE

**定义位置**：`emowall/config/settings.py`
**负责模块**：`emowall/config`
**使用模块**：`emowall/app.py`（Stage 5）

```python
@dataclass(frozen=True)
class OllamaSettings:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 120.0
    num_ctx: int = 8192
    temperature: float = 0.7
    think: bool = False

@dataclass(frozen=True)
class ChatSettings:
    max_context_messages: int = 20
    max_context_chars: int = 6000
    system_prompt: str = "你是 EmoWall 的 AI 伙伴，回答简洁、自然、有情绪温度。"

@dataclass(frozen=True)
class AppSettings:
    ollama: OllamaSettings
    chat: ChatSettings
```

**约束**：
- 构造即校验：非法值抛 `ConfigValidationError`
- `OllamaSettings.base_url` 必须是 http/https 地址
- `OllamaSettings.model` 不能为空
- `OllamaSettings.num_ctx` ∈ [1024, 1048576]
- `OllamaSettings.temperature` ∈ [0, 2]

**兼容性**：Stage 3 不得修改这些类型。

---

## 3. Stage 3 拟定数据模型

### 3.1 会话 (`Conversation`) — 拟定契约

**定义位置**：`emowall/storage/models.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/gui`（Stage 5）、`emowall/app.py`（Stage 5）

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Conversation:
    """一个对话会话的元数据。"""
    id: str              # UUID v4 字符串
    title: str           # 会话标题（≤ 20 字符，自动生成或用户指定）
    model: str           # 使用的模型名（如 "qwen3:8b"）
    created_at: str      # ISO-8601 UTC 创建时间
    updated_at: str      # ISO-8601 UTC 最后更新时间
```

**输入约束**：
- `id`：UUID v4 格式，由 `create()` 内部生成
- `title`：保证非空且 ≤ 20 个 Python 字符（`len()` 计数）；由 Repository 方法归一化：
  1. `strip()` 去除首尾空白
  2. 空串或纯空白 → `"新会话"`
  3. `len > 20` → `title[:17] + "..."`（恰好 20 字符）
  4. 否则原样使用
- `model`：非空字符串
- `created_at` / `updated_at`：ISO-8601 UTC 格式（`"2026-10-23T14:30:00Z"`）

**输出约束**：
- `frozen=True`：构造后不可变
- 从数据库读取时，`updated_at` 反映最后一次 `append_message()` 的时间
- `title` 从数据库读出时**始终非空**（Repository 在写入时已归一化）

**与 AI 层的关系**：
- `Conversation.model` 存储模型名，与 `OllamaSettings.model` 类型一致
- 不做模型有效性验证（由组合根在创建时传入合法值）

### 3.2 消息记录 (`MessageRecord`) — 拟定契约

**定义位置**：`emowall/storage/models.py`（待创建）
**负责模块**：`emowall/storage`
**使用模块**：`emowall/gui`（Stage 5）、`emowall/app.py`（Stage 5）

```python
@dataclass(frozen=True)
class MessageRecord:
    """一条持久化的消息记录。"""
    id: int | None                       # 行 ID（新建时为 None，读库后填充）
    conversation_id: str                 # 所属会话 UUID
    role: str                            # "system" | "user" | "assistant"
    content: str                         # 消息文本
    emotion: str | None                  # 情绪标签名称（如 "happy"），Stage 4 产出
    emotion_intensity: float | None      # 情绪强度 [0.0, 1.0]，Stage 4 产出
    created_at: str                      # ISO-8601 UTC
```

**输入约束**：
- `id`：由数据库自动生成（AUTOINCREMENT），构造时传 `None`；**Repository 方法返回的 MessageRecord 保证 id 非 None**
- `conversation_id`：必须是已存在的会话 UUID（外键约束）
- `role`：字符串，取值 `"system"` / `"user"` / `"assistant"`
  - **注意**：使用 `str` 而非 `emowall.ai.models.Role`，因为 storage 不 import ai
- `content`：字符串，可为空串
- `emotion`：`str | None`；为 `None` 表示尚未分析情绪；非 `None` 时存储情绪名称字符串
  - Stage 4 的 `Emotion` 枚举值（如 `Emotion.HAPPY.value` = `"happy"`）由组合根映射到此字段
- `emotion_intensity`：`float | None`；为 `None` 表示未分析；非 `None` 时 ∈ [0.0, 1.0]
- `created_at`：ISO-8601 UTC 格式

**输出约束**：
- `frozen=True`：构造后不可变
- `list_messages()` 按 `id` 正序返回

**与 AI 层的关系**：
- `MessageRecord.role` ↔ `ChatMessage.role`：值域相同但类型不同（`str` vs `Literal`）
- 组合根负责在 `ChatMessage` → `MessageRecord` 时传入 `role` 字符串
- 组合根负责在 `MessageRecord` → `ChatMessage` 时做 `Role` 类型校验

**与情绪层的关系**：
- `MessageRecord.emotion` ↔ `EmotionResult.emotion.value`（Stage 4）
- `MessageRecord.emotion_intensity` ↔ `EmotionResult.intensity`（Stage 4）
- 两个字段均为 `None`-able，支持"先存消息、后分析情绪"和"不分析情绪"两种场景

### 3.3 数据库表结构 — 拟定契约

```sql
-- conversations 表
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL,  -- ISO-8601 UTC
    updated_at  TEXT NOT NULL   -- ISO-8601 UTC
);

-- messages 表
CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id     TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role                TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
    content             TEXT NOT NULL,
    emotion             TEXT,               -- NULL 或情绪名称
    emotion_intensity   REAL CHECK(emotion_intensity IS NULL OR (emotion_intensity >= 0.0 AND emotion_intensity <= 1.0)),
    created_at          TEXT NOT NULL       -- ISO-8601 UTC
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
```

**PRAGMA 设置**：
```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 2000;
```

**迁移策略**：
- `PRAGMA user_version` 跟踪 schema 版本
- 当前版本：`1`
- 迁移函数表暂为空；未来升级时按版本逐级迁移

---

## 4. 跨模块数据映射约定

### 4.1 AI ↔ Storage 映射

| AI 层类型 | Storage 层类型 | 映射方向 | 映射责任方 |
|----------|---------------|----------|-----------|
| `ChatMessage` | `MessageRecord` | 双向 | 组合根 (`app.py`) |
| `ChatMessage.role` | `MessageRecord.role` | 值相同 | 直接传递字符串 |
| `ChatMessage.content` | `MessageRecord.content` | 值相同 | 直接传递字符串 |
| — | `MessageRecord.emotion` | Stage 4 产出 | 组合根调用 emotion 后写入 |
| — | `MessageRecord.emotion_intensity` | Stage 4 产出 | 组合根调用 emotion 后写入 |

### 4.2 Emotion ↔ Storage 映射（Stage 4 实现，Stage 3 预留接口）

| Emotion 层类型 | Storage 层字段 / 方法 | 映射说明 |
|---------------|----------------------|----------|
| `Emotion.value`（如 `"happy"`） | `MessageRecord.emotion` | 枚举值 → 字符串 |
| `EmotionResult.intensity` | `MessageRecord.emotion_intensity` | 直接传递 float |
| `EmotionResult` | `update_message_emotion(id, emotion=..., emotion_intensity=...)` | 组合根调用，Stage 3 实现 |

**数据流**：

```
AI 回复文本
  → EmotionDetector.detect(text) → EmotionResult
  → 组合根提取 .emotion.value 和 .intensity
  → repo.update_message_emotion(message_id, emotion=result.emotion.value,
                                  emotion_intensity=result.intensity)
  → MessageRecord.emotion / emotion_intensity 已更新
```

### 4.3 Config → Storage 映射

| Config 层类型 | Storage 层用途 | 映射说明 |
|--------------|---------------|----------|
| `OllamaSettings.model` | `Conversation.model` | 创建会话时传入 |
| `default_app_data_dir()` | `Database` 路径 | 数据库文件位于配置目录 |

---

## 5. 数据不变性约束

| 约束 | 说明 | 执行层 |
|------|------|--------|
| `frozen=True` | 所有数据类不可变 | Python dataclass |
| 外键级联删除 | 删除会话自动删除消息 | SQLite `ON DELETE CASCADE` |
| `updated_at` 自动更新 | `append_message()` 时更新 | Repository 实现 |
| `id` 自增 | 消息 ID 由 SQLite 生成 | SQLite `AUTOINCREMENT` |
| `conversation_id` UUID | 会话 ID 由 Repository 生成 | Python `uuid.uuid4()` |
| `title` 非空且 ≤ 20 字符 | 所有写入路径统一归一化 | Repository `_normalize_title()` |
| `MessageRecord.id` 非 None | Repository 返回时保证 | SQLite AUTOINCREMENT |

### 5.1 标题归一化规则（统一实现）

所有涉及标题写入的 Repository 方法（`create()`, `rename()`, `append_message()` 自动标题）共用同一归一化函数：

```python
MAX_TITLE_CHARS = 20

def _normalize_title(raw: str) -> str:
    """统一的标题归一化：strip → 空白回退 → 超长截断。"""
    t = raw.strip()
    if not t:
        return "新会话"
    if len(t) > MAX_TITLE_CHARS:
        return t[:17] + "..."
    return t
```

**截断示例**：

| 输入 | 输出 |
|------|------|
| `""` | `"新会话"` |
| `"   "` | `"新会话"` |
| `"你好"` | `"你好"` |
| `"a" * 20` | `"a" * 20`（恰好 20） |
| `"a" * 21` | `"a" * 17 + "..."` |
| `"Hello World, how are you?"` (25 chars) | `"Hello World, how ..."` |

**`append_message()` 自动标题触发条件**：
- `role == "user"` **且** 该会话尚无 `role == "user"` 的消息
- 使用 `content` 经 `_normalize_title()` 处理后写入 `Conversation.title`
- 与消息写入在**同一事务**内

---

## 6. 数据模型变更规则

1. **已冻结模型**（Stage 1/2）：不得修改，除非经过完整的接口变更申请流程。
2. **拟定模型**（Stage 3）：在 Stage 3 实现过程中可微调签名，但**依赖方向、字段语义、不可变性**不可变。
3. **新增字段**：未来阶段如需新增字段，通过 `PRAGMA user_version` 迁移，不修改已有字段。
4. **删除字段**：不得删除已有字段，只能标记为废弃。

---

## 7. 测试方案

### 7.1 数据模型测试

| 测试项 | 预期 | 实现位置 |
|--------|------|----------|
| `Conversation` 构造校验 | 非法值抛出 `TypeError` / `ValueError` | `tests/test_storage.py` |
| `MessageRecord` 构造校验 | 同上 | `tests/test_storage.py` |
| `frozen=True` | 修改字段抛 `FrozenInstanceError` | `tests/test_storage.py` |
| ISO-8601 格式 | 读写往返一致 | `tests/test_storage.py` |
| 标题截断：空串 | `_normalize_title("")` → `"新会话"` | `tests/test_storage.py` |
| 标题截断：纯空白 | `_normalize_title("   ")` → `"新会话"` | `tests/test_storage.py` |
| 标题截断：恰好 20 字符 | 不变 | `tests/test_storage.py` |
| 标题截断：21 字符 | 前 17 + "..." | `tests/test_storage.py` |
| `MessageRecord.id` 保证 | Repository 返回的 id 非 None | `tests/test_storage.py` |

### 7.2 跨层映射测试

| 测试项 | 预期 | 实现位置 |
|--------|------|----------|
| `ChatMessage` → `MessageRecord` 映射 | 字段值一致 | Stage 5 组合根测试 |
| `MessageRecord` → `ChatMessage` 映射 | 角色校验通过 | Stage 5 组合根测试 |
| `EmotionResult` → `MessageRecord` 映射 | emotion 字段正确 | Stage 5 组合根测试 |
