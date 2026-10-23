# ADR-0002：AI 核心边界、取消机制与上下文裁剪

- 状态：已接受
- 日期：2026-10-23
- 决策者：EmoWall AI 项目
- 相关：ADR-0001、`docs/ARCHITECTURE.md` §3.1 / §5 / §6、`docs/DEVELOPMENT_PLAN.md` Stage 2

---

## 背景

Stage 2 需要把「连接 Ollama、流式输出、多轮上下文、随时取消」做成一个**与界面、配置、存储无关**的核心，
以便未来直接迁移到 EmoWall 主项目，并支持长期扩展（多模型提供者、语音、多模态、长期记忆、Agent 工具等）。

同时必须避免为未来功能过度设计：当前阶段只实现单提供者（Ollama）、单路生成、同步流式核心。

---

## 决策

### 1. 通用数据模型与传输实现分离

- `emowall/ai/models.py` 定义通用的 `ChatMessage`（system / user / assistant）、
  `ChatChunk`（增量文本 + done + 统计）、`GenerationStats`（毫秒统一）。
- Ollama 协议细节（`/api/chat`、NDJSON、`message.content`、纳秒统计）只存在于
  `emowall/ai/client.py`。
- GUI / 存储 / 未来其他提供者只消费通用类型，不解析 Ollama 原始 JSON，也不接触 Qt 类型。

**后果**：未来新增模型提供者时，实现同样的 `stream_chat` 接口即可；消息与事件类型不需要迁移。

### 2. 明确错误层级，不静默吞异常

```
AIError
├── OllamaUnavailableError
│   ├── OllamaConnectionError
│   ├── OllamaTimeoutError
│   └── OllamaHTTPError（携带 status_code）
├── ModelNotFoundError
├── ProtocolError
│   └── StreamInterruptedError
└── CancelledError
```

- 连接失败、超时、HTTP 非 2xx、模型缺失、协议错误、流中断、用户取消分别可识别。
- 单行 NDJSON 解析失败只记 warning 并跳过；整段无有效数据才报 `ProtocolError`。
- 收到 `done=true` 才算正常完成；EOF 早于 done 报 `StreamInterruptedError`。

**理由**：GUI 需要按错误类型给出不同提示（启动 Ollama / 安装模型 / 重试 / 取消），
单一 `Exception` 无法支撑；同时保留 `OllamaUnavailableError` 作为服务不可用的统一捕获点。

### 3. 同步生成器 + CancelToken，不引入 asyncio / 后台任务

- `stream_chat` 是普通生成器，阻塞在调用线程，便于 Qt `QThread` 工作线程使用与离线测试。
- `CancelToken` 用锁保护「活动资源登记表」；连接/等待响应头阶段登记底层 `httpx.Client`，
  收到响应后登记 `httpx.Response`。`cancel()` 置位事件并关闭已登记资源。
- 已取消后再登记的资源会立即关闭，覆盖「取消发生在登记前」的竞态。
- 生成结束 / 异常时反登记并 `with` 关闭响应；取消关闭 owned client 后，下一次请求自动重建。
- 不创建线程、asyncio task 或线程池；读循环把 `httpx.ReadError / StreamClosed` + 已取消映射为 `CancelledError`。

**后果**：取消在「等待响应头 / 冷启动」与「读块中」都能在 500 ms 内生效（本机真实冷启动探针实测 0.5 s），
连接可回收；不需要在 Qt 线程中叠加事件循环。
代价是单客户端同一时刻只适合一路生成（V0.1 本来就是单会话单生成）。

### 4. 上下文裁剪：轮次感知 + 双阈值 + 硬底线

- `system` 提示永远置首、永不裁剪。
- 非 system 消息按「用户消息开启一个轮次」分组，从最新轮次向最旧轮次累加，保持完整轮次。
- 同时受 `max_context_messages`（条数，含 system）与 `max_context_chars`（字符预算，含 system）限制。
- `system` 与最新轮次（含最后一条用户消息）是硬底线，即使单条超预算也保留；其余从最旧轮次开始丢。
- 字符数只是 token 的保守近似，不做 tokenizer；裁剪只影响发送给模型的上下文，不修改历史、不影响持久化。

**理由**：完整轮次比「逐条截断」更符合对话语义，能避免孤立的 assistant 回复；
确定性算法便于单测与复现。V0.1 的 `num_ctx=8192` 与默认 6000 字符预算为系统提示和生成留出空间。

### 5. 配置注入，不反向依赖

- `emowall.ai` 不 import `emowall.config`；`emowall.config` 也不 import AI。
- 组合根（未来的 `emowall/app.py`）读取 `ConfigStore.load().ollama / .chat`，
  把 base_url / 超时 / 模型 / 上下文参数映射为客户端与引擎的构造参数。
- 配置变化时构造新的 `OllamaClient` 实例，不共享旧连接；本阶段用测试验证这一映射。
- 本地默认 `trust_env=False`，不自动继承系统代理；地址仍可配置，但不自动发现外部主机。

**理由**：保持四层扁平、互不依赖的架构铁律；配置与 AI 可以独立测试、独立迁移。

### 6. 测试策略

- 离线测试用 `httpx.MockTransport` / 自定义 `httpx.SyncByteStream`，覆盖分块、UTF-8 跨块、半行断流、
  HTTP 404/500、连接拒绝、超时、取消与资源释放。
- `tests/conftest.py` 默认拦截真实 socket 连接；`integration` 与 `local_network` 标记显式放行。
- 真实 Ollama 用例统一标记 `@pytest.mark.integration`，默认不运行；验收重点是协议、事件顺序、
  状态与资源释放，不把模型输出文字写死。
- 架构守护测试继续保证 `ai` 只依赖标准库 + httpx、不 import Qt / 其他 emowall 层；
  仅允许 `tests/test_ai_client.py` 直接 import httpx 使用 MockTransport。

---

## 未采用方案

| 方案 | 不采用原因 |
| --- | --- |
| asyncio + async generator | 与 Qt 事件循环叠加复杂；V0.1 单路生成不需要 |
| 后台线程池 / 任务队列 | 取消与资源释放更难验证；当前由 GUI 工作线程调用同步 API 已足够 |
| 引入 tokenizer 精确计数 | 增加依赖与模型适配成本；字符预算已能保守控制 |
| 通用 `Provider` 插件框架 | 当前只有一个提供者，过早抽象会固化错误接口 |
| 在 AI 层直接读配置 | 违反依赖方向，测试与迁移成本高 |

---

## 影响

- 正面：AI 核心可零改动迁移到 EmoWall 主项目；错误与取消语义清晰；离线测试可重复。
- 限制：未实现 tokenizer、自动重试、多提供者路由、思考内容（thinking）展示；
  这些留到后续阶段，按实际需求扩展 `ChatChunk` / 引擎接口。
