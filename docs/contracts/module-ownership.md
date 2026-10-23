# Stage 3 接口契约 — 模块所有权与并行开发约定

> 版本：v1.2 最终草案（独立审查 PASS）
> 日期：2026-10-23
> 状态：**已通过审查**（待项目负责人宣布冻结）
> 依赖：AGENTS.md、`docs/ARCHITECTURE.md`

---

## 1. 模块所有权矩阵

### 1.1 已有模块（已冻结）

| 模块 | 所有者 | 状态 | 允许修改者 | 禁止修改者 |
|------|--------|------|-----------|-----------|
| `emowall/ai/` | AI Agent | ✅ STABLE | 仅限 bug fix（需审批） | Stage 3/4/5 Agent |
| `emowall/config/` | Config Agent | ✅ STABLE | 仅限 bug fix（需审批） | Stage 3/4/5 Agent |
| `tests/test_ai_*.py` | AI Agent | ✅ STABLE | 仅限新增（需审批） | Stage 3/4/5 Agent |
| `tests/test_config.py` | Config Agent | ✅ STABLE | 仅限新增（需审批） | Stage 3/4/5 Agent |
| `tests/test_architecture.py` | Architect | ✅ STABLE | 仅限新增守护规则 | 其他 Agent |
| `tests/conftest.py` | Architect | ✅ STABLE | 仅限新增 fixture | 其他 Agent |

### 1.2 Stage 3 模块（拟定）

| 模块 | 所有者 | 状态 | 允许修改者 | 禁止修改者 |
|------|--------|------|-----------|-----------|
| `emowall/storage/` | Storage Agent | 🔲 待实现 | Storage Agent | AI/Config/Emotion/GUI Agent |
| `emowall/storage/__init__.py` | Storage Agent | 🔲 待实现 | Storage Agent | 其他 |
| `emowall/storage/models.py` | Storage Agent | 🔲 待创建 | Storage Agent | 其他 |
| `emowall/storage/database.py` | Storage Agent | 🔲 待创建 | Storage Agent | 其他 |
| `emowall/storage/repository.py` | Storage Agent | 🔲 待创建 | Storage Agent | 其他 |
| `tests/test_storage.py` | Storage Agent | 🔲 待创建 | Storage Agent | 其他 |

### 1.3 未来模块（Stage 4/5 预览）

| 模块 | 预期所有者 | 预期状态 |
|------|-----------|---------|
| `emowall/emotion/` | Emotion Agent | Stage 4 |
| `emowall/gui/` | GUI Agent | Stage 5 |
| `emowall/app.py` | GUI Agent + Architect | Stage 5 |

---

## 2. 文件所有权详细划分

### 2.1 Stage 3 Agent 的文件范围

#### 允许创建/修改的文件

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `emowall/storage/__init__.py` | 修改 | 添加公共 API 导出 |
| `emowall/storage/models.py` | 创建 | `Conversation`, `MessageRecord` |
| `emowall/storage/database.py` | 创建 | `Database` 连接管理 |
| `emowall/storage/repository.py` | 创建 | `ConversationRepository` |
| `emowall/storage/errors.py` | 创建（建议） | `StorageError` 异常层级 |
| `tests/test_storage.py` | 创建 | ≥ 15 个测试用例 |

#### 明确禁止修改的文件

| 文件路径 | 原因 |
|----------|------|
| `emowall/ai/**/*.py` | Stage 2 已冻结 |
| `emowall/config/**/*.py` | Stage 1 已冻结 |
| `emowall/emotion/**/*` | Stage 4 范围 |
| `emowall/gui/**/*` | Stage 5 范围 |
| `emowall/__init__.py` | 不含业务逻辑 |
| `tests/test_ai_*.py` | Stage 2 已冻结 |
| `tests/test_config.py` | Stage 1 已冻结 |
| `tests/test_architecture.py` | 架构守护，由 Architect 管理 |
| `tests/conftest.py` | 共享 fixture，由 Architect 管理 |
| `AGENTS.md` | 长期规则，由项目负责人管理 |
| `docs/ARCHITECTURE.md` | 由 Architect 管理 |
| `docs/DEVELOPMENT_PLAN.md` | 由项目负责人管理 |
| `scripts/chat_probe.py` | Stage 2 工具 |

### 2.2 可能产生冲突的文件

| 文件路径 | 冲突风险 | 解决方案 |
|----------|---------|---------|
| `emowall/storage/__init__.py` | 低 | 仅 Storage Agent 修改 |
| `tests/test_architecture.py` | 中 | 如需新增守护规则，向 Architect 申请 |
| `tests/conftest.py` | 低 | 如需新增 fixture，向 Architect 申请 |
| `.gitignore` | 低 | 如需新增忽略规则，向 Architect 申请 |
| `requirements.txt` | 低 | Stage 3 仅用标准库，不需要新依赖 |

---

## 3. 并行开发工作流

### 3.1 Git 分支策略

```
main (主干)
├── feature/stage3-storage (Storage Agent)
├── feature/stage4-emotion (Emotion Agent, 后续)
└── feature/stage5-gui (GUI Agent, 后续)
```

**规则**：
1. 每个 Stage 使用独立分支
2. 合并前必须通过接口兼容性检查
3. 合并时必须 `$PY -m pytest` 全绿
4. 涉及公共接口变更时，必须先经过架构审批

### 3.2 合并检查清单

合并 Stage 3 分支前，必须验证：

- [ ] `tests/test_architecture.py` 全部通过
- [ ] `tests/test_storage.py` 全部通过（≥ 15 例）
- [ ] 已有测试未减少（`test_ai_*.py`、`test_config.py` 等）
- [ ] `emowall/storage` 不 import `ai / config / emotion / gui / app`
- [ ] `emowall/storage` 只使用标准库（`sqlite3` 等）
- [ ] 公共接口与冻结契约一致
- [ ] 无未解决的 `# TODO` / `# FIXME` 注释
- [ ] `$PY -m pytest` 全绿

### 3.3 接口兼容性检查流程

```
1. Storage Agent 提交 PR
2. Architect 检查公共接口是否与冻结契约一致
3. 如有差异：
   a. 微小调整（签名不变，仅文档/注释）：直接合并
   b. 签名变化：走接口变更申请流程（见 §4）
4. 运行全量测试
5. 合并到 main
```

---

## 4. 接口变更申请流程

### 4.1 何时需要申请

以下变更**必须**经过架构审批：

1. 修改已冻结的公共接口签名（参数、返回类型、异常）
2. 新增公共接口（在 `__init__.py` 的 `__all__` 中新增导出）
3. 删除或重命名公共接口
4. 修改数据模型的字段或类型
5. 修改异常层级的继承关系
6. 修改 `test_architecture.py` 的守护规则

以下变更**不需要**申请：

1. 修改私有方法（`_` 前缀）
2. 新增私有方法
3. 修改注释和文档
4. 修改测试用例（不删除已有用例）
5. 性能优化（不改变行为）

### 4.2 申请模板

```markdown
## 接口变更申请

**申请人**：[Agent 名称]
**日期**：[YYYY-MM-DD]
**影响范围**：[受影响的模块和文件]

### 变更描述

[描述要变更的接口，包括旧签名和新签名]

### 变更原因

[为什么需要这个变更]

### 兼容性影响

[这个变更对已有消费者有什么影响]

### 测试影响

[需要新增或修改哪些测试]

### 回滚方案

[如果变更失败，如何回滚]
```

### 4.3 审批流程

```
1. 申请人提交变更申请（在 docs/contracts/change-requests/ 中创建文件）
2. Architect 审查（≤ 1 个工作日）
3. 审批结果：
   - APPROVED：申请人实施变更
   - REJECTED：申请人修改或放弃
   - NEEDS_REVISION：申请人修改后重新提交
4. 实施变更（包括代码、测试、文档）
5. 更新冻结契约文档
6. 合并到 main
```

---

## 5. 并行开发冲突风险分析

### 5.1 Stage 3 特有风险

| 风险 | 可能性 | 影响 | 应对 |
|------|--------|------|------|
| Storage Agent 修改 `emowall/ai` 代码 | 低 | 高 | 架构守护测试自动检测 |
| Storage Agent 修改 `emowall/config` 代码 | 低 | 高 | 架构守护测试自动检测 |
| `MessageRecord.role` 类型与 `ChatMessage.role` 不一致 | 中 | 低 | 组合根负责映射，已在 data-models.md 中约定 |
| `MessageRecord.emotion` 字段格式与 Stage 4 不一致 | 低 | 中 | 预留 `str \| None`，Stage 4 实现时确认 |
| 标题自动生成逻辑有歧义 | 中 | 低 | 在 `investigation-report.md` 中标记为待确认 |

### 5.2 缓解措施

1. **架构守护测试**：自动检测跨层 import 违规
2. **接口冻结文档**：明确每个接口的签名和约束
3. **模块所有权矩阵**：明确谁可以修改什么
4. **变更申请流程**：防止未经审批的接口变更
5. **合并检查清单**：合并前逐条验证

---

## 6. Stage 3 Agent 工作指南

### 6.1 开始前检查

- [ ] 阅读 `AGENTS.md`（全文）
- [ ] 阅读 `docs/ARCHITECTURE.md`（全文）
- [ ] 阅读 `docs/contracts/stage3-contract-v1.md`（全文）
- [ ] 阅读 `docs/contracts/data-models.md`（全文）
- [ ] 阅读 `docs/contracts/threading-model.md`（全文）
- [ ] 确认 Git 分支为 `feature/stage3-storage`
- [ ] 确认 `$PY -m pytest` 当前全绿

### 6.2 开发顺序建议

1. `emowall/storage/errors.py` — 异常层级（`StorageError` + 3 个子类）
2. `emowall/storage/models.py` — 数据模型（`Conversation`, `MessageRecord`, `_normalize_title`）
3. `emowall/storage/database.py` — 连接管理（`Database`，含 `__cause__` 异常映射）
4. `emowall/storage/repository.py` — CRUD 操作（含 `update_message_emotion` 预留接口）
5. `emowall/storage/__init__.py` — 公共 API 导出
6. `tests/test_storage.py` — 测试用例（≥ 15 个，含标题截断、异常映射、预留接口测试）

### 6.3 完成后检查

- [ ] `$PY -m pytest` 全绿
- [ ] `grep -rn "PySide6\|httpx" emowall/storage` 无结果
- [ ] `tests/test_architecture.py` 全部通过
- [ ] 所有公共接口有类型标注和文档字符串
- [ ] 无未解决的 `# TODO` / `# FIXME`

---

## 7. 未来 Stage 的工作范围预览

### 7.1 Stage 4（情绪系统）

| 文件 | 操作 |
|------|------|
| `emowall/emotion/labels.py` | 创建 |
| `emowall/emotion/detector.py` | 创建 |
| `emowall/emotion/lexicon.py` | 创建 |
| `tests/test_emotion.py` | 创建 |

**约束**：不得修改 `emowall/storage` 代码。`MessageRecord.emotion` 字段已预留。

### 7.2 Stage 5（GUI 集成）

| 文件 | 操作 |
|------|------|
| `emowall/gui/main_window.py` | 创建 |
| `emowall/gui/chat_view.py` | 创建 |
| `emowall/gui/session_panel.py` | 创建 |
| `emowall/gui/settings_dialog.py` | 创建 |
| `emowall/gui/emotion_widget.py` | 创建 |
| `emowall/gui/worker.py` | 创建 |
| `emowall/gui/db_service.py` | 创建 |
| `emowall/app.py` | 创建 |
| `emowall/__main__.py` | 创建 |

**约束**：GUI 层是 storage 层的消费者，必须遵守冻结契约中的线程模型和数据模型约定。
