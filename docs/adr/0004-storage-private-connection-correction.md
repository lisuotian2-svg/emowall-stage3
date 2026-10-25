# ADR-0004：F-05 Database 连接属性私有化纠偏

- 日期：2026-10-24（Asia/Shanghai）
- 状态：APPROVED；项目负责人已批准，独立复审已核实实现事实
- 决策者：项目负责人
- 记录者：Lead Architect V2
- 授权来源：本轮《接管后首轮决策与执行授权》第五节

## 正式决定

负责人明确确认：Database.connection 并非 v1.2 冻结公共接口；将其改为私有 _connection 属于纠正实现偏差。实际文件与此前审查一致时，不需要新的公共接口变更申请。

## 文件核验

固定审查基准 manifest 所列 database.py 只提供私有 _connection 属性；repository.py 在同包内访问它。包级八个公共导出与 v1.2 §3.6 一致，冻结 Database API 未包含 connection。没有引入替代公共属性、修改数据模型或异常继承。

## 闭合结论与范围

F-05 批准缺口现已闭合。ROUND2_FIXES.md 与 HANDOVER.md 中的“待批”仅反映当时状态，应由本记录补充，不能再次作为当前阻塞项。无需新的公共接口变更申请，无需撤销现有私有化。

本决定不批准 Task 6、Git 提交或集成，不批准任何时间戳兼容范围变更。第四轮独立复审已核实实现与此结论一致；后续复验继续保护该结果。

独立依据：固定基准 snapshot_id 693149c0a5d2635ff613c71d5de34c59b53e258e4e590a1475dfa6950d342870 的 database.py、repository.py 与七份冻结契约；独立报告 ROUND4_INDEPENDENT_REVIEW.md 的 F-05 核验及 Task 5 分项结论。
