# TestMind 总项目记录

> 最后更新：2026-09-03
>
> 本文件位于版本子目录之外，记录项目总定位、版本路线、当前状态和文档入口。

## 1. 项目定位

TestMind 是一个面向测试人员的 AI 测试工作平台。

项目以接口自动化测试闭环为基础，逐步增加需求与接口文档管理、功能用例管理、场景串联执行、模型配置、权限管理，并在 V2 阶段把“一次 LLM 调用”升级为可追踪、可评测、有人机审批边界的受控 Agent 工作流。

核心原则：

- 确定性规则负责可稳定判断的工作。
- LLM 负责需求理解、候选生成和复杂归纳。
- Agent 通过白名单工具获取证据并验证结果。
- 保存用例、重新执行等有副作用的动作保留人工确认。
- V2 改造不得破坏 V1 已有业务闭环。

## 2. 当前事实基线

### V1 已具备

- 项目、模块、用户、角色和项目权限管理
- 需求文本、接口文档、接口用例和功能用例管理
- LLM 生成功能用例和接口用例
- 生成结果预览、勾选和保存
- 规则生成 pytest 测试代码
- pytest 动态执行、日志和响应采集
- 场景步骤、变量提取、断言和真实串联执行
- AI 失败日志分析
- 测试报告与模型配置管理

### V2 当前状态

V2.1 的 Agent 数据表、Gateway、Runtime、Worker、用例生成 Skill 与 API 已实现；悬浮前端工作台已完成 SQLite + Fake LLM 的真实 HTTP/Worker 主闭环联调。真实供应商/MySQL 联调、影子评测和版本发布验收尚未完成。根因分析 Agent（V2.2）尚未实现，不得把规划写成已完成功能。详见 V2/02 开发记录和 V2/09 联调说明。

## 3. 版本路线

| 版本 | 目标 | 状态 |
|---|---|---|
| V1.0–V1.5 | 单接口自动化测试基础闭环 | 已完成，历史版本 |
| V1.6 | 项目、模块目录和用例归类 | 已完成 |
| V1.7 | 需求、功能用例和需求生成功能用例 | 已完成 |
| V1.8 | 场景增强与真实接口串联执行 | 已完成 |
| V2.1 | 改造用例生成 Agent | 主闭环已实现，T08 隔离联调通过；待真实环境与 T09 验收 |
| V2.2 | 改造测试失败根因分析 Agent | 待开发 |
| V2.3 | 测试 Skill 扩展与安全、可观测性、评测、交互优化 | 待开发 |
| V2.4 | 根据 V2.1–V2.3 的数据与反馈确定 | 待定 |

## 4. 文档结构

```text
docs/
  PROJECT_RECORD.md                 总项目记录与版本入口
  V1/
    README.md                       V1 文档索引
    00_PROJECT_CONTEXT.md           V1 项目上下文
    01_REQUIREMENTS.md              V1 需求规格
    06_CURRENT_STATUS.md            V1 最终状态快照
    07_CHANGELOG.md                 V1 变更日志
    08_AI_CODING_RULES.md           V1 历史开发规则
    09_ACCEPTANCE_CHECKLIST.md      V1 回归验收清单
  V2/
    README.md                       V2 文档索引与当前状态
    01_AGENT_DEVELOPMENT_PLAN.md    Claude Code 主执行计划
    02_DEVELOPMENT_RECORD.md        V2 实际开发记录与证据
    03_ACCEPTANCE_CHECKLIST.md      V2 分版本验收门禁
    04_CASE_GENERATION_AGENT_PRD.md V2.1 产品需求与前端交互
    05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md
                                    V2.1 技术设计与学习笔记
    06_TEST_AGENT_PLATFORM_ARCHITECTURE.md
                                    对话式测试 Agent 平台总架构
    07_AGENT_CORE_OBJECTS_TUTORIAL.md
                                    Session、Skill、Tool、Artifact 学习笔记
    08_LEARNING_BACKLOG.md          Agent 项目待学习知识点
    09_FRONTEND_BACKEND_INTEGRATION.md
                                    T08 联调证据、启动说明与边界
    prompts/                        可复制给 Claude Code 的单任务提示词
```

## 5. 人与 AI 的协作方式

### 用户与 Codex

- 确定产品范围、优先级、业务边界和技术决策。
- 把当前版本拆成 Claude Code 可执行的小任务。
- 审查实现结果、风险和验收证据。

### Claude Code

- 只执行用户明确指定的当前版本和任务编号。
- 开始前阅读本文件、V2 主计划、V2 开发记录和 V2 验收清单。
- 用户发送 Codex 生成的单任务提示词即代表授权该任务范围；Claude Code 先检查真实源码并输出简短实施摘要，然后直接编码。
- 实现后运行测试，并把真实结果写入 V2 开发记录。
- 不自行跨版本开发，不把未运行的检查标记为通过。
- 只有新增依赖、真实环境操作、数据库范围变化、破坏性操作或任务越界时暂停询问。

## 6. 全项目变更规则

1. V1 文档属于历史快照，原则上只修正断链或明显事实错误。
2. V2 的产品与技术规划写入 `V2/01_AGENT_DEVELOPMENT_PLAN.md`。
3. 实际完成情况只写入 `V2/02_DEVELOPMENT_RECORD.md`，不得用计划代替完成记录。
4. 验收状态只在有命令输出、接口结果、页面验证或人工确认时更新。
5. 数据库结构变化必须使用可回滚迁移，不依赖 `create_all` 修改已有表。
6. 保留旧接口或 feature flag，直到新 Agent 链路完成影子评测和回归验收。
7. 不记录或提交 API Key、Authorization、Cookie、Token、真实密码和敏感响应。
8. 遇到范围冲突时停止实现，由用户与 Codex 重新确认设计。

## 7. 总项目记录

| 日期 | 版本 | 记录 | 证据位置 |
|---|---|---|---|
| 2026-09-01 | V1 | 整理 V1 历史文档，作为现有能力和回归基线 | `docs/V1/` |
| 2026-09-01 | V2 | 确定 V2.1 对话 Shell + 用例生成、V2.2 根因分析、V2.3 Skill 扩展与优化、V2.4 待定 | `docs/V2/01_AGENT_DEVELOPMENT_PLAN.md` |
| 2026-09-01 | V2.1 | 将交互调整为对话式测试 Agent + 结构化 Artifact，并建立用例生成 PRD 与技术设计 | `docs/V2/04_CASE_GENERATION_AGENT_PRD.md`、`05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md` |
| 2026-09-01 | V2 | 基于 Claude Code + Skills 模式，确定 TestMind 自建测试专用 Agent，不直接内嵌 Claude Code CLI | `docs/V2/06_TEST_AGENT_PLATFORM_ARCHITECTURE.md` |
| 2026-09-01 | V2.1 | 完成 Session、Skill、Tool、Artifact 四个核心对象的第一轮学习沉淀 | `docs/V2/07_AGENT_CORE_OBJECTS_TUTORIAL.md` |
| 2026-09-01 | V2.1 | 建立待学习知识点清单，后续学习不阻塞编码 | `docs/V2/08_LEARNING_BACKLOG.md` |
| 2026-09-01 | V2.1 | 生成 V2.1-T01 Baseline 测试的 Claude Code 单任务提示词 | `docs/V2/prompts/V2.1-T01_BASELINE_TESTS_CLAUDE_PROMPT.md` |
| 2026-09-01 | V2.1 | T01 经 Codex 独立复核 33 passed，生成 T02 Agent 平台数据模型与迁移提示词 | `docs/V2/prompts/V2.1-T02_AGENT_PLATFORM_MODELS_CLAUDE_PROMPT.md` |
| 2026-09-01 | V2.1 | T02 报告验收 50 passed，生成 T03 LLM Gateway 与 Provider Adapter 提示词 | `docs/V2/prompts/V2.1-T03_LLM_GATEWAY_PROVIDERS_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2.1 | T03 报告验收 102 passed，将 T04 拆分并生成 T04A Runtime 核心提示词 | `docs/V2/prompts/V2.1-T04A_RUNTIME_CORE_REGISTRIES_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2 | 单任务提示词范围内改为直接编码，仅高风险、越界或新增依赖时暂停确认 | `docs/V2/01_AGENT_DEVELOPMENT_PLAN.md` |
| 2026-09-02 | V2.1 | T04A 报告验收 165 passed，生成 T04B Worker 抢占与恢复提示词 | `docs/V2/prompts/V2.1-T04B_WORKER_RECOVERY_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2.1 | T04B 报告验收 191 passed；T05 审查发现去重阻断问题，生成 T05.1 修复提示词 | `docs/V2/prompts/V2.1-T05.1_DEDUP_FINGERPRINT_FIX_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2.1 | T05.1 报告验收 248 passed，生成 T06 用例生成 Skill 与 Workflow 提示词 | `docs/V2/prompts/V2.1-T06_CASE_GENERATION_SKILL_WORKFLOW_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2.1 | T06 报告验收 288 passed，生成 T07 Agent API、审批续跑与候选保存提示词 | `docs/V2/prompts/V2.1-T07_AGENT_API_APPROVAL_SAVE_CLAUDE_PROMPT.md` |
| 2026-09-02 | V2.1 | T04B 报告验收 191 passed，生成 T05 用例生成领域工具提示词 | `docs/V2/prompts/V2.1-T05_CASE_GENERATION_TOOLS_CLAUDE_PROMPT.md` |
