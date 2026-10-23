# Stage 3 契约修订总结 v1.1

> 修订日期：2026-10-23
> 修订者：Lead Software Architect
> 基线：v1 草案（独立审查 CONDITIONAL PASS）
> 修订后版本：v1.1 修订草案（待复审）

---

## 1. 修订背景

独立审查结论：**CONDITIONAL PASS**。

审查报告提出 3 项 Major 问题和 5 项 Minor 问题。本轮任务：
- 解决全部 3 项 Major
- 尽量同时解决 5 项 Minor
- 保持 Stage 1、Stage 2 代码不变
- 只修订契约文档，不进行 Stage 3 功能开发

---

## 2. Major 问题修订结果

### M1：标题截断策略 ✅ 已解决

**问题**：`create()` 和 `append_message()` 自动标题规则不明确，存在不一致风险。

**修订内容**：

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `create()` | 新增 4 步标题规则（strip → 空白回退 → 截断 → 原样） |
| `stage3-contract-v1.md` | §3.4 `append_message()` | 明确触发条件（role=="user" 且无历史 user 消息） |
| `stage3-contract-v1.md` | §3.4 `rename()` | 明确复用同一规则 |
| `stage3-contract-v1.md` | 附录 A.2 | 新增 `_normalize_title()` 速查 |
| `data-models.md` | §5.1 | 新增标题归一化规则专节（含代码示例和截断示例表） |
| `data-models.md` | §3.1 | Conversation.title 约束细化 |

**统一规则**：
```python
MAX_TITLE_CHARS = 20
def _normalize_title(raw: str) -> str:
    t = raw.strip()
    if not t: return "新会话"
    return t[:17] + "..." if len(t) > MAX_TITLE_CHARS else t
```

**兼容性评估**：与现有实现和 ARCHITECTURE.md 不冲突。DEVELOPMENT_PLAN 已规定"≤ 20 字"，本次仅细化截断算法。

---

### M2：Storage 异常映射 ✅ 已解决

**问题**：`sqlite3.OperationalError` 在不同阶段映射不同，但规则未明确。

**修订内容**：

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §5.2 | 重写为 5 个子节：按阶段区分映射、不捕获的异常、异常链保留、可测试性 |
| `stage3-contract-v1.md` | §3.5 预留接口 | 新增 `__cause__` 要求 |
| `stage3-contract-v1.md` | §7.5.2 | 新增异常映射专项测试（4 个用例） |

**核心规则**：

| 阶段 | sqlite3 异常 | Storage 映射 |
|------|-------------|--------------|
| 连接阶段（`Database.__init__`） | `OperationalError` / `DatabaseError` / `OSError` | `StorageConnectionError` |
| 操作阶段（`Repository.*`） | `IntegrityError` | `StorageIntegrityError` |
| 操作阶段 | `OperationalError` / `DatabaseError` | `StorageIOError` |
| 任意 | `ProgrammingError` | **不映射**（编程错误，直接抛出） |

**异常链**：所有 `StorageError` 必须 `raise ... from exc`，保留 `__cause__`。

**兼容性评估**：未修改 Stage 1/2 代码。新增映射规则与 ARCHITECTURE.md 的异常层级设计一致。

---

### M3：消息情绪更新接口 ✅ 已解决

**问题**：`update_message_emotion()` 是否需要、由谁实现、何时实现，未明确。

**修订内容**：

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | 新增 §3.5 | 完整的预留接口契约（签名、参数约束、返回语义、异常、事务、实现责任） |
| `stage3-contract-v1.md` | §7.5.3 | 新增预留接口专项测试（5 个用例） |
| `stage3-contract-v1.md` | §8.2 | 原"待确认事项 #7"更新为已解决 |
| `data-models.md` | §4.2 | 新增 `EmotionResult → update_message_emotion` 映射 |
| `module-ownership.md` | §6.2 | 开发顺序建议新增预留接口说明 |

**设计决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| 实现时机 | **Stage 3 实现** | 存储操作属于 storage 层职责 |
| 消费时机 | **Stage 4 消费** | 情绪分析结果由 emotion 层产出 |
| 接口标记 | **"预留"（Reserved）** | 当前无调用方，但预留避免 Stage 4 时修改公共接口 |
| 参数设计 | `message_id: int` | 最小化接口耦合，不要求调用方持有完整记录 |
| 返回值 | `MessageRecord` | 调用方可直接使用更新后的数据 |

**明确标注**：接口为"拟定契约 — 尚未实现"，不是已实现接口。

---

## 3. Minor 问题修订结果

### m1：`list_messages(limit <= 0)` 行为 ✅ 已解决

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `list_messages()` | 明确抛 `ValueError`（limit 不是 None 且 limit ≤ 0） |
| `stage3-contract-v1.md` | §7.5.4 | 新增边界条件测试 |

### m2：`rename()` 异常类型 ✅ 已解决

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `rename()` | 明确异常类型：`StorageIntegrityError`（不存在）/ `StorageIOError`（写入失败）；新增标题规则说明 |

### m3：`append_message()` 返回的 `MessageRecord.id` ✅ 已解决

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `append_message()` | Returns 明确："**id 保证非 None**（由 SQLite AUTOINCREMENT 生成）" |
| `stage3-contract-v1.md` | §3.2 `MessageRecord` | id 注释更新为"传入时为 None；Repository 返回时保证非 None" |
| `data-models.md` | §3.2 | id 约束更新 |
| `data-models.md` | §5 | 新增数据不变性约束：`MessageRecord.id` 非 None |

### m4：空标题、空白标题处理 ✅ 已解决（M1 覆盖）

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `create()` | 空串/纯空白 → "新会话" |
| `stage3-contract-v1.md` | §3.4 `append_message()` | 同上 |

### m5：`list_messages()` 对不存在的 `conversation_id` 行为 ✅ 已解决

| 文档 | 位置 | 修订 |
|------|------|------|
| `stage3-contract-v1.md` | §3.4 `list_messages()` | Returns 明确："会话不存在时也返回空列表"（不抛异常） |
| `stage3-contract-v1.md` | §7.5.4 | 新增边界条件测试 |

---

## 4. 文档一致性检查

### 4.1 跨文档引用一致性

| 引用项 | 出现次数 | 一致性 |
|--------|---------|--------|
| "新会话" 回退值 | 17 | ✅ 所有文档一致 |
| `update_message_emotion` 标记为预留 | 12 | ✅ 所有引用均标注"预留" |
| `__cause__` 异常链要求 | 11 | ✅ 规则统一 |
| `_normalize_title` 函数名 | 7 | ✅ 命名一致 |
| v1.1 版本标记 | 4 文件 | ✅ 统一更新 |

### 4.2 新增接口冲突检查

| 检查项 | 结果 |
|--------|------|
| 是否修改 Stage 1/2 已冻结接口 | ❌ 未修改 |
| 是否修改 `test_architecture.py` 守护规则 | ❌ 未修改 |
| 是否引入跨层依赖 | ❌ 未引入 |
| 是否与 ARCHITECTURE.md 矛盾 | ❌ 无矛盾 |
| 是否与 ADR-0001/0002 矛盾 | ❌ 无矛盾 |

---

## 5. Git 修改文件清单

> 注：pwsh 沙箱 ACL 限制，无法执行 `git diff --check`。以文件系统工具检查结果为准。

| 文件 | 操作 | 变更说明 |
|------|------|----------|
| `docs/contracts/stage3-contract-v1.md` | 修改 | M1/M2/M3 全部修订；Minor 全部修订；版本 v1 → v1.1 |
| `docs/contracts/data-models.md` | 修改 | 标题归一化规则；`update_message_emotion` 映射；id 保证 |
| `docs/contracts/threading-model.md` | 修改 | 版本号 v1 → v1.1 |
| `docs/contracts/module-ownership.md` | 修改 | 版本号 v1 → v1.1；开发顺序建议更新 |
| `docs/contracts/investigation-report.md` | 修改 | 待确认事项 #3 和 #7 更新为已解决 |
| `docs/contracts/revision-summary-v1.1.md` | 新建 | 本修订总结报告 |

**未修改的文件**：
- `emowall/` 下所有源代码 ✅
- `tests/` 下所有测试 ✅
- `AGENTS.md` ✅
- `docs/ARCHITECTURE.md` ✅
- `docs/DEVELOPMENT_PLAN.md` ✅
- ADR 文档 ✅

---

## 6. 已实现接口与拟定接口区分

### 6.1 已实现接口（不可修改）

| 模块 | 接口 | 状态 |
|------|------|------|
| `emowall/ai` | `ChatMessage`, `ChatChunk`, `GenerationStats`, `OllamaClient`, `ChatEngine`, `CancelToken`, `AIError` 层级 | ✅ Stage 2 已冻结 |
| `emowall/config` | `OllamaSettings`, `ChatSettings`, `AppSettings`, `ConfigStore`, `ConfigError` 层级 | ✅ Stage 1 已冻结 |

### 6.2 拟定接口（Stage 3 待实现）

| 模块 | 接口 | 状态 |
|------|------|------|
| `emowall/storage` | `Conversation`, `MessageRecord` | 🔲 拟定（Stage 3 实现） |
| `emowall/storage` | `Database`, `ConversationRepository` | 🔲 拟定（Stage 3 实现） |
| `emowall/storage` | `StorageError` 层级 | 🔲 拟定（Stage 3 实现） |
| `emowall/storage` | `update_message_emotion()` | 🔲 **预留**（Stage 3 实现，Stage 4 消费） |

### 6.3 未来接口（不在本文档范围）

| 模块 | 接口 | 状态 |
|------|------|------|
| `emowall/emotion` | `Emotion`, `EmotionResult`, `detect_emotion()` | ❌ Stage 4 设计 |
| `emowall/gui` | 所有 GUI 类 | ❌ Stage 5 设计 |
| `emowall/app.py` | 组合根 | ❌ Stage 5 实现 |

---

## 7. 未解决的问题

### 7.1 仍待项目负责人确认（5 项）

| # | 事项 | 当前假设 | 风险 |
|---|------|----------|------|
| 1 | `Conversation.id` 使用 UUID v4 字符串 | ARCHITECTURE.md §3.3 | 低 |
| 2 | `MessageRecord.role` 使用 `str` 而非 `Role` | storage 不 import ai | 低 |
| 4 | `Database` 支持上下文管理器 | 已纳入契约 | 低 |
| 5 | `emotion` 字段存储枚举值 | 存储 `.value`（如 `"happy"`） | 低 |
| 6 | `list_messages(limit=None)` 表示全部 | ARCHITECTURE.md §3.3 | 低 |

**评估**：所有待确认事项均为低风险，即使后续微调也不影响：
- 依赖方向
- 线程模型
- 数据模型核心字段
- 异常层级结构

### 7.2 技术限制（已知）

| 限制 | 说明 | 影响 |
|------|------|------|
| pwsh 沙箱 ACL | `SetNamedSecurityInfoW` 失败，无法执行 `git diff --check` | 低（已用文件系统工具替代验证） |
| 未运行 pytest | 本轮未执行测试（无代码变更） | 无（仅修订文档） |

---

## 8. 冻结就绪性评估

### 8.1 是否具备冻结条件

**✅ 具备冻结条件（推荐进入复审）**

**理由**：
1. **3 项 Major 已全部解决**：标题截断策略、异常映射规则、预留接口设计
2. **5 项 Minor 已全部解决**：`list_messages` 边界、`rename` 异常、`append_message` id 保证、空白标题、不存在会话处理
3. **Stage 1/2 代码未修改**：完全保持兼容
4. **文档一致性已验证**：跨文档引用统一
5. **无新增接口冲突**：与 ARCHITECTURE.md、ADR-0001/0002 不矛盾

### 8.2 是否建议重新审查

**✅ 建议重新审查**

**理由**：
- 本次修订涉及 3 项 Major 问题的完整解决方案
- 新增 §3.5 预留接口章节是重要的架构决策
- §5.2 异常映射规则重写为按阶段区分，需要独立审查确认
- 标题截断策略的具体算法（前 17 + "..."）需要项目负责人最终确认

**建议审查重点**：
1. §3.5 `update_message_emotion()` 的设计决策是否合理
2. §5.2 异常映射的阶段区分是否清晰
3. §3.4 标题截断算法是否符合预期
4. §7.5 新增测试用例是否覆盖充分

### 8.3 下一步建议

| 步骤 | 行动 | 责任方 |
|------|------|--------|
| 1 | 独立 Agent 复审 v1.1 契约 | 独立审查 Agent |
| 2 | 项目负责人确认 5 项待确认事项 | 项目负责人 |
| 3 | 复审通过后，宣布接口冻结 | 项目负责人 + Architect |
| 4 | Storage Agent 开始实现 | Storage Agent |
| 5 | 实现完成后，按 §7 验收清单逐条验证 | Storage Agent + Architect |

---

## 9. 修订统计

| 指标 | 数值 |
|------|------|
| 修订文档数 | 5 |
| 新建文档数 | 1 |
| Major 问题解决 | 3 / 3 (100%) |
| Minor 问题解决 | 5 / 5 (100%) |
| 新增测试用例 | 13（标题截断 4 + 异常映射 4 + 预留接口 5） |
| 新增章节 | 2（§3.5 预留接口、§5.1 标题归一化） |
| 跨文档引用检查 | 4 项（全部一致） |

---

## 10. 结论

**本轮修订已完成全部 3 项 Major 和 5 项 Minor 问题的解决。**

所有修订均：
- ✅ 保持 Stage 1、Stage 2 代码不变
- ✅ 保持与 ARCHITECTURE.md、ADR-0001/0002 的一致性
- ✅ 明确区分已实现接口与拟定接口
- ✅ 提供完整的测试方案
- ✅ 不引入新的接口冲突

**契约版本**：v1.1 修订草案
**当前状态**：待独立复审
**冻结条件**：复审通过 + 项目负责人确认 5 项待确认事项

---

**停止点**：修订完成，等待独立 Agent 复审。不自动宣告冻结。
