# EmoWall AI V0.1 分阶段开发计划

> 原则：**每阶段必须有可复现的验收标准**，验收通过并提交 Git 后才进入下一阶段。
> 未经项目负责人确认，不进入任何编码阶段（Stage 1、Stage 2 既有交付保留；当前仅执行已授权的 Stage 2 独立审查整改，不进入 Stage 3）。

**命令约定**：以下命令均在项目根目录执行；`$PY` 表示项目虚拟环境解释器 `.\.venv\Scripts\python.exe`，
`$UV` 表示 `uv` 命令。本机裸 `python` 与 `py` 可能指向别的解释器，不要使用。

**环境标准**：Python 3.12（uv 托管 CPython）+ uv 0.13+ 创建/同步 `.venv`；依赖声明的唯一来源是 `requirements.txt`
（不引入 pyproject 依赖表，避免两套依赖来源冲突）。

---

## 总览

| 阶段 | 主题 | 交付物 | 预计工作量 | 状态 |
| --- | --- | --- | --- | --- |
| 0 | 环境审计与项目骨架 | 目录、规范、计划、Git | 0.5 天 | ✅ 完成 |
| 1 | 配置系统 | `emowall/config` | 0.5 天 | ✅ 完成 |
| 2 | AI 核心 | `emowall/ai` | 1 天 | ✅ 完成 |
| 3 | SQLite 存储 | `emowall/storage` | 0.5 天 | ⬜ |
| 4 | 情绪系统 | `emowall/emotion` | 0.5 天 | ⬜ |
| 5 | GUI 集成 | `emowall/gui`、`emowall/app.py` | 1.5 天 | ⬜ |
| 6 | 打包与 V0.1 验收 | PyInstaller EXE、验收报告 | 1 天 | ⬜ |

合计约 5 个工作日（按每天 4~6 小时有效编码估算）。

依赖顺序：`1 → 2 → 3 → 4 → 5 → 6`。其中 2 只依赖 1 的数据结构；3、4 可与 2 并行，但为降低协作成本按顺序推进。

---

## Stage 0 — 环境审计与项目骨架 ✅

**目标**：在没有写任何业务代码前，确认环境可用、把工程规矩立起来。

**交付物**

- `README.md`、`AGENTS.md`、`requirements.txt`、`.gitignore`、`.gitattributes`、`pytest.ini`
- `docs/ARCHITECTURE.md`、`docs/DEVELOPMENT_PLAN.md`、`docs/ENVIRONMENT_AUDIT.md`
- `scripts/check_env.py`（仅标准库的环境自检）
- `emowall/` 包骨架（各层 `__init__.py` 只有职责说明，无业务代码）
- `tests/test_architecture.py`（架构守护：Qt 边界 / 层间隔离 / 依赖白名单 / 负向用例）
- `tests/test_package.py`（包冒烟）、`tests/test_docs.py`（文档与结构一致）、`tests/test_check_env.py`（自检脚本）、`tests/test_pytest_config.py`（测试隔离）
- Git 仓库初始化 + 首次提交

**验收标准**

1. 目录结构与 `docs/ARCHITECTURE.md` 一致（6 个包目录：`emowall` 与 `ai / config / storage / emotion / gui`，均含 `__init__.py`）。
2. `$PY scripts\check_env.py` 逐项输出 Python / 依赖 / git / ollama / Ollama API / 本地模型 / 模型目录 / 应用数据目录 的 PASS / WARN / FAIL，退出码 0（无 FAIL）或 1（有 FAIL）。
3. `$PY -m pytest` 全绿（架构守护测试通过）。
4. `git log --oneline` 至少有 1 条提交，`git status` 干净。
5. 仓库中不存在 `*.db`、`.venv`、`build/`、`dist/`、密钥文件。
6. 架构守护测试含**负向用例**：临时注入 `import PySide6` 或跨层 import 时，守护函数必须报告违规（证明规则真的会拦人）。

---

## Stage 1 — 配置系统 ✅

**目标**：让「Ollama 地址 / 模型 / 上下文预算」可配置、可持久化、可损坏恢复，为后续所有层提供唯一事实来源。

**交付物**

- `emowall/config/paths.py`：`default_app_data_dir()`（`%APPDATA%\EmoWall`，`EMOWALL_HOME` 可覆盖）
- `emowall/config/settings.py`：`OllamaSettings / ChatSettings / AppSettings`（frozen dataclass + 校验）
- `emowall/config/errors.py`：`ConfigError / ConfigValidationError / ConfigIOError`
- `emowall/config/store.py`：`ConfigStore.load()` / `save()`（原子写入、损坏备份回退、未知字段保留、版本兼容）
- `docs/adr/0001-configuration-store.md`：配置存储设计决策
- `tests/test_config.py`（37 个用例：默认值、读写、校验、损坏恢复、版本兼容、原子写入、目录隔离）

**技术要点**

- 默认值集中在 `defaults()`，不散落。
- 校验：URL 必须 `http/https` 且非空；`num_ctx ≥ 1024`；`temperature ∈ [0, 2]`；超时 > 0。
- 未知字段忽略并 `logging.warning`；`version` 字段预留升级位。
- 不 import `httpx`/Qt；只用标准库。

**验收标准**

1. 首次运行自动生成 `config.json`（默认值），再次加载结果一致（round-trip）。
2. 删除文件 → 返回默认值，不抛异常。
3. 写坏 JSON → 备份为 `config.corrupt-*.json`，返回默认值，日志有 warning。
4. 非法值（`base_url=""`、`temperature=9`）→ 抛 `ConfigValidationError` 且不写盘。
5. 写入过程先写临时文件再 `os.replace`：人为中断不会留下半截 JSON。
6. `EMOWALL_HOME` 指向临时目录时，配置文件落在该目录（测试隔离）。
7. `$PY -m pytest` 全绿；`grep -rn "PySide6" emowall/config` 无结果。

**验收结果（2026-10-22，Stage 1 完成）**

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 1 首次生成 + round-trip | ✅ | `test_first_load_creates_file_with_defaults`、`test_round_trip_persists_settings` |
| 2 删除文件回默认 | ✅ | `test_delete_file_returns_defaults` |
| 3 坏 JSON 备份恢复 | ✅ | `test_corrupt_json_is_backed_up_and_recovers`、`test_json_array_is_treated_as_corrupt` |
| 4 非法值拒绝写盘 | ✅ | 12 项 `test_invalid_settings_are_rejected`、`test_save_raises_io_error_when_disk_fails` |
| 5 原子写入 | ✅ | `test_save_leaves_no_temp_files` |
| 6 EMOWALL_HOME 隔离 | ✅ | `test_emowall_home_isolates_storage` |
| 7 测试全绿 + 无 Qt | ✅ | `$PY -m pytest`：97 passed / 1 skipped；架构守护测试通过 |

---

## Stage 2 — AI 核心 ✅

**状态：整改中（2026-10-23，独立审查 CONDITIONAL PASS）**

本次按 G1 取消令牌竞态 → G2 HTTP 所有权 → G3 真实集成验收 → G4 文档同步执行，
每项独立测试、审查与提交。下方原始验收记录保留为历史证据，不能代替本次复测。
Stage 3 仍未获准开始。

- G1 已修复并复测：旧代码新增首批用例 **6 failed**；修复后客户端 **71 passed**，
  默认测试 **223 passed / 1 skipped / 8 deselected**，严格离线 **221 passed / 1 skipped / 10 deselected**。
  默认测试首次因沙箱回环权限失败，允许本机回环后原样通过；唯一 skipped 为未安装 PySide6。
  取消标志保持至生成器异常分类、资源释放与取消回调均结束；公开 API 不变。

**目标**：把「连 Ollama、流式说话、多轮上下文、随时取消」做成与界面无关、可移植的核心。

**交付物**

- `emowall/ai/errors.py`：`AIError` + 4 个顶层子类；另含 `OllamaConnectionError / OllamaTimeoutError / OllamaHTTPError / StreamInterruptedError` 细分
- `emowall/ai/models.py`：`ChatMessage / ChatChunk / GenerationStats`（通用消息与流式事件，无 Qt）
- `emowall/ai/cancel.py`：`CancelToken`（跨线程取消 + 活动响应登记/关闭）
- `emowall/ai/client.py`：`OllamaClient`（`version / list_models / stream_chat`，NDJSON 解析、错误分类、资源释放）
- `emowall/ai/engine.py`：`ChatEngine`（上下文裁剪、系统提示、多轮顺序、`stream_reply`）
- `scripts/chat_probe.py`：命令行联调工具（多轮 `--prompt`、`--list-models`、Ctrl+C 取消）
- `tests/test_ai_client.py`（61 例）、`tests/test_ai_engine.py`（35 例）、`tests/test_ai_config.py`（6 例）、`tests/test_ai_probe.py`（3 例）——MockTransport / 假客户端 / 自定义 transport，全部离线
- `tests/test_ai_integration.py`（8 例，`@pytest.mark.integration`，真实 Ollama，默认跳过）
- `docs/adr/0002-ai-core-boundaries-and-cancellation.md`：AI 核心边界、错误分类、取消与上下文决策

**技术要点**

- `httpx.Client(timeout=httpx.Timeout(connect=..., read=..., write=..., pool=...))`；本地默认 `trust_env=False`，不自动继承系统代理。
- 流解析：`response.iter_lines()` → `json.loads`；空行跳过；单行解析失败记 warning 不中断（整段无有效数据才报 `ProtocolError`）；`done=true` 才视为正常完成，EOF 早于 `done` 报 `StreamInterruptedError`。
- 错误映射：连接失败 → `OllamaConnectionError`；超时 → `OllamaTimeoutError`；404 / `model ... not found` → `ModelNotFoundError`；其他非 2xx → `OllamaHTTPError`；取消 → `CancelledError`。
- 取消：`CancelToken` 在等待响应头阶段登记底层 `httpx.Client`、收到响应后登记 `httpx.Response`；`cancel()` 关闭活动资源，owned client 下次请求自动重建。等待响应头（冷启动）与读块中都能及时停止，且不会污染下一轮。
- 上下文裁剪：按「用户消息开启轮次」分组，从最新轮次向最旧轮次累加；条数与字符预算同时生效；`system` 与最新轮次（含最后一条用户消息）为硬底线；字符预算只是 token 的保守近似。
- 配置方向：`emowall.ai` 不 import `emowall.config`；由组合根读取 `ConfigStore.load().ollama / .chat` 后构造客户端与引擎，配置变化时构造新客户端实例。
- 不做 tokenizer、不做重试风暴、不引入 asyncio / 后台线程池。

**验收标准**

1. `$PY -m pytest` 全绿（默认已排除 integration），且**全程无真实网络**（可用断网复跑验证）。
2. Mock 用例覆盖：正常多块拼接、`done` 统计字段、`error` 字段、HTTP 404/500、连接拒绝、半行断流、取消发生在第 2 块之后。
3. 取消语义：`token.cancel()` 后生成器在 500 ms 内抛 `CancelledError`，且已产出的块数被准确记录。
4. 上下文：构造 60 条历史 + 预算 6000 字符，断言发送给 client 的消息满足条数/字符上限，且 system 与最后一条用户消息保留。
5. 真实联调：启动 Ollama 后 `$PY scripts\chat_probe.py --prompt "你好"` 逐字打印；按 Ctrl+C 立即停止且不打印堆栈。
6. `$PY -m pytest -m integration`（Ollama 已启动）通过。
7. `$PY -c "import emowall.ai"` 在**未安装 PySide6 的纯环境**下可导入（验证核心零 Qt 依赖）。
8. `git grep -n "PySide6" -- emowall/ai` 无结果。

**验收结果（2026-10-23，Stage 2 完成）**

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 1 全量离线测试 | ✅ | `$PY -m pytest`：211 passed / 1 skipped（8 个 integration 用例默认 deselect）；`tests/conftest.py` socket 守卫 + MockTransport 证明离线用例零真实外网 |
| 2 Mock 覆盖 | ✅ | `tests/test_ai_client.py`：分块 / 半行 / 404 / 500 / 连接拒绝 / 超时 / 取消 / 资源释放 |
| 3 取消语义 | ✅ | `test_cancel_from_another_thread_stops_within_500ms`、`test_cancel_after_two_chunks_raises_and_closes`、`test_cancel_while_waiting_for_response_headers_is_timely`；真实冷启动探针 0.5 s 取消 |
| 4 上下文 60 条 + 6000 字符 | ✅ | `test_acceptance_context_60_messages_budget_6000`：19 条、字符数 ≤ 6000；`test_char_budget_actually_binds` 单独验证字符预算确实先于条数生效 |
| 5 真实 probe | ✅ | `scripts\chat_probe.py --list-models` → `qwen3:8b`；`--prompt "请只回复：你好"` → `你好。`，退出码 0 |
| 6 integration | ✅ | `$PY -m pytest -m integration`：8 passed（版本、模型列表、普通回复、流式顺序、两轮上下文、取消后恢复、未知模型、关闭） |
| 7 零 Qt 导入 | ✅ | `test_ai_core_imports_with_qt_blocked` 在 Qt 导入被阻断的子进程中成功导入 `emowall.ai` |
| 8 无 PySide6 引用 | ✅ | `git grep -n "PySide6" -- emowall/ai` 无结果（最终提交前复核） |

**独立评审修复（2026-10-23）**

- P1-1 冷启动/响应头前取消：已修复（登记底层 `httpx.Client`，取消后自动重建；真实冷启动探针 0.5 s）。
- P2 已处理：3xx 不再当成功、404 仅 `/api/chat` 映射模型缺失、错误文案匹配收窄、`base_url` 拒绝查询/片段、`reset()` 活动态抛错、AI 层新增 `sqlite3/asyncio` 守护、配置测试相对导入展开、integration 去掉脆弱输出断言、新增字符预算绑定用例、subprocess 回环用例加 `local_network` 标记、NDJSON 日志不再输出行内容。

---

## Stage 3 — SQLite 存储

**目标**：会话与消息可靠落盘，重启后可恢复；存储层完全不知道 AI 的存在。

**交付物**

- `emowall/storage/database.py`：连接、PRAGMA、建表、`user_version` 迁移
- `emowall/storage/models.py`：`Conversation / MessageRecord`
- `emowall/storage/repository.py`：`ConversationRepository`
- `tests/test_storage.py`（≥ 15 个用例，临时目录 DB）

**技术要点**

- `storage` 同步、线程无关：不建线程、不加锁、不依赖 Qt；每次操作短事务，`busy_timeout=2000`。
- 保留 sqlite3 默认 `check_same_thread=True`：连接只在其所属线程使用（Stage 5 由独立 DB 工作线程独占）。
- WAL + `foreign_keys=ON`。
- 时间 UTC ISO-8601；会话 `updated_at` 在追加消息时更新。
- 删除会话级联删除消息；`list_messages` 按 `id` 正序。

**验收标准**

1. 空目录首次打开自动建库建表，`PRAGMA user_version` 为 1。
2. 建会话 → 追加 3 条消息 → 重启（重新打开连接）后顺序、内容、角色完全一致。
3. `list_recent(limit)` 按 `updated_at` 倒序；`limit` 生效。
4. 删除会话后其消息数为 0（级联生效），其他会话不受影响。
5. `emotion/emotion_intensity` 可为 NULL，写入后原样读回。
6. 同一会话第 1 条用户消息自动生成标题（≤ 20 字），空内容回退为「新会话」。
7. 并发场景最小验证：两个独立线程各持一个连接交替读写，不报 `database is locked`（WAL + busy_timeout=2000 生效）；同一连接跨线程使用应抛 `ProgrammingError`（证明 `check_same_thread=True` 未被关闭）。
8. `$PY -m pytest` 全绿；`grep -rn "PySide6\|httpx" emowall/storage` 无结果。

---

## Stage 4 — 情绪系统

**目标**：把回复文本映射成 5 种基础表情，纯函数、确定性、可单测，为未来壁纸提供情绪信号。

**交付物**

- `emowall/emotion/labels.py`：`Emotion` 枚举 + `presentation()`（名称 / emoji / 主色）
- `emowall/emotion/detector.py`：`detect_emotion(text) -> EmotionResult`
- `emowall/emotion/lexicon.py`：中英文关键词表（每类 ≥ 12 个）
- `tests/test_emotion.py`（表驱动，≥ 25 组输入）

**技术要点**

- 打分 = Σ 命中词权重（emoji 1.5 / 强词 1.0 / 弱词 0.5）；最高分 ≤ 0 或并列 → `calm`。
- 否定短语（`不开心`、`不高兴`、`没意思`、`not happy`）优先映射到 `sad`。
- 强度 `min(1.0, score / 3.0)`；返回命中词元组便于调试与未来调参。
- 纯标准库、无 I/O、无随机、无时间依赖。

**验收标准**

1. 5 个类别各有正例全部命中；20 条中性文本全部判定为 `calm`。
2. 表驱动用例覆盖：单关键词、多类别混合（取最高分）、否定短语、emoji、空串/纯空白、超长文本（10k 字不异常）。
3. 同输入连续调用 100 次结果完全相同（确定性）。
4. 强度恒在 `[0, 1]`，且 `matched_keywords` 是命中词的子集。
5. `presentation()` 对 5 类均返回非空名称、单个 emoji、`#RRGGBB` 颜色。
6. `$PY -m pytest` 全绿；`emowall/emotion` 无 Qt / httpx / sqlite 依赖。

---

## Stage 5 — GUI 集成

**目标**：一个真正好用、不卡顿、能取消、能恢复历史的最小聊天界面。

**交付物**

- `emowall/gui/main_window.py`：主窗口（三栏：会话列表 / 消息区 / 输入区）
- `emowall/gui/chat_view.py`：消息气泡渲染（含流式追加、自动滚动、错误条）
- `emowall/gui/session_panel.py`：新建 / 切换 / 重命名 / 删除会话
- `emowall/gui/settings_dialog.py`：地址、模型（下拉取自 `/api/tags`）、温度、上下文预算
- `emowall/gui/emotion_widget.py`：5 表情指示器（emoji + 名称 + 主色）
- `emowall/gui/worker.py`：`ChatWorker(QObject)` + `QThread` 编排与取消
- `emowall/gui/db_service.py`：`StorageService(QThread)` 独占数据库连接，按队列执行读写并回传结果
- `emowall/app.py`：组合根（`python -m emowall` 入口）
- `emowall/__main__.py`
- `tests/test_gui_imports.py`（无显示器环境下只做导入/结构守护，不跑事件循环）

**技术要点**

- 主线程只做 UI；`ChatWorker` 通过 `moveToThread` 运行，信号：`chunk(str) / finished(stats, emotion) / failed(str) / cancelled()`。
- 数据库工作线程（独立 `QThread`）：`StorageService` 在 `run()` 内打开连接、`finally` 关闭；所有读写经信号投递，主线程不调用 repository。
- 「生成中」状态：发送键变「停止」，输入框保留可编辑但不可重复发送。
- 冷启动提示：首块到达前显示「模型加载中…」（因为 qwen3:8b 冷启动约 40 s）。
- 失败分类提示：连接失败 → 「Ollama 未启动？点击查看启动方法」；模型缺失 → 「模型未安装」+ 建议命令。
- 关闭窗口：先取消生成并等待 AI 线程结束 → 投递 `close()` 并等待 DB 线程退出 → 关闭窗口。

**验收标准**

1. `$PY -m emowall` 启动主窗口，默认读取配置；无 Ollama 时窗口正常打开并显示可理解的错误提示（不崩溃）。
2. 提问后回复**逐字流入**气泡；生成过程中窗口可拖动/切换会话（证明主线程未阻塞）。
3. 冷启动（先 `ollama stop qwen3:8b`）首问显示「加载中」，40 s 内不误判失败。
4. 点击「停止」→ 1 s 内停止输出，已生成部分保留在界面且入库；再次发送正常。
5. 新建会话 → 对话 → 关闭应用 → 重启 → 会话出现在列表，点开历史消息与表情完整恢复。
6. 修改设置（地址填错 / 模型换名）→ 保存后立即生效；错误地址给出提示，不崩溃。
7. 每条 AI 回复后有 5 种表情之一显示，且与 `emotion` 层的单测结论一致。
8. `$PY -m pytest` 全绿；`grep -rn "PySide6" emowall/ai emowall/storage emowall/config emowall/emotion` 无结果。
9. 人工检查：无空白窗格、无占位文字、长消息自动换行横向不滚动、滚动条跟随到底部。
10. 主线程零数据库访问：日志显示所有 SQL 都在 DB 工作线程执行，主线程从未调用 repository（可用仓储包装计数验证）。

---

## Stage 6 — 打包与 V0.1 验收

**目标**：双击即可运行的 Windows EXE，并完成 V0.1 功能验收清单。

**交付物**

- `build/emowall.spec`（PyInstaller 配置：`--noconsole`、onedir、排除无用 Qt 模块）
- `scripts/build_exe.ps1`（一键构建 + 版本号 + 产物校验）
- `docs/RELEASE_V0.1.md`（构建步骤、实测体积、启动时间、已知限制）
- `docs/ACCEPTANCE_V0.1.md`（10 项功能需求逐条验收记录）
- 根目录 `main.py`（打包入口）

**技术要点**

- 先用 **onedir**（启动快、误报少），再评估 `--onefile`；两者都记录体积。
- 排除 `PySide6.QtWebEngine*`、`Qt3D`、`QtMultimedia` 等未用模块以缩小体积。
- 用户数据不进安装目录：仍写 `%APPDATA%\EmoWall`。
- 版本信息：文件属性里写入 `0.1.0`、产品名 `EmoWall AI`。

**验收标准**

1. `.\scripts\build_exe.ps1` 成功产出 `dist\EmoWallAI\EmoWallAI.exe`，构建日志无 ERROR。
2. 双击 EXE 无控制台窗口，主界面正常显示；冷启动 ≤ 8 s（本机实测并记录）。
3. EXE 内完成一次真实对话（流式 + 取消 + 表情 + 历史恢复），与源码运行表现一致。
4. 删除 `%APPDATA%\EmoWall` 后首次运行自动重建配置与数据库。
5. 产物中不含 `.py` 源码、不含密钥、不含本机绝对路径（抽查 `strings` 与 `config`）。
6. `docs/ACCEPTANCE_V0.1.md` 中 10 项功能需求全部勾选并附证据（截图/日志/命令）。
7. 打 tag `v0.1.0`，提交信息符合约定；README 更新「运行方式（源码 / EXE）」。

---

## 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 冷启动 40 s 被误判为卡死 | 用户以为崩溃、重复点击 | 「加载中」状态 + 取消可用 + 不设首包短超时（已写入架构） |
| 取消时 httpx 在另一线程关闭响应 | 偶发异常未分类 | Stage 2 专项测试：取消点覆盖读块中/加载中；统一映射 `CancelledError` |
| OneDrive 同步 `.venv` / `.git` | 文件锁、同步冲突 | `.gitignore` 已排除；建议暂停该目录同步或迁移到 `C:\dev\` |
| PySide6 体积大、打包后更大 | EXE 体积 100 MB+ | 排除未用 Qt 模块；onedir 优先；在 RELEASE 中如实记录 |
| 真实 Ollama 联调依赖本机服务 | CI 不可复现 | 全部核心测试用 MockTransport；集成测试单独标记 |
| 情绪规则过硬 | 判定不准 | V0.1 接受规则法；预留 `source` 字段，未来换模型打分不破坏接口 |

---

## 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-10-22 | 初始计划；完成 Stage 0 |
| 2026-10-22 | Stage 0 工程修复：统一 Qt 允许范围、数据库改为独立工作线程、统一 Python 3.12 + uv 环境、加强架构/文档/脚本测试 |
| 2026-10-22 | 完成 Stage 1 配置系统：数据结构与校验、原子读写、损坏恢复、未知字段保留、版本兼容；新增 ADR-0001 |
| 2026-10-23 | 完成 Stage 2 AI 核心：Ollama 流式传输与 NDJSON 解析、取消令牌、上下文裁剪、错误分类、配置注入、真实联调；新增 ADR-0002 |
