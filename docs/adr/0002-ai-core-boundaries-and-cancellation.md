# ADR-0002：AI 核心边界、取消机制与上下文裁剪

- 状态：已接受
- 日期：2026-10-23
- 修订：2026-10-23，Stage 2 G1/G2 整改；G3 真实取消时延待重新验收
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
- `CancelToken` 用锁保护活动生成、资源登记与取消清理状态。自有客户端在发送请求前登记
  `httpx.Client.close`；两种所有权模式在收到响应后都登记 `httpx.Response.close`。
- `cancel()` 置位事件并关闭已登记资源，但不清空登记表；资源由所属生成器退出时反登记。
  已取消后再登记的资源会立即关闭，并保留登记直至所属生成器清理。
- `reset()` 在生成器、异常分类、资源登记或取消清理尚未结束时抛 `RuntimeError`。
  `cancel()` 返回不代表旧生成器已退出；必须等旧生成结束后才能复用令牌或开始下一轮。
- 生成器必须消费完或由消费它的线程显式 `close()`，使 `with` 块及时关闭响应、解除登记。
  提前停止消费 `ChatEngine.stream_reply()` 时也适用；不能依赖垃圾回收完成连接释放。
- 不创建线程、asyncio task 或线程池；已取消时的读取错误、安静 EOF、错误正文读取失败
  都优先归类为 `CancelledError`，不把用户取消提示为网络中断。

#### HTTP 客户端所有权与取消边界

| 模式 | 创建与关闭责任 | 取消行为与使用范围 |
| --- | --- | --- |
| 不传 `client`，使用默认传输 | `OllamaClient` 创建并关闭底层 `httpx.Client`；显式 `close()` 后不得继续使用 | 取消关闭自有客户端及已收到的响应；取消后下一请求自动重建底层客户端。Stage 5 生产路径必须使用此模式，每个客户端独占一路生成 |
| 不传 `client`，传入 `transport` | 底层 `httpx.Client` 仍为自有，关闭会传递给该传输 | 供测试或明确控制传输生命周期的调用方使用；取消能力及关闭后能否复用传输取决于传输实现，不能用假传输的行为证明真实网络能力 |
| 传入外部 `client` | 外部调用方创建并负责最终关闭；`OllamaClient.close()` 不关闭它 | 供测试或明确的外部生命周期管理使用，不用于 Stage 5 生产工作线程。取消仅关闭已收到的响应；响应头到达前没有可关闭的响应，因此不保证及时中断 |

注入模式在等待响应头期间仍保留取消标志并阻止 `reset()`；只有外部请求返回、超时或被外部
生命周期管理者中断后，生成器才能完成取消分类和清理。这是已记录的能力限制，底层取消能力并未因此得到修复。
收到响应后，两种模式都会尝试关闭响应，但真实唤醒时延仍依赖传输及运行环境。

自有模式也不承诺所有连接阶段的统一取消时限：TCP/TLS 建连尚未完成时，底层连接可能尚未
成为可关闭资源；关闭客户端不保证立即中断该阶段。不能用缩短首包超时替代取消，模型冷启动仍允许长等待。

**历史与当前证据（2026-10-23）**：Stage 2 原交付记录曾报告本机冷启动探针约 0.5 s，
并据此宣称等待响应头和读块均在 500 ms 内取消。该历史测量保留，但不再作为普遍时延保证，
也不代表本次整改的集成验收已经通过。G3 将以 1 s 目标重新测量真实 Ollama 冷启动取消、
连续取消和恢复；最终结果写入 Stage 2 交付记录，skipped 不计为 passed。

**后果**：同步核心保持单客户端、单路生成；生产工作线程的所有权、收尾与复用责任明确。
及时取消的验收必须区分默认真实传输、假传输与外部注入模式。

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
