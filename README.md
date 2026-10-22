# EmoWall AI V0.1

> 面向 **Windows 11** 的本地 AI 聊天应用，作为未来 **EmoWall AI 情绪壁纸** 的可复用「AI 对话核心」。
> 本项目是练习版本：重点不在功能堆叠，而在**分层解耦**与**可迁移性**——做对的骨架，未来直接搬进 EmoWall 主项目。

---

## 当前状态

**Stage 0（环境审计 + 项目骨架 + 开发规范）已完成。** 业务代码尚未开始，按约定需经项目负责人确认后才进入 Stage 1。

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Stage 0 | 环境审计、目录结构、规范文档、Git 初始化 | ✅ 完成 |
| Stage 1 | 配置系统（Ollama 地址/模型、app 数据目录） | ⬜ 待确认 |
| Stage 2 | AI 核心（Ollama 传输、流式输出、多轮上下文、取消） | ⬜ |
| Stage 3 | SQLite 存储（会话 / 消息） | ⬜ |
| Stage 4 | 情绪系统（5 种基础表情） | ⬜ |
| Stage 5 | PySide6 GUI 集成（聊天界面、会话管理、设置） | ⬜ |
| Stage 6 | PyInstaller 打包为 Windows EXE + V0.1 验收 | ⬜ |

阶段划分、每阶段交付物与**验收标准**见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。

---

## 技术栈

| 组件 | 选型 | 用途 |
| --- | --- | --- |
| 语言 | Python 3.12 | 运行时 |
| GUI | PySide6（Qt 6） | 仅出现在 `emowall/gui` 与组合根 `emowall/app.py` |
| 模型服务 | Ollama（本地 HTTP API） | 本地推理 |
| HTTP | httpx | 同步流式请求 |
| 存储 | SQLite（标准库 `sqlite3`） | 聊天记录 |
| 测试 | pytest | 单元 / 架构守护 / 集成 |
| 打包 | PyInstaller | Windows EXE |

---

## 目录结构（目标形态）

```
emowall-v0.1-ai聊天机器人/
├─ emowall/                  # 应用包（6 个包目录，均含 __init__.py）
│  ├─ ai/                    # AI 核心：Ollama 客户端、流式生成、取消、上下文窗口
│  ├─ config/                # 配置系统：JSON 配置、默认值、校验、原子写入
│  ├─ storage/               # SQLite 存储：会话 / 消息仓库（无 Qt、无线程）
│  ├─ emotion/               # 情绪系统：5 种基础表情的纯函数映射
│  ├─ gui/                   # PySide6 界面 + 工作线程编排（Stage 5 含 db_service.py）
│  ├─ app.py                 # 组合根：装配各层，启动应用（Stage 5）
│  └─ __main__.py            # python -m emowall 入口（Stage 5）
├─ tests/                    # pytest 用例：架构守护 / 文档一致性 / 自检脚本
├─ scripts/check_env.py      # 环境自检（仅标准库，可在装依赖前运行）
├─ docs/                     # ARCHITECTURE、DEVELOPMENT_PLAN、ENVIRONMENT_AUDIT
├─ requirements.txt          # 依赖声明（唯一来源）
├─ pytest.ini                # 测试配置（默认排除 integration）
├─ .gitignore / .gitattributes
├─ AGENTS.md                 # 长期开发规则（给人和 AI 协作者）
└─ README.md
```

> 说明：`ai / config / storage / emotion` 四层**互不 import**，且都不允许 import Qt；
> GUI 只允许向下依赖，依赖方向由 `tests/test_architecture.py` 自动守护。

---

## 环境要求

| 项 | 本机实测 |
| --- | --- |
| 操作系统 | Windows 11（10.0.26200，20 核 / RTX 5060 Laptop 8 GB） |
| 环境与依赖 | Python 3.12（uv 托管）+ uv 0.13+；依赖声明见 `requirements.txt` |
| Python | 3.12.15（`%LOCALAPPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe`） |
| Git | 2.56.0（提交前需配置 `user.name` / `user.email`） |
| Ollama | 0.40.6，API `http://127.0.0.1:11434` |
| 模型 | `qwen3:8b`（Q4_K_M，8.2B，约 4.9 GB） |
| 模型目录 | `D:\ollama\models`（由用户环境变量 `OLLAMA_MODELS` 指定） |

> ⚠️ 本机 `py` 启动器默认解析到 Python **3.15**，请始终使用虚拟环境里的解释器（`.venv\Scripts\python.exe`）；不要用裸 `python` 或 `py` 等模糊命令。

### 环境与依赖管理

- 环境：Python 3.12（uv 托管）+ uv 0.13+，虚拟环境固定为项目根目录的 `.venv`（不入库）。
- 依赖：**唯一来源是 `requirements.txt`**，故意不引入 `pyproject.toml` 依赖表，避免两套来源冲突。
- 安装：`uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt`。
- 备用：普通桌面终端也可用 `python -m venv .venv` + `pip install -r requirements.txt`；受限环境里 `ensurepip` 可能失败（见环境审计「问题 7」）。

---

## 快速开始

```powershell
# 1) 进入项目目录
cd <项目目录>   # 例：C:\Users\<你>\OneDrive\文档\emowall-v0.1-ai聊天机器人

# 2) 创建虚拟环境并安装依赖（推荐 uv；已存在的 .venv 会复用，不会重建）
uv venv --python 3.12 .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt

# 备用（pip 可用的普通桌面终端）：
# python -m venv .venv
# .\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3) 启动 Ollama（若未运行）
ollama serve          # 或从开始菜单启动 Ollama

# 4) 环境自检（仅用标准库，可在装依赖前运行）
.\.venv\Scripts\python.exe scripts\check_env.py

# 5) 跑测试
.\.venv\Scripts\python.exe -m pytest

# 6) 启动应用（Stage 5 完成后可用）
.\.venv\Scripts\python.exe -m emowall
```

---

## 环境自检脚本

`scripts/check_env.py` 会逐项检查并给出可执行的修复建议：

- Python 版本是否 ≥ 3.12
- `PySide6 / httpx / pytest` 是否可导入
- `git`、`ollama` 命令是否在 PATH
- Ollama 服务是否可达（`/api/version`）及本地模型列表（`/api/tags`）
- `OLLAMA_MODELS` 模型目录是否存在
- 应用数据目录位置（`%APPDATA%\EmoWall`，或 `EMOWALL_HOME` 覆盖）

输出逐项 `PASS / WARN / FAIL`；退出码 0 = 无 FAIL，1 = 有 FAIL（`--strict` 时 WARN 也算失败）。

```powershell
.\.venv\Scripts\python.exe scripts\check_env.py --help
```

---

## 已知环境问题

| 问题 | 影响 | 处理方式 |
| --- | --- | --- |
| Ollama 服务默认未在后台运行 | 首次请求报连接失败 | 启动 Ollama（开始菜单 / `ollama serve`；开机启动项已存在 `Ollama.lnk`） |
| 受限沙箱下 Ollama 写日志失败 | 在受限执行环境中 `ollama serve` 会因 `app.log` 无写权限而启动超时 | 正常桌面环境无此问题；详见 [环境审计](docs/ENVIRONMENT_AUDIT.md) 的「问题 2」 |
| 受限环境无法创建临时目录 | `pip` / `ensurepip` 因 chmod 被拒而失败 | 用 `uv` 并把缓存与临时目录指向工作区（详见环境审计「问题 7」） |
| 模型冷启动慢 | `qwen3:8b` 首次加载约 40 s、首包延迟高 | 界面显示「模型加载中」状态并允许取消；不设短超时 |
| 项目位于 OneDrive 目录 | 大量小文件（`.venv/.git`）会触发同步 | 建议在本目录暂停 OneDrive 同步，或后续迁移到非同步目录 |

---

## 文档

- [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) — 分阶段开发计划与验收标准
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 分层架构、接口契约、线程与取消模型
- [docs/ENVIRONMENT_AUDIT.md](docs/ENVIRONMENT_AUDIT.md) — 本机环境审计报告与修复建议
- [AGENTS.md](AGENTS.md) — 长期开发规则（架构铁律、代码 / 测试 / Git 规范）

---

## V0.1 功能验收清单（最终目标）

- [ ] 连接本地 Ollama 模型
- [ ] 流式 AI 对话
- [ ] 多轮上下文
- [ ] SQLite 保存聊天记录
- [ ] 新建会话 / 恢复历史会话
- [ ] 简单聊天 GUI
- [ ] 五种基础 AI 表情
- [ ] 可配置 Ollama 地址与模型
- [ ] 取消正在进行的生成
- [ ] 可打包为 Windows EXE
