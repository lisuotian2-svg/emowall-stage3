# Stage 3 Storage 第四轮修复与验证补充记录

日期：2026-10-24（Asia/Shanghai）。分支：`feature/stage3-storage`。HEAD：`2ddbdcd86b6ee83d0b2bea004e1d4607856d1882`。

**本会话交接结论：NEEDS FIX。** 已确认的两个 Major 的专项回归通过，但 ISO-8601 承诺范围及执行期间出现的并行编辑尚未确认。不能据当前选定输入的测试全绿认定 F-03 全部边界已关闭。不宣布 Stage 3 Storage PASS，不进入 Task 6。

## 1. 前置检查、证据来源和文件保护

已读取 AGENTS.md、v1.2 契约、threading-model.md、module-ownership.md、data-models.md、ARCHITECTURE.md、ROUND2_FIXES.md、database.py、repository.py 和 test_storage.py。第三次独立审查报告全文未在项目及其父工作目录找到；本次依据用户提供的第三轮审查结论与实际运行复现，不声称已经读到报告全文。

初始状态：3 个已跟踪文件有改动（AGENTS.md、HANDOVER.md、storage/__init__.py），7 个文件未跟踪。开始编辑前，在忽略目录 `.tmp/round4-2213f2af04f34493a544d2a99b02727a/before/` 保存了 57 个项目文件的内容副本与 SHA-256 清单。最终核对这些文件，只有 repository.py 和 test_storage.py 内容变化；其他初始文件均保留且哈希不变。没有删除未知文件、暂存既有改动、提交、推送或修改标签。

本会话先增加 90 项参数化运行实例，再修复五个写方法。执行期间，list_recent() 及 4 项额外测试实例在没有本会话对应写入调用的情况下出现变动，随后出现 ROUND4_FIXES.md。本会话完整保留这些内容，已向用户提出并行编辑确认。本文件单独记录本会话实测证据，不覆盖 ROUND4_FIXES.md；两份报告的“开始时”是不同时间点，不能混用其修复前统计。

## 2. 失败测试 → 最小修复 → 再验证

### 2.1 初次真正的修复前测试

在修改 repository.py 前增加 7 个测试方法、90 项运行实例，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -k Round4 --tb=short -rf
```

结果：**56 passed / 34 failed / 0 skipped / 158 deselected**。JUnit 证据：`pre-fix.xml`；文本：`pre-fix.txt`。

- 排序测试：27 项中 11 项失败。包括案例 A、案例 B、相差 1 微秒、秒与微秒、同秒 2/4/5 位小数、历史库重开和非法时间文本。
- 写方法测试：63 项中 23 项失败。五方法的 ProgrammingError 与 InterfaceError 执行/提交阶段共 20 项，加真实非法参数绑定 3 项。失败表现为 StorageIOError 误映射，或 InterfaceError 透传后遗留未回滚事务。
- 案例 A：先插入 `.123100Z`、后插入 `.123Z`，旧查询得到 older/newer，期望 newer/older。
- 案例 B：先插入 `.123200Z`、后插入 `.123100Z`，旧查询得到 older/newer，期望 newer/older。
- 每组同时测试两种插入顺序，避免 rowid 恰好正确而掩盖缺陷；同时验证 limit=1 与原始返回时间文本。

### 2.2 写方法最小修复后的测试

在五个方法的 DatabaseError 分支之前加入：

```python
except (sqlite3.ProgrammingError, sqlite3.InterfaceError):
    conn.rollback()
    raise
```

没有改变公共签名、F-01 守卫位置、F-02 的 UPDATE → SELECT → COMMIT 顺序。写方法专项实测：**63 passed / 0 failed / 0 skipped / 185 deselected**。

### 2.3 对最终 94 项测试重放最初实现

额外 4 项实例进入工作区后，用开始时保存的原始 repository.py 在独立测试进程内执行最终测试；只替换进程内模块对象，不回写源文件：

```powershell
.\.venv\Scripts\python.exe .tmp/round4-2213f2af04f34493a544d2a99b02727a/replay_before.py
```

结果：**58 passed / 36 failed / 0 skipped / 158 deselected**。其中排序 13 失败、写方法 23 失败。证据为 `pre-final-tests.xml` 与 `pre-final-tests.txt`。这是补充重放证据，不能替代 §2.1 真实先写失败测试的时间顺序记录。

当前实现运行相同最终专项：**94 passed / 0 failed / 0 skipped / 158 deselected**，证据 `round4-final.xml`。

## 3. 当前排序算法、固定宽度研究及精度边界

当前 SQL 用两个 CTE 提取 Z 或 +00:00 后缀及原始小数文本。通过秒字段与 SQLite 日期解析结果一致性、数字字符检查验证当前支持的形式；生成：

```text
YYYY-MM-DDTHH:MM:SS + '.' + rtrim(原始小数, '0') + '/'
```

`/` 的字符序小于 `0` 至 `9`，所以短小数的结束位置早于任何后续有效位；尾零去除使同刻不同精度得到同一键。按键 DESC、rowid DESC 排序，最后 LIMIT。没有把小数交给 `%f` 或浮点数排序。秒字段验证使用 `%S`，实际排序的小数仍来自原文。正常写入依旧返回原毫秒 Z 时间戳；读取返回原始 created_at/updated_at，未迁移或更新历史数据。两次重开、整库 iterdump 一致性、同刻反复查询和 limit 已验证。

研究的固定宽度候选为统一六位小数的 UTC 文本键。1,000 行、秒至微秒混合数据的完整顺序验证通过。但固定六位会合并 `.123456788Z` 和 `.123456789Z`，因此不能在契约未限定最大小数位时采用截断。当前变长文本键保留九位小数，并不把超过六位擅自定义为非法。

SQLite 官方文档说明 `%f` 输出为 SS.SSS，日期函数支持的 ISO 文本只是 ISO-8601 的子集，不能从“SQLite 能解析”推导“契约允许的全部表示都受支持”。[SQLite 日期与时间函数](https://www.sqlite.org/lang_datefunc.html)。

### 3.1 性能与查询计划（本会话实测）

隔离的 SQLite `:memory:`，SQLite 3.53.1；limit=50，15 次中位数；数据每 9 行共享秒字段，含秒、毫秒、微秒、九位小数和 +00:00，故意让较旧记录后插入。完整排序与 top 50 均用“整数日序/秒数 × 10^9 + 原始九位小数整数，随后 rowid”作为独立判据；没有用浮点时间或会截断九位小数的 datetime 作为该数据集的精度判据。

| 方案 | 200 行 ms | 1,000 行 ms | 5,000 行 ms | 20,000 行 ms | 完整精度排序 |
|---|---:|---:|---:|---:|---|
| 原 HYBRID | 0.3356 | 1.4773 | 7.5867 | 28.9169 | 各规模均错误 |
| 固定六位候选 | 0.8062 | 3.3162 | 16.2995 | 64.5921 | 九位小数处错误；≤6 位单独控制组正确 |
| 当前精确文本键 | 0.7822 | 3.6012 | 16.4345 | 66.6531 | 各规模完整排序和 top 50 均正确 |
| julianday 负对照 | 0.1779 | 0.7865 | 3.3749 | 12.9867 | 各规模均错误 |
| 原始列字符串负对照 | 0.0940 | 0.0980 | 0.0958 | 0.0992 | 各规模均错误 |

原 HYBRID、固定六位、当前文本键和 julianday 的计划均为 `SCAN conversations` + `USE TEMP B-TREE FOR ORDER BY`。原始列字符串方案使用 idx_conversations_updated_at，但有次级排序临时结构且结果不正确。没有增加表达式索引或更改 schema。当前方案在 5,000 行约为原 HYBRID 的 2.17 倍；这是准确性成本，20,000 行约 67 ms 不能被当成无限数据量性能保证。证据：`benchmark.py` 与 `benchmark.json`。

### 3.2 尚未关闭的 ISO 契约问题（不能以测试全绿掩盖）

冻结契约只写 ISO-8601 UTC，未明确限定扩展式、Z/+00:00 或小数分隔符。已向用户询问，尚未收到明确范围。当前 SQL 对以下四种表示均将较新的记录排在较旧的标准 Z 记录之后：

| 较新的 UTC 表示 | 当前输出 | 时间先后期望 |
|---|---|---|
| `20261024T120000.123200Z` | older, newer | newer, older |
| `2026-10-24T12:00:00,123200Z` | older, newer | newer, older |
| `2026-10-24T12:00:00.123200+0000` | older, newer | newer, older |
| `2026-W43-6T12:00:00.123200Z` | older, newer | newer, older |

共同较旧值为 `2026-10-24T12:00:00.123100Z`。诊断先用 Python 3.12 fromisoformat 确认这些值较新，再执行当前实际 SQL；结果写入 `iso-scope-probe.json`。这 4 次诊断不计入 pytest 的通过数量。Python 官方也列明基本式、周日期等解析能力及其限制。[Python 3.12 datetime 文档](https://docs.python.org/3.12/library/datetime.html#datetime.datetime.fromisoformat)。

这些表示不能被本会话单方面划为“非法数据”。需要架构师确认承诺输入范围；若属于冻结承诺，应先补正式失败测试再修复其排序。序数日期、24:00、闰秒等范围也未裁决，未宣称支持。本会话因未确认的并行编辑而保留当前查询，不覆盖其他执行上下文的改动。

## 4. 五个写方法逐项检查

| 写方法 | ProgrammingError/InterfaceError 执行与提交透传 | I/O 映射及原始 cause | 失败回滚 | 外部事务保护 |
|---|---|---|---|---|
| create | 通过 | 通过 | 通过 | 通过 |
| rename | 通过 | 通过 | 通过 | 通过 |
| delete | 通过 | 通过 | 通过 | 通过 |
| append_message | 通过 | 通过 | 通过 | 通过 |
| update_message_emotion | 通过 | 通过 | 通过 | 通过 |

异常分支顺序检查与运行测试均已完成。50 项矩阵覆盖 5 方法 × 2 故障阶段 × 5 异常类型；ProgrammingError 和 InterfaceError 断言返回同一个异常对象，OperationalError / DatabaseError / OSError 断言 StorageIOError.__cause__ 是原对象。执行阶段注入前先在真实连接建立未提交变更；提交阶段在方法已完成其写 SQL 后注入。失败后检查事务已结束、完整 iterdump 不变，并用另一个连接观察无部分提交。

另外 3 项用真正不支持的 sqlite 参数绑定（object()）触发 ProgrammingError；10 项覆盖五方法对外部活动事务的拒绝，断言不执行任何 SQL、不提交也不回滚，调用方随后自行 commit/rollback 的两种结局都正确。没有只检查源代码文本。

## 5. F-01 批准与实施状态

ROUND2_FIXES.md 明确记载方案 B 待批准；本次未找到主架构师正式批准记录。用户本轮任务要求先确认，不等同于无条件批准方案 B。已提出确认问题；**未实施分类变化**，保留 StorageIOError 与原有事务边界。上述 10 项同时锁定当前异常类型和外部事务不变性。未新增公共异常类型，也未改变冻结异常继承层级。

若方案 B 已正式批准，需要提供批准记录或明确确认，再更新守卫及相关异常类型断言；不应从“主架构师建议”推定为正式批准。

## 6. 新增、保留与全部测试结果

- 原有 Storage：158 个测试方法/158 项运行实例。
- 最终 Storage：166 个测试方法/252 项运行实例。
- **新增 8 个测试方法、94 项运行实例；替换 0、删除 0，净增 94 项**。其中本会话最初新增 7 方法/90 实例；执行期间额外出现 1 方法与 4 实例，已保留并验证。
- 排序 31 项；写方法 63 项。原有 158 项均保留。

| 实际执行范围 | 通过 | 失败 | 跳过 | 未选 |
|---|---:|---:|---:|---:|
| 初次修复前专项（90 项） | 56 | 34 | 0 | 158 |
| 原实现重放最终专项（94 项） | 58 | 36 | 0 | 158 |
| 修复后最终专项 | 94 | 0 | 0 | 158 |
| 写方法修复后专项（当时共 248 项 Storage） | 63 | 0 | 0 | 185 |
| 最终 Storage 完整 | 252 | 0 | 0 | 0 |
| 架构守护 | 22 | 0 | 0 | 0 |
| Stage 1/2 指定文件回归 | 166 | 0 | 0 | 10 |
| 默认全量基线（修复前，受限环境） | 408 | 1 | 1 | 10 |
| 默认全量最终回归（允许本机回环） | 503 | 0 | 1 | 10 |
| 严格零连接全量（排除 integration/local_network） | 501 | 0 | 1 | 12 |

默认基线失败是 test_check_env.py::test_http_json_rejects_non_json_payload 的 127.0.0.1 连接报 WinError 10013。自动审批允许在受限环境之外运行原测试配置后，默认全量通过；没有修改测试或 Windows ACL。严格零连接运行仍使用原 conftest.py socket 守卫。没有访问真实 Ollama 或外网服务。跳过的 1 项为缺少 PySide6 的包级 GUI 导入测试；不是 Storage 跳过。

最终全量收集总数为 514；默认选择 504（503 通过 + 1 跳过），严格零连接选择 502（501 通过 + 1 跳过）。

复现命令（均使用项目 .venv Python）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -k Round4 --tb=short -rfs
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py --tb=short -rfs
.\.venv\Scripts\python.exe -m pytest tests/test_architecture.py --tb=short -rfs
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_ai_client.py tests/test_ai_config.py tests/test_ai_engine.py tests/test_ai_probe.py tests/test_ai_integration.py --tb=short -rfs
.\.venv\Scripts\python.exe -m pytest --tb=short -rfs
.\.venv\Scripts\python.exe -m pytest -m 'not integration and not local_network' --tb=short -rfs
```

各运行的 JUnit XML 均保留于上述忽略证据目录。

## 7. 契约一致性、文件清单及 Git 状态

构造函数及 Repository 八个公共方法的 inspect.signature 与开始时快照完全一致。storage 公共导出、数据模型和异常类文件未变化。以下四文档与 stage3-contract-v1.2 标签的 Git blob **逐字节一致**：stage3-contract-v1.md、threading-model.md、module-ownership.md、data-models.md。

Git 已跟踪差异 `git diff --check` 通过；对两份未跟踪代码/测试相对初始快照的差异也没有空白错误。原有 Stage 1/2 代码、架构测试、共享夹具及开发计划均未修改；未推进阶段。

| 文件 | 本次交接内容 |
|---|---|
| emowall/storage/repository.py | 本会话增加五写方法异常透传与回滚；保留执行期间出现的精确文本排序 SQL |
| tests/test_storage.py | 原 158 项保留；新增专项最终 94 项运行实例 |
| ROUND4_FIXES.md | 执行期间出现的另一份报告，已读取并保留，未覆盖 |
| ROUND4_VALIDATION.md | 本会话的补充证据、范围诊断和交接结论 |

最终 Git 状态应为原来的 3 个 M 加 7 个 ??，另新增两份第四轮报告 ??。repository.py、test_storage.py 在本轮开始和结束都属于未跟踪文件，因此普通 git diff 不展示它们的内容变化，不能据此称“工作区干净”。已用开始时副本进行差异和哈希核对。未执行 Git 提交，未宣称阶段完成。

## 8. 剩余风险、接口申请与交接条件

1. **待确认 ISO 范围**：§3.2 四种表示已有运行时排序反例。没有获得缩小 ISO-8601 UTC 支持范围的授权，不能关闭这一项。
2. **待确认并行编辑**：保留当前 SQL、附加测试和 ROUND4_FIXES.md；需协调所有者后继续修改共享文件。
3. **F-01 正式批准缺失**：按本轮指令保留现状；若批准方案 B，再实施与补测。
4. **性能与容量**：当前精确排序仍为全表扫描及临时 B 树；20,000 行约 67 ms，未验证更大数据库、低速磁盘或生产 UI 响应时延。
5. **异常中的异常**：本次验证连接仍可回滚时的执行/提交错误；未验证 rollback() 本身失败或连接在故障期间被关闭时的异常遮蔽。
6. **环境与验收边界**：未安装 PySide6；未做真实用户数据库、GUI 或真实 Ollama 验收，这些也不属于本轮授权工作。

已落地修复没有公共接口变更，不需要新增接口变更申请。F-01 仍需正式裁决；如果通过“只支持扩展式 Z/+00:00”排除 §3.2 的表示来解决问题，会缩小未限定的冻结承诺，必须先由架构师明确批准，不能当作内部实现选择。

**NEEDS FIX**。停止本轮写入，等待契约范围/并行编辑确认及独立审查反馈；不自行宣布 Stage 3 Storage PASS，不进入 Task 6。
