# Stage 4 情绪核心契约（草案）

> **状态：草案 v0.1 — 未冻结、未获批。**
> 本文件不是已批准契约，也不构成对公共接口的冻结。文中凡标注 **[草案]** 的接口与语义，
> 必须经项目负责人裁决 §9 决策表后才能实施；标注 **[待裁决]** 的条目不得以默认值悄悄落地。
>
> 日期：2026-10-25（Asia/Shanghai）
> 工作树：`<stage4-worktree>`（隔离 clone，见 §0.3）
> 分支：`feature/stage4-emotion-core`
> 基线：`422d532335fc3c7d127478b7c1f20da05c0112c6` / tree `fd14d897072633c30c0a75be1adfd1ced77f382d`

---

## 0. 文档地位、授权与证据

### 0.1 本轮授权

项目负责人以本轮任务书（2026-10-25）授权 **Stage 4 Emotion 情绪识别核心的实施**，
明确不包含：推送、合并、创建 PR、修改远端标签、启动 Stage 5。
授权范围包含：隔离工作区、契约草案与黄金样本、必要准备、获批后的实现与测试、审查材料。

### 0.2 仓库内是否存在正式 Stage 4 批准记录

**结论：没有找到任何正式 Stage 4 公共语义/词典批准记录。** 逐项核对：

| 证据 | 内容 | 结论 |
| --- | --- | --- |
| `docs/adr/` | 仅 0001（配置）、0002（AI 核心）、0003/0004（Storage） | 无 emotion ADR |
| `README.md` | Stage 4 行状态为 `⬜` | 未开始 |
| `docs/STAGE3_CURRENT_STATUS.md` | 明确写 "Stage 4/5 未获授权" | 无批准 |
| `docs/DEVELOPMENT_PLAN.md` | Stage 4 章节是**计划**（目标/交付物/验收标准），无批准签署；其 Stage 4 状态行（本地已提交、未推送）只记录本轮实施授权 | 计划，非契约 |
| `docs/contracts/` | 无 stage4 契约文件 | 无 |
| 原工作树未跟踪文件 | 仅有 Stage 3 第四轮批准记录（Storage） | 与 Stage 4 无关 |

> 本轮任务书授权的是"实施"，并已在 `docs/DEVELOPMENT_PLAN.md` 的 Stage 4 状态行（本地已提交、未推送）
> 记录；这不等于批准 §3–§5 的公共语义与词典内容。

因此，本文件把知识来源严格分成三层：

- **[已批准]**：`AGENTS.md` §2/§3/§5/§6 的长期工程规则（架构铁律、隐私、测试规范）。
- **[设计定稿·未批准]**：`docs/ARCHITECTURE.md` §3.4、§7 的五类划分、规则法、
  `EmotionResult` / `EmotionPresentation` 字段草案；`docs/DEVELOPMENT_PLAN.md` Stage 4 的
  权重、强度、否定短语与验收标准。
- **[草案/待裁决]**：本文件 §3–§9 的全部公共接口与算法细节。

> 注：`docs/ARCHITECTURE.md` 开头写的是 "设计已定稿"，但同时说明 "文中接口为契约草案"；
> 这不等于项目负责人批准。`docs/STAGE3_CURRENT_STATUS.md` 的授权声明早于本轮任务书，
> 属于历史记录，不作为 Stage 4 的否决依据，也不应被静默改写（见 §10.4）。

### 0.3 基线与工作区隔离（已核验）

| 项 | 值 | 核验方式 |
| --- | --- | --- |
| 远端 `main` | `422d532335fc3c7d127478b7c1f20da05c0112c6` | `git ls-remote <repo> refs/heads/main` |
| clone HEAD | 同上 | `git rev-parse HEAD` |
| clone tree | `fd14d897072633c30c0a75be1adfd1ced77f382d` | `git rev-parse HEAD^{tree}` |
| 目标目录是否已存在 | 否（clone 前 `Test-Path` 为 `False`） | 先检查后 clone，未覆盖任何目录 |
| 分支 | `feature/stage4-emotion-core`（仅本地） | `git checkout -b`，未推送 |
| 原工作树 | `<stage3-worktree>`（未做任何写操作） | 仅只读命令；状态见 §0.5 |

### 0.4 环境与基线测试（已核验）

- Python 3.12.15（`uv` 创建 `.venv`），pytest 9.1.1，httpx 0.28.1；PySide6 未安装（与 Stage 3
  验收环境一致，GUI 导入用例按设计跳过）。
- 基线离线全量：`<python> -m pytest`
  → **662 passed, 1 skipped, 10 deselected**（29.00 s）。skip 为 PySide6 缺失；deselected 为
  `integration`（真实 Ollama）用例，符合 `pytest.ini` 默认约定。
- 该结果随 clone 的干净工作区产生；未在原工作树运行任何写操作。

### 0.5 隔离与不变量

- 所有实施仅在 `<stage4-worktree>` + `feature/stage4-emotion-core` 内进行。
- 原工作树 `<stage3-worktree>` 的未提交内容（Storage 第四轮工作）**不复制、不合并、
  不 stash、不 reset、不 clean、不改 Git 配置**。
- 本文件不改变 Stage 3 的任何已冻结公共接口、Schema、事务或线程规则。

---

## 1. 范围

### 1.1 本阶段范围内

1. 纯 Python、标准库优先、确定性、完全离线的文本 → 5 类基础情绪映射。
2. 自有中英文小词典（每类 ≥ 12 个词条），固定权重，非重叠匹配。
3. 否定短语及遮蔽规则（短语集合与语义均待 §9 D02/D03 裁决，当前**不是**已批准规则）。
4. 规范化、英文词边界、重复词处理。
5. 情绪强度、稳定排序的命中词元组。
6. 不可变的展示元数据。
7. 输入校验、确定性测试、架构依赖守护。

### 1.2 明确不做

- 不调用任何 AI 模型、不发网络请求、不读配置/数据库/文件。
- 不接入 GUI、不写 `emowall/app.py`、不启动 Stage 5。
- 不改 Stage 3 Storage 的 Schema、公共接口、事务与线程规则。
- 不新增公开状态转换 API、异常继承体系、包级导出（除 §9 D01 裁决的 5 个名字）。
- 不把回复正文或命中词写入日志或任何外部服务。
- 不新增第三方运行时依赖（`emowall/emotion` 只用标准库）。

---

## 2. 架构约束（[已批准]，不可由本契约修改）

依据 `AGENTS.md` §2、§3、§6：

1. `emowall/emotion` 是**扁平叶子层**：不得 import `emowall.ai` / `config` / `storage` / `gui` /
   `app`，也不得被其它叶子层 import。
2. 仅标准库；禁止 `PySide6` / `PyQt*` / `httpx` / `sqlite3` / 网络 / 文件 I/O。
3. 纯函数、无全局可变状态、无随机、无时间依赖；同输入必同输出。
4. 线程模型：不创建线程、不需加锁（纯函数、无状态）。
5. 隐私：不记录正文、不记录命中词、不发送任何请求。
6. 由 `tests/test_architecture.py` 守护；新增依赖规则必须同步更新该测试。

### 2.1 模块布局（[草案]，来自 DEVELOPMENT_PLAN Stage 4）

```text
emowall/emotion/
├─ __init__.py     # 仅导出 §3.2 裁决后的名字
├─ labels.py       # Emotion 枚举 + EmotionPresentation + presentation()
├─ lexicon.py      # 词典数据（词条、权重、否定短语），纯数据、无逻辑
└─ detector.py     # 规范化 / 匹配 / 计分 / EmotionResult / detect_emotion()
```

---

## 3. 公共接口（[草案]，待 §9 D01/D02/D07/D10/D11 裁决）

### 3.1 数据模型

```python
class Emotion(str, Enum):
    HAPPY = "happy"
    CALM = "calm"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"

@dataclass(frozen=True)
class EmotionResult:
    emotion: Emotion
    intensity: float                  # [0.0, 1.0]，2 位小数
    matched_keywords: tuple[str, ...] # 规范化后的命中词形，按首次出现排序、去重
    source: str = "rule"

@dataclass(frozen=True)
class EmotionPresentation:
    label: str    # 中文名，非空
    emoji: str    # 单个 emoji（单个 Unicode 码位）
    color: str    # #RRGGBB（大写十六进制）
```

### 3.2 函数与包级导出

```python
def detect_emotion(text: str) -> EmotionResult: ...
def presentation(emotion: Emotion) -> EmotionPresentation: ...
```

`emowall/emotion/__init__.py` 的 `__all__` **仅**包含：

```python
["Emotion", "EmotionResult", "EmotionPresentation", "detect_emotion", "presentation"]
```

- `Emotion` 是否属于包级导出，见 D01/D07（任务书的 "候选公开接口" 未列出 `Emotion`，
  但 `presentation(emotion)` 和 `result.emotion` 都需要它）。
- 不新增 `EmotionDetector` 类。`docs/contracts/data-models.md` §4.2 中的
  `EmotionDetector.detect(text)` 是早期示意，**不作为本阶段接口**；以 `detect_emotion(text)` 为准。
  该 Stage 3 文档的同步见 §9 D18（本阶段不擅自修改）。
- 包级导出由 G98 精确断言；`Emotion` 的三条等式由 G100 断言。
- `Emotion` 使用 `(str, Enum)`（按 `docs/ARCHITECTURE.md` §3.4），因此
  `Emotion.HAPPY == "happy"`、`Emotion.HAPPY.value == "happy"`、`Emotion("happy") is Emotion.HAPPY`。
  与 Storage 的映射始终使用 `.value`。

### 3.3 不变量

| 编号 | 不变量 |
| --- | --- |
| I1 | `emotion` ∈ 5 类 |
| I2 | `0.0 <= intensity <= 1.0`，且等于 2 位小数舍入后的值 |
| I3 | `matched_keywords` 是 `tuple[str, ...]`，元素两两不同 |
| I4 | `source == "rule"` |
| I5 | `EmotionResult` / `EmotionPresentation` 不可变（frozen dataclass） |
| I6 | 同一输入任意次调用返回相等结果（`==` 与逐字段相等） |

---

## 4. 算法语义（[草案]）

### 4.1 规范化（[草案] D16）

按顺序执行：

1. 类型校验：非 `str` → `TypeError`（D09）。
2. `unicodedata.normalize("NFKC", text)`：全角 → 半角、兼容字符归一。
3. 弯引号 `’`（U+2019）/ `‘`（U+2018）/ `` ` `` → ASCII `'`（U+0027），以便 `don't like` 等短语命中。
4. `casefold()`：英文大小写不敏感。
5. `re.sub(r"\s+", " ", ...).strip()`：空白折叠 + 去首尾（内部单个空格保留，用于 `not happy`）。

匹配只使用规范化后的文本；`matched_keywords` 返回**词典规范词形**（英文小写、中文原样），
不返回原文表面形式（D07）。

### 4.2 匹配：非重叠、最左最长（[草案] D17）

1. 对每个词元（含否定短语）在规范化文本中查找**所有**出现位置。
2. 英文/ASCII 词元要求词边界：若词元首字符是 `[A-Za-z0-9]`，则前一字符不得是 `[A-Za-z0-9]`
   （或位于开头）；末字符同理。中文与 emoji 词元不要求边界（中文按子串匹配）。
3. 候选按 `(起始位置升序, 词元长度降序, 词典声明顺序升序)` 排序。
4. 从左到右贪心接受：若候选起点 >= 上一个已接受候选的终点，则接受，否则丢弃。
5. 效果：`不高兴` 命中后，其覆盖的 `高兴` 不再命中；`想哭` 命中后，`哭` 不再命中。
   这就是 "遮蔽"（masking）的实现方式，也是否定短语遮蔽内部正向词的机制。
6. 不使用正则回溯，只用 `str.find` 循环 + 手写边界判断，保证 10k 文本无灾难性回溯。

### 4.3 否定短语

- 否定短语作为**权重 1.0 的 sad 词条**参与同一套匹配（内部可用单独的 `NEGATION_PHRASES`
  常量维护，但不得重复计分）。
- 候选短语集合（[草案]，D02）：`不开心`、`不高兴`、`没意思`、`not happy`、`don't like`。
- 语义（[草案]，D03）：命中否定短语只**累加 sad 权重**并遮蔽内部正向词，**不做整句强制覆盖**；
  最终仍按总分最高者判定。因此 `not happy but wonderful` 在推荐方案下是 1.0 : 1.0 并列 → `calm`。
- 未列入短语的否定形式（如 `不快乐`、`不开心地`、`didn't like`）**不额外处理**；
  其中 `不快乐` 会因 `快乐` 命中而判为 `happy`（已知误报，见 §10.2）。
  扩展否定规则必须另行批准，不得擅自实现。

### 4.4 计分

| 权重 | 值 | 适用 |
| --- | --- | --- |
| 强词 | 1.0 | 明确情绪词 |
| 弱词 | 0.5 | 语气词、弱情绪词 |
| emoji | 1.5 | 表情符号 |
| 否定短语 | 1.0 | 映射到 `sad` |

- 每个被接受的命中**按次数累加**（D06）：`开心开心` = 2.0。
- 分数只增不减，故 `score >= 0`。

### 4.5 选择与并列

1. 若没有任何命中 → `calm`，`intensity = 0.0`，`matched_keywords = ()`。
2. 取最高分；若最高分被两个及以上不同类别共享 → `calm`（D04）。
3. 若唯一的最高分类别是 `calm`（显式平静词胜出）→ `calm`，强度按 4.6 计算（D05）。
4. 否则取该类别。

### 4.6 强度与舍入

```text
intensity = round(min(1.0, score / 3.0), 2)
```

- 回退到 `calm`（无命中或并列）时 `intensity = 0.0`（D04）。
- 舍入使用 Python 内置 `round`（银行家舍入）。现行权重都是 0.5 的倍数，`score/3` 不会落在
  `x.xx5` 边界上，故舍入模式对现行词典无实际差异；未来改权重需重新评估（D14）。

### 4.7 命中词元组

- 内容：所有被接受的命中（包括落败类别的命中、包括并列回退时的命中），按**首次出现位置升序**，
  相同规范词形只保留一次（D07）。
- 只返回规范词形：英文小写（如 `happy`）、中文原样（如 `不开心`）、emoji 原样（如 `😊`）。
- 并列回退到 `calm` 时仍保留命中词（便于调试）；`matched_keywords` 为空仅表示"零命中"。

### 4.8 展示元数据（[草案] D11）

| Emotion | label | emoji | color |
| --- | --- | --- | --- |
| HAPPY | 开心 | 😊 | `#FFB74D` |
| CALM | 平静 | 😌 | `#81C784` |
| SAD | 难过 | 😢 | `#64B5F6` |
| ANGRY | 生气 | 😠 | `#E57373` |
| SURPRISED | 惊讶 | 😲 | `#BA68C8` |

- 5 个 emoji 均为单个 Unicode 码位，满足 "单个 emoji" 验收。
- `presentation()` 返回模块级 frozen 实例（结构相等、不可变）。
- 入参严格性：仅接受 `Emotion` 实例；传 `"happy"` / `None` → `TypeError`（D10）。

---

## 5. 词典与权重（[草案]，附录 A 为完整表）

- 每类词条数（含 emoji）：`happy 22`、`sad 23`、`angry 19`、`surprised 22`、`calm 19`；
  不含 emoji 的文本词条也均 ≥ 12。
- 英文统一小写；中文原样；emoji 原样。
- 同一类内词形不重复；允许"短词被长词包含"（如 `哭` ⊂ `想哭`），由 §4.2 的非重叠规则消解。
- 词典是全量公开行为的组成部分；G97 对附录 A 的 105 条词条（词形、类别、权重、声明顺序）
  做逐条精确断言，任何增删改都会失败，必须走契约修订。

### 5.1 词典内容风险说明

规则法必然有误报。已知且**未擅自修复**的例子（因为修复需要新增规则，超出本轮授权）：

| 输入 | 现行草案结果 | 原因 |
| --- | --- | --- |
| `不快乐` | `happy`（若 D02 不扩展） | 只批准了 `不开心`/`不高兴` 等短语 |
| `生气勃勃` | `angry` | `生气` 是子串，中文无词边界 |
| `别生气` | `angry` | 未批准"别 X"规则 |
| `不满意` | `happy`（若 D02 不扩展） | 只批准了 `不高兴` 等短语 |
| `这是一个笑话` | `happy` | `笑` 是 `happy` 的弱词（子串，无词边界） |

这些是**待裁决事项**，不是已通过行为；对应 characterization 测试见 §7.15（G92–G96），
均标记为已知限制，不得解释为期望行为。

---

## 6. 输入校验、边界与失败行为（[草案] D09）

| 输入 | 行为 |
| --- | --- |
| `str`（含空串） | 正常检测；空串/纯空白 → `calm`/`0.0`/`()` |
| 非 `str`（`None`、数字、bytes、list 等） | `TypeError`，消息含 "text" 与期望类型 |
| 10,000 字符级文本 | 不异常；结果确定；无长度上限 |
| `str` 子类 | 接受（按 `str` 处理） |
| 含 NUL / 控制字符 | 不异常；按普通字符处理 |

- 不把异常吞掉后返回 `calm`：类型错误必须暴露（否则调用方会把编程错误当成中性文本）。
- `detect_emotion` 不读取任何全局配置；不存在"关闭检测"的开关。

---

## 7. 黄金测试预期（逐例，可复现）

> 说明：
> - "intensity" 按 §4.6 计算；"matched" 按 §4.7 排序/去重。
> - **⚠️** 表示该行期望值依赖 §9 的待裁决项；裁决前不得写成"已批准"断言。
> - 所有中文/英文输入均按 §4.1 规范化后再匹配；表中显示原始输入。

### 7.1 五类基础正例

| ID | 输入 | emotion | intensity | matched | 备注 |
| --- | --- | --- | --- | --- | --- |
| G01 | `开心` | happy | 0.33 | `("开心",)` | |
| G02 | `难过` | sad | 0.33 | `("难过",)` | |
| G03 | `生气` | angry | 0.33 | `("生气",)` | |
| G04 | `惊讶` | surprised | 0.33 | `("惊讶",)` | |
| G05 | `平静` | calm | 0.33 | `("平静",)` | ⚠️ D05 |
| G06 | `😊` | happy | 0.50 | `("😊",)` | emoji 1.5 |
| G07 | `💔` | sad | 0.50 | `("💔",)` | |
| G08 | `😠` | angry | 0.50 | `("😠",)` | |
| G09 | `😲` | surprised | 0.50 | `("😲",)` | |
| G10 | `😌` | calm | 0.50 | `("😌",)` | ⚠️ D05 |

### 7.2 计分、强度与舍入

| ID | 输入 | emotion | intensity | matched | 计算 |
| --- | --- | --- | --- | --- | --- |
| G11 | `满意` | happy | 0.17 | `("满意",)` | 0.5/3 |
| G12 | `开心高兴` | happy | 0.67 | `("开心","高兴")` | 2.0/3 |
| G13 | `开心高兴快乐` | happy | 1.00 | 前三词 | 3.0/3 |
| G14 | `开心满意` | happy | 0.50 | `("开心","满意")` | 1.5/3 |
| G15 | `开心😊` | happy | 0.83 | `("开心","😊")` | 2.5/3 |
| G16 | `开心高兴快乐幸福` | happy | 1.00 | 前四词 | 4.0/3 截断 |
| G17 | `😊😄` | happy | 1.00 | `("😊","😄")` | 3.0/3 |
| G18 | `happy` | happy | 0.33 | `("happy",)` | |
| G19 | `HAPPY` | happy | 0.33 | `("happy",)` | casefold + 规范词形 |
| G20 | `开心happy` | happy | 0.67 | `("开心","happy")` | 中文相邻不阻断边界 |
| G21 | `开心，开心，开心，开心` | happy | 1.00 | `("开心",)` | 4 次命中、截断、去重；⚠️ D06 |

### 7.3 英文词边界

| ID | 输入 | emotion | intensity | matched | 说明 |
| --- | --- | --- | --- | --- | --- |
| G22 | `sadistic` | calm | 0.00 | `()` | `sad` 后有字母，拒绝 |
| G23 | `gladiator` | calm | 0.00 | `()` | `glad` 后有字母，拒绝 |
| G24 | `happiness` | calm | 0.00 | `()` | `happy` 后有字母，拒绝 |
| G25 | `I am happy!` | happy | 0.33 | `("happy",)` | 标点算边界 |
| G26 | `unhappy` | sad | 0.33 | `("unhappy",)` | 长词优先，`happy` 被遮蔽 |
| G27 | `We are not happy.` | sad | 0.33 | `("not happy",)` | 否定短语遮蔽 `happy` |

### 7.4 否定与遮蔽

| ID | 输入 | emotion | intensity | matched | 备注 |
| --- | --- | --- | --- | --- | --- |
| G28 | `我不开心` | sad | 0.33 | `("不开心",)` | 若未遮蔽：happy 1.0 + sad 1.0 → 并列 |
| G29 | `我不高兴` | sad | 0.33 | `("不高兴",)` | 同上 |
| G30 | `没意思` | sad | 0.33 | `("没意思",)` | |
| G31 | `I don't like it.` | sad | 0.33 | `("don't like",)` | ⚠️ D02（短语是否批准） |
| G32 | `不快乐` | happy | 0.33 | `("快乐",)` | ⚠️ D02；若扩展 P1 则变 sad |
| G33 | `not happy but wonderful` | calm | 0.00 | `("not happy","wonderful")` | ⚠️ D03/D04；硬覆盖方案为 sad 0.33 |

### 7.5 非重叠匹配

| ID | 输入 | emotion | intensity | matched | 说明 |
| --- | --- | --- | --- | --- | --- |
| G34 | `想哭` | sad | 0.33 | `("想哭",)` | 若同时计 `哭` 则为 0.50 |
| G35 | `有点想哭` | sad | 0.33 | `("想哭",)` | 位置无关 |
| G36 | `不高兴，但也不难过` | sad | 0.67 | `("不高兴","难过")` | `高兴` 被遮蔽；`不难过` 非已批准短语，故 `难过` 仍命中（sad 2.0） |

### 7.6 混合类别、胜出与排序

| ID | 输入 | emotion | intensity | matched | 说明 |
| --- | --- | --- | --- | --- | --- |
| G37 | `开心，生气，愤怒` | angry | 0.67 | `("开心","生气","愤怒")` | happy 1.0 < angry 2.0 |
| G38 | `开心，难过，伤心` | sad | 0.67 | `("开心","难过","伤心")` | happy 1.0 < sad 2.0 |
| G39 | `开心，生气` | calm | 0.00 | `("开心","生气")` | ⚠️ D04 并列回退 |
| G40 | `开心😊 平静` | happy | 0.83 | `("开心","😊","平静")` | calm 显式命中但落败 |
| G41 | `开心 难过 开心` | happy | 0.67 | `("开心","难过")` | ⚠️ D06 重复计数；去重 |

### 7.7 20 条独立中性文本（全部 calm / 0.00 / `()`）

| ID | 输入 |
| --- | --- |
| G42 | `这是一段普通的说明文字。` |
| G43 | `会议室在三楼东侧。` |
| G44 | `请把文件放到桌面上。` |
| G45 | `今天的天气是阴天。` |
| G46 | `我需要核对一下表格数据。` |
| G47 | `列车将在十分钟后到达。` |
| G48 | `这个函数返回布尔值。` |
| G49 | `密码需要至少八位字符。` |
| G50 | `请在周五之前提交申请。` |
| G51 | `打印机缺纸了。` |
| G52 | `我下午三点有个会议。` |
| G53 | `这段代码使用标准库。` |
| G54 | `快递预计明天送达。` |
| G55 | `请关闭所有电源。` |
| G56 | `这本书共有十二个章节。` |
| G57 | `The report is due on Friday.` |
| G58 | `Please update the spreadsheet.` |
| G59 | `The meeting room is on the third floor.` |
| G60 | `Insert the cable into the port.` |
| G61 | `The package arrives tomorrow.` |

> 自检：测试同时断言这 20 条与词典"零命中"（中文子串、英文边界），防止未来加词后
> 中性样本悄悄失效。

### 7.8 空白、长文本、无效输入

| ID | 输入 | 期望 |
| --- | --- | --- |
| G62 | `""` | calm / 0.00 / `()` |
| G63 | `" \t\n\r\f\v"`（空格/制表/换行/回车/换页/垂直制表） | calm / 0.00 / `()` |
| G64 | `  开心  ` | happy / 0.33 / `("开心",)` |
| G65 | `开 心` | calm / 0.00 / `()`（中文不跨空格匹配） |
| G66 | `"这是一段很长的文本。" * 1000`（10,000 字符） | calm / 0.00 / `()`，不异常 |
| G67 | `"这是一段很长的文本。" * 1000 + "开心"` | happy / 0.33 / `("开心",)` |
| G68 | `None` | `TypeError`，消息含 `text` 与期望类型 |
| G69 | `123` | `TypeError`，消息含 `text` 与期望类型 |
| G70 | `b"happy"` | `TypeError`，消息含 `text` 与期望类型 |

### 7.9 重复词

| ID | 输入 | emotion | intensity | matched | 备注 |
| --- | --- | --- | --- | --- | --- |
| G71 | `开心开心` | happy | 0.67 | `("开心",)` | ⚠️ D06 每次累加 |
| G72 | `开心开心开心` | happy | 1.00 | `("开心",)` | ⚠️ D06 |

### 7.10 确定性

| ID | 内容 |
| --- | --- |
| G73 | 取 `开心`、`not happy but wonderful`、`😊😄`、20 条中性之一、10k 长文本，各连续调用 100 次；每次 `EmotionResult` 逐字段相等、`matched_keywords` 元组相等 |

### 7.11 展示元数据与不可变性

| ID | 内容 |
| --- | --- |
| G74 | 5 类 `presentation()` 均返回非空 `label`、`len(emoji) == 1`、`color` 匹配 `^#[0-9A-F]{6}$` |
| G75 | 5 类精确值：HAPPY=`("开心","😊","#FFB74D")`、CALM=`("平静","😌","#81C784")`、SAD=`("难过","😢","#64B5F6")`、ANGRY=`("生气","😠","#E57373")`、SURPRISED=`("惊讶","😲","#BA68C8")` |
| G76 | 对 `EmotionPresentation` 赋值字段抛 `FrozenInstanceError` |
| G77 | `presentation("happy")` → `TypeError`（⚠️ D10） |
| G78 | `presentation(None)` → `TypeError` |

### 7.12 结果不变量

| ID | 内容 |
| --- | --- |
| G79 | 对 §7 全部输入（含 20 条中性、空串、10k 长文本）结果满足 I1–I4（emotion 值域、intensity 范围、matched 去重、source） |
| G80 | 对 `EmotionResult` 赋值字段抛 `FrozenInstanceError` |

### 7.13 词典与架构守护

| ID | 内容 |
| --- | --- |
| G81 | 每类词条数 ≥ 12；且不含 emoji 的文本词条也 ≥ 12 |
| G82 | 词元非空、同类内不重复、跨类不重复（否定短语除外）、权重 ∈ {0.5, 1.0, 1.5} |
| G83 | §7.7 的 20 条中性语料与词典零命中 |
| G84 | `tests/test_architecture.py` 既有规则全绿：emotion 不 import Qt / 兄弟层 / 第三方 |
| G85 | 新增 emotion 禁用依赖守护：`sqlite3`、`socket`、`http`、`urllib`、`ssl`、`subprocess`、`pathlib`；AST 检查无 `print(` / `open(` 调用（⚠️ D13） |

### 7.14 规范化与边界补充

| ID | 输入 | emotion | intensity | matched | 说明 |
| --- | --- | --- | --- | --- | --- |
| G86 | `made` | calm | 0.00 | `()` | `mad` 后有字母，边界拒绝 |
| G87 | `sadness` | calm | 0.00 | `()` | `sad` 后有字母，边界拒绝 |
| G88 | `ＨＡＰＰＹ`（全角） | happy | 0.33 | `("happy",)` | NFKC + casefold |
| G89 | `NOT HAPPY` | sad | 0.33 | `("not happy",)` | casefold |
| G90 | `don’t like it`（弯引号） | sad | 0.33 | `("don't like",)` | 引号归一后命中 |
| G91 | `NOT   HAPPY`（多空格） | sad | 0.33 | `("not happy",)` | 空白折叠 |

### 7.15 已知限制（characterization，不得当作期望行为）

> 以下断言记录的是**当前草案规则下的可复现结果**，用于防止误报被悄悄"修好"或扩大；
> 它们不是产品期望行为。修掉任意一条都需要先批准新的否定/排除规则（D02/D08）。

| ID | 输入 | emotion | intensity | matched | 已知误报原因 |
| --- | --- | --- | --- | --- | --- |
| G92 | `生气勃勃` | angry | 0.33 | `("生气",)` | 中文子串，无词边界 |
| G93 | `别生气` | angry | 0.33 | `("生气",)` | 未批准"别 X"规则 |
| G94 | `这是一个笑话` | happy | 0.17 | `("笑",)` | `笑` 弱词子串 |
| G95 | `不满意` | happy | 0.17 | `("满意",)` | ⚠️ D02；若批准 P1 则变 sad 0.33 |
| G96 | `not great` | happy | 0.17 | `("great",)` | 未批准 `not` 前缀规则 |

### 7.16 词典、导出与规范化的精确断言

| ID | 内容 |
| --- | --- |
| G97 | 附录 A.1–A.5 的 105 条词条 + A.6 的 5 条否定短语，逐条精确断言词形、类别、权重与声明顺序 |
| G98 | `emowall.emotion.__all__ == ["Emotion", "EmotionResult", "EmotionPresentation", "detect_emotion", "presentation"]`，且 5 个名字均可从包级导入 |
| G99 | `"\u3000开心\u3000"`（全角空格）→ happy / 0.33 / `("开心",)`（NFKC 转空格后 strip） |
| G100 | `Emotion.HAPPY == "happy"`；`Emotion.HAPPY.value == "happy"`；`Emotion("happy") is Emotion.HAPPY` |

---

## 8. 测试计划与验收映射

### 8.1 测试文件

| 文件 | 内容 |
| --- | --- |
| `tests/test_emotion.py` | G01–G100（表驱动 ≥ 25 组输入 + 词典/中性/确定性/展示/不变量） |
| `tests/test_architecture.py` | G84 既有守护；G85 新增 emotion 禁用依赖守护（含负向用例） |

### 8.2 与任务书 §6 的映射

| 任务书要求 | 覆盖用例 |
| --- | --- |
| 五类基础正例 | G01–G10 |
| 20 条独立中性文本 | G42–G61（+ G83 自检） |
| 每类至少 12 个词条 | G81 |
| 计分、并列、强度与舍入 | G11–G21、G39、G40 |
| 否定遮蔽、重叠匹配、英文边界 | G22–G36、G86–G87 |
| 规范化（大小写 / 全角 / 弯引号 / 空白折叠） | G19、G88–G91、G99 |
| 空白、长文本、无效输入 | G62–G70 |
| 重复词、命中词排序与去重 | G19、G21、G41、G71–G72 |
| 已知误报（characterization，非期望行为） | G92–G96 |
| 词典 / 导出 / 枚举精确断言 | G97–G98、G100 |
| 同一输入 100 次确定性 | G73 |
| 展示元数据 | G74–G78 |
| 架构依赖检查 | G84–G85 |

### 8.3 执行顺序（AGENTS §9 回归规范）

1. **RED**：先写 `tests/test_emotion.py`，在未实现的 emotion 包上运行，确认因
   `ImportError` / `AttributeError` 失败；保存原始输出。
2. **GREEN**：实现 `labels.py` / `lexicon.py` / `detector.py`，同一测试转绿；保存输出。
3. 定向：`<python> -m pytest tests/test_emotion.py tests/test_architecture.py -q`
4. 全量离线：`<python> -m pytest`（默认排除 `integration`），记录 passed / skipped / deselected。
5. 记录环境（Python、pytest、httpx 版本）、commit、tree；证据存于工作区 `.tmp/stage4-evidence/`
   （gitignored），报告中给出可复现命令与关键输出。

### 8.4 Stage 4 验收清单（获批后适用）

- [ ] 五类正例全命中
- [ ] 20 条中性文本全部 `calm`
- [ ] 每类 ≥ 12 词条
- [ ] 计分/强度/舍入符合 §4.4–4.6
- [ ] 否定短语与遮蔽符合 §4.2–4.3（按 D02/D03 裁决）
- [ ] 英文边界、非重叠、重复词、排序/去重符合 §4.7
- [ ] 空白/长文本/无效输入符合 §6
- [ ] 100 次确定性
- [ ] 展示元数据符合 §4.8
- [ ] 架构守护全绿
- [ ] 全量离线 pytest 全绿
- [ ] `docs/DEVELOPMENT_PLAN.md` Stage 4 状态已更新（实施阶段按 AGENTS §7 执行）
- [ ] 本地提交完成（不推送），`git status` 除 `.venv/`、`.tmp/` 外干净
- [ ] 证据保存在 `.tmp/stage4-evidence/`（基线、RED、GREEN、全量、环境）

---

## 9. 待裁决决策（集中报告负责人）

> 推荐方案 = 若无反对即可实施；替代方案 = 需要负责人明确选择。带 **阻塞** 的条目未裁决前，
> 其对应的黄金样本与实现不得冻结。

| ID | 事项 | 推荐方案 | 替代方案 | 兼容性影响 | 阻塞 |
| --- | --- | --- | --- | --- | --- |
| D01 | 公共接口形状与包级导出 | 冻结 5 个名字：`Emotion`、`EmotionResult`、`EmotionPresentation`、`detect_emotion`、`presentation`；`source="rule"` 保留 | 不导出 `Emotion`（调用方改从子模块导入）；或新增 `EmotionDetector` 类 | Stage 5 组合根、测试、未来调参都依赖；改动需变更申请 | 是 |
| D02 | 否定短语集合 | 文档出现过的 5 条：`不开心`、`不高兴`、`没意思`、`not happy`、`don't like`；另建议扩展 `不快乐`、`不满意`、`不愉快`（P1） | 仅 4 条（不含 `don't like`）；或扩到 `not good`、`didn't like` 等 | 决定 `不快乐`/`不满意` 的结果；扩展需逐条批准 | 是 |
| D03 | 否定语义 | 加权 + 非重叠遮蔽，不整句覆盖（`not happy but wonderful` → 并列 → calm） | 硬覆盖：出现否定短语即 sad | 混合句结果不同；影响存储的 emotion | 是 |
| D04 | 并列与并列强度 | 最高分并列 → `calm`，`intensity=0.0`，保留全部命中词 | 并列 → calm 但保留 `并列分/3` 强度；或按类别优先级 | 决定 `intensity` 与 `matched_keywords` | 是 |
| D05 | 明确平静词强度 | 平静词按普通权重计分，胜出时用同一强度公式（`平静` → 0.33） | 平静词只遮蔽不计分（calm 恒 0.0） | 决定"我很平静"的强度信号 | 是 |
| D06 | 重复词计分 | 每次命中累加（`开心开心` → 0.67） | 每个词元只计一次（0.33） | 决定 intensity | 是 |
| D07 | `matched_keywords` 内容与排序 | 规范词形、首次出现升序、去重、含否定短语、并列回退时保留 | 原文表面形式；或按类别/权重排序 | 调试/调参接口；不持久化 | 是 |
| D08 | 排除词 | v1 不设排除词；已知误报（`生气勃勃`、`别生气`）写入测试与风险 | 建立排除表（需逐项批准） | 词典匹配行为 | 是（建议"无"） |
| D09 | 非 `str` 输入的异常类型 | `TypeError`；空串/纯空白 → calm 0.0 | `ValueError`；或自定义异常 | 调用方错误处理 | 否（低风险） |
| D10 | `presentation()` 入参严格性 | 仅接受 `Emotion` 实例，`"happy"` → `TypeError` | 接受 `str` 并 `Emotion(str)` 转换 | GUI 调用便利性 | 否（低风险） |
| D11 | 展示元数据取值 | §4.8 的 5 组 label/emoji/color | 负责人指定其它取值 | Stage 5 表情指示器显示 | 是（内容确认） |
| D12 | 取消/失败的部分回复 | 仅成功完成后检测；取消/失败的部分消息保持 `emotion=NULL` | 对部分正文也检测 | Stage 5 组合根行为；不影响 emotion API | 否（Stage 5 前置） |
| D13 | 架构守护加强 | emotion 禁用 `sqlite3`/`socket`/`http`/`urllib`/`ssl`/`subprocess`/`pathlib`，并 AST 检查 `print`/`open` | 仅依赖现有第三方白名单 | 仅测试 | 否（低风险） |
| D14 | 舍入方式 | 内置 `round(x, 2)`；权重为 0.5 倍数，无 `.xx5` 边界 | `decimal.ROUND_HALF_UP` | 现行词典无差异；未来改权重需复评 | 否（低风险） |
| D15 | 词典内容与权重 | 附录 A 全表 | 负责人增删词条/调权重 | 全部黄金样本 | 是（内容确认） |
| D16 | 规范化规则 | NFKC → 弯引号归一 → casefold → 空白折叠 + strip | 仅 casefold + strip（不处理全角/弯引号） | 决定 G19、G88–G91、G99；影响英文短语命中 | 是 |
| D17 | 匹配与边界算法 | 最左最长、非重叠贪心；ASCII 词边界；中文/emoji 子串匹配 | 正则边界；或全局最长优先（非最左） | 决定 G20、G22–G36、G86–G87；直接改变遮蔽行为 | 是 |
| D18 | Stage 3 文档同步 | 获批后在 Stage 4 提交中把 `data-models.md` §4.2 的 `EmotionDetector.detect` 改为 `detect_emotion`，或注明以本契约为准 | 保持 Stage 3 文档不动，仅在本契约声明差异 | 文档一致性；不改代码 | 否 |

> 裁决时请一并注意两处措辞差异：
> 1. D02 的替代项"仅 4 条（不含 `don't like`）"与 `docs/ARCHITECTURE.md` §7 已出现的
>    `don't like` 冲突；
> 2. D03 的推荐（加权 + 遮蔽）与 `docs/DEVELOPMENT_PLAN.md` Stage 4 "否定短语**优先映射**到 sad"
>    的措辞存在解释差异——后者更像整句硬覆盖。请明确选择其一。

### 9.1 建议的最小放行路径

若负责人只希望尽快放行，可先裁决 **D01–D08、D11、D15、D16、D17**（公共语义、匹配算法与词典内容），
其余低风险条目按推荐方案执行，并在实现完成后一次性复核。任何裁决都请以"批准/不批准 + 选择项"
的形式记录，便于写入契约与提交说明。

---

## 10. 风险与已知限制

### 10.1 规则法精度

- 关键词法无法理解反讽、上下文与程度副词；V0.1 接受（`docs/DEVELOPMENT_PLAN.md` 风险表已记录），
  `source="rule"` 为未来换模型预留。
- 中文子串匹配会带来误报（`生气勃勃`）；未批准排除词前不修复。

### 10.2 草案规则下的已知误报（待裁决）

- `不快乐` / `不满意` → happy（若 D02 不扩展）。
- `别生气` → angry；`not great` → happy（若 `not` 规则未批准）。
- 对应 characterization 测试 G92–G96，显式标记为已知限制，不得伪装成通过；
  修掉任一误报都要先批准新的否定/排除规则（D02/D08）。

### 10.3 并列回退丢失信号

推荐方案把并列降为 `calm` + 0.0，可能丢失"又开心又生气"的强度信息；若未来壁纸需要更丰富信号，
应通过契约修订增加次级强度字段，而不是在本阶段偷偷改变语义。

### 10.4 文档状态可能过期

`README.md` 与 `docs/STAGE3_CURRENT_STATUS.md` 仍写 "Stage 4 未授权/⬜"。本轮授权来自任务书，
已记录在本地已提交（未推送）的 `docs/DEVELOPMENT_PLAN.md` Stage 4 状态行；但这两份旧文档仍是历史快照。
Stage 4 实施提交时应同步更新 `DEVELOPMENT_PLAN.md` 状态（AGENTS §7），
但**不擅自重写** Stage 3 的历史授权记录。

### 10.5 与 Stage 3 的边界

- 不改 `emowall/storage`；只通过组合根（Stage 5）调用既有
  `update_message_emotion(message_id, *, emotion, emotion_intensity)`。
- 组合根也可以在 `append_message(..., emotion=..., emotion_intensity=...)` 时直接写入；
  两条路径都由组合根决定，emotion 层不感知。
- `intensity ∈ [0,1]` 满足 Storage 的 `CHECK` 约束；`emotion` 存 `.value` 字符串。
- Stage 3 的 `MessageRecord.emotion/emotion_intensity` 可为 `NULL`，与"取消/失败不检测"兼容。

### 10.6 Stage 3 文档中的旧示意

`docs/contracts/data-models.md` §4.2 仍写 `EmotionDetector.detect(text)`，与本契约的
`detect_emotion(text)` 不一致。本阶段不修改 Stage 3 文档；建议在获批的 Stage 4 实施提交中
同步（D18），避免两份契约各说各话。

---

## 11. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-25 | 初稿：基线核验、接口草案、算法语义、词典、100 条黄金样本、18 项决策请求 |

---

## 附录 A：词典全表（[草案]）

> 权重：`1.0` 强词 / `0.5` 弱词 / `1.5` emoji / 否定短语 `1.0`（映射 sad）。

### A.1 happy（22）

| 词条 | 权重 |
| --- | --- |
| 开心 | 1.0 |
| 高兴 | 1.0 |
| 快乐 | 1.0 |
| 幸福 | 1.0 |
| 兴奋 | 1.0 |
| 愉快 | 1.0 |
| 满意 | 0.5 |
| 太好了 | 1.0 |
| 太棒了 | 1.0 |
| 哈哈 | 1.0 |
| 嘻嘻 | 0.5 |
| 笑 | 0.5 |
| happy | 1.0 |
| glad | 1.0 |
| joyful | 1.0 |
| wonderful | 1.0 |
| great | 0.5 |
| awesome | 1.0 |
| love | 1.0 |
| yay | 1.0 |
| 😊 | 1.5 |
| 😄 | 1.5 |

### A.2 sad（23）

| 词条 | 权重 |
| --- | --- |
| 难过 | 1.0 |
| 伤心 | 1.0 |
| 悲伤 | 1.0 |
| 失落 | 0.5 |
| 沮丧 | 1.0 |
| 郁闷 | 0.5 |
| 委屈 | 0.5 |
| 哭 | 0.5 |
| 想哭 | 1.0 |
| 遗憾 | 0.5 |
| 绝望 | 1.0 |
| 心痛 | 1.0 |
| 唉 | 0.5 |
| sad | 1.0 |
| unhappy | 1.0 |
| depressed | 1.0 |
| cry | 0.5 |
| lonely | 1.0 |
| miserable | 1.0 |
| heartbroken | 1.0 |
| 😢 | 1.5 |
| 😭 | 1.5 |
| 💔 | 1.5 |

### A.3 angry（19）

| 词条 | 权重 |
| --- | --- |
| 生气 | 1.0 |
| 愤怒 | 1.0 |
| 恼火 | 1.0 |
| 讨厌 | 0.5 |
| 烦躁 | 0.5 |
| 火大 | 1.0 |
| 气死 | 1.0 |
| 可恶 | 1.0 |
| 受不了 | 0.5 |
| 恨 | 1.0 |
| 气人 | 1.0 |
| angry | 1.0 |
| mad | 0.5 |
| furious | 1.0 |
| annoyed | 0.5 |
| hate | 1.0 |
| 😠 | 1.5 |
| 😡 | 1.5 |
| 🤬 | 1.5 |

### A.4 surprised（22）

| 词条 | 权重 |
| --- | --- |
| 惊讶 | 1.0 |
| 吃惊 | 1.0 |
| 震惊 | 1.0 |
| 意外 | 0.5 |
| 没想到 | 1.0 |
| 竟然 | 0.5 |
| 居然 | 0.5 |
| 哇 | 1.0 |
| 天哪 | 1.0 |
| 不敢相信 | 1.0 |
| 惊喜 | 0.5 |
| surprised | 1.0 |
| shocked | 1.0 |
| wow | 1.0 |
| amazing | 0.5 |
| unexpected | 0.5 |
| whoa | 0.5 |
| omg | 1.0 |
| 😲 | 1.5 |
| 😮 | 1.5 |
| 😱 | 1.5 |
| 🤯 | 1.5 |

### A.5 calm（19）

| 词条 | 权重 |
| --- | --- |
| 平静 | 1.0 |
| 冷静 | 1.0 |
| 放松 | 1.0 |
| 安心 | 1.0 |
| 安稳 | 0.5 |
| 淡定 | 1.0 |
| 舒适 | 0.5 |
| 舒服 | 0.5 |
| 宁静 | 1.0 |
| 平和 | 1.0 |
| 还好 | 0.5 |
| 没事 | 0.5 |
| calm | 1.0 |
| relaxed | 1.0 |
| peaceful | 1.0 |
| chill | 0.5 |
| tranquil | 0.5 |
| serene | 1.0 |
| 😌 | 1.5 |

### A.6 否定短语（[草案] D02，权重 1.0 → sad）

`不开心`、`不高兴`、`没意思`、`not happy`、`don't like`；
建议扩展（P1）：`不快乐`、`不满意`、`不愉快`。

---

## 附录 B：依据来源

| 文件 | 用途 |
| --- | --- |
| `AGENTS.md` | 架构铁律、隐私、测试与回归规范 |
| `docs/ARCHITECTURE.md` §3.4/§7 | 五类、规则法、接口字段草案 |
| `docs/DEVELOPMENT_PLAN.md` Stage 4 | 交付物、权重、强度、否定短语、验收标准 |
| `docs/contracts/data-models.md` §3.2/§4.2 | Storage 字段与 `EmotionResult` 映射 |
| `docs/contracts/stage3-contract-v1.md` §3.5 | `update_message_emotion()` 消费关系 |
| `docs/contracts/threading-model.md` §2.4 | emotion 纯函数/无线程约束 |
| `docs/contracts/stage3-storage-timestamp-v1.3.md` | Stage 4 数据字段不变的边界声明 |
| `tests/test_architecture.py` | 层依赖、Qt、第三方白名单守护 |
