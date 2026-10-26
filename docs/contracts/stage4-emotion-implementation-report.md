# Stage 4 实现与验证报告（D01–D18 最终批准后）

> **状态（2026-10-26 C1–C4 整改后）：实现与测试完成；契约仍为 DRAFT；未冻结、未验收；已创建仅限 Stage 4 的本地候选提交（未推送）。**
> 日期：2026-10-26（Asia/Shanghai）
> 正式基线：`422d532335fc3c7d127478b7c1f20da05c0112c6` / tree `fd14d897072633c30c0a75be1adfd1ced77f382d`
> 工作分支：`feature/stage4-emotion-core`（本地，无 upstream，未推送）
> 当前 HEAD：`f52cc602115485616d2a469ee5e409ee41b0d8a5`（未新增 commit）
> 授权来源：项目负责人 2026-10-26 两份裁决指令（D01–D18 首批 + D08/D11/D15/D17 最终专项）。
> 说明：本报告是**实现与验证报告**，不是验收报告；测试通过不等于 Stage 4 PASS。

---

## 1. 结论摘要

- **D08 已实现**：5 条排除短语进入同一次候选扫描；局部区间遮蔽、0 分、不进
  `matched_keywords`、不覆盖整句其他情绪。
- **D08 黄金样本已更新**：G92–G94、G96、G102 改为 `calm 0.00`；新增 G103（`不开心果`，已知限制）
  与 G104–G112 组合句；G113 锁定 5 条排除短语。
- **D11 已落实**：五组展示值不变；契约补充“强调色/深色背景、不作浅色主题文字色”的约束。
- **D15 已落实**：105 基础 + 8 否定作为 v1.0 基线；契约附录 C 保存来源声明与核查记录；
  **未创建 LICENSE**，也未宣称许可证获批。
- **D17 已落实**：确定性基础算法 + D08 五条排除；排除与情感词/否定短语共用同一次扫描。
- **RED→GREEN**：D08 测试先失败 13 项，修复后 156 项情绪测试全绿；C1/C2 补测后 **163 项**全绿。
- 全量离线：**835 passed, 1 skipped, 10 deselected**（C1/C2 补测后；含本报告文档参数）。
- **已创建仅限 Stage 4 的本地候选提交（未推送）；未冻结、未验收、未进入 Stage 5。**

---

## 2. 本轮变更

### 2.1 代码

| 文件 | 变更 | 行数 |
| --- | --- | --- |
| `emowall/emotion/lexicon.py` | 新增 `EXCLUSION_PHRASES`（5 条，独立于 105 基础 + 8 否定） | 151 |
| `emowall/emotion/detector.py` | 候选加入 kind（排除=0，情感/否定=1）；排除仅遮蔽不计分；`matched_keywords` 跳过排除 | 153 |

### 2.2 测试

| 文件 | 变更 | 结果 |
| --- | --- | --- |
| `tests/test_emotion.py` | D08 阶段：G92–G94/G96 改为批准后的 calm；新增 G102–G112 与 G113（156 项）。C1/C2 阶段：补 G99、`str` 子类、NUL/控制字符（163 项） | D08 156 passed；整改后 **163 passed** |
| `tests/test_architecture.py` | 无逻辑变化（D13 文档串沿用上一轮） | 26 passed |

### 2.3 文档

| 文件 | 变更 |
| --- | --- |
| `docs/contracts/stage4-emotion-v1.md` | v0.3 DRAFT：D08 规则、D11 约束、D15 v1.0 基线/附录 C、D17 优先级、G92–G113 |
| `docs/contracts/stage4-emotion-pending-review.md` | 更新为“已批准”专项记录；修正 `别生气了`/`开心果酱` 遮蔽措辞 |
| `docs/contracts/stage4-emotion-decision-report.md` | 增加“历史记录”说明，指向本报告 |
| `docs/contracts/stage4-emotion-review-report.md` | 历史快照说明指向本报告 |
| `docs/contracts/stage4-emotion-implementation-report.md` | 本报告（新增） |

### 2.4 未改动

- 未修改 Stage 3 冻结契约、Storage 代码/测试、标签、原工作树。
- 未创建 LICENSE/NOTICE；未修改 `README.md`、`docs/DEVELOPMENT_PLAN.md`（保持已提交状态）。

---

## 3. D01–D18 合规矩阵

| ID | 批准状态 | 代码/契约落实 | 测试证据 | 结论 |
| --- | --- | --- | --- | --- |
| D01 | APPROVED | 5 个包级导出 + `source="rule"` | G98/G100 | 一致 |
| D02 | APPROVED | `NEGATION_PHRASES` 8 条 | G31/G32/G95/G97/G101 | 一致 |
| D03 | APPROVED | 加权 + 遮蔽 | G28–G36 | 一致 |
| D04 | APPROVED | 并列 calm/0.0/保留命中 | G39 | 一致 |
| D05 | APPROVED | 平静词计分 | G05/G10 | 一致 |
| D06 | APPROVED | 重复命中累加 | G21/G41/G71/G72 | 一致 |
| D07 | APPROVED | 规范词形/首现排序/去重/含否定 | G19/G36/G37 | 一致 |
| D08 | APPROVED | 5 条排除 + 局部遮蔽 + 0 分 | G92–G94/G96/G102/G104–G113 | 一致 |
| D09 | APPROVED | 非 str → TypeError；空串有效 | G62–G70 | 一致 |
| D10 | APPROVED | `presentation()` 严格 | G77/G78 | 一致 |
| D11 | APPROVED WITH CONSTRAINTS | 五组值 + 契约约束 | G74/G75 | 一致（约束仅文档） |
| D12 | APPROVED（Stage 5 行为） | 契约记录；emotion 层无代码 | — | 不适用本层 |
| D13 | APPROVED | 有限静态守护 + 限制说明 | G84/G85 | 一致 |
| D14 | APPROVED | 内置 `round(x, 2)` | G11–G17 | 一致 |
| D15 | APPROVED AS V1 BASELINE | `lexicon` 105+8；附录 C 来源/核查 | G97 | 一致（词典基线） |
| D16 | APPROVED | 固定规范化顺序 | G19/G88–G91/G99 | 一致 |
| D17 | APPROVED | 基础算法 + 5 条排除 | G20/G22–G36/G86–G87/G102–G112 | 一致 |
| D18 | APPROVED | 未改 `data-models.md`；契约声明正式接口 | 契约 §3.2/§10.6 | 一致 |

---

## 4. D08 实现细节

### 4.1 规则

| 排除短语 | 匹配边界 | 贡献 | 典型输入 | 输出 |
| --- | --- | --- | --- | --- |
| `生气勃勃` | 中文子串 | 0 | `生气勃勃` | calm 0.00 `()` |
| `别生气` | 中文子串 | 0 | `别生气` | calm 0.00 `()` |
| `笑话` | 中文子串 | 0 | `这是一个笑话` | calm 0.00 `()` |
| `开心果` | 中文子串 | 0 | `开心果` | calm 0.00 `()` |
| `not great` | 英文词边界 | 0 | `not great` | calm 0.00 `()` |

### 4.2 优先级（D17）

1. 规范化（NFKC → 撇号 → casefold → 空白折叠）。
2. 情感词、否定短语、排除短语进入同一次候选扫描。
3. 排序：`起点升序 → 长度降序 → 类别优先级（排除=0，其他=1）→ 声明顺序`。
4. 贪心接受非重叠匹配。
5. 排除命中只遮蔽自己的区间、贡献 0、不进 `matched_keywords`；其他命中正常计分。
6. 同起点同长度：排除短语优先；其他按固定声明顺序。

### 4.3 组合句验证

| 输入 | 结果 | 说明 |
| --- | --- | --- |
| `别生气，我很开心` | happy 0.33 `("开心",)` | 排除不吞整句 |
| `开心果让我很开心` | happy 0.33 `("开心",)` | 只遮蔽首个 `开心果` |
| `别生气了` | calm 0.00 `()` | 前后缀变体被遮蔽 |
| `开心果酱` | calm 0.00 `()` | 前后缀变体被遮蔽 |
| `别太生气` | angry 0.33 `("生气",)` | 已知限制：内部插入未覆盖 |
| `not-so-great` | happy 0.17 `("great",)` | 已知限制：连字符分隔未覆盖 |
| `笑笑话` | happy 0.17 `("笑",)` | 排除只遮蔽自己的区间 |
| `not  great` | calm 0.00 `()` | 空白折叠后命中 |
| `Not Great` | calm 0.00 `()` | casefold 后命中 |

### 4.4 已知限制

- `不开心果` → sad 0.33（`不开心` 位置 0 优先；**不代表正确语境判断**）。
- `别太生气`、`not-so-great` 等内部插入/分隔变体未覆盖。
- 只做有限规则，不做分词、语境推断或通用否定理解。

---

## 5. D11 / D15 / D17 落实

### 5.1 D11（APPROVED WITH CONSTRAINTS）

| 枚举 | label | emoji | color |
| --- | --- | --- | --- |
| HAPPY | 开心 | 😊 | `#FFB74D` |
| CALM | 平静 | 😌 | `#81C784` |
| SAD | 难过 | 😢 | `#64B5F6` |
| ANGRY | 生气 | 😠 | `#E57373` |
| SURPRISED | 惊讶 | 😲 | `#BA68C8` |

约束：仅作强调色/适当深色背景展示值，不作浅色主题文字颜色；Stage 5 必须同时展示
中文名、emoji、颜色；浅色主题文字色另行评估与验收。

### 5.2 D15（APPROVED AS V1 BASELINE）

- 105 条基础词条（happy 22 / sad 23 / angry 19 / surprised 22 / calm 19）
  + 8 条否定短语 = v1.0 基线；另有 5 条排除短语（D08），三类分开计数。
- 来源：本项目自编通用词，未复制第三方词典；仓库无 LICENSE/NOTICE；
  **未创建许可证**，许可证待发行前单独裁决。
- 契约附录 C 保存来源声明与核查记录；G97 锁定 105+8，G113 锁定 5 条排除。
- 不把测试覆盖/词典锁定称为自然语言理解能力。

### 5.3 D17（APPROVED）

- 基础算法：最左匹配、同起点最长、非重叠计分、ASCII 词边界、中文子串。
- D08 排除共用同一扫描；同起点同长度排除优先。
- 新增 G102–G112；G113 锁定排除短语；G92–G94/G96 更新为 calm。

---

## 6. RED → GREEN 证据

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| RED | `<python> -m pytest tests/test_emotion.py` | **13 failed, 143 passed** |
| GREEN | 同上 | **156 passed** |

RED 失败项：

- G92 `生气勃勃`、G93 `别生气`、G94 `这是一个笑话`、G96 `not great`、G102 `开心果`
  （旧实现仍返回 angry/happy）。
- G104 `别生气，我很开心`、G105 `开心果让我很开心`、G106 `别生气了`、G107 `开心果酱`、
  G110 `笑笑话`、G111 `not  great`、G112 `Not Great`（旧实现无排除）。
- `test_exclusion_phrases_exact`：`EXCLUSION_PHRASES` 尚不存在（ImportError）。

证据：`.tmp/stage4-evidence/d08-red.txt`、`d08-green.txt`。

C1/C2 只补测试、不改检测算法，因此没有伪造新的 RED；整改后情绪测试为 **163 passed**。

---

## 7. 测试结果

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Emotion 专项 | `<python> -m pytest tests/test_emotion.py` | **163 passed** |
| 架构守护 | `<python> -m pytest tests/test_architecture.py` | **26 passed** |
| 文档链接、路径和过期表述等检查 | `<python> -m pytest tests/test_docs.py` | **56 passed** |
| 全量离线 | `<python> -m pytest` | **835 passed, 1 skipped, 10 deselected** |

- 环境：Python 3.12.15（uv）、pytest 9.1.1、httpx 0.28.1；PySide6 未安装（1 项按设计跳过）；
  10 项 `integration` 默认排除。
- 基线（实现前）：662 passed, 1 skipped, 10 deselected。
- 证据：`.tmp/stage4-evidence/`（C1–C4 JUnit 为 `c1c4-*.xml`；旧 RED/GREEN 与最终实现证据保留）。
- Stage 3 记录 663 PASS 与本次基线 662 的差 1：Stage 3 原工作树含未入库文档
  `docs/contracts/change-requests/2026-10-24-storage-timestamp-compatibility.md`，而 `422d532`
  已提交树没有该文件；`tests/test_docs.py` 按文档参数化，因此恰好多 1 个文档参数。
  独立复验：基线 662 passed / 1 skipped，加入该文档后 663 passed / 1 skipped；无测试丢失。
- 计数闭合：662（基线）+ 163（emotion）+ 4（架构新增）+ 6（文档新增）= 835 passed；加 1 skip 为 836 JUnit tests。


---

## 8. 精确 diff 与提交状态

### 8.1 已跟踪修改（`git diff --numstat`）

| 文件 | +/− | 说明 |
| --- | --- | --- |
| `docs/contracts/stage4-emotion-v1.md` | +235 / −96 | v0.3：D08/D11/D15/D17、G92–G113、附录 C |
| `emowall/emotion/__init__.py` | +13 / −0 | 5 个导出（上一轮候选实现，本轮未改） |
| `tests/test_architecture.py` | +67 / −0 | emotion 守护（上一轮）+ D13 文档串 |

### 8.2 未跟踪文件

| 文件 | 行数 |
| --- | --- |
| `emowall/emotion/labels.py` | 46 |
| `emowall/emotion/lexicon.py` | 151 |
| `emowall/emotion/detector.py` | 153 |
| `tests/test_emotion.py` | 511 |
| `docs/contracts/stage4-emotion-pending-review.md` | 396 |
| `docs/contracts/stage4-emotion-decision-report.md` | 262 |
| `docs/contracts/stage4-emotion-review-report.md` | 242 |
| `docs/contracts/stage4-emotion-implementation-report.md` | 本报告 |

### 8.3 Git 状态

- C3 整改前 HEAD 为 `f52cc60`；本轮创建仅限 Stage 4 的本地候选提交
  （commit/tree SHA 见交付报告与 `.tmp/stage4-evidence/c1c4-git.txt`）；未推送、未合并、未建 PR、未动标签。
- C3 前工作树：3 个已跟踪修改 + 8 个未跟踪文件（含本报告）；提交内容见 §13 正式文件清单。
- `.tmp` 辅助文件 gitignored，不入库。

---

## 9. 未解决问题、风险与覆盖限制

1. **D11 浅色主题文字色**：未批准，留待 Stage 5 另行评估与验收。
2. **D15 项目 LICENSE**：未裁决；未创建许可证；发行前必须单独处理。
3. **D12 GUI 生命周期**：仅批准“成功后检测/取消失败保持 NULL”的原则；Stage 5 审定。
4. **D08 已知限制**：`不开心果` 仍 sad；`别太生气`、`not-so-great` 等变体未覆盖；
   不代表正确语境判断。
5. **D13 局限**：有限静态守护，不证明无间接 I/O。
6. **独立实现审查已完成**（2026-10-26，CONDITIONAL PASS）；C1–C4 整改已执行，待独立复审；Stage 4 未验收；契约未冻结。
7. **候选实现已创建仅限 Stage 4 的本地候选提交**（未推送）；等待独立复审/正式验收。
8. **文档状态**：`README.md`/`STAGE3_CURRENT_STATUS.md`/`data-models.md` 仍为旧状态；
   本报告未擅自改写。
9. **Stage 3 计数差 1 已解释**：Stage 3 原工作树多一个未入库文档
   `docs/contracts/change-requests/2026-10-24-storage-timestamp-compatibility.md`，文档参数化测试 +1；
   基线 662 passed / 1 skipped，加入该文档后 663 passed / 1 skipped；无测试丢失。

---

## 10. 独立实现审查与 C1–C4 整改状态

- 独立实现审查已于 2026-10-26 完成，结论为 **CONDITIONAL PASS**。
- C1/C2：已补 G99、`str` 子类、NUL/控制字符测试；情绪专项 **163 passed**，未改检测算法。
- C4：`docs/DEVELOPMENT_PLAN.md` Stage 4 状态已按指定措辞更新。
- C5：原 Stage 3 工作树计数已更正为 **4 modified + 19 untracked（23 项）**。
- C6：“文档一致性 56 passed”已改述为“文档链接、路径和过期表述等检查 56 passed”。
- C3：已完成安全检查并创建仅限 Stage 4 的本地候选提交（未推送）。
- 待独立审查员定向复审；D11 浅色主题文字色、D12 GUI 生命周期、D15 LICENSE 仍属 Stage 5/发行前事项。
- **Stage 4 尚未正式验收，契约尚未冻结；本轮不启动 Stage 5。**

---

## 11. Stage 3 保护

- 未修改 `docs/contracts/data-models.md`、`stage3-contract-v1.md`、
  `stage3-storage-timestamp-v1.3.md`、ADR-0003/0004、Storage 代码/测试/标签。
- 原工作树 `<stage3-worktree>` 本次整改前后 `git status` 一致：
  **4 个已跟踪修改 + 19 个未跟踪（合计 23 项）**；此前报告写的“3 + 20”为计数错误（总数相同）。
  本轮未 reset/clean/stash/覆盖式 checkout/删除/改 Git 配置。
- 未改远端、分支、标签；Stage 3 HEAD 未变。

---

## 12. 停止点与 C3 更新

原停止点（独立审查前）为“不提交、不推送、不合并、不冻结契约、不宣布 Stage 4 PASS、不启动 Stage 5”。
C3 授权后，本轮在完成正式文件清单、暂存检查和测试绑定检查后，创建了仅限 Stage 4 的
本地候选提交；**仍然不推送、不合并、不冻结契约、不宣布 Stage 4 PASS、不启动 Stage 5**。
等待独立审查员定向复审与正式验收。

---

## 13. C1–C4 定向整改关闭报告（2026-10-26）

### 13.1 测试覆盖补全（C1/C2）

- C1：在 `tests/test_emotion.py` 的 `GOLDEN_CASES` 中新增 G99：
  `"\u3000开心\u3000"` → happy / 0.33 / `("开心",)`。
- C2：新增 `test_str_subclass_is_accepted`，验证 `str` 子类按普通 `str` 接受。
- C2：新增 `test_nul_and_control_characters_are_accepted`，覆盖 NUL、STX/ETX、BEL、ESC/US、NUL/DEL。
- 本轮**只新增测试，未修改 `labels.py`/`lexicon.py`/`detector.py`**；没有伪造 RED。
- 结果：`tests/test_emotion.py` **163 passed**；原 156 项全部保留并通过。

### 13.2 计划状态与报告修正（C4/C5/C6）

- C4：`docs/DEVELOPMENT_PLAN.md` Stage 4 状态更新为：
  “负责人 D01–D18 裁决完成；候选实现与开发者测试完成；独立审查 CONDITIONAL PASS；C1–C4 整改中；尚未正式验收、尚未冻结契约、Stage 5 未授权。”
- C5：原 Stage 3 工作树实际为 **4 modified + 19 untracked（23 项）**；已重新确认，
  并更正本报告 §11 的旧计数“3 + 20”。
- C6：将“文档一致性 56 passed”改述为“文档链接、路径和过期表述等检查 56 passed”，
  避免把 `test_docs.py` 的覆盖面误读为 D01–D18 语义一致性。
- 662/663 差异已按未入库文档参数解释，见 §7。

### 13.3 历史证据与低风险登记（R1/R2/R3）

- R1：`labels._PRESENTATIONS` 与 `detector._APOSTROPHE_TRANSLATION` 是私有可变 `dict`；
  本轮按审查意见仅登记为低风险，不无依据扩大代码修改范围。
- R2：D08 RED 的修复前代码快照未单独保留；`d08-red.txt` 的原始输出保留，
  本轮未修改旧证据，也没有为测试补全伪造 RED。
- R3：`arch-red.txt` 与 `arch-green.txt` 均为 26 passed；前者不是真正的 RED，
  初始 RED 证据是 `red-emotion.txt`；该命名限制如实记录，旧文件未改写。

### 13.4 本轮复验结果

| 范围 | 结果 | JUnit |
| --- | --- | --- |
| Emotion 专项 | **163 passed** | `.tmp/stage4-evidence/c1c4-emotion.xml` |
| 架构守护 | **26 passed** | `.tmp/stage4-evidence/c1c4-arch.xml` |
| 文档链接/路径/过期表述检查 | **56 passed** | `.tmp/stage4-evidence/c1c4-docs.xml` |
| 默认离线全量 | **835 passed, 1 skipped, 10 deselected** | `.tmp/stage4-evidence/c1c4-full.xml` |

- 环境：Python 3.12.15 / pytest 9.1.1 / httpx 0.28.1；PySide6 未安装（1 skip）；10 项 integration 默认排除。
- 计数：662（基线）+ 163（emotion）+ 4（架构新增）+ 6（文档新增）= 835 passed；JUnit 836 tests。
- 当前候选 SHA-256 见交付报告；C3 提交的 commit/tree SHA 见 `.tmp/stage4-evidence/c1c4-git.txt`。

### 13.5 Stage 3 复核

- `git diff 422d532 -- docs/contracts/data-models.md docs/contracts/stage3-contract-v1.md docs/contracts/stage3-storage-timestamp-v1.3.md docs/contracts/threading-model.md docs/contracts/module-ownership.md docs/adr` 为空。
- `git diff 422d532 -- emowall/storage tests/test_storage.py tests/test_storage_timestamp_v13.py` 为空。
- 原 Stage 3 工作树 HEAD `2ddbdcd` 与状态（4 modified + 19 untracked）未变。

### 13.6 边界

本轮未推送、未合并、未创建远端发布标签、未修改 Stage 3 冻结契约、未重做 D01–D18、
未宣称 Stage 4 最终 PASS、未冻结 Stage 4 v1.0、未启动 Stage 5。
