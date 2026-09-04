# V2：对话式 Test Agent 与可持续测试资产工作台

**TestMind V2 是一个面向测试人员的对话式 Test Agent 工作台**：用户可以像使用 Coding Agent 修改代码一样，通过持续对话让 AI 读取、创建、修改、重构和检查测试资产，并以脑图等结构化视图实时协作。

> 核心原则：**Model controls sequence；Program controls capability and safety；Artifact stores the evolving result。** 测试设计不是固定 Workflow。
> 状态：V2-P01～P04（消息 / Provider / Agent Loop / 会话持久化）已通过各自范围验收；P05（Conversation Runtime 收敛 + Legacy Workflow 退役）起尚未实施，路线见 [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)。
> V2 之内完成“测试设计与用例协作编辑”纵向闭环；API 测试、失败根因、造数、缺陷、执行/CI 等更高级测试能力属于 [V3](../V3/README.md)。

## 如何阅读

**第一次了解 V2：**

1. 本 README
2. [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md)（产品是什么样）
3. [05_TECHNICAL_DESIGN.md](05_TECHNICAL_DESIGN.md)（架构怎么实现）

**准备开发当前阶段：**

1. [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)（当前阶段任务卡）
2. [05_TECHNICAL_DESIGN.md](05_TECHNICAL_DESIGN.md) 对应章节
3. [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)（仅 Agent Core 相关阶段需要）

**开发完成：**

1. 更新 [02_DEVELOPMENT_RECORD.md](02_DEVELOPMENT_RECORD.md)（实际做了什么）
2. 对照 [03_ACCEPTANCE_CHECKLIST.md](03_ACCEPTANCE_CHECKLIST.md)（怎么验收）

## 正式文档职责（唯一当前规范）

| 文档 | Source of Truth |
|---|---|
| [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md) | 下一步开发什么：P01～P10 任务卡（Goal/Scope/实现要点/Acceptance/Stop boundary），唯一开发路线 |
| [02_DEVELOPMENT_RECORD.md](02_DEVELOPMENT_RECORD.md) | 已经实际完成了什么（按阶段事实记录） |
| [03_ACCEPTANCE_CHECKLIST.md](03_ACCEPTANCE_CHECKLIST.md) | 怎么验收：P01～P10 门禁 + Artifact/Conversational Editing/UI 验收域 |
| [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md) | 用户最终怎么使用（产品，不含实现细节） |
| [05_TECHNICAL_DESIGN.md](05_TECHNICAL_DESIGN.md) | 架构和代码应该怎么实现（唯一技术设计，含数据模型与工具合同） |

## 参考资料目录

- [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)：Agent Core 的 Pi 源码参考（固定 GitHub 提交、符号、Python 映射）。Artifact/MindMap/Diff 是 TestMind 自研业务层，不在其中。
- [learning/](learning/)：个人学习资料（核心对象教程、按阶段学习清单），非正式规范。
- [archive/](archive/)：历史路线与已完成使命的迁移记录（ADR、文档迁移清单、Legacy Workflow 迁移档案、旧固定 Workflow 文档）。仅作历史，不作为当前规范。
- reviews/：已完成阶段的 Codex 验收证据记录。

参考仓库 D:\pi；TestMind D:\Ai-test-assistant。Python 重实现不是 TypeScript 逐行翻译，不承诺 Pi 插件兼容。
旧路线（V2.1-Txx 时代）快照在 [docs/archive/PRE_PI_V2_2026-09-03](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，不作为本版执行命令。
