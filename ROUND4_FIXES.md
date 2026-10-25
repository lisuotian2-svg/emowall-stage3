# Stage 3 Storage — 第四轮精准修复记录

日期：2026-10-24。分支 `feature/stage3-storage`，HEAD `2ddbdcd86b6ee83d0b2bea004e1d4607856d1882`。

本轮仅处理 F-03 微秒排序、五个写方法的编程错误透传及相应回归；未修改冻结契约、Stage 1/2 代码、Git 历史或 Task 6。原有未提交与未跟踪文件全部保留。第三次独立审查报告未在工作区找到文件；依据本轮任务中的审查结论和实际代码核查。

## 1. F-03 失败测试与修复

先运行 `TestRound4TimestampSorting or TestRound4WriteErrors`：90 项中 **79 通过、11 失败**。失败包括 `00.123Z < 00.123100Z`、`00.123100Z < 00.123200Z`、同秒微秒历史库重开，以及非法时间文本排在有效时间之前。原 HYBRID 查询把未知小数精度送进 `strftime('%f')`，而 SQLite 的 `%f` 只给毫秒，随后 `rowid DESC` 错误地决定先后。

修复仅改 `ConversationRepository.list_recent()` 的 SQL 排序表达式。新键由经 SQLite 日期解析验证的 UTC 秒、小数位去尾零、终止符 `/` 组成；`/` 的字典序小于任何十进制数字，因此不同精度在同秒内按真实先后排列，等值精度表示得到相同键。`rowid DESC` 保持同刻稳定顺序。支持原秒级 `Z`、毫秒 `Z`、有效微秒及更长小数、`+00:00`；无效文本键为 NULL，排在有效时间之后。只读取历史时间字段，返回原始字符串，不迁移数据，也不更改公共 API。

固定宽度六位微秒键已经考虑，但会截断合法的更长小数；因此采用不截断的数字键。排序值未经过 `julianday()` 浮点比较，也未经过 `%f` 毫秒化比较。新增用例覆盖秒/毫秒、秒/微秒、毫秒/微秒、同毫秒不同微秒、九位小数、等时不同精度、`+00:00` 等时表示、历史库重开、`limit`、非法文本。

修复后第四轮专项 **94 通过、158 未选**；Storage **252 通过**。这 94 项是相对上一轮 158 项 Storage 测试的净增，未替换既有用例。此前 90 项专项测试在本轮开始时已存在；本轮另外补充 4 个参数化实例（九位小数双插入顺序、UTC 偏移等时表示、非法日历日期）。

### 独立性能与查询计划

使用隔离的 SQLite `:memory:`，混合秒、毫秒、微秒和 `+00:00`，按 Python `datetime.fromisoformat` 核对 200/1000/5000 行，均正确。`limit=50` 20 次查询中位数约 **0.655 / 2.535 / 11.021 ms**。另在相同 5000 行集上作 30 次对比：旧 HYBRID **6.382 ms**，新键 **14.666 ms**；不同试跑的绝对数值有波动，约 2.3 倍开销是可观察的。`EXPLAIN QUERY PLAN` 为 `SCAN conversations` 与 `USE TEMP B-TREE FOR ORDER BY`，原 HYBRID 同样需要临时排序；未使用 `idx_conversations_updated_at`。个人规模数据可继续复审，若将来会话数显著增长，应由架构师另行评估索引或 schema 方案。

### 契约边界

冻结 v1.2 只写明 `ISO-8601 UTC`，没有枚举所有合法的 ISO-8601 文本表示。当前 SQL 明确覆盖扩展式日期时间、`Z` 与 `+00:00`、任意十进制小数位；其他表示（例如基本式日期、逗号小数、非零时区偏移）未列为已验证兼容范围。请架构师明确这些是否属于承诺输入；本轮不修改冻结契约或对外时间戳返回语义。

## 2. 五个写方法异常映射

逐一核查 `create`、`rename`、`delete`、`append_message`、`update_message_emotion`：各自的 `except (sqlite3.ProgrammingError, sqlite3.InterfaceError)` 位于 `except sqlite3.DatabaseError` 之前，先回滚本次事务，再原样 `raise`。真实不支持绑定参数引发的 `ProgrammingError` 在 `rename`、`delete`、`append_message` 中运行验证；五方法的执行及提交阶段均注入原异常对象，验证原样透传。`OperationalError`、通用 `DatabaseError`、`OSError` 仍映射到 `StorageIOError` 且保留 `__cause__`。故障注入在已有未提交写入后触发，验证回滚、重开观察及外部活动事务不被提交或回滚。

本轮开始检查时，五个写方法的异常分支及大部分测试已位于未跟踪工作文件中，故没有对该缺陷再次修改代码，也不声称本轮取得该缺陷的修复前失败运行记录。第三次独立审查指出旧的通用 `DatabaseError` 分支会误映射 `ProgrammingError`；本轮专项运行实际验证了当前代码的修复后行为。

## 3. F-01 分类

`ROUND2_FIXES.md` 记录方案 B（外部事务误用抛 `sqlite3.ProgrammingError`）为**待批准**。本轮未在工作区找到正式批准；附图只是要求确认审批状态，亦不构成批准。因此保持 `_ensure_no_external_transaction()` 的现有 `StorageIOError`，不新增公共异常类。五方法的活动事务保护仍由 10 个运行用例验证；调用方事务不被提交或回滚。此分类与 `StorageIOError` 的“磁盘读写失败”语义仍有待架构师裁决。

## 4. 回归结果与差异

全部命令均设 `PYTHONDONTWRITEBYTECODE=1`，使用 `-p no:cacheprovider`。测试夹具在项目 `.tmp/pytest` 下创建唯一临时库并自行清理；未访问用户数据库或真实 AI API。

| 范围 | 通过 | 失败 | 跳过 | 未选 |
|---|---:|---:|---:|---:|
| 第四轮专项（修复前，额外 4 项加入前） | 79 | 11 | 0 | 158 |
| 第四轮专项（修复后） | 94 | 0 | 0 | 158 |
| Storage 完整 | 252 | 0 | 0 | 0 |
| 架构守护 | 22 | 0 | 0 | 0 |
| Stage 1/2 严格离线 | 166 | 0 | 0 | 0 |
| 项目严格离线全量 | 501 | 0 | 1 | 12 |

严格离线全量命令为 `python -m pytest -p no:cacheprovider -m 'not integration and not local_network' --tb=short -ra`。跳过项为缺少 PySide6 时的打包测试；12 项网络/集成标记用例未选。

改动文件：`emowall/storage/repository.py`（F-03 查询；五方法映射已存在于本轮起始工作文件）、`tests/test_storage.py`（第四轮 94 项运行实例）、本报告。冻结的 `stage3-contract-v1.md`、`threading-model.md`、`module-ownership.md` 与标签 `stage3-contract-v1.2` 的 Git blob 均完全一致。未提交 Git。

## 5. 剩余风险与交接

- F-01 的异常分类仍待主架构师正式裁决；方案 B 若批准，再按批准内容修改并补测。
- 冻结契约对其他 ISO-8601 UTC 文本形式没有具体列举，需确认承诺范围。当前已测输入的原始时间戳值保持不变。
- 5000 行排序约 11–15 ms，且不能使用 `updated_at` 列索引；未来数据量扩大时重新评估。
- 写方法若在回滚本身失败时，原始编程错误可能被回滚错误遮蔽；正常 SQLite 可用连接、绑定错误和故障注入路径已验证，异常中的异常尚未模拟。

现有冻结公共接口没有变化，当前修复**不需要接口变更申请**；如架构师要求扩展 ISO 表示保证或改变 F-01 公开可见的异常类型，应先形成明确裁决。状态：**READY FOR RE-REVIEW**。等待独立审查 Agent 复审，不宣告 Stage 3 Storage 验收通过，不进入 Task 6。
