# AGENTS.md — EmoWall AI V0.1 长期开发规则

本文件是**长期有效**的工程约定，面向所有协作者（人类与 AI 代理）。规则优先于个人偏好；
确需违反时，必须在提交说明中写明理由并同步修改本文件。

---

## 1. 项目定位

- 产品：Windows 11 本地 AI 聊天应用（Ollama 驱动），作为未来 **EmoWall AI 情绪壁纸** 的「AI 对话核心」。
- 本版本目标：**可复用的 AI 对话核心 + 最小可用 GUI**，不追求功能多。
- 判断标准：代码是否**可被 EmoWall 主项目直接迁移**、分层是否清晰、测试是否可靠。

---

## 2. 架构铁律（不可违背）

### 2.1 依赖方向

```
emowall/gui  ──►  emowall/{ai, storage, emotion, config}   （只允许向下）
emowall/app.py ──►  emowall/{gui, ai, storage, emotion, config}（组合根，可 import 全部）
emowall/{ai, storage, emotion, config} ──►  互不 import，也不 import gui / app
```

- `ai / config / storage / emotion` 是**扁平叶子层**，彼此独立；跨层数据由组合根（`app.py`）映射。
- 只有 `emowall/gui/**` 与组合根 `emowall/app.py` 允许 `import PySide6`；其他任何模块（含 `emowall/__init__.py`）禁止。
- 四层第三方依赖白名单：`ai` 仅 `httpx`，`config / storage / emotion` 仅标准库。
- `emowall/ai` 只允许依赖 **标准库 + httpx**；不得 import `PySide6`、`emowall.gui`、`emowall.app`。
- `emowall/ai` 是同步核心，额外禁止 `sqlite3` / `asyncio`（不叠加数据库与事件循环）。
- 由 `tests/test_architecture.py` 自动守护上述规则；**新增层必须同步更新该测试**。

### 2.2 GUI 线程规则

- 网络、模型加载与生成等阻塞等待**不得在 GUI 主线程执行**；一律通过工作线程（`QThread` + worker 对象）执行，用信号回传结果。
- 数据库使用**独立数据库工作线程**：SQLite 连接由该线程创建、使用、关闭，保留 `check_same_thread=True`；主线程与 AI 工作线程都不直接触碰连接。
- GUI 不等待数据库：读写都投递到 DB 线程队列，结果用信号回传；DB 错误以信号提示，不阻塞生成。
- `emowall/storage` 只提供同步、线程无关的库接口，不创建线程、不依赖 Qt。
- 工作线程只调用 AI 核心的**同步 API**，不引入 `asyncio` 事件循环叠加 Qt 事件循环。
- UI 更新（追加文本、滚动、按钮状态）只在主线程做。

### 2.3 流式与取消

- 生成必须是**可取消**的：取消按钮 → `CancelToken.cancel()` → 中断 `httpx` 响应流 → 核心抛 `CancelledError`（或被识别为取消）。
- 取消后必须：停止写 UI、把已收到的部分内容持久化、恢复输入框可用、会话状态一致。
- 不设「首包短超时」：本地模型冷启动可能 40 s+，需要「加载中」状态而不是失败。

---

## 3. 模块职责边界

| 包 | 负责 | 明确不负责 |
| --- | --- | --- |
| `emowall/ai` | Ollama HTTP 调用、NDJSON 流解析、上下文窗口裁剪、取消、错误分类 | 不碰 Qt、不碰 SQLite、不读配置文件 |
| `emowall/config` | `%APPDATA%\EmoWall\config.json` 读写、默认值、校验、原子写入 | 不发网络请求、不 import `emowall.ai`（含其数据类） |
| `emowall/storage` | SQLite 打开/建表/迁移、会话与消息 CRUD | 不生成 AI 内容、不依赖 Qt、不创建线程（线程封装在 GUI 层） |
| `emowall/emotion` | 文本 → 5 种基础表情的纯函数映射（确定性、可测试） | 不发网络请求、不依赖 Qt / DB |
| `emowall/gui` | 窗口、控件、信号槽、线程编排、把各层拼起来用 | 不直接拼 HTTP、不写 SQL 字符串 |
| `emowall/app.py` | 组合根：加载配置、建 DB、建引擎、注入 GUI | 不含业务规则 |

**数据模型原则**：每层使用自己的数据结构（dataclass），由组合根做映射；不要为了省事让 storage 依赖 ai 的模型类。

---

## 4. 代码规范

- Python 3.12；全量类型标注（`from __future__ import annotations`），公共函数必须标注返回值。
- 数据结构优先 `@dataclass(frozen=True)`；错误用自定义异常层级（`AIError` → `OllamaUnavailableError` / `ModelNotFoundError` / `CancelledError` / `ProtocolError`）。
- 无全局可变状态；依赖通过构造函数注入，便于测试。
- 不 `print` 调试输出：用 `logging`（`emowall.*` 命名空间）。
- 文件读写用 `pathlib.Path`；配置写入必须**原子**（临时文件 + `os.replace`）。
- 不在代码中硬编码 API 密钥 / Token / 个人路径；配置值从配置系统或环境变量读取。
- 不引入当前版本用不到的框架（例如不要为了 V0.1 引入 FastAPI、LangChain、ORM、依赖注入容器）。
- 不覆盖或删除已有文件；修改前先读，删除/移动前确认目标路径。

---

## 5. 测试规范

- 所有测试放 `tests/`，`$PY -m pytest`（`$PY` = `.\.venv\Scripts\python.exe`）必须**离线可跑**、不依赖真实 Ollama；默认配置已排除 `integration` 用例。
- 网络层测试用 `httpx.MockTransport` 或自定义假客户端，禁止真实外网调用；`httpx` 仅允许在 `tests/test_ai_client.py` 直接导入用于 MockTransport，其他测试文件禁止直接导入网络客户端。
- `tests/conftest.py` 默认拦截真实 socket 连接（`integration` / `local_network` 标记例外），保证默认测试离线。
- 真实 Ollama 的联调测试标记 `@pytest.mark.integration`，默认跳过（`-m integration` 手动运行）。
- 每个阶段结束必须：`$PY -m pytest` 全绿 **且** 手动验收清单勾完，才允许进入下一阶段。
- 新功能必须带测试；架构规则改动必须带守护测试。

---

## 6. 数据、配置与隐私

- 用户数据目录：`%APPDATA%\EmoWall\`（配置 `config.json`、数据库 `emowall.db`、日志 `logs\`）。
- 数据库、日志、`.venv`、`build/`、`dist/` **一律不入库**（见 `.gitignore`）。
- 聊天内容属于用户隐私：只存本地；日志不得记录完整对话正文（可记录长度、耗时、状态）。
- 应用不向外网发送任何数据（Ollama 地址必须指向本机或用户显式配置的内网地址）。

---

## 7. Git 与阶段流程

- 分支：`main` 为主干；每个阶段一个或多个提交，提交信息格式：`<type>(<scope>): <说明>`。
  - `type` ∈ `feat | fix | test | docs | chore | refactor | build`
  - 例：`feat(ai): 实现 Ollama 流式聊天与取消`
- **每个阶段结束必须提交**，且提交前工作区干净、测试通过。
- 提交粒度：一个提交只做一件事；不提交注释掉的死代码、调试语句、临时文件。
- 阶段推进：先更新 `docs/DEVELOPMENT_PLAN.md` 的状态，再开始编码。
- **未经项目负责人确认，不得越过阶段边界**（尤其不得提前进入 AI 核心 / GUI 实现）。

---

## 8. 环境事实（本机，2026-10-22 审计）

> 本节是当时本机的快照；路径统一用占位符，具体值以 `scripts/check_env.py` 的输出为准。

| 项 | 值 |
| --- | --- |
| 工作目录 | `<项目目录>`（本机位于 OneDrive 同步目录，用 `Get-Location` 查看） |
| Python | 3.12.15，uv 托管（`uv python find 3.12` 可定位；实际路径因机器而异） |
| `py` 启动器 | 默认 3.15（另有 Store 3.13）——**不要依赖裸 `py`** |
| Git | 2.56.0，提交前需配置 `user.name` / `user.email` |
| Ollama | 0.40.6（默认安装于 `%LOCALAPPDATA%\Programs\Ollama\`） |
| Ollama API | `http://127.0.0.1:11434`（未运行时会连接失败，需先启动） |
| 模型 | `qwen3:8b`（Q4_K_M，8.2B，约 4.9 GB，支持 thinking/tools） |
| 模型目录 | `D:\ollama\models`（用户环境变量 `OLLAMA_MODELS`） |
| 硬件 | 20 核 CPU / RTX 5060 Laptop 8 GB（模型可全部驻留显存）/ C: 167 GB 可用 |

- 冷启动：`qwen3:8b` 首次加载约 **40 s**；热请求（短问）约 **0.3 s**。
- 当前运行时上下文长度（`/api/ps`）：**8192**，多轮上下文需按此裁剪。

---

## 9. 完成定义（Definition of Done）

一个阶段算完成，必须同时满足：

1. 交付物齐全（代码 / 文档）；
2. `$PY -m pytest` 全绿；
3. 阶段的验收清单逐条可复现；
4. `docs/DEVELOPMENT_PLAN.md` 状态已更新；
5. 已提交 Git，工作区干净；
6. 向项目负责人报告：做了什么、证据、已知限制、下一步。
