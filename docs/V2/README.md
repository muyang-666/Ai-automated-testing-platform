# V2：参考 Pi 的 Python Agent 基础架构

> 新路线生效于 2026-09-03。V2-P01～P03 已通过各自声明范围的 Codex 验收；P04～P10 尚未开始。

P02 验收证据见 [P02 验收记录](reviews/V2-P02_ACCEPTANCE.md)；P03 证据见 [Agent Loop 验收记录](reviews/V2-P03_ACCEPTANCE.md)。下一阶段为 P04，尚未实施。
> 用例生成、根因分析、造数和缺陷描述转入 [V3](../V3/README.md)。

## 必看顺序

1. [总项目记录](../PROJECT_RECORD.md)
2. [V2 主计划](01_AGENT_DEVELOPMENT_PLAN.md)
3. [对话 PRD](04_AGENT_SHELL_PRD.md)
4. [基础架构](06_TEST_AGENT_PLATFORM_ARCHITECTURE.md)
5. [Pi 源码对照](10_PI_SOURCE_AUDIT.md)
6. [当前记录](02_DEVELOPMENT_RECORD.md)、[验收清单](03_ACCEPTANCE_CHECKLIST.md)

## 文档职责

| 文件 | 用途 |
|---|---|
| [01 主计划](01_AGENT_DEVELOPMENT_PLAN.md) | 10 个任务、依赖、文件范围、验收和越界限制 |
| [02 开发记录](02_DEVELOPMENT_RECORD.md) | 新 V2 的实际结果，不继承旧勾选 |
| [03 验收清单](03_ACCEPTANCE_CHECKLIST.md) | 聊天/工具/Skill/恢复/安全门禁 |
| [04 对话 PRD](04_AGENT_SHELL_PRD.md) | 普通聊天优先、任务与会话分开 |
| [06 架构](06_TEST_AGENT_PLATFORM_ARCHITECTURE.md) | Python 模块、存储、Worker、API、事件和权限 |
| [07 核心对象](07_AGENT_CORE_OBJECTS_TUTORIAL.md) | 面向小白的概念对照 |
| [08 待学习](08_LEARNING_BACKLOG.md) | 每个任务按需学习 |
| [09 联调计划](09_FRONTEND_BACKEND_INTEGRATION.md) | 分层验证和真实环境边界 |
| [10 源码对照](10_PI_SOURCE_AUDIT.md) | 固定 GitHub 提交、源码符号及 Python 映射 |
| [prompts](prompts/README.md) | 后续 Claude 单任务提示词约定 |

参考仓库 D:\pi；TestMind D:\Ai-test-assistant。Python 重实现不是 TypeScript 逐行翻译，不承诺 Pi 插件兼容。
旧路线全部在 [历史归档](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，旧 V2.1-Txx 不能作为本版执行命令。
