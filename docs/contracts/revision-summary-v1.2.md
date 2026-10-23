# Stage 3 契约修订总结 v1.2

> 修订日期：2026-10-23
> 修订者：Lead Software Architect
> 基线：v1.1 修订草案（独立审查二轮 CONDITIONAL PASS）
> 修订后版本：v1.2 最终草案（待最终复审）

---

## 1. 修订背景

独立审查 Agent 对 v1.1 进行了第二轮复审，结论：**CONDITIONAL PASS**。

审查报告发现 3 项 Minor 问题和 2 项 Note：

| # | 严重度 | 发现 | 状态 |
|---|--------|------|------|
| F1 | Minor | §7.2 方法计数 "7" 应为 "8"（预留接口未计入） | ✅ 已修复 |
| F2 | Minor | §5.2.3 未列出 `sqlite3.InterfaceError` | ✅ 已修复 |
| F3 | Minor | §5.2.2 操作阶段未映射 `OSError` | ✅ 已修复 |
| F4 | Note | §7.5.3 缺少纯空白 emotion 测试用例 | ✅ 已补充 |
| F5 | Note | §3.5 未标注"不支持清除 emotion"限制 | ✅ 已补充 |

同时，**项目负责人确认了 5 项设计假设**，附带 2 条补充要求：

| # | 确认事项 | 补充要求 | 状态 |
|---|----------|----------|------|
| 2 | `MessageRecord.role` 使用 `str` | **Repository 必须校验合法角色值** | ✅ 已强化 |
| 6 | `list_messages(limit=None)` 表示全部 | **调用方应注意超长会话的内存风险** | ✅ 已补充 |

---

## 2. 修订详情

### F1：方法计数修正 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §7.2 line 719 | "7 个方法" → "8 个方法（含 1 个预留接口 `update_message_emotion`）" |

### F2：`sqlite3.InterfaceError` 纳入不捕获列表 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §5.2.3 | 新增 `InterfaceError` 行：与 `ProgrammingError` 同属编程错误，不映射 |

**理由**：`InterfaceError` 是 `sqlite3.Error` 的直接子类，与 `DatabaseError` 是**兄弟关系**（不是父子关系）。它通常在连接内部状态损坏或参数绑定错误时触发，属于编程错误，不应被吞掉。

### F3：操作阶段 `OSError` 映射 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §5.2.2 | 新增 `OSError` → `StorageIOError` 行 |

**理由**：连接阶段已映射 `OSError` → `StorageConnectionError`（§5.2.1）。操作阶段的文件系统错误（如运行时 `ENOSPC` 磁盘满）同样需要映射，否则违反 §5.3 第 2 条"emowall/storage 只抛出 StorageError 及其子类"的保证。

### F4：纯空白 emotion 测试用例 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §7.5.3 | 新增 `update_message_emotion(1, emotion="   ", ...)` 抛 `ValueError` |

### F5：emotion 不可清除限制 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.5 设计决策表 | 新增一行："不支持将 emotion 重置为 None" / "V0.1 不做" |

### 项目负责人补充：role 校验强化 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.2 `MessageRecord.role` 注释 | 明确"Repository 负责校验合法值" |
| `stage3-contract-v1.md` | §3.4 `append_message()` role 参数 | 添加"必须校验"说明 |
| `stage3-contract-v1.md` | §8.2 确认表 #2 | 备注栏强调校验要求 |

**合法角色值**：`{"system", "user", "assistant"}`（与 `emowall/ai/models.py` 的 `VALID_ROLES` 保持一致）。

### 项目负责人补充：list_messages 大数据量风险 ✅

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `list_messages()` docstring | 新增 `limit` 参数注意说明 |
| `stage3-contract-v1.md` | §8.2 确认表 #6 | 备注栏提示内存风险 |

**具体建议**：Stage 5 的 StorageService 应结合 AI 引擎的上下文窗口（`qwen3:8b` 当前 8192 tokens）使用合适的 `limit` 值。

---

## 3. §8.2 状态变更

v1.1 的"仍待项目负责人最终确认"已变更为"已由项目负责人确认（2026-10-23）"。

5 项设计假设全部 ✅ 确认，附带条件已纳入契约文档。

---

## 4. 版本头更新

| 字段 | v1.1 | v1.2 |
|------|------|------|
| 版本 | v1.1 修订草案 | v1.2 最终草案 |
| 状态 | 待复审 | 待最终复审 |
| 审核者 | 首轮 CONDITIONAL PASS | 首轮 + 二轮 CONDITIONAL PASS |
| 批准者 | 待定 | 已确认 5 项 |

---

## 5. 修订统计

| 指标 | 数值 |
|------|------|
| 修订文档数 | 1（`stage3-contract-v1.md`） |
| 新建文档数 | 1（本文件 `revision-summary-v1.2.md`） |
| F1–F3（Minor）解决 | 3 / 3 (100%) |
| F4–F5（Note）解决 | 2 / 2 (100%) |
| 项目负责人确认 | 5 / 5 (100%) |
| 新增测试用例 | 1（纯空白 emotion） |
| 新增映射行 | 2（`OSError` 操作阶段、`InterfaceError` 不捕获） |
| 新增设计决策 | 1（emotion 不可清除） |

---

## 6. 结论

**本轮修订已完成全部审查发现和项目负责人反馈的处理。**

所有修订均：
- ✅ 保持 Stage 1、Stage 2 代码不变
- ✅ 保持与 ARCHITECTURE.md、ADR-0001/0002 的一致性
- ✅ 不引入新的接口变更
- ✅ 仅填补边界情况的遗漏

**契约版本**：v1.2 最终草案
**当前状态**：待独立审查 Agent 最终复审（预期 PASS）
**冻结条件**：最终复审 PASS

---

**停止点**：修订完成，等待最终复审 PASS 后宣布冻结。
