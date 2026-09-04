# V2：对话式 Test Agent 与可持续测试资产工作台

> 2026-09-03 启动 Pi 架构 Python 实现路线；2026-09-04 依据 [方向 ADR](11_V2_DIRECTION_ADR.md) 起调整 P05 及之后的路线。
> V2-P01～P04 已通过各自声明范围的 Codex 验收；P05（Conversation Runtime 收敛 + Legacy Workflow 退役）尚未实施，按 [P05～P10 新开发路线](12_POST_P04_DEVELOPMENT_PLAN.md) 推进。

**TestMind V2 是一个面向测试人员的对话式 Test Agent 工作台**：用户可以像使用 Coding Agent 修改代码一样，通过持续对话让 AI 读取、创建、修改、重构和检查测试资产，并以脑图等结构化视图实时协作。

P03 证据见 [Agent Loop 验收记录](reviews/V2-P03_ACCEPTANCE.md)；P04 证据见 [会话持久化验收记录](reviews/V2-P04_ACCEPTANCE.md)。下一阶段为 P05，尚未实施。

测试设计不是固定 Workflow。核心原则：**Model controls sequence；Program controls capability and safety；Artifact stores the evolving result。** 基础测试设计（测试点 / 测试用例协作编辑）现在是 V2 的纵向闭环；API 测试、失败根因、造数、缺陷辅助等更高级测试能力继续留在 [V3](../V3/README.md)。

## 必看顺序

1. [总项目记录](../PROJECT_RECORD.md)
2. [V2 主计划](01_AGENT_DEVELOPMENT_PLAN.md)
3. [方向 ADR](11_V2_DIRECTION_ADR.md)
4. [P05～P10 新开发路线](12_POST_P04_DEVELOPMENT_PLAN.md)
5. [Test Artifact / Case Tree 设计](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md)
6. [Artifact Tool 与 Agent 协议](14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL.md)
7. [Chat + MindMap + Diff 产品设计](15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md)
8. [Legacy Workflow 迁移计划](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)
9. [对话 PRD](04_CONVERSATIONAL_TEST_AGENT_PRD.md)、[基础架构](06_TEST_AGENT_PLATFORM_ARCHITECTURE.md)
10. [Pi 源码对照](10_PI_SOURCE_AUDIT.md)
11. [当前记录](02_DEVELOPMENT_RECORD.md)、[验收清单](03_ACCEPTANCE_CHECKLIST.md)

## 文档职责

| 文件 | 用途 |
|---|---|
| [01 主计划](01_AGENT_DEVELOPMENT_PLAN.md) | 10 个阶段、依赖、里程碑、验收与边界；P05～P10 以 12 为准 |
| [02 开发记录](02_DEVELOPMENT_RECORD.md) | 新 V2 的实际结果，不继承旧勾选 |
| [03 验收清单](03_ACCEPTANCE_CHECKLIST.md) | P01～P04 记录 + 新 P05～P10 门禁 + Artifact/协作/UI 验收域 |
| [04 对话 Test Agent PRD](04_CONVERSATIONAL_TEST_AGENT_PRD.md) | 持续对话 + 持续编辑 Test Artifact 的产品定义 |
| [06 架构](06_TEST_AGENT_PLATFORM_ARCHITECTURE.md) | Conversation → Agent Loop → Artifact Tools → Artifact Domain 主链 |
| [07 核心对象](07_AGENT_CORE_OBJECTS_TUTORIAL.md) | 面向小白的概念对照 |
| [08 待学习](08_LEARNING_BACKLOG.md) | 每个阶段按需学习 |
| [09 联调计划](09_FRONTEND_BACKEND_INTEGRATION.md) | 分层验证和真实环境边界 |
| [10 源码对照](10_PI_SOURCE_AUDIT.md) | 固定 GitHub 提交、源码符号及 Python 映射（Agent Core） |
| [11 方向 ADR](11_V2_DIRECTION_ADR.md) | 从固定 Workflow 转向可持续编辑 Test Agent 的决策 |
| [12 P05～P10 路线](12_POST_P04_DEVELOPMENT_PLAN.md) | P05～P10 详细里程碑与验收 |
| [13 Test Artifact 设计](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md) | Artifact / Case Tree / Revision / Operation / Diff / Undo 数据模型 |
| [14 Artifact 工具协议](14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL.md) | Agent 如何安全增量读写 Artifact |
| [15 Chat+MindMap+Diff 产品](15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md) | 工作台产品体验 |
| [16 Legacy 迁移](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md) | 旧 Workflow 退役执行计划 |
| [17 文档修改清单](17_EXISTING_DOCS_CHANGESET.md) | 本次既有文档迁移记录（已执行） |
| [prompts](prompts/README.md) | 后续 Claude 单任务提示词约定 |

参考仓库 D:\pi；TestMind D:\Ai-test-assistant。Python 重实现不是 TypeScript 逐行翻译，不承诺 Pi 插件兼容。
旧路线全部在 [历史归档](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，旧 V2.1-Txx 不能作为本版执行命令。
