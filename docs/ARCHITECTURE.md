# EmoWall AI V0.1 架构设计

> 状态：**设计已定稿，Stage 2 AI 核心已落地**。文中接口为契约草案，实际签名可在实现时微调，
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
4. `storage` 不创建线程、不依赖 Qt；SQLite 连接由应用层工作线程独占（见 §5.1）。
5. `ai` 额外禁止 `sqlite3` / `asyncio`；同步生成器 + `QThread` 工作线程，不叠加事件循环。

---

## 3. 接口契约（草案）

### 3.1 `emowall/ai`

```python
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

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
class OllamaUnavailableError(AIError): ...            # 服务不可用总类
class OllamaConnectionError(OllamaUnavailableError): ...  # 连接失败
class OllamaTimeoutError(OllamaUnavailableError): ...     # 超时
class OllamaHTTPError(OllamaUnavailableError): ...        # 非 2xx（404 除外）
class ModelNotFoundError(AIError): ...                # 404 / model not found
class ProtocolError(AIError): ...                     # JSON / NDJSON 格式错误
class StreamInterruptedError(ProtocolError): ...      # done 前断流
class CancelledError(AIError): ...                    # 用户取消

class CancelToken:
    """线程安全取消令牌；活动生成及取消清理结束前禁止 reset。"""
    def cancel(self) -> None: ...
    def reset(self) -> None: ...
    @property
    def is_cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...

class OllamaClient:
    """同步流式传输；生产使用自有客户端，注入模式由外部管理生命周期。"""
    def __init__(self, base_url: str = "http://127.0.0.1:11434", *,
                 connect_timeout: float = 5.0, read_timeout: float = 120.0,
                 write_timeout: float = 30.0, pool_timeout: float = 5.0,
                 client: httpx.Client | None = None,
                 transport: httpx.BaseTransport | None = None) -> None: ...
    def version(self) -> str: ...
    def list_models(self) -> list[str]: ...
    def stream_chat(self, *, model: str, messages: Sequence[ChatMessage],
                    options: Mapping[str, object] | None = None,
                    think: bool = False,
                    cancel: CancelToken | None = None) -> Iterator[ChatChunk]: ...
    def close(self) -> None: ...

class ChatEngine:
    """对话引擎：上下文裁剪 + 提示组装 + 调用客户端。不含 UI/DB。"""
    def __init__(self, client: OllamaClient, *, model: str,
                 max_context_messages: int = 20, max_context_chars: int = 6000,
                 system_prompt: str | None = None,
                 options: Mapping[str, object] | None = None,
                 think: bool = False) -> None: ...
    def build_context(self, history: Sequence[ChatMessage]) -> list[ChatMessage]: ...
    def stream_reply(self, history: Sequence[ChatMessage], *,
                     cancel: CancelToken | None = None) -> Iterator[ChatChunk]: ...
```

> 实际实现见 `emowall/ai/{errors,models,cancel,client,engine}.py`；设计决策见
> [ADR-0002](adr/0002-ai-core-boundaries-and-cancellation.md)。

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

> `EmotionPresentation` 是 **Stage 4 设计约定**（名称 / emoji / 主色三个字段），Stage 0 只统一文档，不实现。

---

## 4. 一次对话的数据流

```
用户在输入框回车
      │ GUI 主线程：校验输入、禁用发送、显示用户气泡、开启“生成中”
      │ 投递「写用户消息」给数据库工作线程（异步，不等待返回）
      ▼
GUI 工作线程（QThread / ChatWorker）
      │ 1) engine.stream_reply(界面已加载的历史 + 新消息, cancel=token)
      │    （引擎内部 build_context 完成裁剪，避免重复裁剪）
      ▼
OllamaClient.stream_chat → POST /api/chat (stream=true)
      │ 每行 NDJSON → ChatChunk → signal chunk(text) ───────► 主线程追加到气泡
      ▼
done=true → GenerationStats（或 cancelled / failed）
      │ 3) emotion.detect_emotion(全文)                      ← 纯函数
      │ 4) 投递「写 assistant 消息」给数据库工作线程（异步）
      │ 5) signal finished(stats, emotion) ────────────────► 主线程：恢复输入、更新表情
      ▼
数据库工作线程（QThread / StorageService，独占一个 sqlite3 连接）
      │ FIFO 执行：append_message(user) → append_message(assistant)
      │ 结果信号：会话列表刷新 / storage_error(str)
```

> 所有 SQLite 读写都在**专用数据库工作线程**执行；GUI 主线程与 AI 工作线程都不直接触碰数据库（见 §5.1）。

失败/取消路径同一收尾函数：已收到文本非空则落库（`content` 为部分内容），
然后 `signal failed(msg)` 或 `signal cancelled()`，UI 恢复可交互。

---

## 5. 线程与取消模型

- **核心同步**：`stream_chat` 是普通生成器，挂在调用线程上阻塞，便于移植与测试。
- **GUI 侧**：`ChatWorker(QObject)` 通过 `moveToThread(QThread)` 运行；信号 `chunk / finished / failed / cancelled`。
- **取消**：`CancelToken` 分别跟踪活动生成、资源登记和取消清理。自有模式在请求前登记底层
  `httpx.Client.close`，收到响应后再登记 `httpx.Response.close`；注入模式只登记响应。
  `cancel()` 从任意线程调用，置位事件并关闭资源，但保留登记直到生成器退出。
  已取消时的读取错误、安静 EOF、错误正文读取失败优先映射为 `CancelledError`。
- **复用**：`reset()` 在旧生成器、异常分类、资源登记或取消清理尚未结束时抛 `RuntimeError`。
  取消发起后必须等旧生成结束；取消关闭的自有客户端在下一次请求时自动重建，不创建后台任务。
- **所有权**：默认底层客户端由 `OllamaClient` 创建和关闭；外部注入客户端由调用方创建、关闭，
  `OllamaClient.close()` 不关闭它。注入模式供测试或明确的外部生命周期管理使用，不用于 Stage 5 生产工作线程。
- **实际边界**：注入模式在响应头之前没有可关闭的响应，不保证及时取消；需要等请求返回、超时
  或外部管理者中断后才能退出。响应后关闭响应的唤醒时延仍依赖传输。自有模式也不承诺
  TCP/TLS 建连尚未完成时的统一取消时限；这些限制不能通过文档约定视为底层能力已修复。
- **不做的**：不在 Qt 线程里跑 `asyncio`；不做线程池并发多路生成（V0.1 单会话单生成）。
- **资源**：生成器消费完或由消费线程显式 `close()`，通过 `with` 释放响应；提前结束
  `ChatEngine.stream_reply()` 也须关闭生成器。线程结束 `quit()+wait()`；退出应用时先取消再关库。

> 历史记录（2026-10-23 Stage 2 原交付）：曾报告真实 Ollama 冷启动探针取消约 0.5 s。
> 这不是普遍时延保证，也不等于本次整改已通过真实验收。G3 将按 1 s 目标重新测量，
> 当前待实测；离线假传输的及时关闭不能替代真实网络结果。详见 [ADR-0002](adr/0002-ai-core-boundaries-and-cancellation.md)。

### 5.1 数据库线程归属（长期设计）

**架构决定：数据库使用独立工作线程，连接由该线程独占。**

- `emowall/storage` 是**同步、线程无关**的库：不创建线程、不依赖 Qt、不加锁；由调用方保证同一时刻只被一个线程使用。
- 应用层用 `QThread` + `StorageService`（`emowall/gui/db_service.py`）独占一个 SQLite 连接：连接在线程 `run()` 内打开，在 `finally` 中关闭。
- 保留 sqlite3 默认的 `check_same_thread=True`：任何跨线程误用会立刻抛 `ProgrammingError`，把问题暴露在开发期，而不是用锁掩盖。
- 所有读写都经队列投递到 DB 线程，结果用信号回传；GUI 主线程**不持有连接、不调用 repository**，界面零阻塞。
- 顺序保证：单线程 FIFO，同一会话「用户消息 → AI 消息」的写入天然串行，不需要业务锁。
- 失败处理：DB 线程捕获 `sqlite3.Error` 并发 `storage_error(str)` 信号，界面提示「保存失败」，不中断当前生成；`busy_timeout = 2000`。
- 关闭顺序：取消生成 → 等待 AI 线程结束 → 投递 `close()` 并等待 DB 线程退出 → 关闭窗口。
- Stage 0 只定架构；Stage 3 实现无 Qt 的 `storage`，Stage 5 实现 DB 线程封装，均不提前实现。

### 5.2 Stage 5 AI 工作线程契约（未来实现）

- 组合根创建默认自有模式的 `OllamaClient`，不传入外部 `client`；工作线程独占该实例，
  同一时刻只运行一路生成。生产取消能力以默认真实 HTTP 传输的验收结果为依据。
- 工作线程消费 `ChatEngine.stream_reply()`，在 `finally` 显式关闭仍未消费完的生成器。
  先完成生成器清理和取消/错误分类，再发本轮终止信号；下一轮不得与旧生成重叠。
- 每轮优先使用新 `CancelToken`；若复用旧令牌，必须在旧生成与取消清理全部结束后 `reset()`。
  `cancel()` 返回或收到 `done` 块都不能代替生成器完成清理的确认。
- 取消后保留已收到文本，按既定异步数据库流程持久化。退出时先取消并等待 AI 工作线程收尾，
  再关闭自有客户端；配置变化也须先结束旧请求，再替换客户端。
- 冷启动显示加载状态，不使用首包短超时；注入模式响应头前取消的限制不得被 UI 宣称为已解决。
  本节仅规定未来职责，本次整改不实现 GUI 或工作线程。

---

## 6. 多轮上下文策略

1. 历史消息按时间正序；`system` 提示始终置首，永不裁剪。
2. 非 system 消息按「用户消息开启一个轮次」分组，从最新轮次向最旧轮次累加；只保留完整轮次，避免孤立的 assistant 回复。
3. 裁剪双阈值：`max_context_messages`（条数，含 system）+ `max_context_chars`（字符预算，含 system）。
4. 硬底线：`system` 与最新轮次（含最后一条用户消息）即使单条超预算也保留；其余从最旧轮次开始丢。
5. 字符预算估算：CJK 约 1 token/字，英文约 4 字符/token；V0.1 用「字符数」保守近似即可，不做 tokenizer，字符数不等于模型 token 数。
6. 运行时 `num_ctx` 当前为 8192；预算默认 6000 字符，留出系统提示与生成空间。
7. 裁剪只影响**发送给模型的上下文**，不影响数据库里的完整历史；引擎不持有会话状态。

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

- 加载优先级（V0.1）：配置文件 > 内置默认值；显式覆盖（命令行 / 环境变量）留到需要时再加，不提前实现。
- 字段非法：该字段回退默认值并记录 warning，**不重写用户文件**；整体损坏才备份重置。
- 整体损坏：重命名为 `config.corrupt-<UTC 时间戳>.json` 后写回默认值；备份失败则保持原文件不动。
- 未知字段：运行时忽略，保存时原样保留（避免新版本写入的字段被旧版本丢弃）。
- 版本：`version` 为整数；较新版本只读已知字段并 warning，较旧版本缺失字段用默认值；迁移钩子留待后续。
- 写入：同目录临时文件 + `fsync` + `os.replace` 原子替换；`EMOWALL_HOME` 可整体重定向。
- 实现：`emowall/config/{errors,paths,settings,store}.py`，仅标准库；设计决策见 [ADR-0001](adr/0001-configuration-store.md)。

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
