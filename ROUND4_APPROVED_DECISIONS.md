# 第四轮批准后修复与最终交接记录

日期：2026-10-24，Asia/Shanghai。分支 `feature/stage3-storage`，HEAD `2ddbdcd86b6ee83d0b2bea004e1d4607856d1882`。

**本报告是项目负责人回复批准之后的最新状态。** ROUND4_FIXES.md 和 ROUND4_VALIDATION.md 保留为批准前不同执行时点的记录，不以其中“F-01 待批准”描述当前状态。

## 1. 冲突调查、暂停与恢复依据

收到指令后暂停 repository.py 写入，只读检查 Git 状态、当前内容、修改时间和哈希，并读取本机同工作目录的会话工具调用元数据。

已定位另一既有对话 `01a16c89-2961-7b73-9825-52cedf8132b4` 在 15:49:33 发起 CTE 补丁，之后增加附加测试与 ROUND4_FIXES.md。确切调用完成时间与文件修改时间吻合。该对话最新执行于 15:59:50 结束。核查全部匹配此工作目录的四份本机会话记录，除当前对话外均已结束；多轮哈希采样没有进一步写入。

先提交 ROUND4_CONFLICT_INVESTIGATION.md 及推荐保留方案，再在写入前再次核对 repository.py 哈希与调查版本一致，才继续已批准的修复。没有撤销或覆盖 CTE SQL，没有发消息给其他对话、终止进程、修改 ACL 或改变 Git 历史。此为恢复时点的静止性确认，不保证其他对话日后不会重新启动。

## 2. F-01 正式批准、依赖检查与实施

项目负责人明确批准方案 B：外部活动事务属于调用方误用，守卫抛 sqlite3.ProgrammingError。记录在非冻结 ADR：

`docs/adr/0003-storage-transaction-ownership.md`

实施前搜索业务源码、测试和文档：没有发现其他业务调用方依赖旧异常分类；五个原有 F-01 测试与一组十项参数化实例期待 StorageIOError，已更新。

最小代码改动仅将 `_ensure_no_external_transaction()` 的拒绝异常及相关 docstring 改为 ProgrammingError。守卫在写方法 try/rollback 范围之外的原有位置，未移动；不执行 SQL、commit 或 rollback。未新增公共异常类型，未改变异常继承层级。

十项运行测试对五个写方法分别覆盖调用方最终 commit/rollback，断言精确异常类型、SQL trace 为空、活动事务仍存在、待提交数据不变、观察连接看不到未提交内容、调用方仍可自行结束事务。五个原有拒绝测试同时通过。

## 3. 新生成时间戳的批准与实施

项目负责人已明确纠正格式笔误：**包含 :SS，统一六位微秒**。生成格式为：

```text
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

`_utcnow()` 移除毫秒截断，保留 strftime 的完整六位微秒。三个固定时钟运行实例覆盖 1、123456、999999 微秒，通过 create、append_message、rename 及重新读取验证公共返回与持久化值精确一致。

只影响新生成的时间文本；旧秒、毫秒、微秒记录不改写。公共字段仍为 ISO-8601 UTC 字符串，方法签名和 Schema 未改变。这一生成精度变化依据本次正式批准，不是擅自改变先前冻结文件。

## 4. 测试先行与准确计数

批准后先更新异常类型期望、添加生成格式测试，在旧代码上执行专项：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py -k 'F01TransactionOwnership or external_transaction_unchanged or ApprovedTimestampFormat' --tb=short -rf
```

**修复前：0 passed / 18 failed / 0 skipped / 237 deselected。** 其中 15 项暴露旧的 StorageIOError 分类，3 项暴露毫秒截断。

**修复后：18 passed / 0 failed / 0 skipped / 237 deselected。** 两阶段 XML 与文本保存于 `.tmp/round4-approved-c6fb51d5e46c4d78a1a038d1d013f9b7/`。

本次批准后增量：新增 1 个测试方法、3 个参数化实例；修改 6 个已有方法的异常类型断言，涉及 15 项实例；没有替换或删除测试。相对整个第四轮初始状态，Storage 测试为 **158 → 167 个方法，158 → 255 项运行实例**：累计新增 9 方法/97 实例，替换 0、删除 0。

新增两份 docs 下的文档还由已有 test_docs.py 自动收集为 2 项文档检查；没有修改该测试文件。整个第四轮全项目实例净增 99（97 Storage + 2 文档），总收集数 **420 → 519**。

## 5. F-03 独立验证、推荐与剩余缺口

CTE SQL 与冲突调查时的查询字符串逐字一致。保留的精确文本键使用原始小数去尾零及 `/` 终止符，随后 rowid DESC，排序后才 LIMIT；没有毫秒截断或浮点时间排序。

批准前同一最终 94 项测试对原始实现重放为 58 通过/36 失败，当前实现为 94 通过；其中排序组 13 项失败 → 31 项通过，五写方法组 23 项失败 → 63 项通过。批准后没有改变 CTE，相关测试随本次 Storage 完整回归再次通过。

本次冲突调查另行独立验证：12,000 行扩展式秒/毫秒/微秒、Z/+00:00，以整数秒与微秒作为判据。CTE 完整排序零错位，HYBRID 有 60 处错位；七个 LIMIT 边界均正确。另验证年份边界、闰日、跨年与 .999999，顺序正确。

性能证据来自不同测试，不混为同一个口径：

- 相同混合数据、limit=50、15 次中位数：5,000 行 CTE 16.4345 ms，HYBRID 7.5867 ms；20,000 行 CTE 66.6531 ms。
- 12,000 行完整取回的单次运行：CTE 64.256 ms，HYBRID 43.394 ms。
- 两方案都为 SCAN conversations + USE TEMP B-TREE FOR ORDER BY，未改变 Schema 或索引。
- 固定六位键对 ≤6 位控制组正确，对九位相邻小数会失去区分；不作为任意 ISO 精度的替代方案。

**推荐保留 CTE 对已确认格式的精确比较，但完整 ISO-8601 承诺仍未闭合。** 当前基本式、逗号小数、+0000、周日期仍有合法较新值被置尾的反例；24:00 与次日零点未归为同刻，已在实际 SQL 运行确认。同刻插入 next-day 后再插入 end-day 时，应按 rowid 得到 end-day/next-day，当前却得到 next-day/end-day。

数据调查未发现项目非临时 .db，也未发现当前配置数据目录或 emowall.db；未创建或改写用户目录。因此没有真实历史数据库可用于判断这些形式的实际使用频率，不能据此排除它们。

已正式提出非冻结契约澄清申请：

`docs/contracts/change-requests/2026-10-24-storage-timestamp-compatibility.md`

申请列明基本式、逗号小数、超过六位、周日期、序数日期、24:00、闰秒的解析支持矩阵，请求明确完整兼容范围、未支持合法记录的显式处置方式及本次复审范围。没有把解析失败当成违反 ISO，也没有缩小或修改 v1.2 冻结契约。单纯记录兼容缺口不等于已修复其运行时错排。

## 6. 五个写方法异常映射复核

create、rename、delete、append_message、update_message_emotion 均保留 ProgrammingError/InterfaceError 在 DatabaseError 之前的原样透传分支；执行/提交失败回滚本次事务。OperationalError、通用 DatabaseError、OSError 仍映射为 StorageIOError，并保留原始 cause。

五方法 × 两阶段 × 五异常类型共 50 项矩阵，加 3 项真实非法参数绑定和 10 项外部事务不变性测试，全数包含在本次通过的 Storage 255 项中。原始异常对象、异常链、真实未提交写入的回滚、观察连接无部分提交均验证。F-02 原有 SELECT/COMMIT 失败原子性回归也保留通过。

## 7. 最新完整回归结果

| 范围 | 通过 | 失败 | 跳过 | 未选 |
|---|---:|---:|---:|---:|
| 批准项修复前专项 | 0 | 18 | 0 | 237 |
| 批准项修复后专项 | 18 | 0 | 0 | 237 |
| Storage 完整 | 255 | 0 | 0 | 0 |
| 架构守护 | 22 | 0 | 0 | 0 |
| Stage 1/2 指定文件回归 | 166 | 0 | 0 | 10 |
| 默认全量（含批准的本机回环测试） | 508 | 0 | 1 | 10 |
| 严格零连接全量 | 506 | 0 | 1 | 12 |

默认选择 509 项（508 通过 + 1 跳过），严格零连接选择 507 项（506 通过 + 1 跳过），均从 519 项收集总数筛选。唯一跳过项是缺少 PySide6 的包级 GUI 导入测试。没有 Storage 跳过项。

默认全量按原配置运行；本机回环测试沿用此前授权，在受限环境之外执行以避免 WinError 10013。严格零连接命令为：

```powershell
.\.venv\Scripts\python.exe -m pytest -m 'not integration and not local_network' --tb=short -rfs
```

没有调用真实 Ollama 或外网服务。各范围的 JUnit XML 均保留在批准后证据目录，文件名为 storage.xml、architecture.xml、stage12.xml、full-default.xml、strict-offline.xml。

## 8. 契约、文件清单、Git 状态与限制

构造函数和 Repository 八个公共方法签名与最初快照完全一致。导出、数据模型和异常类文件未修改。stage3-contract-v1.md、threading-model.md、module-ownership.md、data-models.md 均与 stage3-contract-v1.2 标签逐字节一致。没有修改 Stage 1/2 业务代码、共享测试夹具、架构测试、数据库 Schema 或 Git 标签。

本次批准后阶段的文件：

| 文件 | 操作与必要性 |
|---|---|
| emowall/storage/repository.py | 修改 F-01 已批准分类、生成六位微秒及相关文档；保留原 CTE SQL |
| tests/test_storage.py | 更新批准分类断言，新增 3 项生成格式回归 |
| ROUND4_CONFLICT_INVESTIGATION.md | 新增；先提交共享写入来源、静止性和保留方案 |
| docs/adr/0003-storage-transaction-ownership.md | 新增；按项目负责人要求保存非冻结批准记录 |
| docs/contracts/change-requests/2026-10-24-storage-timestamp-compatibility.md | 新增；按要求提出明确契约澄清申请，不更改冻结内容 |
| ROUND4_APPROVED_DECISIONS.md | 新增；本次批准后的最新交接与测试证据 |

所有初始文件均保留；最初 57 文件清单中只有 repository.py、test_storage.py 内容变化。Git 仍有先前未提交的 AGENTS.md、HANDOVER.md、storage/__init__.py，以及 Storage 实现、测试和报告等未跟踪文件。工作区不干净，未提交；本阶段未宣布完成，未擅自将既有未提交成果打包提交。

已知限制：其他合法 ISO 表示及 24:00 同刻语义未修复，等待澄清；未验证 rollback 本身失败造成的异常遮蔽、20,000 行以上或低速磁盘性能、真实历史用户数据库、GUI 或真实 Ollama。本次未把这些未验证场景列为通过。

F-01 与新生成时间戳的决定已有正式批准，不需重复申请；签名和 Schema 无新变更需求。**完整 ISO 兼容仍需要上面的契约澄清裁决，不能自行降低验收标准。**

**NEEDS FIX**：已批准的精准修复及回归完成；完整 ISO 兼容项保持未关闭。停止本轮工作，等待独立审查与架构澄清，不自行宣布 Stage 3 Storage PASS，不进入 Task 6。
