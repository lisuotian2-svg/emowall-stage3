# 环境审计报告 — EmoWall AI V0.1

- 审计时间：2026-10-22 22:37 ~ 22:50（Asia/Shanghai）
- 审计对象：`<项目目录>`（本机为 OneDrive 同步目录，实际路径用 `Get-Location` 查看）
- 审计方式：只读检查 + 一次真实 Ollama API 探测；**未修改用户环境变量、未升级 Ollama、未改动系统配置**。
  项目内创建了 `.venv` 并装入 pip / pytest（原因见「问题 7」）。

> 本报告记录的是本机 2026-10-22 的实测值；仓库文档统一使用占位符，具体路径以 `scripts/check_env.py` 输出为准。

---

## 1. 结论摘要

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 工作目录 | ✅ 可用 | 审计开始时为空目录，无既有文件可覆盖 |
| Python 3.12 | ✅ 满足 | 3.12.15（uv 托管），uv 0.13.3；项目 `.venv` 内 pip 26.2.2 |
| Git | ✅ 满足 | 2.56.0，已配置用户名/邮箱；目录原本不是仓库，已 `git init` |
| Ollama | ⚠️ 已安装未运行 | 0.40.6，二进制与 API 均正常，服务需启动 |
| 本地模型 | ✅ 有可用模型 | `qwen3:8b`（Q4_K_M，8.2B，约 4.9 GB），存于 `D:\ollama\models` |
| Python 依赖 | ⚠️ 部分安装 | 项目 `.venv` 内已有 pip 26.2.2 + pytest 9.1.1；`PySide6 / httpx / pyinstaller` 未装（Stage 1 安装） |
| 环境与依赖管理 | ✅ 已统一 | Python 3.12（uv 托管）+ uv 0.13.3；`.venv` 复用未重建；依赖唯一来源 `requirements.txt`；`uv pip install --dry-run -r requirements.txt` 可解析全部依赖 |
| 网络（PyPI） | ✅ 可达但不稳定 | 查询版本成功，出现数次 `SSL: UNEXPECTED_EOF` 重试 |
| 硬件 | ✅ 充裕 | RTX 5060 Laptop 8 GB（模型全部驻留显存）、20 核、C: 167 GB 可用 |

**总体判断：环境具备开发条件，唯一必须先解决的是「让 Ollama 服务在开发时保持运行」。**

---

## 2. 详细检查结果

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 操作系统 | Windows 11（NT 10.0.26200） | `[Environment]::OSVersion` |
| CPU | 20 逻辑核 | `NUMBER_OF_PROCESSORS=20` |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU，8151 MiB，驱动 592.15 | `nvidia-smi` |
| 磁盘 | C: 167.3 GB 可用 / 400 GB；D: 395.1 GB 可用 / 551.6 GB | `System.IO.DriveInfo` |
| Python | 3.12.15 | `%LOCALAPPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe` |
| `py` 启动器 | 默认 **3.15**，另有 Store 3.13 | `py -0` ⚠️ 与项目要求的 3.12 不一致 |
| pip / uv | 项目 `.venv`：pip 26.2.2；uv 0.13.3 | `.venv\Scripts\python.exe -m pip --version`、`uv --version` |
| Git | 2.56.0.windows.1，已配置提交身份 | `git --version`、`git config --global` |
| Git 仓库 | 审计时**非**仓库；随后初始化 | `git status` → `fatal: not a git repository`（审计时） |
| Ollama | 0.40.6（提示可升级到 0.40.8，安装包已下载未安装） | `ollama --version` |
| Ollama 服务 | **未运行**（11434 不可达） | `Test-NetConnection` → False |
| 本地模型 | `qwen3:8b`，4.87 GiB，Q4_K_M，支持 `completion/tools/thinking` | `GET /api/tags` |
| 模型存储 | `D:\ollama\models`（用户环境变量 `OLLAMA_MODELS`） | `[Environment]::GetEnvironmentVariable` |
| 开机启动 | 启动目录存在 `Ollama.lnk` | Startup 文件夹列表 |
| Python 依赖 | 全局解释器无 PySide6/httpx/pytest；项目 `.venv` 内有 pip + pytest | `pip list`；`.venv\Scripts\python.exe -m pip list` |
| 项目虚拟环境 | ✅ 已建（`.venv`，Python 3.12.15） | `--without-pip` 创建后经 `uv` 安装 pip 26.2.2 / pytest 9.1.1（见问题 7） |
| PyPI 版本 | PySide6 6.12.0 / httpx 0.28.1 / pytest 9.1.1 / PyInstaller 6.22.3 | `pip index versions` |

**环境管理约定（Stage 0 修复后统一）**

- 解释器：Python 3.12（uv 托管 CPython）+ uv 0.13+；虚拟环境固定为项目根目录 `.venv`。
- 依赖声明：**唯一来源 `requirements.txt`**；故意不引入 `pyproject.toml` 依赖表，避免两套来源漂移。
- 安装方式：`uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt`；
  受限环境需把 `TMP/TEMP/UV_CACHE_DIR` 指向工作区（见「问题 7」）。
- 备用路径：普通桌面终端可用 `pip install -r requirements.txt`；受限环境 `ensurepip` 可能失败，不作为首选。
- 现有 `.venv` 不重建：`python -m venv --without-pip` 创建后由 uv 装入 pip/pytest（见「问题 7」）。

---

## 3. 实测性能（决定超时与交互设计）

用 `qwen3:8b` 直接调用 `POST /api/chat`（`stream=true`）：

| 场景 | 耗时 | 细节 |
| --- | --- | --- |
| 冷启动请求（模型未加载） | **81.4 s** 总耗时 | 其中 `load_duration` **40.6 s**，`prompt_eval` 20 tokens 用 29.7 s，生成 9 tokens 用 11.0 s |
| 热请求（模型已在显存） | **0.33 s** | `load_duration` 11.7 ms，生成 8 tokens 用 0.17 s |
| 流式形态 | 9 行 NDJSON | 8 个内容块 + 1 个 `done=true` 末块（含 `eval_count`、`total_duration` 等统计） |
| 显存占用 | 5.24 GiB（`size_vram`），运行上下文 8192 | `/api/ps` |

**设计含义（已写入架构与计划）**

- 不能设置「首包短超时」，否则冷启动必然误报失败 → 用「模型加载中」状态。
- 首问 40 s 内必须可取消，取消要能打断连接（而不是等问题结束）。
- 多轮上下文按 8192 上限裁剪，默认字符预算 6000。

---

## 4. 问题清单与修复方案（按优先级）

### 问题 1：Ollama 服务未运行（P0，阻塞联调）

**现象**：`11434` 端口不可达；`ollama list` 报 `could not connect to a running Ollama instance`。

**修复（任选其一）**

```powershell
# 方式 A：前台启动（开发时推荐，能看到日志）
ollama serve

# 方式 B：从开始菜单启动 Ollama 应用（已在启动目录，登录后自动运行）
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\Ollama.exe"

# 验证
ollama list
curl.exe http://127.0.0.1:11434/api/version
```

> 提示：如果 11434 已被占用，说明已有实例在跑，无需重复启动。

### 问题 2：受限沙箱下 Ollama 写日志失败（仅影响受限执行环境）

**现象**：在受限文件沙箱内执行 `ollama serve` 时，日志文件 `%LOCALAPPDATA%\Ollama\app.log` 无法创建，
随后 `Error: timed out waiting for server to start`；旧日志轮转也报 `Access is denied`。

**原因**：该执行环境只允许写工作区与临时目录，Ollama 需要写 `%LOCALAPPDATA%\Ollama`。

**修复**

- 正常桌面环境：**无需处理**，直接在开始菜单启动 Ollama 即可。
- 受限环境（脚本/CI）：把 `LOCALAPPDATA` 重定向到可写临时目录再启动，审计中已用此方式验证服务可以正常工作：

```powershell
$tmp = Join-Path $env:TEMP "ollama_runtime"
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:LOCALAPPDATA = $tmp          # 仅影响本次会话
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
```

> 注意：重定向会让「Ollama 托盘应用」的日志与设置写到临时目录；开发联调可用，日常使用请用正常启动方式。

**审计期间的处理**：为验证 API 与模型，临时以重定向方式启动了一个 `ollama serve` 进程，探测完成后**已停止**，
未改动任何用户级配置。

### 问题 3：`py` 启动器默认指向 Python 3.15（P1，易踩坑）

**现象**：`py -V` → 3.15.0；项目要求 3.12。裸用 `py` 或某些 IDE 默认解释器会装错环境。

**修复**：全部命令显式使用 `.venv\Scripts\python.exe`；创建虚拟环境时钉住版本：

```powershell
python -m venv .venv     # 当前 python 即 3.12.15
.\.venv\Scripts\python.exe -V   # 应输出 Python 3.12.15
```

### 问题 4：依赖未安装，且 PyPI 连接偶发抖动（P1，Stage 1 前处理）

**现象**：`PySide6 / httpx / pyinstaller` 未安装（`pytest` 已装入项目 `.venv`）；查询 PyPI 时出现 `SSL: UNEXPECTED_EOF_WHILE_READING` 重试后成功。

**修复**：安装时加超时与重试，必要时使用国内镜像（二选一，不混用）：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --timeout 120 --retries 5

# 若持续超时，可临时改用镜像：
# .\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

PySide6 下载体积较大（百 MB 级），首次安装请预留时间；C: 剩余 167 GB 空间充足。

> 受限执行环境中 `ensurepip` 会因临时目录 chmod 被拒而失败；用 `uv` 安装的方式见「问题 7」。

### 问题 5：项目位于 OneDrive 同步目录（P2，潜在干扰）

**风险**：`.venv`（数千文件）、`.git`、数据库文件会被 OneDrive 同步，可能造成文件锁、同步冲突、磁盘占用翻倍。

**建议**（不擅自执行）：

1. 在 OneDrive 设置中暂停对本目录的同步，或
2. 将项目迁移到 `C:\dev\emowall-v0.1` 后再开工（需要你确认后我再操作），或
3. 保持现状，但忽略同步冲突提示（`.gitignore` 已排除 `.venv`、`*.db`、`build/`、`dist/`）。

### 问题 6：Ollama 可升级到 0.40.8（P3，非阻塞）

安装包已下载至 `%LOCALAPPDATA%\Ollama\updates_v2\...\OllamaSetup.exe`，升级会重启 Ollama 服务。
**建议保持 0.40.6**：V0.1 依赖的 `/api/chat` 流式协议稳定，升级收益低；如需升级请单独安排并复跑集成测试。

---

### 问题 7：受限环境无法创建临时目录（P1，影响 pip / 测试工具）

**现象**：

- `python -m venv .venv`（带 pip）在 `ensurepip` 阶段失败：`PermissionError: [WinError 5] 拒绝访问`。
- `uv` 报 `error: Could not acquire lock`，因为默认缓存目录在用户目录、不在可写范围。
- `pytest` 报 `PytestCacheWarning: could not create cache path`（不影响用例结果）。

**原因**：当前受限执行环境**拒绝 `chmod` / 修改 ACL**。Python 的 `tempfile.mkdtemp()` 创建临时目录后会执行
`chmod(0700)`；ensurepip、pip 构建、pytest 缓存都依赖它，于是失败。**普通桌面终端没有这个限制。**

**修复（仅在受限环境需要）**

```powershell
# 1) 临时目录与工具缓存都指向工作区内可写位置
New-Item -ItemType Directory -Force .tmp, .uv-cache, .pip-cache | Out-Null
$env:TMP = "$PWD\.tmp"; $env:TEMP = "$env:TMP"
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:PIP_CACHE_DIR = "$PWD\.pip-cache"

# 2) 用 uv 安装（绕过 ensurepip / pip 的临时目录 chmod）
uv pip install --python ".\.venv\Scripts\python.exe" pip pytest --link-mode copy
```

- 上述目录已加入 `.gitignore`（`.tmp/`、`.uv-cache/`、`.pip-cache/`）。
- 若 `python -m venv .venv` 在本机普通终端可用，则**不需要**本节，直接在终端里用 pip 即可。
- 受限环境下跑测试可加 `-p no:cacheprovider` 消除缓存告警。
- **现有 `.venv` 的实际来源**：`python -m venv .venv --without-pip`（沙箱下唯一可行方式）→ 由 uv 装入 pip 26.2.2 与 pytest 9.1.1；**未重建、未覆盖**。新机器标准流程为 `uv venv --python 3.12 .venv`。

---

## 5. 审计期间做过 / 没做过的事

**做过（均在项目目录或临时目录内）**

- 创建项目骨架文件（`README.md`、`AGENTS.md`、`docs/`、`scripts/`、`tests/`、`emowall/` 包目录）
- 初始化 Git 仓库并提交
- 临时启动 `ollama serve`（`LOCALAPPDATA` 指向 `%TEMP%`）用于探测 API 与模型，**已停止**
- 在项目内创建 `.venv`（沙箱下用 `--without-pip` 创建），经 `uv` 安装 pip 26.2.2 与 pytest 9.1.1，用于跑**架构**守护测试

**没做过（避免擅自改动环境）**

- 未升级 / 重装 Ollama，未改动 `OLLAMA_MODELS`、`OLLAMA_HOST` 等用户环境变量
- 未安装 PySide6 / httpx / pyinstaller（留到 Stage 1，先确认）
- 未改系统 PATH、未改注册表、未动开始菜单启动项
- 未迁移项目目录、未暂停 OneDrive
- 未删除或覆盖任何既有文件（审计开始时目录为空）

---

## 6. 建议的启动顺序（Stage 1 之前）

1. 启动 Ollama（问题 1），`ollama list` 能看到 `qwen3:8b`；
2. 创建 `.venv` 并 `pip install -r requirements.txt`（问题 4）；
3. 运行 `.\.venv\Scripts\python.exe scripts\check_env.py`，各项为 PASS/WARN 而非 FAIL；
4. 运行 `.\.venv\Scripts\python.exe -m pytest`，架构守护测试全绿；
5. 确认进入 Stage 1（配置系统）。
