# ADR-0003：Storage 外部事务误用的异常分类

- 状态：已批准并实施
- 日期：2026-10-24
- 决策者：项目负责人
- 批准来源：本次 Stage 3 Storage 第四轮修复对话中的正式裁决：“外部活动事务属于调用方误用，_ensure_no_external_transaction() 应抛出 sqlite3.ProgrammingError，而非 StorageIOError。”
- 关联：`docs/contracts/stage3-contract-v1.md` §5.2.3、`ROUND4_CONFLICT_INVESTIGATION.md`、`ROUND4_APPROVED_DECISIONS.md`

## 背景

Repository 的每个写操作拥有自己的短事务。若连接已经存在调用方发起的活动事务，Repository 必须在执行任何 SQL 前拒绝操作，避免误提交或误回滚调用方事务。

原实现以 StorageIOError 拒绝该场景，虽然事务保护有效，但与该异常的磁盘 I/O 语义不符。ROUND2_FIXES.md 曾建议方案 B，直到本次对话才取得项目负责人的正式批准。不能将先前建议或第四轮开发授权本身当作批准。

## 决定

1. `_ensure_no_external_transaction()` 在 `connection.in_transaction` 为真时抛出标准库 `sqlite3.ProgrammingError`。
2. 不新增公共异常类型，不修改 StorageError 的冻结继承层级，不修改任何公共方法签名。
3. 五个写方法仍在原有位置调用该守卫；守卫位于各方法写入异常处理的 try 之前，拒绝时不进入 rollback 路径。
4. 拒绝不执行 SQL，不调用 commit 或 rollback，不改变调用方未提交的数据。
5. 操作阶段真正的 OperationalError、DatabaseError 和 OSError 仍按既有映射处理，保留原始异常链。ProgrammingError 与 InterfaceError 保持原样透传。

## 调用方影响与验证

实施前只读搜索了业务源码和测试。没有发现其他业务调用方依赖旧分类；发现 TestF01TransactionOwnership 的五个测试，以及参数化 test_external_transaction_unchanged 的十项实例，期待 StorageIOError。

这些测试已按正式批准更新为 ProgrammingError。十项事务不变性测试额外断言精确异常类型、SQL trace 为空、活动事务仍存在、当前连接保留待提交变更、观察连接看不到未提交变更，并分别验证调用方后续自行 commit 或 rollback。

更新期望后，相关十五项在旧实现上全部失败；实施守卫分类修复后全部通过。与新时间戳格式的三项测试合并执行，完整证据为 18 failed → 18 passed，保留于 `.tmp/round4-approved-c6fb51d5e46c4d78a1a038d1d013f9b7/`。

## 兼容性与批准边界

调用方若将外部事务误用归入 `except StorageError`，现在将收到未映射的 ProgrammingError，应修正事务边界。此可见异常变化已由项目负责人明确批准；本 ADR 记录批准，不修改 v1.2 冻结契约文件，也不宣称取得其他接口变更授权。

本决定不更改数据库 Schema、历史记录、线程模型或 F-02 情绪更新原子性，不授权推进 Task 6。
