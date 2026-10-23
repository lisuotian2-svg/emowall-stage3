# Stage 2 独立审查整改交付总结

日期：2026-10-23（Asia/Shanghai）。基线：`fca909e`，分支：`feature/stage2-ai-core`。
任务来源：独立审查 CONDITIONAL PASS 后的 G1 → G2 → G3 → G4；未获取额外独立审查报告文件，
按任务中给出的 P1-1/P1-2/P1-3 描述逐项核对实际代码，未把描述直接当成事实修改。

**结论：技术整改已交付；Codex 在 G4 提交前中断，DeepSeek 已续接复验并补完 G4 提交。仍待独立复审与用户确认，Stage 3 尚未获准开始。**
公开 API、依赖声明、Stage 1 配置实现及 Stage 2 上下文功能未改变。
未实现数据库、GUI、情绪系统、Provider 注册表、DI 容器或事件总线。

## 1. 问题与复现证据

| 问题 | 独立验证及整改前表现 | 最小处理 |
| --- | --- | --- |
| G1 / P1-1 | `cancel()` 清空 `_closers`，暂停在首块后的旧生成器尚未退出，`reset()` 却不抛错；仅保留资源登记仍不能覆盖反登记到异常分类之间的窗口 | 保留资源登记，增加内部活动生成计数及取消清理状态；保护延续至最外层 `finally` |
| G1 相关分类 | 取消触发安静 EOF 时原代码抛 `StreamInterruptedError`；错误正文读取取消也可能报 HTTP 错误 | `AIError` 分支优先检查取消状态，不改变正常错误分类 |
| G2 / P1-2 | 注入模式不登记底层客户端关闭函数；等待响应头时取消既不能释放假传输等待，也不能关闭外部客户端 | 明确所有权及能力边界，生产路径限定默认自有客户端、独占单路；没有声称修好了注入模式底层取消 |
| G3 / P1-3 | 原交付曾记录 8 passed；后续交付检查为 1 passed、7 skipped，其中唯一 passed 是不发网络请求的关闭测试 | 将关闭测试迁入离线组，新增 3 项真实网络测试并实际重跑 |
| 附加资源检查 | 现有 `yield from` / `with` 结构支持显式关闭，无需重构 | 补充 client/engine、两种所有权的提前关闭回归与真实响应检查 |

G1 先加测试、后修生产代码。以下命令在旧实现上得到 **6 failed / 63 deselected（1.47 s）**：

```powershell
& $PY -m pytest tests/test_ai_client.py -k 'reset_after_cancel_waits or reset_is_blocked_until or cancelled_eof or cancelled_registration or reset_waits_for_cancel'
```

失败包括自有/注入两种挂起生成器 reset、资源反登记后的异常分类窗口、安静 EOF、取消后注册、
关闭回调尚未返回时 reset。随后补充空 EOF 与错误正文取消分支，共新增 8 个 G1 用例。
定向测试修复后为 71 passed。没有降低阈值、跳过失败测试或放宽原有断言。

## 2. 修改文件及关键行为

| 任务 | 文件 | 关键变化 |
| --- | --- | --- |
| G1 | `emowall/ai/cancel.py`、`emowall/ai/client.py`、`tests/test_ai_client.py`、`docs/DEVELOPMENT_PLAN.md` | 生成开始时原子检查/登记；异常分类和资源收尾之后才释放活动状态；cancel 保留登记直到反登记；正在执行关闭回调时也禁止 reset |
| G2 | `emowall/ai/client.py`、`tests/test_ai_client.py`、`docs/ARCHITECTURE.md`、`docs/adr/0002-ai-core-boundaries-and-cancellation.md`、`docs/DEVELOPMENT_PLAN.md` | 所有权文档、未来 Stage 5 工作线程契约、注入限制及提前关闭验证 |
| G3 | `tests/test_ai_integration.py`、`tests/test_ai_client.py`、`docs/DEVELOPMENT_PLAN.md` | 真实冷启动/连续取消/提前关闭；客户端关闭测试迁移；fixture 和旧取消用例补显式 finally 清理 |
| G4 | `README.md`、`docs/STAGE2_HANDOFF.md`、`docs/DEVELOPMENT_PLAN.md`、`docs/ARCHITECTURE.md`、ADR-0002、本报告、`tests/test_docs.py` | 历史与当前分开、统一事实、递归检查 ADR 文档链接及路径；保留历史记录 |

`cancel()` 返回并不等于旧生成退出；收到 `done` 块也不等于生成器清理完成。调用方须消费完或显式
`generator.close()`，等旧生成及取消回调结束后再复用令牌、客户端或发起下一轮。
自有客户端由 `OllamaClient` 创建并关闭，取消后按需重建。外部客户端由注入者创建和最终关闭，
核心只关闭收到的响应；响应头之前只能等外部请求返回/超时/外部中断，不满足未来 GUI 生产取消要求。

## 3. 测试增量与分组

- G1：新增 8 例，覆盖两种所有权下取消后 reset、分类窗口、空/部分 EOF、错误正文、迟注册与回调生命周期。
- G2：新增 7 例，覆盖响应头前注入模式限制、外部关闭不重建、上下文管理责任，以及 client/engine × 自有/注入的 4 种提前关闭。
- G3：新增 3 项真实测试；原 `test_close_releases_owned_client` 从 integration 移到离线文件，测试逻辑保留。
- 文档：`test_docs.py` 改为递归枚举 `docs/**/*.md`，把 ADR-0001/0002 纳入既有链接、路径与过期表述检查。
- 当前 AI 测试库存：client **79**、engine **35**、config 映射 **6**、probe **3**、真实 integration **10**。

默认 pytest 排除 integration，但包含 **2 项 `local_network` 本机回环测试**；严格离线组同时排除它们。
唯一常规 skipped 是 `test_gui_layer_importable_when_qt_installed`，因为未安装 PySide6；这不是通过，
不影响当前纯 AI 核心的零 Qt 导入验证，也不代表完成 GUI 验收。

## 4. 最终验收命令与结果

以下命令均从项目根目录运行，`$PY = '.\.venv\Scripts\python.exe'`，设置 `$env:PYTHONUTF8='1'`。
默认测试及真实集成在允许本机回环连接的执行环境运行；严格离线在沙箱内运行，socket 守卫保持开启。
下表是 Codex 在 G4 提交前（2026-10-23 19:50 前后）的实际运行结果；DeepSeek 续接后的独立重跑见 §11。

| 命令 | 最终结果 | 耗时 |
| --- | --- | --- |
| `& $PY -m pytest` | **244 passed, 1 skipped, 10 deselected** | 20.85 s |
| `& $PY -m pytest -m 'not integration and not local_network'` | **242 passed, 1 skipped, 12 deselected** | 17.64 s |
| `& $PY -m pytest -m integration -vv -o log_cli=true --log-cli-level=INFO --durations=20 --junitxml=.tmp/stage2-final-integration.xml -o junit_family=legacy` | **10 passed, 0 skipped, 245 deselected** | 8.27 s |
| `& $PY -m pytest tests/test_ai_client.py -k 'cancel or reset or close or recover or injected or generator'` | **27 passed, 52 deselected** | 0.87 s |
| `& $PY -m pytest tests/test_architecture.py` | **22 passed** | 0.82 s |
| `& $PY -m pytest tests/test_docs.py` | **34 passed** | 0.31 s |

共收集 **255** 项：默认选择 245 项（244 passed + 1 skipped），真实 integration 10 项。
最终总数增加也包含新增文档和链接展开的参数化检查；G1–G3 检查点的历史数量不应覆盖此表。

## 5. 真实 Ollama 验收与资源证据

环境：Windows 11、Python 3.12.15、httpx 0.28.1、httpcore 1.0.9、Ollama 0.40.6、
qwen3:8b（Q4_K_M、8.2B）、RTX 5060 Laptop GPU。测试使用本机 `127.0.0.1:11434`，上下文 4096。

初始两次只读采样均为 `/api/ps` 空列表，无活动请求连接，仅 Ollama 监听；GPU 3%、940 MiB。
后续冷启动重跑仅在确认无活动连接后卸载本任务加载的模型；不停止 Ollama 服务、不删除模型。
Ollama API 没有独占锁，这些采样是当时未观察到其他任务的证据，并不保证其他程序不能随后发请求。

冷启动定义为模型未驻留后的加载请求，不等同于重启机器或清除 OS 文件缓存。测试观察真实 HTTP/1
等待响应头 trace，等待 0.25 s 后确认还没有响应头，再调用取消；不替换传输、不插入人为阻塞。
采用高精度单调时钟 `perf_counter`，取 `cancel()` 返回和消费线程最终退出的较晚者，严格要求 **< 1.0 s**。

G3 最终检查点：**10 passed、0 skipped、233 deselected，9.55 s**。

| 测量 | G3 检查点实测 |
| --- | --- |
| 冷启动取消总耗时 | 0.0004907 s（约 0.491 ms） |
| 消费线程退出 | 0.0003872 s |
| cancel 调用返回 | 0.0004907 s |
| 连续三轮取消 | 0.0004054 / 0.0004396 / 0.0004031 s |
| 冷启动分类 | `ReadError` → `CancelledError`，0 个块，无提前响应头 |
| 恢复 | 每轮通过同一 OllamaClient 重建底层客户端并完成正常请求 |

最终 G4 复测：**10 passed、0 skipped、245 deselected，8.27 s**。
冷启动取消总耗时 **0.0004380 s（0.438 ms）**，其中消费线程退出 **0.0003662 s**、
cancel 返回 **0.0004380 s**；三轮取消 **0.0004064 / 0.0002664 / 0.0002701 s**，每轮恢复成功。
冷启动仍为 `ReadError` → `CancelledError`、零块，1 s 阈值未改。

资源断言覆盖：响应 `is_closed`、旧客户端关闭、旧连接对象 `is_closed()`、池连接与活动请求清空、
令牌可 reset；恢复后最多保留一个正常 IDLE 连接，fixture 退出时全部关闭。G3 后系统采样活动连接为 **0**。
模型缓存驻留属于 Ollama keep-alive，不等同于 HTTP 泄漏；本测试测量客户端退出，不证明服务端 GPU
计算也在相同微秒数内结束。连续取消测试在消费者取得首块后取消，冷启动测试覆盖真实跨线程阻塞读取。

复现前置步骤（先确保没有其他模型任务；有活动连接时停止，不卸载）：

```powershell
$connections = @(Get-NetTCPConnection -LocalPort 11434 -State Established -ErrorAction SilentlyContinue)
if ($connections.Count -gt 0) { throw 'Ollama 有活动连接，停止冷启动准备' }
ollama stop qwen3:8b
if ($LASTEXITCODE -ne 0) { throw '模型卸载失败' }
Invoke-RestMethod http://127.0.0.1:11434/api/ps
# 确认 models 为空，再运行上表 integration 命令。
```

冷启动测试自身不自动卸载模型；前置条件不满足会失败。服务不可用时夹具会明确 skipped，不能用于验收通过。
完整原始 JUnit 文件位于本地忽略目录 `.tmp/`，不提交含个人绝对路径的原始 XML；报告保留指标与可复现命令。

## 6. 历史记录与本次失败处理

| 时间/检查点（均保留） | 实际结果与解释 |
| --- | --- |
| Stage 2 原交付，2026-10-23 | 计划记录 211 passed、1 skipped，integration 8 passed；其中 1 个关闭用例无网络，不等于 8 项真实网络验收 |
| 原交付检查，2026-10-23 | 默认 215 passed、1 skipped、8 deselected；严格离线 213 passed、1 skipped、10 deselected；integration 1 passed、7 skipped（服务不可用） |
| 本次 G1 修复前 | 新增首批 6 例全部失败，复现真实生命周期/分类问题 |
| 本次 G1 沙箱默认回归 | 1 failed、220 passed、1 skipped、8 deselected，回环连接 WinError 10013；没有忽略失败，允许回环后原样重跑通过 |
| 本次 G1 完成 | client 71 passed；默认 223 passed、1 skipped、8 deselected；严格离线 221 passed、1 skipped、10 deselected |
| 本次 G2 检查点 | client 78 passed；默认 230 passed、1 skipped、8 deselected；文档/架构 44 passed |
| 本次 G3 首轮 | 1 failed、9 passed、233 deselected，14.63 s；新增冷启动测试误把 `_http_json` 的 `(status, payload)` 当字典，尚未执行冷启动取消，修正测试后重跑 |
| 本次 G3 修正后 | 10 passed、233 deselected，7.39 s；进一步将取消计时取两个完成点最大值、补池清理断言后为 10 passed，9.55 s |
| 本次 G3 回归 | 默认 232 passed、1 skipped、10 deselected（27.98 s）；严格离线 230 passed、1 skipped、12 deselected（19.01 s） |

上述各检查点数量不同是测试增量与文档参数展开所致。当前事实以上方最终验收表为准。

## 7. Git 提交及范围

| 任务 | 提交 | 内容 |
| --- | --- | --- |
| G1 | `9a6933e` | `fix(ai): 修复取消令牌重置与异常分类竞态` |
| G2 | `246a954` | `docs(ai): 明确 HTTP 客户端所有权及取消边界` |
| G3 | `ea9df21` | `test(ai): 验证真实 Ollama 冷启动取消与资源恢复` |
| G4 | 本报告所在提交（DeepSeek 续接提交），使用 `git log -1 --oneline` 查询 | `docs(stage2): 同步整改交付证据与准入状态` |

初始工作区干净；未切换或重写原分支历史。最终核对 `git diff --check`、`git status --short`、
`git log -4 --oneline`、`git diff fca909e..HEAD --stat`。全部改动限 AI 取消、测试及文档；
无新增第三方依赖、无数据文件、无临时文件进入提交。

## 8. 已知限制与尚未完成工作

1. 注入客户端响应头前的及时取消仍不支持；已明确排除未来 GUI 生产路径，不把文档限制算底层修复。
2. 自有模式 TCP/TLS 建连尚未完成时不保证立即中断；本次通过的是 Windows 本机 Ollama 默认 HTTP 传输。
3. 单实例单路生成仍为调用契约；不支持并发复用客户端，不增加运行时并发框架。
4. 消费者放弃生成器却不显式 close 仍可能占用资源；本次验证的是显式提前关闭行为。
5. 未做长时压力/大规模取消测试；资源检查读到了 httpcore 内部状态，升级依赖时应复核测试。
6. 未安装 PySide6，GUI/DB 的部分内容持久化、按钮恢复与线程信号顺序仍是 Stage 5 契约；未提前实现。
7. 原字符预算近似、扩展提供者接口、隐私专项审查等既有长期风险不在本次整改范围。

## 9. 给 DeepSeek 的复审重点

1. 查看 G1 红色复现证据与 `_begin_generation` / 最外层 `finally`，确认 reset 保护跨越资源反登记到异常分类的窗口。
2. 检查 cancel 快照、迟注册、关闭回调和生成器退出的配合；确认取消后 EOF/HTTP 正文错误不丢取消语义。
3. 核对注入模式的测试确实要求等待外部释放，文档未宣称响应头前完整取消；自有模式重建与单路契约一致。
4. 检查真实测试的冷启动前置条件、trace 相位、两个结束时刻最大值、严格 1 s 阈值及未跳过结果。
5. 复核资源指标不仅是 is_closed：还包括旧连接、池中活动请求、线程退出、恢复请求及系统活动连接数。
6. 对照历史与最终测试数量，确认纯本地关闭用例已移出 integration；文档一致性检查已覆盖 ADR。
7. 审查全部范围及 Stage 1/2 回归，确认没有 Stage 3 或 GUI 实现混入。

## 10. 准入决定与验收清单

- [x] 原问题独立验证，G1 首批测试先失败后通过。
- [x] 取消后立即 reset 受保护；旧请求报告 CancelledError；退出后正常请求恢复。
- [x] 所有权、注入限制与未来工作线程契约明确；提前关闭生成器有回归证据。
- [x] 真实服务/模型/占用已检查；冷启动取消及连续恢复实际执行，未提高阈值。
- [x] 保留历史结果、失败记录和未完成工作，未伪造 skipped 为 passed。
- [x] 最终六组验收通过，差异审查通过；G4 与本报告同一提交，提交后核对干净工作区。
- [x] DeepSeek 续接复验（非独立复审）：复核 G1–G4 证据、重跑六组命令、保护未提交内容并补完 G4 提交。
- [ ] 独立复审通过。
- [ ] 用户确认进入 Stage 3。

技术整改通过不等于流程准入。独立复审和用户确认均未完成，**本次停止于 Stage 2 整改交付，不进入 Stage 3**。

## 11. DeepSeek 续接复验记录（2026-10-23）

Codex 在完成 G1–G3 提交并写好 G4 文档后额度中断；中断时工作区有 6 个已修改文件和 1 个未跟踪文件，
全部未提交。DeepSeek 接管后未重置分支、未清理工作区、未改写既有提交，也未修改 `emowall/ai` 生产代码。

### 11.1 接管状态与安全恢复点

- 接管 HEAD：`ea9df21`（`test(ai): 验证真实 Ollama 冷启动取消与资源恢复`），分支 `feature/stage2-ai-core`。
- 未提交：`README.md`、`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT_PLAN.md`、`docs/STAGE2_HANDOFF.md`、
  `docs/adr/0002-ai-core-boundaries-and-cancellation.md`、`tests/test_docs.py` 已修改；
  `docs/STAGE2_REMEDIATION.md` 未跟踪。`git diff --cached` 为空，`git ls-files -u` 无冲突。
- 保护：原文件复制到忽略目录 `.tmp/recovery-20261023-201204/`，保存 tracked patch、SHA-256 与
  `git bundle --all`；另以 `refs/backup/stage2-g4-pre-20261023-201204` 保存 stash 对象。
  上述操作不改变工作区、不移动 HEAD、不删除未跟踪文件。
- 敏感信息：待提交内容仅为文档与文档测试，未发现密钥、令牌或个人绝对路径；未加入数据文件或临时文件。

### 11.2 独立重跑结果（与 §4 的 Codex 记录分开）

环境：Windows 11、Python 3.12.15、Ollama 0.40.6、`qwen3:8b`。运行前确认 11434 无 ESTABLISHED
连接，并用 `ollama stop qwen3:8b` 卸载模型；`/api/ps` 为空后执行，未停止服务、未删除模型。
`$PY = '.\.venv\Scripts\python.exe'`，`$env:PYTHONUTF8='1'`。

| 命令 | DeepSeek 实际结果 | 耗时 |
| --- | --- | --- |
| `$PY -m pytest` | **244 passed, 1 skipped, 10 deselected** | 21.61 s |
| `$PY -m pytest -m "not integration and not local_network"` | **242 passed, 1 skipped, 12 deselected** | 17.92 s |
| `$PY -m pytest -m integration -vv -o log_cli=true` | **10 passed, 0 skipped, 245 deselected** | 11.42 s（首轮）/ 8.96 s（最终） |
| `$PY -m pytest tests/test_ai_client.py -q -k "cancel or reset or close"` | **24 passed, 55 deselected** | 1.10 s |
| `$PY -m pytest tests/test_architecture.py` | **22 passed** | 1.15 s |
| `$PY -m pytest tests/test_docs.py` | **34 passed** | 0.40 s |

真实 integration 两轮明细：冷启动取消总耗时 **0.000431 s / 0.000651 s**，
消费线程退出 **0.0003575 s / 0.0004039 s**，取消调用返回 **0.000431 s / 0.000651 s**；
连续三轮取消首轮 **0.0003611 / 0.0003765 / 0.0003310 s**，最终 **0.0003920 / 0.0003584 / 0.0002806 s**，
每轮恢复成功；冷启动均为 `ReadError` → `CancelledError`，0 个内容块，取消前未收到响应头；
旧客户端、响应和旧连接均关闭，连接池与请求队列为空。JUnit 证据在本地忽略目录
`.tmp/stage2-g4-integration.xml` 与 `.tmp/stage2-g4-final-integration.xml`
（均为 10 tests、0 failures、0 errors、0 skipped）。默认组唯一 skip 仍为
`test_gui_layer_importable_when_qt_installed`（PySide6 未安装），未计为 passed。

### 11.3 结论与仍待验证项

- G1 旧实现（`fca909e`）经静态复核：`cancel()` 清空 `_closers`，`reset()` 只检查 `_closers`，
  因此暂停中的旧生成可被错误重置；历史 6 failed 记录保留在 §1，未重造旧提交。
- G1、G2 的代码与文档行为和 §1–§2 一致；G3 真实用例在本机重跑通过；G4 文档与实现同步。
  默认、严格离线、真实 integration、架构、文档五组计数与 §4 的 Codex 记录一致；integration 耗时差异
  来自本机冷启动加载（简单请求 7.87 s / 6.12 s）。取消专项在 §4 使用更宽的过滤（含 recover/injected/generator），
  为 27 passed；§11.2 按任务指定命令重跑为 24 passed / 55 deselected，两者不是同一筛选。
- 本次是续接复验，不是独立第三方复审。注入模式响应头前取消、TCP/TLS 建连阶段、
  长时间压力测试、GUI/DB 集成仍未验证。
- G4 提交信息为 `docs(stage2): 同步整改交付证据与准入状态`；提交后核对干净工作区。
- 未进入 Stage 3；准入仍由独立复审与用户确认决定。
