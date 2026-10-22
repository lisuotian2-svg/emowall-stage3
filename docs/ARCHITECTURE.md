# EmoWall AI V0.1 架构设计

> 状态：**设计已定稿，代码按阶段落地**（Stage 0 仅骨架）。文中接口为契约草案，实际签名可在实现时微调，
> 但**依赖方向、线程模型、取消语义、数据边界**四项不可变。

---

## 1. 设计目标与约束

| 目标 | 约束 |
| --- | --- |
| AI 核心可迁移到 EmoWall 主项目 | `emowall/ai` 只依赖标准库 + httpx，不含任何产品/界面/存储概念 |
| 网络不阻塞 GUI | 同步流式核心 + `QThread` 工作线程，信号回传 |
| 生成可随时取消 | 取消令牌贯穿 HTTP 响应流；取消后保留部分内容 |
| 各层可独立测试 | 四层扁平、互不 import；网络用 `MockTransport` 替身 |
| 不做过度设计 | 无 asyncio、无 ORM、无依赖注入框架、无插件系统 |

---

## 2. 分层与依赖

```
                         ┌─────────────────────┐
                         │   emowall/app.py    │  组合根（唯一装配点）
                         └──────┬──────────────┘
             ┌──────────┬────────┴───────┬───────────────┐
             ▼          ▼                ▼               ▼
        ┌────────┐ ┌────────┐      ┌─────────┐    ┌──────────┐
        │  gui   │ │  ai    │      │ storage │    │  config  │
        │ (Qt)   │ │(httpx) │      │sqlite3  │    │  (json)  │
        └────────┘ └────────┘      └─────────┘    └──────────┘
             │          ▲                ▲               ▲
             │          └────────────────┴───────────────┘
             └──────────────►  仅 gui 可向下 import 四层
                                 四层之间互不 import
        ┌──────────┐
        │ emotion  │  纯函数层（标准库 only），可被 gui / app 使用
        └──────────┘
```

**硬规则**（由 `tests/test_architecture.py` 守护）：

1. `ai / config / storage / emotion` 不得 import 彼此，也不得 import `gui`、`app`。
2. 只有 `emowall/gui/**` 与组合根 `emowall/app.py` 可以 import `PySide6`；`emowall/__init__.py` 不得 import Qt 或 gui/app。
3. 四层第三方依赖白名单：`ai` 仅 `httpx`，`config / storage / emotion` 仅标准库。

---

## 3. 接口契约（草案）

### 3.1 `emowall/ai`

```python
from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Literal, Sequence

Role = Literal["system", "user", "assistant"]

@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str

@dataclass(frozen=True)
class GenerationStats:
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    total_duration_ms: int | None = None
    load_duration_ms: int | None = None
    done_reason: str | None = None

@dataclass(frozen=True)
class ChatChunk:
    text: str                    # 增量文本；可为空串
    done: bool = False
    stats: GenerationStats | None = None

class AIError(Exception): ...
class OllamaUnavailableError(AIError): ...   # 连接失败 / 5xx
class ModelNotFoundError(AIError): ...       # 404 / model not found
class ProtocolError(AIError): ...            # NDJSON 无法解析等
class CancelledError(AIError): ...           # 用户取消

class CancelToken:
    """线程安全取消令牌。取消后可中断正在读取的 HTTP 响应。"""
    def cancel(self) -> None: ...
    def reset(self) -> None: ...
    @property
    def is_cancelled(self) -> bool: ...

class OllamaClient:
    """Ollama HTTP 传输层（同步、流式）。不认识的字段一律忽略。"""
    def __init__(self, base_url: str, *, connect_timeout: float = 5.0,
                 read_timeout: float = 120.0, client: httpx.Client | None = None) -> None: ...
    def version(self) -> str: ...
    def list_models(self) -> list[str]: ...
    def stream_chat(self, *, model: str, messages: Sequence[ChatMessage],
                    options: dict | None = None, think: bool = False,
                    cancel: CancelToken | None = None) -> Iterator[ChatChunk]: ...

class ChatEngine:
    """对话引擎：上下文裁剪 + 提示组装 + 调用客户端。不含 UI/DB。"""
    def __init__(self, client: OllamaClient, *, model: str,
                 max_context_messages: int = 20, max_context_chars: int = 6000,
                 system_prompt: str | None = None) -> None: ...
    def build_context(self, history: Sequence[ChatMessage]) -> list[ChatMessage]: ...
    def stream_reply(self, history: Sequence[ChatMessage], *,
                     cancel: CancelToken | None = None) -> Iterator[ChatChunk]: ...
```

### 3.2 `emowall/config`

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

class ConfigStore:
    def __init__(self, path: Path) -> None: ...
    def load(self) -> AppSettings: ...     # 文件缺失/损坏 → 默认值 + 备份坏文件
    def save(self, settings: AppSettings) -> None: ...  # 原子写入

def default_app_data_dir() -> Path: ...    # %APPDATA%\EmoWall，可用 EMOWALL_HOME 覆盖
```

### 3.3 `emowall/storage`

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
    def __init__(self, path: Path) -> None: ...   # 建目录、建表、PRAGMA
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

### 3.4 `emowall/emotion`

```python
class Emotion(str, Enum):
    HAPPY = "happy"
    CALM = "calm"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"

@dataclass(frozen=True)
class EmotionResult:
    emotion: Emotion
    intensity: float                      # 0.0 ~ 1.0
    matched_keywords: tuple[str, ...]
    source: str = "rule"

@dataclass(frozen=True)
class EmotionPresentation:
    label: str        # 中文名，如「开心」
    emoji: str        # 单个 emoji
    color: str        # 主色 #RRGGBB

def detect_emotion(text: str) -> EmotionResult: ...      # 纯函数、确定性
def presentation(emotion: Emotion) -> EmotionPresentation: ...  # 名称/表情/主色
```

---

## 4. 一次对话的数据流

```
用户在输入框回车
      │ GUI 主线程：校验输入、禁用发送、显示用户气泡、开启“生成中”
      ▼
GUI 工作线程（QThread）
      │ 1) storage.append_message(user)                    ← 先落库，崩溃不丢
      │ 2) engine.build_context(history + 新消息)           ← 裁剪
      │ 3) engine.stream_reply(ctx, cancel=token)
      ▼
OllamaClient.stream_chat → POST /api/chat (stream=true)
      │ 每行 NDJSON → ChatChunk → signal chunk(text) ───────► 主线程追加到气泡
      ▼
done=true → GenerationStats
      │ 4) emotion.detect_emotion(全文)                     ← 纯函数
      │ 5) storage.append_message(assistant, emotion...)     ← 落库
      │ 6) signal finished(stats, emotion) ────────────────► 主线程：恢复输入、更新表情
```

> 落库位置：图中 1) 与 5) 的 `storage` 写操作在 **GUI 工作线程**内完成；会话列表与历史消息的短读由主线程执行（见 §5.1）。

失败/取消路径同一收尾函数：已收到文本非空则落库（`content` 为部分内容），
然后 `signal failed(msg)` 或 `signal cancelled()`，UI 恢复可交互。

---

## 5. 线程与取消模型

- **核心同步**：`stream_chat` 是普通生成器，挂在调用线程上阻塞，便于移植与测试。
- **GUI 侧**：`ChatWorker(QObject)` 通过 `moveToThread(QThread)` 运行；信号 `chunk / finished / failed / cancelled`。
- **取消**：`CancelToken` 保存当前活动的 `httpx.Response`；`cancel()` 从任意线程调用 → 置位事件 + 关闭响应。
  工作线程读取循环捕获 `httpx.ReadError/StreamClosed`，若令牌已取消则抛 `CancelledError`（而非错误弹窗）。
  冷启动（模型加载 ~40 s）期间取消同样生效，因为关闭的是底层连接。
- **不做的**：不在 Qt 线程里跑 `asyncio`；不做线程池并发多路生成（V0.1 单会话单生成）。
- **资源**：每次生成结束必须 `response.close()`，线程结束 `quit()+wait()`；退出应用时先取消再关库。

### 5.1 数据库线程归属

- 写操作（用户消息、AI 回复）在 GUI 工作线程内执行，与生成串行，避免写冲突与 UI 卡顿。
- 读操作（会话列表、历史加载）允许在主线程执行：WAL 下读写并发安全，单条查询预期 < 10 ms。
- 连接用 `check_same_thread=False` + 模块级锁保护，`busy_timeout = 2000`；超时提示「数据库忙，请重试」。
- 若实测主线程单次读 > 50 ms，Stage 5 再把读也移到专用存储线程（V0.1 默认不做，避免过度设计）。

---

## 6. 多轮上下文策略

1. 历史消息按时间正序；`system` 提示始终置首。
2. 裁剪双阈值：`max_context_messages`（条数）+ `max_context_chars`（字符预算），从最旧的成对消息开始丢。
3. 字符预算估算：CJK 约 1 token/字，英文约 4 字符/token；V0.1 用「字符数」保守近似即可，不做 tokenizer。
4. 运行时 `num_ctx` 当前为 8192；预算默认 6000 字符，留出系统提示与生成空间。
5. 裁剪只影响**发送给模型的上下文**，不影响数据库里的完整历史。

---

## 7. 情绪系统（V0.1）

- 5 种基础表情（不可扩展，避免过度设计）：`happy 开心 / calm 平静 / sad 难过 / angry 生气 / surprised 惊讶`。
- 识别方式：**规则 + 关键词加权**（确定性），不额外调用模型，不增加延迟与依赖。
  - 关键词表：中文 + 英文常用词、语气词、表情符号；emoji 权重更高。
  - 打分：命中词权重求和 → 取最高；最高分 ≤ 0 或并列 → `calm`（默认平静）。
  - 强度：`min(1.0, score / 3.0)`，保留 2 位小数。
  - 简单否定处理：`不开心 / 不高兴 / don't like` 之类短语按预设反向短语表处理，不做通用 NLP。
- 输出 `EmotionResult` 同时写入消息记录（`emotion`、`emotion_intensity`），供未来壁纸生成使用。
- 展示数据（`presentation`）只含名称/emoji/主色十六进制，**不含 Qt 类型**，GUI 自行渲染。

---

## 8. SQLite 数据模型

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role              TEXT NOT NULL CHECK (role IN ('system','user','assistant')),
    content           TEXT NOT NULL,
    emotion           TEXT,
    emotion_intensity REAL,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
```

- 版本管理用 `PRAGMA user_version`，迁移写成顺序函数列表（V0.1 只有一个初始版本）。
- 会话标题：首条用户消息截断 20 字；为空时用「新会话」。
- 时间统一存 UTC ISO-8601 字符串，展示时转本地时区。

---

## 9. 配置文件（`%APPDATA%\EmoWall\config.json`）

```json
{
  "version": 1,
  "ollama": {
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen3:8b",
    "connect_timeout_seconds": 5.0,
    "read_timeout_seconds": 120.0,
    "num_ctx": 8192,
    "temperature": 0.7,
    "think": false
  },
  "chat": {
    "max_context_messages": 20,
    "max_context_chars": 6000,
    "system_prompt": "你是 EmoWall 的 AI 伙伴，回答简洁、自然、有情绪温度。"
  }
}
```

- 加载优先级：显式构造参数 > 配置文件 > 内置默认值。
- 损坏时：重命名坏文件为 `config.corrupt-<时间戳>.json`，回退默认值并在 UI 顶部提示。
- 写入：同目录临时文件 + `os.replace` 原子替换；`EMOWALL_HOME` 环境变量可整体重定向（测试用）。

---

## 10. 迁移到 EmoWall 主项目

| 组件 | 迁移成本 | 说明 |
| --- | --- | --- |
| `emowall/ai` | 零改动 | 只依赖 stdlib + httpx，无产品概念 |
| `emowall/emotion` | 零改动 | 纯函数；主项目可扩展壁纸参数映射 |
| `emowall/config` | 低 | 路径由构造函数注入，主项目换成自己的配置存储即可 |
| `emowall/storage` | 低 | 只暴露仓库接口；主项目可换表结构或迁移 |
| `emowall/gui` | 不可复用（预期） | 练习版界面，主项目重做 UI |

**结论**：能搬走的是「网络 + 流式 + 取消 + 上下文 + 情绪判定」；不可搬走的是界面与装配方式。

---

## 11. V0.1 明确不做

- 多模型并行、Agent 工具调用、RAG、语音、图片生成。
- Token 级精算、模型自托管、远程服务鉴权。
- 多用户 / 云同步 / 加密数据库。
- 自定义主题、插件、国际化。

超出范围的建议记入 `docs/BACKLOG.md`（Stage 6 之后按需创建），不在 V0.1 顺手实现。
