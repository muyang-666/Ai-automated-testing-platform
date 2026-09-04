# ADR 2026-09-04：从固定 Workflow 转向可持续编辑的对话式 Test Agent

> 状态：Accepted（已执行）。本文件是历史决策记录，当前规范见 docs/V2 主文档（README / 01_DEVELOPMENT_PLAN / 04_PRODUCT_PRD / 05_TECHNICAL_DESIGN）。

## Context

V2-P01～P04 已交付 Agent Message / Provider / Agent Loop / ToolCall / ToolResult / Conversation Persistence（参考 Pi Agent 的基础能力）。项目仍存在更早期实现的固定测试流程：CaseGenerationWorkflow、AgentRunner、next_step、execute_step，由 phase / gate 驱动。

产品方向已改变。TestMind 不再是一键式“需求 → case_generation Workflow → analyze → generate → validate → coverage → repair → save → 结果”，而应成为**一个可以持续对话、持续读取和编辑测试资产的 Test Agent**，体验类似 Coding Agent 修改代码：用户先列测试点、展开其中几个、直接补用例、删除一个、修改已有用例、让 AI 补边界、检查覆盖率、手工改脑图、再让 AI 基于人工修改继续、看 Diff、Undo、第二天继续同一 Conversation。

真实测试过程并不固定。继续在固定 Workflow 上打补丁（分支/phase/gate/特殊跳转/resume 规则）会让 Workflow 取代模型成为业务控制器，与“持续对话 Agent”目标冲突。

## Decision

1. V2 目标调整为：构建持续对话、持续读取和修改测试资产的 Test Agent；测试用例从“一次 Workflow 的输出”变为类似代码文件的长期 Artifact。
2. V2-P05 起，新 Conversation Agent 不再进入固定测试 Workflow；测试设计路径由 Agent 根据当前上下文动态决定。
3. 确定性能力保留为 Tool / Domain Service；Skill 定义为“领域知识 + 行为规则”，不用于编排固定状态迁移。
4. TestArtifact 提升为一等业务对象（Node / Revision / Operation / Diff / Undo / 乐观锁），脑图只是其视图；AI 与人工写操作走同一 Application Service。
5. V2 的纵向闭环改为：持续聊天 → 打开/创建 Test Artifact → AI 读取 → AI 增量编辑 → UI 脑图实时展示 → Diff → 用户继续对话修改 → Revision 可恢复。完成后 V3 再扩展 API 测试 / RCA / 造数 / 缺陷 / 执行等高级能力。
6. 核心原则：**Model controls sequence；Program controls capability and safety；Artifact stores the evolving result。**

## Why

- 固定 Workflow 只适合一次性生成任务，不适合持续协作式测试设计；它会持续累积分支与 gate，最终与“模型决定下一步”冲突。
- Coding Agent 模式已被验证：工具化增量编辑 + 版本化资产，比“整体生成一份 JSON”更适合人机长期协作。
- P01～P04 已具备的 Pi-like Agent Core 正是这种模式的基础设施，不需要推翻，只需接入 Artifact 与编辑工具。

## Consequences

- Positive：
  - 用户获得“像 Coding Agent 改代码一样维护测试用例”的体验；AI 与人工可在同一 Artifact 上持续协作。
  - 增量 Operation 提供 Diff / Undo / 审计 / 乐观并发 / 小粒度审批，减少大模型误改无关内容。
  - 后续 V3 高级能力复用同一 Conversation + Agent Loop + Tools + Artifact 模型，不再每个功能新建 Workflow Runtime。
- Negative / Cost：
  - 需要新建 Artifact 领域（数据模型、Revision/Diff/Undo、乐观锁）与 Artifact Tools，P07/P08 工作量前置；
  - 旧的固定 Workflow 测试资产（gate、prompt 流程、orchestration tests）需要迁移或删除（见开发计划 V2-P05 的 A/B/C 分类）；
  - “覆盖/查重必须自动跑”的旧习惯不再成立，质量工具变成可选能力，质量门禁需要重新设计（按动作风险）。
- Risks：
  - Agent 自由决定路径可能弱化流程纪律 → 用 Tool Contract、Policy/Approval、测试设计 Skill 的行为规则约束；
  - 版本/并发复杂度上升 → 首期线性 Revision + expected_revision 乐观锁，不做 Git DAG / CRDT。

## Alternatives Rejected

1. **继续在固定 Workflow 上加分支与模式（rejected）**：随用户请求组合增多，Workflow 变成 if/else 业务控制器；与“模型决定下一步”冲突，且维护成本持续上升。
2. **V2 只做通用聊天基础、测试 Artifact 全部推后到 V3（rejected）**：无法形成可验收的测试价值闭环；用户无法用 V2 做真实测试工作，V3 又要从零补协作编辑基础。
3. **每次用户输入都重新完整生成整棵用例 JSON（rejected）**：token 成本高、误删无关内容、无法 Diff/Undo、人工编辑与 AI 输出无法共存。
4. **把脑图结构（某 UI 库坐标/组件）当底层数据存储（rejected）**：视图与业务真相耦合；改为 TestArtifact（数据）→ MindMap/Table/JSON 视图（投影）。
5. **为保持兼容长期保留两套执行核心并行（rejected）**：会出现两个“谁决定下一步”的控制器、两套 Tool 路径与 Approval 语义；新代码不知道该写 Tool 还是 Step。改为新 Agent 只走 Agent Loop，旧 Workflow 退役为 legacy 兼容区或删除。
