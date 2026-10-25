# Stage 3 Storage — 第二轮精准修复报告

> 对应独立审查第二轮定向复审结论 **FAIL**（未通过项：F-03、F-04、F-07；疑点：F-01 异常分类、
> F-02 SELECT 回滚覆盖、F-06 仅源码断言）。
> 本轮只做精准修复，未重构、未改动冻结公共接口、未进入 Task 6。
> 时间：2026-10-24 15:20（Asia/Shanghai）｜分支 `feature/stage3-storage`｜HEAD `2ddbdcd`

---

## 0. 变更范围与安全前置

- 起始工作区：`M AGENTS.md`、`M HANDOVER.md`、`M emowall/storage/__init__.py`，另有 6 个未跟踪文件；
  全部保留，未执行 `git clean` / `reset --hard` / rebase。
- 冻结契约 `docs/contracts/stage3-contract-v1.md`：**本轮结束仍为 CLEAN（未修改）**。
- Stage 1 / Stage 2 业务代码：未修改。
- 本轮仅改 3 个文件 + 新增本报告（见 §9）。

---

## 1. F-03 修复：历史时间戳排序

### 1.1 缺陷复现（修复前，确定性）

原始实现 `ORDER BY updated_at DESC`。同一秒内：

| id | updated_at |
|---|---|
| old-sec | `2026-10-24T12:00:00Z` |
| new-ms | `2026-10-24T12:00:00.123Z` |

`'Z'(0x5A=90) > '.'(0x2E=46)` ⇒ 字符串降序把 **old-sec 排在前**，而它实际比 new-ms 早 123 ms。
修复前该组回归测试 **5 项全部失败**，其中一条断言输出：

```
assert ['old-sec', 'new-ms'] == ['new-ms', 'old-sec']
```

> 原第一轮测试用 `2026-01-01T00:00:00Z` 对照「当前时间」新建记录，两者**不同日期**，
> 字符串序恰好正确，因此漏检。本轮改为**同秒跨精度**构造，才能检出缺陷。

### 1.2 候选方案 Benchmark（SQLite `:memory:`，未访问真实用户数据库）

数据集：5,000 条，**每两条共享同一秒**（偶数毫秒级、奇数秒级），强制跨精度同秒碰撞；
limit=50；正确性以「真实 `datetime` 降序 + 同刻 `rowid DESC`」为期望。
边界集：同秒内 `…:00Z / .000Z / .001Z / .123Z / .999Z / .123456Z / …:01Z`。

| 方案 | 5,000 行正确性 | 同秒跨精度边界 | 6 位小数 | 非法/空值 | 200 行 | 1,000 行 | 5,000 行 | 用索引 |
|---|---|---|---|---|---|---|---|---|
| PLAIN（`updated_at DESC`） | ❌ | ❌ | ❌ | ❌（非法值排最前） | 0.04 ms | 0.04 ms | 0.04 ms | ✅ |
| JULIANDAY | ✅ | ✅ | ✅ | ✅ | 0.09 ms | 0.35 ms | 1.67 ms | ❌ |
| STRFTIME | ✅ | ✅ | ✅ | ✅ | 0.26 ms | 1.14 ms | 5.76 ms | ❌ |
| CASE3（仅长度分支） | ✅ | ✅ | ❌ | ❌ | 0.11 ms | 0.47 ms | 2.21 ms | ❌ |
| **HYBRID（采用）** | ✅ | ✅ | ✅ | ✅ | **0.11 ms** | **0.47 ms** | **2.33 ms** | ❌ |

- 同秒跨精度边界实测（降序，期望 `nextsec, ms999, us123456, ms123, ms001, ms000, sec`）：
  - PLAIN → `nextsec, sec, ms999, ms123, us123456, ms001, ms000`（**错误**）
  - CASE3 → `nextsec, ms999, ms123, us123456, …`（6 位小数处**错误**）
  - JULIANDAY / STRFTIME / HYBRID → 与期望一致
- 索引：`EXPLAIN QUERY PLAN` 显示仅 PLAIN 命中 `idx_conversations_updated_at`
  （`SCAN … USING INDEX`）；所有正确方案均为 `SCAN` + `USE TEMP B-TREE FOR ORDER BY`。
  表达式排序无法用列索引，属预期；已量化绝对耗时。
- `julianday` 未采用：返回浮点，1 ms ≈ 1.16e-8 天，相对 magnitude 2.46e6 的 double 精度余量有限。
- `datetime()` / `strftime('%s')` 未采用：**丢弃毫秒**，直接破坏排序。
- `strftime` 解析 NULL 行数 = 0（合法数据）。

### 1.3 最终实现

`emowall/storage/repository.py::list_recent()`：

```sql
ORDER BY CASE
    WHEN length(updated_at) = 20 THEN substr(updated_at, 1, 19) || '.000Z'
    WHEN length(updated_at) = 24 THEN updated_at
    ELSE strftime('%Y-%m-%dT%H:%M:%fZ', updated_at)
END DESC,
rowid DESC
LIMIT ?
```

- 长度 20 = 旧秒级 → 补 `.000Z`；长度 24 = 新毫秒级 → 原样；
  其他精度 → `strftime` 归一化到毫秒（3 位）。
- 次级排序 `rowid DESC`：归一化后并列时「后插入者在前」，结果稳定确定（冻结契约未规定 tie-break，
  此为实现层明确约定）。
- 不修改历史数据、不改公共时间戳语义、不新增公共接口。

**选择理由**：正确性覆盖最全（含 6 位小数与非法值），且比 STRFTIME 快约 2.5 倍；
在 200/1000/5000 行下分别为 0.11/0.47/2.33 ms，个人级数据量可接受。

### 1.4 修复后回归测试

`TestF03MixedTimestampSorting` 共 **8 项**，全部通过：同秒新旧、显式 123 ms、多个毫秒值、
历史库关闭重开、纯旧格式库可读、limit 在正确排序后截断、6 位小数回退、并列 tie-break。

---

## 2. F-04 修复：跨线程关闭连接

### 2.1 缺陷复现（修复前）

原实现：

```python
try:
    conn.close()
except sqlite3.ProgrammingError:
    pass          # ← 吞没
finally:
    self._closed = True   # ← 失败也置位
```

实测（`check_same_thread=True` 默认）：非创建线程 `close()` 抛
`ProgrammingError: SQLite objects created in a thread can only be used in that same thread.`
被 `except` 吞掉后 `finally` 仍将 `_closed=True` ⇒ **连接实际仍打开却标记已关闭**，
创建线程的合法关闭被错误跳过。

修复前该组回归 **4 项失败**：

```
AssertionError: 跨线程 close() 必须抛出 ProgrammingError，而不是被吞没
AssertionError: 关闭失败不得错误置 _closed=True   (assert True is False)
AssertionError: 连接仍可用（_closed 应为 False）
AssertionError: 创建线程仍能关闭（_closed 应为 False）
```

### 2.2 修复实现

`emowall/storage/database.py::close()`：

```python
if getattr(self, "_closed", False):
    return                       # 已正常关闭 → 幂等
conn = getattr(self, "_conn", None)
if conn is None:
    self._closed = True          # 构造早期失败、无资源
    return
conn.close()                     # 失败（含跨线程 ProgrammingError）向上传播
self._closed = True              # 仅成功后置位
```

- 仅成功关闭后置 `_closed=True`；失败保持 `False`。
- 关闭失败异常按契约 §5.2.3 **不映射**，直接传播。
- 已关闭后重复 `close()` 由 `_closed` 守卫短路（且 `sqlite3` 对已关闭连接再 `close()` 原生无异常）。
- 公共方法签名未变；上下文管理器 `__exit__` 仍调用 `close()`，异常按 Python 语义传播。

### 2.3 修复后回归测试

`TestF04CrossThreadClose` 共 **10 项**全部通过：创建线程正常关闭、重复关闭、真实连接已关闭
（`conn.execute("SELECT 1")` 抛 `ProgrammingError`）、非创建线程首次关闭异常传播、
失败后 `_closed` 为 False、失败后连接仍可用、创建线程后续可关闭、已关闭后跨线程 close 幂等、
`with` 正常退出释放、`with` 体内异常传播且释放。

---

## 3. F-07 测试质量补强

| 要求 | 处理 |
|---|---|
| 使用能实际触发缺陷的运行测试 | F-03/F-04 全部改为真实执行路径；F-06 改为运行时注入 |
| 避免仅 `inspect.getsource()` | 删除 3 个源码文本断言，改为 `PropertyMock` 注入 `OSError` 的实际执行断言 |
| F-03/F-04 确定性复现 | 使用固定时间戳常量与 `threading.Thread + join`，不依赖调度巧合 |
| F-02 补 SELECT 失败回滚 | 新增 `TestF02RollbackOnFailure`（SELECT 失败 / COMMIT 失败 / 不误报成功） |
| F-06 运行时 OSError + 异常链 | 3 个只读方法各注入 `OSError(28)`，断言 `StorageIOError` 且 `__cause__` 为 `OSError`、`errno==28` |
| 事务失败无部分提交 | F-02 回滚后重新读取，断言 `emotion is None` |
| 失败诊断清晰 | 断言带中文说明与期望值，失败信息可直接定位 |
| 不删除/弱化已有断言 | 仅替换 7 个弱测试；其余原断言保持不变 |

### 缺陷先行的前后证据

修复前（`_pre_fix` 运行）**10 项失败**：
F-03 5 项、F-04 4 项、F-06 1 项（`ProgrammingError` 被 `except sqlite3.DatabaseError` 误映射）。
修复后（`_post_fix` 运行）**26 项通过 / 0 失败**。

---

## 4. F-01 异常分类结论（额外检查）

### 4.1 对照冻结契约

- §5.2.2 操作阶段映射表：`OperationalError` / `DatabaseError` / `OSError(文件系统层)` → `StorageIOError`。
- §5.2 异常定义（第 150–159 行）：`StorageIOError` 用于**磁盘读写错误**。
- §5.2.3 不捕获：`ProgrammingError`（跨线程/关闭后使用）、`InterfaceError`、
  `ValueError`/`TypeError`（参数校验）——均属**调用方误用**，直接抛出。
- 冻结契约**未**定义「存在外部活动事务」应抛哪一类异常。

### 4.2 判断

`_ensure_no_external_transaction()` 抛 `StorageIOError` 表示的是**调用方事务所有权误用**，
并非磁盘 I/O 故障，与 §5.2 对 `StorageIOError` 的语义定义不一致；其性质更接近 §5.2.3 的
「调用方误用」类别。**当前分类语义上偏差，但不构成数据损坏**（拒绝执行、未提交/回滚调用方事务）。

### 4.3 本轮处理：不改代码，提交审批

- F-01 已于第一轮复审 **PASS**；
- 契约对「外部活动事务」无冻结异常类型，属**歧义**；
- 指令要求：契约歧义时提交问题供主架构师审批，且不得擅自新增公共异常类型或改冻结异常层级。

**提交主架构师裁决（三选一）**：

| 选项 | 做法 | 优点 | 代价 |
|---|---|---|---|
| A（现状） | 保持 `StorageIOError` | 零改动、F-01 已 PASS | 语义与「磁盘 I/O」不符，疑点留存 |
| B（推荐） | 改抛 `sqlite3.ProgrammingError` | 命中 §5.2.3「调用方误用」类别；**不新增公共类型**、不改异常层级 | 改变 F-01 已通过行为，需批准 |
| C | 改抛内置 `RuntimeError`/`ValueError` | 不新增公共类型 | 不在 §5.2.3 列举范围，契约依据更弱 |

本轮**未实施 A/B/C 任一变更**，等待审批后执行。

---

## 5. F-02 / F-06 运行回归结果

### F-02 原子性 + 回滚（`TestF02RollbackOnFailure`，3 项通过）

| 用例 | 注入 | 结果 |
|---|---|---|
| `test_select_failure_rolls_back_update` | UPDATE 后 SELECT 抛 `OperationalError` | `StorageIOError` 且 `__cause__` 为 `OperationalError`；重新读取 `emotion is None`（**无部分提交**） |
| `test_commit_failure_rolls_back_update` | `commit()` 抛 `OperationalError` | `StorageIOError`；回滚后 `emotion is None` |
| `test_commit_failure_does_not_report_success` | 同上 | 未返回任何 `MessageRecord`（不误报成功） |

另保留原 `TestF02EmotionUpdateAtomicity`：返回记录与库内记录一致（1 项通过）。

### F-06 运行时 OSError 映射（`TestF06RuntimeOSErrorMapping`，4 项通过）

| 用例 | 注入 | 断言 |
|---|---|---|
| `list_recent` | `OSError(28, "No space left…")` | `StorageIOError`，`__cause__` 为 `OSError`，`errno==28` |
| `get` | 同上 | 同上 |
| `list_messages` | 同上 | 同上 |
| `ProgrammingError` 不吞没 | `sqlite3.ProgrammingError` | 原样抛出（不映射为 `StorageIOError`） |

> 第 4 项在修复前**失败**，暴露了额外真实缺陷：`sqlite3.ProgrammingError` 继承自
> `sqlite3.DatabaseError`，被 `except sqlite3.DatabaseError` 捕获并误映射为 `StorageIOError`，
> 违反契约 §5.2.3。本轮在 `list_recent` / `get` / `list_messages` 的 `except` 链中，
> 于 `DatabaseError` **之前**插入 `except sqlite3.ProgrammingError: raise` 与
> `except sqlite3.InterfaceError: raise`，使编程错误按契约透传。

---

## 6. 实际新增测试数量（准确统计）

| 测试类 | 本轮新增方法 | 删除的弱测试 | 净变化 |
|---|---|---|---|
| `TestF03MixedTimestampSorting` | 8 | 2 | +6 |
| `TestF04CrossThreadClose` | 10 | 2 | +8 |
| `TestF06RuntimeOSErrorMapping` | 4 | 3（源码断言） | +1 |
| `TestF02RollbackOnFailure` | 3 | 0 | +3 |
| **合计** | **25** | **7** | **+18** |

- `tests/test_storage.py`：**140 → 158**（净增 18）。
- 说明：第一轮报告曾误称「+24」，实际净增 18（122 → 140）；本轮按实际方法数统计。

---

## 7. 测试执行结果（全部实测）

| 范围 | 通过 | 失败 | 跳过 | 未选（integration） | 退出码 |
|---|---|---|---|---|---|
| 新增专项（F-02/F-03/F-04/F-06） | 26 | 0 | 0 | 0 | 0 |
| `tests/test_storage.py` | **158** | 0 | 0 | 0 | 0 |
| `tests/test_architecture.py` | **22** | 0 | 0 | 0 | 0 |
| 全量严格离线 `pytest tests/` | **409** | **0** | **1** | **10** | 0 |

- 收集总数 420（410 选入 = 409 通过 + 1 跳过；10 个 `integration` 用例按 `pytest.ini` 默认排除）。
- 各文件：ai_client 79 / ai_config 6 / ai_engine 35 / ai_probe 3 / architecture 22 /
  check_env 10 / config 43 / docs 41 / package 8 / pytest_config 5 / **storage 158**。
- 环境限制项：无。本轮所有验证均已实际执行；Benchmark 以 `:memory:` 完成，未访问真实用户数据库。

---

## 8. 公共接口与契约一致性

- `emowall.storage.__all__`：8 个符号，与冻结契约 §3.6 **完全一致**。
- `Database` 公共成员：仅 `close`、`schema_version`；**不存在** `connection`，`_connection` 为私有。
- `ConversationRepository` 8 个公共方法**签名全部未变**。
- 异常层级未变：`StorageError` → {`StorageConnectionError`, `StorageIntegrityError`, `StorageIOError`}。
- `emowall.storage` 未加载 Qt / httpx（仅标准库）。
- 冻结契约文件未修改；`git diff --check` 退出码 0；代码与测试文件行尾空白为 0。

---

## 9. 修改文件清单

| 文件 | 类型 | 变更 |
|---|---|---|
| `emowall/storage/database.py` | 修改 | F-04：`close()` 仅在成功后置 `_closed`，失败传播不吞没 |
| `emowall/storage/repository.py` | 修改 | F-03：`list_recent()` HYBRID 归一化排序 + `rowid DESC` 次级排序；F-06：三只读方法在 `DatabaseError` 前透传 `ProgrammingError`/`InterfaceError` |
| `tests/test_storage.py` | 修改 | F-03/F-04/F-06 测试重写、F-02 回滚用例新增、辅助工具 `_insert_conv`/`_ProxyConn`、清理行尾空白 |
| `ROUND2_FIXES.md` | 新增 | 本报告 |

未修改：冻结契约、Stage 1/2 业务代码、`tests/test_architecture.py`、`tests/conftest.py`、Git 标签。
未执行：`git commit` / `push` / `rebase` / `reset --hard` / ACL 修改 / 删除未知未跟踪文件。
（`HANDOVER.md` 与 `AGENTS.md` 的既有改动非本轮产生，未触碰。）

---

## 10. 剩余风险

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| 表达式排序无法命中 `updated_at` 索引 | 低 | 实测 200/1000/5000 行 = 0.11/0.47/2.33 ms；个人级数据量可接受。若未来会话数上万，可向架构师申请「归一化列」或表达式索引（需 schema 变更审批） |
| 非法/空时间戳排在末尾 | 低 | 行为确定（SQLite `NULL` 降序置尾）；正常写入路径不会产生非法值 |
| 写方法仍以 `except sqlite3.DatabaseError` 兜底 | 低 | 写方法在 `try` 前已执行 `_ensure_no_external_transaction()`，关闭后误用会在此处抛 `ProgrammingError` 并透传；`try` 内绑定类 `ProgrammingError` 理论上仍被映射，建议后续轮次对齐（未在本轮范围内，避免改动 F-01/F-02 已通过代码） |
| F-01 异常分类语义偏差 | 中（待裁决） | 见 §4；本轮未改，等待主架构师在 A/B/C 中裁决 |
| F-05 `connection → _connection` 变更待批 | 待批 | 第一轮已提交，尚未获正式批准 |

---

## 11. 是否存在接口变更需求

- **有新需求**：F-01 异常类型裁决（选项 B 若采纳，`_ensure_no_external_transaction()` 改抛
  `sqlite3.ProgrammingError`；不新增公共异常类型、不改冻结异常层级）。**本轮未实施，待批准。**
- **遗留待批**：F-05 `Database.connection → _connection`（第一轮提交，尚无批准结论）。
- 除上述两项外，无其他公共接口变更需求。

---

## 12. 最终结论

**READY FOR RE-REVIEW**

- F-03：已修复，HYBRID 归一化排序在 5,000 行与全部同秒跨精度边界下正确，性能已量化。
- F-04：已修复，跨线程关闭失败不再吞没、`_closed` 状态与实际一致、创建线程可后续关闭。
- F-07：已补强，25 个新运行测试（净 +18），删除 7 个弱测试；修复前 10 项失败 → 修复后 0 失败。
- F-01：结论已给出，契约歧义已整理为 A/B/C 选项提交主架构师审批（未擅自改动）。
- F-02 / F-06：SELECT/COMMIT 失败回滚与运行时 `OSError` 注入均已自动化覆盖；
  额外修复 `ProgrammingError` 被误映射的真实缺陷。
- 测试：storage 158 通过、architecture 22 通过、全量 409 通过 / 1 跳过 / 10 未选 / 0 失败。
- 冻结契约未修改，公共接口签名未变。

**未获独立复审前，不宣布 Stage 3 Storage 通过验收，不进入 Task 6。**
