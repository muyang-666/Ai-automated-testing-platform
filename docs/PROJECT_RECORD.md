# TestMind 总项目记录

> 更新：2026-09-03。当前生效路线：V2 参考 Pi 用 Python 实现基础 Agent；测试能力统一归 V3。
> 用户与 Codex 负责设计和审查；Claude Code 按明确任务实施。此次修改仅为文档规划和克隆参考仓库。

## 1. 版本定义

| 版本 | 范围 | 当前事实 |
|---|---|---|
| V1 | 已有测试平台：项目、需求、用例、执行、报告、模型和权限 | 已有代码，保留兼容 |
| V2 | Pi 风格 Python Agent 基础：对话、模型流、工具循环、Skill、上下文、持久化、取消、权限 | 新 V2-P01～P10 已规划，未实施验收 |
| V3.1 | 用例生成 Skill 接入与改进 | 旧版 Workflow/工具/产物可复用，未完成新内核接入 |
| V3.2 | 测试失败根因分析 Skill | 原规划后移，未实现 |
| V3.3 | 测试数据准备 Skill | 原规划后移，未实现 |
| V3.4 | 缺陷描述 Skill 与测试体验优化 | 原规划后移，未实现 |

V2 不是 Pi 全量功能复制，也不是新增 Node 服务；参考 TypeScript 源码的行为设计，在 TestMind 用 Python 实现。前端仍为 React。参考仓库 D:\pi 与 D:\Ai-test-assistant 分开，前者不作为运行依赖。

## 2. 既有成果如何处理

旧 V2.1-T01～T08 形成了 Gateway、Agent 表、Workflow Runner、Worker、工具/用例 Workflow、API、悬浮工作台及测试。这些代码保留，属于可复用历史基线，不重复标记为新 V2 已完成。

本地提交 29414c7（V2.1 用例生成 Agent 与悬浮工作台）是可追踪基线，但重规划时仍有模型空响应等未提交代码/测试/文档修改；本轮原样保留，没有替它们做新提交或重跑测试。

2026-09-03 V2-R01（结构整理）在基线上把 Agent/LLM 模块按 models/services/schemas/routers 内子包归类，纯移动 + 导入更新 + 文档；结构测试 6 条、受影响/代表回归 338 条通过，详见 [V2 开发记录](V2/02_DEVELOPMENT_RECORD.md#21--2026-09-03--v2-r01-agent--llm-模块目录整理)。该项不是 V2-Pxx 对话内核成果，也未 commit/push。

旧开发记录、旧验收清单、旧 PRD/设计、提示词及根 README 均完整快照到 [旧路线归档](archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)。其中“已完成”只描述当时的局部工作，不代表新的基础对话 Agent 通过验收。

## 3. 当前事实与缺口

- 旧前端发送路径仍主要启动 case_generation；不能把状态气泡当作真实多轮助手回复。
- 新通用会话尚需独立入口、可空项目、模型预检、工具结果反馈、流式传输和恢复机制。
- 模型未绑定、无 Worker、外键孤立引用、空模型响应等历史问题都保留证据，不因版本更名消失。
- V2 验收不能要求先有需求/接口文档，也不能用用例生成成功替代普通聊天验证。
- 通用安全、身份隔离、预算和取消仍属于 V2，不能随测试任务一起延期。
- 真实 MySQL/模型配置不是迁移 Pi 自动解决的问题；任何真实写入和计费请求仍需授权。

## 4. 文档入口

~~~text
docs/
  PROJECT_RECORD.md
  V1/                      历史平台文档（不改业务定义）
  V2/
    README.md
    01_AGENT_DEVELOPMENT_PLAN.md        V2-P01～P10 执行计划
    02_DEVELOPMENT_RECORD.md            新路线事实记录
    03_ACCEPTANCE_CHECKLIST.md          基础 Agent 门禁
    04_AGENT_SHELL_PRD.md               通用对话产品定义
    06_TEST_AGENT_PLATFORM_ARCHITECTURE.md
    07_AGENT_CORE_OBJECTS_TUTORIAL.md
    08_LEARNING_BACKLOG.md
    09_FRONTEND_BACKEND_INTEGRATION.md  新路线联调计划（未执行）
    10_PI_SOURCE_AUDIT.md               固定源码、符号、测试及差异
    prompts/README.md                  新任务提示词规则
  V3/
    README.md
    01_TEST_CAPABILITY_PLAN.md          测试能力任务与旧成果复用
    02_DEVELOPMENT_RECORD.md
    03_ACCEPTANCE_CHECKLIST.md
    04_CASE_GENERATION_AGENT_PRD.md
    05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md
  archive/PRE_PI_V2_2026-09-03/         旧路线完整快照
~~~

V2 内旧 04_CASE_GENERATION... / 05_CASE_GENERATION... 文件仅保留跳转说明，不能再作为当前 V2 任务书。

## 5. 执行与协作规则

1. 当前任务编号使用 V2-Pxx，测试能力使用 V3.x-Txx；不重用旧 V2.1-Txx 造成歧义。
2. 指定任务后先读源码、列边界、再实施，不重复确认已授权范围；未指定任务不自动开工。
3. 一次一个可验证增量；默认新增/直接相关测试，发布节点才全量回归。
4. 不把规划、目录存在、Fake 结果或旧测试数当成新能力已完成。
5. 迁移必须显式 Alembic、真实外键/并发测试与回滚边界；禁止关闭外键、重建库、造占位项目掩盖错误。
6. 真实模型、生产数据、外部系统写入与新增依赖按实际风险单独授权。
7. 保留用户改动；代码导入可能有建库副作用，诊断优先纯配置/只读 SQL，不输出 Secret。
8. 业务任务延后不等于删掉已实现业务；V2 新 catalog 不默认加载测试 Skill。

## 6. 决策记录

| 日期 | 决策 | 依据 |
|---|---|---|
| 2026-09-01～03 | 旧路线完成部分 Agent 测试 Workflow 与联调 | 归档开发记录，原任务编号保留 |
| 2026-09-03 | 用户明确要求先正常聊天，用例生成只是 Skill | 不再把固定工作流包装为完整对话 Agent |
| 2026-09-03 | 参考 Pi 架构，服务端坚持 Python，不接 Pi npm/Node 服务 | 用户明确技术偏好 |
| 2026-09-03 | V2 只交付基础架构，测试能力移到 V3 | 本计划替代旧版本范围 |
| 2026-09-03 | Pi 克隆到 D:\pi，锁定 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 | 源码对照文档，不安装/运行上游 |

历史逐任务记录见 [旧开发记录](archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)，不要将历史记录改名为新的完成记录。
