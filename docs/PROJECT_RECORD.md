# TestMind 总项目记录

> 更新：2026-09-04。当前生效路线：V2 参考 Pi 用 Python 实现“对话式 Test Agent”：Agent Core + 持续对话 + TestArtifact 协作编辑（测试点/用例）；基础测试设计与用例协作编辑在 V2 完成，V3 转向 API Testing / Failure RCA / Test Data / Defect / Execution 等更高级测试能力。
> 用户负责产品选择和体验；Codex 负责设计、实施任务与审查，通常由 Claude Code 按明确任务编码；每次实际执行者以开发记录为准。

## 1. 版本定义

| 版本 | 范围 | 当前事实 |
|---|---|---|
| V1 | 已有测试平台：项目、需求、用例、执行、报告、模型和权限 | 已有代码，保留兼容 |
| V2 | 对话式 Test Agent：Agent Core + 持续对话 + TestArtifact（Node/Revision/Operation/Diff/Undo）+ Artifact Tools + Chat/MindMap/Diff 工作台 | V2-P01～P04（消息/Provider/Agent Loop/会话持久化）已通过各自范围验收；P05 起按 [V2 开发主计划](V2/01_DEVELOPMENT_PLAN.md) 实施，尚未开始 |
| V3.1 | API Testing Agent | 占位；待 V2-P10 后规划 |
| V3.2 | Failure RCA | 原规划后移，未实现 |
| V3.3 | Test Data / 造数 | 原规划后移，未实现 |
| V3.4 | Defect Assistant | 原规划后移，未实现 |
| V3.5 | Execution / CI Integration | 占位；未实现 |

V2 不是 Pi 全量功能复制，也不是新增 Node 服务；参考 TypeScript 源码的行为设计，在 TestMind 用 Python 实现。前端仍为 React。参考仓库 D:\pi 与 D:\Ai-test-assistant 分开，前者不作为运行依赖。
基础测试设计与用例协作编辑现在是 V2 的纵向闭环；V3 更高级测试能力统一复用 V2 的 Conversation + Agent Loop + Tools + Artifact 模型，不为单个功能新建固定 Workflow Runtime。

## 2. 既有成果如何处理

旧 V2.1-T01～T08 形成了 Gateway、Agent 表、Workflow Runner、Worker、工具/用例 Workflow、API、悬浮工作台及测试。这些代码保留，属于可复用历史基线，不重复标记为新 V2 已完成。

本地提交 29414c7（V2.1 用例生成 Agent 与悬浮工作台）是可追踪基线，但重规划时仍有模型空响应等未提交代码/测试/文档修改；本轮原样保留，没有替它们做新提交或重跑测试。

2026-09-03 V2-R01（结构整理）在基线上把 Agent/LLM 模块按 models/services/schemas/routers 内子包归类，纯移动 + 导入更新 + 文档；结构测试 6 条、受影响/代表回归 338 条通过，详见 [V2 开发记录](V2/02_DEVELOPMENT_RECORD.md)。该项不是 V2-Pxx 对话内核成果，也未 commit/push。

旧开发记录、旧验收清单、旧 PRD/设计、提示词及根 README 均完整快照到 [旧路线归档](archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)。其中“已完成”只描述当时的局部工作，不代表新的基础对话 Agent 通过验收。

## 3. 当前事实与缺口

- 旧前端发送路径仍主要启动 case_generation；不能把状态气泡当作真实多轮助手回复。
- 新通用会话尚需独立入口、可空项目、模型预检、工具结果反馈、流式传输和恢复机制。
- 模型未绑定、无 Worker、外键孤立引用、空模型响应等历史问题都保留证据，不因版本更名消失。
- V2 验收以“持续对话 + TestArtifact 协作编辑”真实闭环为准；不能只凭用例生成成功替代，也不能只验证普通聊天而忽略 Artifact 修改。
- 通用安全、身份隔离、预算和取消仍属于 V2，不能随测试任务一起延期。
- 真实 MySQL/模型配置不是迁移 Pi 自动解决的问题；任何真实写入和计费请求仍需授权。
- V2-P01 合同阶段通过 Codex 复审：实际 90 passed in 5.41s；不代表浏览器已能聊天，详情见 V2/02_DEVELOPMENT_RECORD.md 2.10 与 V2/reviews/V2-P01_ACCEPTANCE.md。
- 2026-09-04 源码审计：conversation Agent Loop（loop/tool_executor/policy/budget/messages/events）已实现但未接任何 Worker/Router/Service，当前不存在 ConversationRunner；conversation queued Run 不被 Worker 消费；TestArtifact / Revision / Diff 尚不存在。P05 起点详见 V2/01_DEVELOPMENT_PLAN.md 的 V2-P05 任务卡。

## 4. 文档入口

~~~text
docs/
  PROJECT_RECORD.md
  V1/                      历史平台文档（不改业务定义）
  V2/                      当前规范 = 5 份主文档 + README（2026-09-04 收敛）
    README.md              入口与阅读顺序
    01_DEVELOPMENT_PLAN.md     唯一开发路线（P01～P10 任务卡）
    02_DEVELOPMENT_RECORD.md   实际完成记录
    03_ACCEPTANCE_CHECKLIST.md 验收门禁 + Artifact/协作/UI 验收域
    04_PRODUCT_PRD.md          产品定义（唯一 PRD）
    05_TECHNICAL_DESIGN.md     技术设计（唯一，含数据模型与工具合同）
    references/PI_SOURCE_AUDIT.md   Agent Core 的 Pi 源码对照
    learning/                      个人学习资料（教程/待学习清单）
    archive/                       历史记录：ADR、文档迁移清单、Legacy 迁移档案、
                                    legacy-workflow（旧固定 Workflow PRD/设计）
    reviews/                       已完成阶段的验收证据
  V3/
    README.md
    01_TEST_CAPABILITY_PLAN.md          API Testing / RCA / Test Data / Defect / Execution
    02_DEVELOPMENT_RECORD.md
    03_ACCEPTANCE_CHECKLIST.md
    04_CASE_GENERATION_AGENT_PRD.md     用例生成已进入 V2 的说明
    05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md  同上
  archive/PRE_PI_V2_2026-09-03/         旧路线完整快照
~~~

docs/V2 根目录只保留 README 与 01～05 五份长期主文档；references/learning/archive/reviews 按用途分目录，archive 仅作历史、不作为当前规范。

## 5. 执行与协作规则

1. 当前任务编号使用 V2-Pxx，测试能力使用 V3.x-Txx；不重用旧 V2.1-Txx 造成歧义。
2. 指定任务后先读源码、列边界、再实施，不重复确认已授权范围；未指定任务不自动开工。
3. 按完整 V2-Pxx 阶段实施：Codex 先读 Pi 并设计阶段任务，Claude 一次完成阶段实现/必要修正/针对性测试/记录，Codex 复审。阶段内不逐小步暂停、不自动跨阶段；仅在用户明确要求整理笔记时更新 D:\TestAgent node，不自动沉淀知识点。未测试不算验收，发布节点才做版本级回归。
4. 不把规划、目录存在、Fake 结果或旧测试数当成新能力已完成。
5. 迁移必须显式 Alembic、真实外键/并发测试与回滚边界；禁止关闭外键、重建库、造占位项目掩盖错误。
6. 真实模型、生产数据、外部系统写入与新增依赖按实际风险单独授权。
7. 保留用户改动；代码导入可能有建库副作用，诊断优先纯配置/只读 SQL，不输出 Secret。
8. 业务任务延后不等于删掉已实现业务；V2 的 test-design Skill（P08 起）按需加载，Skill/catalog 不默认自动执行固定业务流程；固定 case_generation Workflow 按 [V2 开发计划 V2-P05](V2/01_DEVELOPMENT_PLAN.md#v2-p05--conversation-runtime-收敛--legacy-workflow-退役) 退役，不隐藏在新 Tool 内部继续整链调用。

## 6. 决策记录

| 日期 | 决策 | 依据 |
|---|---|---|
| 2026-09-01～03 | 旧路线完成部分 Agent 测试 Workflow 与联调 | 归档开发记录，原任务编号保留 |
| 2026-09-03 | 用户明确要求先正常聊天，用例生成只是 Skill | 不再把固定工作流包装为完整对话 Agent |
| 2026-09-03 | 参考 Pi 架构，服务端坚持 Python，不接 Pi npm/Node 服务 | 用户明确技术偏好 |
| 2026-09-03 | V2 只交付基础架构，测试能力移到 V3 | 已在此次调整中被 2026-09-04 决策部分取代 |
| 2026-09-03 | Pi 克隆到 D:\pi，锁定 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 | 源码对照文档，不安装/运行上游 |
| 2026-09-04 | V2 转为“对话式 Test Agent”：持续对话 + 可持续编辑 TestArtifact；基础测试设计与用例协作编辑进入 V2；固定 case_generation Workflow 退役 | ADR 档案见 V2/archive/V2_DIRECTION_ADR_2026-09-04.md；P05～P10 见 V2/01_DEVELOPMENT_PLAN.md；退役并入其 V2-P05 |
| 2026-09-04 | V3 重定位为更高级测试能力：API Testing / Failure RCA / Test Data / Defect / Execution | 复用 V2 Conversation + Agent Loop + Tools + Artifact，不为单功能新建 Workflow Runtime |

历史逐任务记录见 [旧开发记录](archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)，不要将历史记录改名为新的完成记录。
