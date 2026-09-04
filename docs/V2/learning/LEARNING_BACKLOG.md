# V2 学习记录与阶段笔记

学习目标：能在面试中结合实际 Python 源码，讲清设计、运行和验证证据。

## 笔记组织

总目录：[TestMind 学习笔记](<D:/TestAgent node/README.md>)。

一个阶段一个文件夹，全部知识点集中在该阶段的《学习笔记.md》。已按用户指定的 obsidian-markdown skill 整理：属性/标签、库内双链、章节导航、状态块引用、可折叠待修项与面试问答；TestMind 源码位置使用脚注，Pi 引用固定提交。P01 的 41 个知识小节保留；旧版笔记归档已按用户授权删除。2026-09-04 起 P05 后的学习主题按 [P05～P10 新路线](../01_DEVELOPMENT_PLAN.md) 重排：原“P07 通用 Skill / P08 上下文 / P09 人工门禁”的旧阶段主题并入新路线对应阶段（Skill 归 P08、上下文与审批归 P10）。

| 阶段 | 主要知识点 | 当前状态 / 笔记 |
|---|---|---|
| P01 | 架构位置、消息/Turn、Pydantic、用量/停止原因、两层事件、工具校验、隔离测试与审查反例 | 阶段验收通过；[P01 学习笔记](<D:/TestAgent node/V2-P01/学习笔记.md>) 已整理 |
| P02 | Provider 适配、异步模型流、分片与重试、AttemptRecord | 阶段验收通过；本阶段知识点待沉淀 |
| P03 | Agent Loop、Tool Executor、策略改参后重校验、预算与取消 | 阶段验收通过；本阶段知识点待沉淀 |
| P04 | 持久化、事务、幂等键、序号游标、活跃 Turn 串行化、乐观并发起点 | 阶段验收通过；本阶段知识点待沉淀 |
| P05 | Worker：lease、heartbeat、fencing token、cancellation、队列与 follow-up；ConversationRunner；Legacy Workflow 退役与依赖审计 | 未实施 |
| P06 | SSE（Bearer 鉴权 / 游标 / 重连 / 去重）、ConversationRunner 接线、persistent conversation、前端 Turn 提交 | 未实施 |
| P07 | Domain Modeling、Tree Model（node_type/order/source_ref）、Revision Log vs Event Sourcing、Optimistic Lock、结构化 Diff、Undo 语义 | 未实施 |
| P08 | Tool Contract（expected_revision / audit / RuntimeContext）、Patch Semantics（增量而非整树替换）、Agent Editing Pattern（read before write / minimal edit）、Skill Design（领域知识 + 行为规则，非状态机） | 未实施 |
| P09 | MindMap 作为 Artifact 视图、Diff UX（added/updated/deleted/moved）、Optimistic UI / conflict、人工与 AI 编辑同一 Artifact、impact preview | 未实施 |
| P10 | Context Compaction、Long-lived Artifact Context（不整树塞 prompt）、Approval by Action Risk、Recovery 故障注入、E2E | 未实施 |

## 当前学习与开发边界

- 笔记明确分开已实现、待修、未实现；审查缺口作为案例解释，不包装成已修复能力。
- 正常节奏仍是整阶段实现/测试、Codex 审查、复盘学习；用户要求提前整理时可以先补已知知识，保留事实边界。
- 代码实现、测试通过、阶段验收、用户理解分别记录，不因文档已整理就标为已掌握。
