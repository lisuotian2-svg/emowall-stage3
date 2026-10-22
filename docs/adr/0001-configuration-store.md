# ADR-0001：配置存储设计

- 状态：已接受（2026-10-22，Stage 1）
- 决策者：项目负责人 + 实现者
- 影响范围：`emowall/config`，以及后续所有读取配置的层（组合根、GUI 设置页）

## 背景

V0.1 需要把 Ollama 地址、模型名、推理参数、上下文预算持久化，并能安全应对用户手改文件、
磁盘异常与版本升级。配置必须能被未来的 EmoWall 主项目复用，且不能把 GUI 或网络依赖带进核心。

## 决策

1. **单一 JSON 文件**
   - 路径：`%APPDATA%\EmoWall\config.json`；`EMOWALL_HOME` 可整体重定向（测试、便携、多实例）。
   - 选 JSON 而非 TOML/YAML：标准库直接支持、人类可读、无额外依赖；配置规模小，不需要 YAML 的表达力。
   - 不引入 `pyproject.toml` 依赖表：依赖声明仍以 `requirements.txt` 为唯一来源，避免双来源漂移。

2. **frozen dataclass + 构造即校验**
   - `OllamaSettings / ChatSettings / AppSettings` 在 `__post_init__` 中归一化并校验，
     非法值抛 `ConfigValidationError`，从源头保证「能构造出来的对象一定是合法的」。
   - 字段校验与默认值集中在 `settings.py`，`store` 不重复定义默认值。

3. **加载容错优先于严格失败**
   - 文件缺失：写回默认配置并返回默认值（首次运行体验）。
   - JSON 损坏 / 根不是对象：先备份为 `config.corrupt-<UTC 时间戳>.json` 再重置；
     若备份失败，**不覆盖原文件**，只用默认值继续运行。
   - 单字段非法：该字段回退默认值并记录 warning，**不重写用户文件**，让用户有机会自行修复。
   - 目录不可写：加载仍成功（默认值 + warning）；显式 `save()` 失败时抛 `ConfigIOError`。

4. **未知字段保留**
   - 运行时只读取已知字段；保存时用"深合并"把已知字段写回，未知字段（顶层与子节）原样保留。
   - 目的：旧版本打开新版本写的配置时不会丢数据；也避免用户手写的实验字段被静默删除。

5. **版本策略**
   - 顶层 `version` 为整数，当前 `1`。
   - 较新版本：只读已知字段 + warning；较旧版本：缺失字段用默认值 + warning；两者都不阻塞启动。
   - 保存时统一写回当前支持的 `version`，未知字段仍然保留（即"版本号回到当前值，数据不丢"）。
   - 迁移函数表暂为空；未来升级时按 `version` 逐级迁移，不在这里提前实现。

6. **原子写入**
   - 同目录 `tempfile.mkstemp` → 写入 → `flush` + `os.fsync` → `os.replace`。
   - 读取使用 `utf-8-sig`（兼容 Windows 记事本写入的 BOM）；写入为无 BOM 的 UTF-8 + 结尾换行。
   - 不先写目标文件，避免断电/崩溃留下半截 JSON；临时文件在异常路径上清理。

7. **依赖约束**
   - 仅标准库（`json / os / tempfile / pathlib / dataclasses / urllib.parse / logging`）。
   - 不依赖 Qt、httpx，不执行任何网络或推理操作。

## 备选方案

| 方案 | 未采用原因 |
| --- | --- |
| `QSettings` | 把配置绑进 Qt，违反「配置层不依赖 GUI」，也无法被 EmoWall 主项目复用 |
| TOML / YAML | TOML 需 `tomllib`（只读，写入要额外库）；YAML 需第三方依赖，收益不足 |
| Pydantic / attrs | 为 3 个小 dataclass 引入大型依赖，与「不提前引入复杂框架」冲突 |
| 环境变量唯一来源 | 不适合多参数、可编辑、可版本化；仅作为 `EMOWALL_HOME` 的路径覆盖 |
| 数据库存配置 | 启动早于数据库初始化，且配置应可被人直接编辑与备份 |

## 后果

**正面**

- 配置层零 Qt/网络依赖，可原样迁移到 EmoWall 主项目。
- 用户手改配置导致的问题有明确降级路径，不会出现"启动即崩"。
- 未知字段保留为未来扩展（多模型后端、语音、记忆等新 section）留出空间。

**负面 / 需要记住的**

- 单字段非法只回退不纠正，用户文件会持续告警，直到手动修复（这是有意的非破坏性取舍）。
- 未知字段保留意味着配置文件可能长期携带废弃字段，需要未来的清理工具（V0.1 不做）。
- 配置写入不是并发安全的：同一进程内由调用方保证单线程使用，多进程同时写不在 V0.1 范围。

## 后续扩展（不提前实现）

- 多后端：新增 `backends` section，保留 `ollama` 作为默认；通过 `version` 迁移。
- 迁移函数表：`MIGRATIONS: dict[int, Callable[[dict], dict]]`，按版本逐级应用。
- 设置页：GUI 只依赖 `ConfigStore.load()/save()` 与 dataclass，不直接读写 JSON。
