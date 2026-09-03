# TestMind V2 文档索引

> 当前状态（2026-09-03）：T01–T07 已实现，T08 前端主闭环完成隔离联调；真实环境联调、扩展交互和 T09 发布验收尚未完成。

## 版本目标

- **V2.1**：用例生成 Agent
- **V2.2**：测试失败根因分析 Agent
- **V2.3**：测试 Skill 扩展与细节优化
- **V2.4**：待定

## Claude Code 必读顺序

1. `../PROJECT_RECORD.md`
2. `01_AGENT_DEVELOPMENT_PLAN.md`
3. `06_TEST_AGENT_PLATFORM_ARCHITECTURE.md`
4. V2.1 任务额外阅读 `04_CASE_GENERATION_AGENT_PRD.md`
5. V2.1 任务额外阅读 `05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md`
6. `02_DEVELOPMENT_RECORD.md`
7. `03_ACCEPTANCE_CHECKLIST.md`
8. 与当前任务相关的真实源码

## 文件职责

| 文件 | 作用 |
|---|---|
| `01_AGENT_DEVELOPMENT_PLAN.md` | 产品和技术决策、任务依赖、实现顺序、文件范围和完成定义 |
| `02_DEVELOPMENT_RECORD.md` | 只记录真实实施结果、命令、测试证据、问题和后续事项 |
| `03_ACCEPTANCE_CHECKLIST.md` | V2.1、V2.2、V2.3 的硬门禁和回归检查 |
| `04_CASE_GENERATION_AGENT_PRD.md` | V2.1 用户流程、页面交互、功能需求和产品验收 |
| `05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md` | V2.1 架构、技术选型、状态、工具、数据、API、测试和学习笔记 |
| `06_TEST_AGENT_PLATFORM_ARCHITECTURE.md` | 对话式测试 Agent、Skill、Tool、Artifact、模型接入和版本路线总架构 |
| `07_AGENT_CORE_OBJECTS_TUTORIAL.md` | 面向小白的 Session、Skill、Tool、Artifact 概念、示例和练习 |
| `08_LEARNING_BACKLOG.md` | 按开发任务维护的待学习知识点和实践状态 |
| `09_FRONTEND_BACKEND_INTEGRATION.md` | T08 实际 API 合同、隔离联调入口、启动说明、验证证据与边界 |
| `prompts/` | 用户可直接复制给 Claude Code 的单任务实施提示词 |

## 使用规则

- Claude Code 每次只执行用户指定的一个任务编号。
- 用户发送 Codex 生成的单任务提示词即视为授权该任务；Claude 输出简短实施摘要后直接编码，不等待二次确认。
- 计划书描述“应该做什么”，开发记录描述“实际做了什么”。
- 未获得真实验证结果时，不得修改任务状态为完成。
- V2.1 未验收前，不进入 V2.2；V2.2 未验收前，不进入 V2.3。

