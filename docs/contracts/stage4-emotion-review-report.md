# Stage 4 情绪核心只读审议报告

> **历史快照**：本文件记录 2026-10-26 负责人裁决**之前**的候选状态。
> 负责人随后已下达 D01–D18 裁决，D08/D11/D15/D17 也已最终批准；
> 当前状态见 `docs/contracts/stage4-emotion-implementation-report.md` 与契约 v0.3。
> 本文件不再代表当前状态。

> **状态：只读审议；不构成批准、冻结、验收或阶段推进。**
> 日期：2026-10-26（Asia/Shanghai）
> 正式基线：`422d532335fc3c7d127478b7c1f20da05c0112c6` / tree `fd14d897072633c30c0a75be1adfd1ced77f382d`
> 工作分支：`feature/stage4-emotion-core`（本地，无 upstream，未推送）
> 当前 HEAD：`f52cc602115485616d2a469ee5e409ee41b0d8a5` / tree `1ae4446b489a87538d616afdf01b88b3b79af756`
> 本报告不修改任何已提交内容；本轮未新增 commit、未改分支、未改远端。

---

## 1. 结论摘要

- 情绪核心**已实现并有可复现测试**，但**未获负责人批准、未冻结为公共契约、未做实现级独立审查、未做正式验收**。
- `docs/contracts/stage4-emotion-v1.md` 保持 **草案 v0.1 — 未冻结、未获批**。
- 自动审查拒绝的"已批准 / 冻结为 v1.0"表述已从文档恢复；本报告不声称任何批准。
- 现有 18 项待裁决事项（D01–D18），其中 12 项被草案标为阻塞；逐项见 §6。
- 当前代码实现的是**推荐候选语义**；其中 D02 的候选代码含 P1 三条否定短语，与草案黄金样本不一致，**必须由负责人裁决**（见 §7）。
- 待负责人逐项裁决前：不提交候选实现、不推送、不冻结契约、不进入 Stage 5。

---

## 2. 五种状态的明确区分（不得混用）

| 对象 | 已实现 | 已测试 | 已审查 | 已获负责人批准 | 已冻结契约 |
| --- | --- | --- | --- | --- | --- |
| `emowall/emotion` 候选实现 | 是（候选） | 是（144 专项） | **否**（实现级未审） | **否** | **否** |
| `tests/test_emotion.py` | 是 | 是（144 passed） | **否** | **否** | **否** |
| 架构守护增量（emotion 禁用依赖） | 是 | 是（26 passed） | **否** | **否** | **否** |
| `docs/contracts/stage4-emotion-v1.md` | 文档已存在 | 文档测试通过 | 是（独立只读审计，CONDITIONAL PASS；MAJOR 已修） | **否** | **否** |
| 黄金样本（G01–G101） | 是（测试内） | 是 | 部分（审计复算 46+21 条零差异） | **否** | **否** |
| Stage 4 正式验收 | 否 | 否 | 否 | 否 | 否 |

说明：

- **已实现**：代码在工作树中存在并断言了候选语义，不代表接口被批准或冻结。
- **已测试**：当前环境下的 pytest 结果；不等于独立审查或验收。
- **已审查**：仅指契约草案由隔离的只读审计员做过一次审计；实现代码**尚未**被独立审查。
- **已获负责人批准**：本轮**没有任何事项**取得可记录的正式批准。
- **已冻结契约**：**无**。任何"冻结"表述都不是事实。

---

## 3. 基线、隔离与 Git 状态

| 项 | 值 | 说明 |
| --- | --- | --- |
| 远端 `main` | `422d532…` | 本轮开始时重新 `ls-remote` 核验，与正式基线一致 |
| clone HEAD | `422d532…` | 隔离 clone 的起点 |
| 当前 HEAD | `f52cc60`（tree `1ae4446`） | 仅含契约草案与 `DEVELOPMENT_PLAN` 状态行；未再新增 commit |
| 分支 | `feature/stage4-emotion-core` | 本地；`@{u}` 报 "no upstream"；未推送 |
| 原工作树 | `<stage3-worktree>` | 只读；前后 `git status` 一致（3 modified + 20 untracked） |
| 远端/标签 | 未改 | 未 push、未 merge、未建 PR、未动标签 |

当前工作树中的候选实现（**未提交**）：

- 新增：`emowall/emotion/labels.py`、`emowall/emotion/lexicon.py`、`emowall/emotion/detector.py`、`tests/test_emotion.py`
- 修改：`emowall/emotion/__init__.py`、`tests/test_architecture.py`

---

## 4. 自动审查拒绝的审批记录：纠正说明

**被拒内容（已删除）**：

1. 文档头部 "v1.0 — 已由项目负责人批准……公共语义与词典冻结"。
2. 知识来源列表中的 "本契约 v1.0（项目负责人批准）"。

**纠正方式**：使用 `git checkout -- docs/contracts/stage4-emotion-v1.md` 将文档恢复为
`f52cc60` 已提交的草案状态，并全文检索确认不再存在
"已由项目负责人批准 / 冻结为 v1.0 / 批准记录（本契约）"字样。

**事实说明**：此前对话中的一次选择未被认定为正式授权。候选代码是在该选择之后按推荐方案写的，
因此其状态是"候选实现"，不是"获批实现"；本报告不据此声称任何批准。

---

## 5. 现有成果（已实现、已测试）

### 5.1 文件

| 文件 | 状态 | 内容 |
| --- | --- | --- |
| `emowall/emotion/labels.py` | 新增（未提交） | `Emotion`、`EmotionPresentation`、`presentation()` |
| `emowall/emotion/lexicon.py` | 新增（未提交） | 105 条词条 + 8 条否定短语（P0 5 + P1 3） |
| `emowall/emotion/detector.py` | 新增（未提交） | 规范化、非重叠匹配、计分、并列、强度、`EmotionResult`、`detect_emotion()` |
| `emowall/emotion/__init__.py` | 修改（未提交） | 5 个包级导出 |
| `tests/test_emotion.py` | 新增（未提交） | G01–G101 黄金样本 + 无效输入/确定性/展示/词典精确断言 |
| `tests/test_architecture.py` | 修改（未提交） | 新增 emotion 禁用 stdlib 与 `print`/`open` 守护（含负向用例） |

### 5.2 候选语义（代码实际行为）

1. 规范化：NFKC → 弯引号归一 → `casefold` → 空白折叠 + `strip`（D16 候选）。
2. 匹配：最左最长、非重叠贪心；ASCII 词边界；中文/emoji 子串（D17 候选）。
3. 权重：强词 1.0 / 弱词 0.5 / emoji 1.5；否定短语 1.0 → sad。
4. 选择：最高分唯一者胜；并列 → `calm`；无命中 → `calm`。
5. 强度：`round(min(1.0, score / 3.0), 2)`；并列回退 0.0；显式平静词按同一公式（D05 候选）。
6. 命中词：规范词形、首次出现升序、去重、含否定短语；并列回退时保留。
7. 展示：5 组 `label/emoji/color`（D11 候选）。

### 5.3 可复现证据

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `<python> -m pytest`（实现前） | 662 passed, 1 skipped, 10 deselected（29.00 s） |
| RED | `<python> -m pytest tests/test_emotion.py` | collection `ImportError`（已归档） |
| GREEN | 同上 | 144 passed（0.70 s） |
| 架构 | `<python> -m pytest tests/test_architecture.py` | 26 passed |
| 文档 | `<python> -m pytest tests/test_docs.py` | 53 passed（含本报告） |
| 全量 | `<python> -m pytest` | **813 passed, 1 skipped, 10 deselected**（31.73 s；含本报告的 1 个文档参数） |

- 环境：Python 3.12.15（uv）、pytest 9.1.1、httpx 0.28.1；PySide6 未安装（1 项按设计跳过）。
- 证据目录：`.tmp/stage4-evidence/`（gitignored）：`red-emotion.txt`、`green-emotion.txt`、
  `arch-red.txt`、`arch-green.txt`、`full-suite-*.txt/xml`、`env.txt`、`golden_check.out`。
- Stage 3 记录 663 PASS 与本次基线 662 的差 1：Stage 3 验收绑定 70 文件候选快照（含未入库文档），
  正式 commit 少一个 doc 测试参数；**无失败**，建议独立审查确认。

---

## 6. D01–D18 逐项待裁决

> "当前候选"= 现有代码/草案的实际行为；"推荐"= 建议负责人选择的方案及理由；
> "不决定风险"= 保持未决会带来的具体问题；"影响"= 对现有代码、测试与 Stage 5 集成的影响。

| ID | 待决问题 | 当前候选 | 推荐方案与理由 | 不决定时的风险 | 对代码、测试与 Stage 5 的影响 |
| --- | --- | --- | --- | --- | --- |
| D01 | 公共接口是否固定为 5 个名字（`Emotion`/`EmotionResult`/`EmotionPresentation`/`detect_emotion`/`presentation`），保留 `source="rule"`？ | 代码与草案均为 5 名；`__all__` 精确；两个 dataclass frozen | 批准 5 名 + `source`；理由：来自 ARCHITECTURE §3.4，Stage 5 需要 `result.emotion`/`intensity` 与 `presentation()`；不新增类 | 接口可能变化，Stage 5 调用点返工；G98/G100 需改 | `emotion/__init__.py`、`test_emotion` G98/G100、Stage 5 组合根 |
| D02 | 否定短语集合：文档出现 4/5 条；是否加入 P1（`不快乐`/`不满意`/`不愉快`）？ | **代码 8 条（P0+P1）**；草案 G32/G95 仍按 P0 期望 `happy`，G97 记 5 条——**代码与草案不一致** | 批准 8 条；理由：减少三类常见负面表达的明显误报；仍是闭集、确定性、可测 | 代码含未批准规则；若最终选 P0，需删 3 条短语、改 G32/G95、移除 G101、G97 改 5 条 | `lexicon`、`detector`、`test_emotion` G31/G32/G95/G97/G101、Stage 5 用户可见结果 |
| D03 | 否定短语语义：加权 + 遮蔽，还是出现即整句 `sad`？ | 加权 + 非重叠遮蔽（`not happy but wonderful` → 并列 → `calm`） | 加权 + 遮蔽；理由：与"命中词权重求和取最高"一致，避免一个否定词吞掉整句 | 混合句结果不确定，G33 期望不稳 | `detector` 选择逻辑、G33、Stage 5 显示 |
| D04 | 最高分并列时：`calm`？强度 0.0？是否保留命中词？ | `calm` / 0.0 / 保留全部命中（G39） | 保持；理由：与 ARCHITECTURE/PLAN "并列 → calm" 一致；0.0 表示无主导情绪 | 丢失"又开心又生气"的强度信号；未来需扩展字段 | `detector`、G39、Stage 5 壁纸强度 |
| D05 | 明确平静词（平静/冷静等）是否计分？胜出时强度？ | 计分，胜出时 `min(score/3)`（`平静` → 0.33） | 保持；理由：与其它类一致；无命中回退仍是 0.0 | G05/G10/G40 期望；用户对"平静"强度预期 | `detector`、G05/G10、Stage 5 |
| D06 | 同一词元重复出现是否重复计分？ | 每次命中累加（`开心开心` → 0.67），`matched` 去重 | 保持；理由：与"权重求和"字面一致，重复强调情绪更强 | G41/G71/G72 期望；若选单次计分需改 4 个断言 | `detector`、G41/G71/G72、Stage 5 强度 |
| D07 | `matched_keywords` 返回规范词形还是表面形式？排序/去重/含否定短语？ | 规范词形（英文小写）、首现升序、去重、含否定短语、并列保留 | 保持；理由：稳定可复现、便于调参；不持久化 | 调试接口变化；G19/G36/G37 等断言 | `detector`、`test_emotion`、未来调参；不影响 Storage |
| D08 | 是否引入排除词/白名单（如 `生气勃勃`、`笑话`、`别生气`）？ | 无排除词；G92–G94/G96 作为已知误报 characterization | v1 不设；理由：避免主观词表膨胀，误报透明可测 | 用户可见误报；Stage 5 表情偏差 | `lexicon`/`detector`、G92–G96、Stage 5 |
| D09 | 非 `str` 输入抛什么异常？ | `TypeError`（消息含 `text`）；空串/纯空白 → `calm` 0.0 | `TypeError`；理由：类型契约，编程错误应暴露而非吞成中性 | 调用方异常处理不一致 | `detector`、invalid 测试、Stage 5 组合根 |
| D10 | `presentation()` 只接受 `Emotion` 还是也接受 `str`？ | 只接受 `Emotion`；`"happy"`/`None` → `TypeError` | 严格；理由：避免隐式转换与拼写错误，GUI 从 `result.emotion` 取值 | 调用便利性 vs 明确性；G77/G78 | `labels`、`test_emotion`、Stage 5 |
| D11 | 5 组 `label/emoji/color` 是否批准？ | 开心😊`#FFB74D`、平静😌`#81C784`、难过😢`#64B5F6`、生气😠`#E57373`、惊讶😲`#BA68C8` | 批准；理由：单码位 emoji、`#RRGGBB`、语义直观、与词典 emoji 一致 | 与 GUI 主题冲突；G74/G75 期望 | `labels._PRESENTATIONS`、测试、Stage 5 GUI |
| D12 | 生成取消/失败时，是否对部分正文检测情绪？ | 未实现（属 Stage 5 组合根）；建议仅成功完成后检测，失败/取消保持 `NULL` | 仅成功后检测；理由：部分回复语义不完整，情绪可能误导；Storage 已允许 NULL | Stage 5 落库行为未定 | Stage 5 `app`/worker + Storage；emotion API 无变化 |
| D13 | 是否接受新增的 emotion 架构守护（禁 I/O/网络/DB + `print`/`open`）？ | **已实现**：`sqlite3`/`socket`/`http`/`urllib`/`ssl`/`subprocess`/`pathlib` + `print`/`open` AST 检查，26 passed | 批准；理由：落实 AGENTS §3/§6 的纯函数与隐私要求；负向用例证明会失败 | 未来若需文件读取/调试输出需先改契约 | `tests/test_architecture.py`；实现已符合 |
| D14 | 强度舍入方式？ | 内置 `round(x, 2)`；权重为 0.5 倍数，无 `.xx5` 边界 | 保持；理由：现行词典下与 HALF_UP 无差异；标准库 | 未来改权重可能出现舍入差异 | `detector._intensity`、G11–G17 |
| D15 | 105 条词条与权重是否批准？ | 已实现附录 A 全表；G97 逐条锁定 | 批准；理由：每类 ≥12、覆盖中英文/emoji、权重固定、非重叠可测 | 词典是全量行为，任何增删改都会破坏黄金样本 | `lexicon`、G97、Stage 5 识别质量 |
| D16 | 规范化规则是否批准？ | NFKC + 弯引号归一 + `casefold` + 空白折叠/`strip`（G19/G88–G91/G99） | 批准；理由：全角/大小写/弯引号/多空格在真实输入中常见；确定性 | G88–G90 期望；NFKC 对极少数兼容字符有影响 | `detector._normalize`、测试、Stage 5 输入 |
| D17 | 匹配与边界算法是否批准？ | 最左最长、非重叠贪心 + ASCII 词边界；中文/emoji 子串（G20/G22–G36/G86–G87） | 批准；理由：遮蔽/长词优先/英文边界可复现，无正则回溯 | 中文子串误报（见 D08）；混合文本解释成本 | `detector._accepted_hits`、大量黄金样本、Stage 5 |
| D18 | 是否同步 `data-models.md` §4.2 的旧接口名 `EmotionDetector.detect`？ | 未改 Stage 3 文档；本契约声明以 `detect_emotion` 为准 | 获批后同步或注明；理由：避免两份契约各说各话 | Stage 5 可能按旧名实现 | 文档一致性；不改代码；Stage 5 组合根接口名 |

### 6.1 建议的最小裁决包

优先裁决 **D01–D08、D11、D15–D17**（公共接口、否定语义、计分/并列、词典、展示、规范化、匹配）；
其余低风险项（D09/D10/D12/D13/D14/D18）可按推荐执行，但**仍需负责人明确记录**。

---

## 7. 契约草案与候选实现的差异（必须裁决）

| 项 | 草案 `stage4-emotion-v1.md`（G01–G91） | 候选代码/测试（G01–G101） |
| --- | --- | --- |
| 否定短语 | 5 条（P0：`不开心`/`不高兴`/`没意思`/`not happy`/`don't like`） | 8 条（P0 + P1：`不快乐`/`不满意`/`不愉快`） |
| G32 `不快乐` | `happy` / 0.33 / `("快乐",)` | `sad` / 0.33 / `("不快乐",)` |
| G95 `不满意` | `happy` / 0.17 / `("满意",)` | `sad` / 0.33 / `("不满意",)` |
| G101 `不愉快` | 不存在 | `sad` / 0.33 / `("不愉快",)` |
| G97 词典锁定 | 105 + 5 条 | 105 + 8 条 |

除上述差异外，候选实现与草案黄金样本逐条一致（由 144 项测试与独立复算覆盖）。
**在 D02 裁决前，不能宣称"实现符合契约"**：当前只是候选实现。

---

## 8. 审查状态

- **契约草案**：由隔离的只读审计员审计，结论 **CONDITIONAL PASS**（0 BLOCKER，5 MAJOR 已在草案中修正：
  新增 D16/D17、纠正 §1.1 措辞、补 G92–G96、补 G97、修正授权表述）。审计员另做了
  46 条表行 + 指定 21 条黄金样本的独立复算，**零差异**。
- **实现代码**：**未做独立审查**。建议的审查范围：diff 清单（3 个新文件 + 2 个修改）、
  144 项情绪测试、架构守护负向用例、RED/GREEN 证据、D02 差异。
- **Stage 4 验收**：未开始。实现完成 ≠ 测试通过 ≠ 已审查 ≠ 已批准 ≠ 已冻结 ≠ 已验收。

---

## 9. 风险与未解决问题

1. **D02 未决且代码与草案不一致**（P1）：这是当前最大的一致性风险。
2. **未批准**：所有候选语义均无正式批准记录；不得写入"已批准/冻结"。
3. **实现未独立审查**：只有契约草案被审计。
4. **已知误报**：`生气勃勃`、`别生气`、`这是一个笑话`、`not great` 按候选规则会误报（G92–G94/G96）。
5. **并列丢信号**：推荐方案把并列降为 `calm` + 0.0，可能丢失"又开心又生气"的强度。
6. **文档状态过期**：`README.md` 仍写 Stage 4 `⬜`；`STAGE3_CURRENT_STATUS.md` 仍写"Stage 4/5 未获授权"；
   `data-models.md` §4.2 仍写旧接口名；`DEVELOPMENT_PLAN.md` 已提交的状态行仍写"待裁决后再编码"，
   而工作树已有候选实现。均未擅自改写（避免把候选实现表述为阶段推进）。
7. **候选代码未提交**：工作树含未提交实现；这是有意保留，等待裁决。
8. **Stage 3 计数差 1**：663（Stage 3 报告）vs 662（本次基线）；无失败，建议独立审查解释。
9. **先前选择不构成授权**：本报告不把对话中的一次选择当作批准依据。

---

## 10. 请求负责人逐项裁决

在 D01–D18 获得明确裁决（批准/不批准 + 选择项）之前：

- 不提交候选实现；
- 不推送、不合并、不建 PR、不改标签；
- 不把契约冻结为 v1.0；
- 不进入 Stage 5；
- 不宣称 Stage 4 完成或验收通过。

如负责人希望保留当前 P1 候选，请在 D02 明确批准 8 条；若选择 P0，则按 §7 调整代码与测试后重跑证据。

---

## 附录 A：证据与命令

```text
工作区: <stage4-worktree>
python: .venv\Scripts\python.exe  (Python 3.12.15)
pytest: 9.1.1
httpx : 0.28.1

基线:      python -m pytest                          -> 662 passed, 1 skipped, 10 deselected
RED:       python -m pytest tests/test_emotion.py    -> ImportError（collection）
GREEN:     python -m pytest tests/test_emotion.py    -> 144 passed
架构:      python -m pytest tests/test_architecture.py -> 26 passed
文档:      python -m pytest tests/test_docs.py       -> 53 passed（含本报告）
全量:      python -m pytest                          -> 813 passed, 1 skipped, 10 deselected
证据目录:  .tmp/stage4-evidence/
```

## 附录 B：文件清单（工作树状态）

| 文件 | Git 状态 |
| --- | --- |
| `emowall/emotion/labels.py` | 新增，未跟踪 |
| `emowall/emotion/lexicon.py` | 新增，未跟踪 |
| `emowall/emotion/detector.py` | 新增，未跟踪 |
| `emowall/emotion/__init__.py` | 已修改，未提交 |
| `tests/test_emotion.py` | 新增，未跟踪 |
| `tests/test_architecture.py` | 已修改，未提交 |
| `docs/contracts/stage4-emotion-v1.md` | 已恢复为 `f52cc60` 的草案版本（无改动） |
| 本报告 | 新增，未跟踪 |
