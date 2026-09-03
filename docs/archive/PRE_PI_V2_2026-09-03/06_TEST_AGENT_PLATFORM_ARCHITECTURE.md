# TestMind 对话式测试 Agent 平台架构

> 文档类型：平台级产品与技术架构
>
> 当前版本：v0.5
>
> 状态：方向已确定；数据模型（T02）、LLM Gateway（T03）、Runtime/Registry/Service（T04A）、Worker（T04B）、领域工具（T05/T05.1）、case_generation Skill/Workflow（T06）、会话/Run/GATE/保存 API（T07）已实施并验证；前端工作台尚未实现
>
> 目标：借鉴 Claude Code + Skills 的工作方式，但建设 TestMind 自己的测试专用 Agent

## 1. 最终建议

TestMind 不直接把 Claude Code CLI 内嵌为后端，而是实现一个测试专用的对话式 Agent 平台。

推荐形态：

```text
TestMind 对话工作台
  → Test Agent Runtime
  → Skill Registry
  → Tool Registry / MCP Adapter
  → TestMind 业务数据与测试环境
  → 结构化 Artifact
  → 用户审批后写入业务系统
```

Claude 可以作为 TestMind 的一个模型 Provider，但不是 TestMind 的产品外壳。

## 2. 从实习项目抽象出的设计模式

对 `D:\Wenext_api_test\api-test` 的只读检查表明，该项目的能力主要来自以下组合，而不是 Claude 模型本身：

### 2.1 Claude Code 是通用 Agent 宿主

Claude Code 负责：

- 对话；
- 识别任务；
- 读取匹配的 Skill；
- 调用文件、终端和 MCP 工具；
- 维护当前会话上下文；
- 把工具结果继续交给模型判断。

### 2.2 Skills 注入测试领域流程

项目中的 Skills 定义：

- 什么时候触发；
- 先读取什么资料；
- 分几个 Phase；
- 哪些步骤是 GATE；
- 哪些信息必须向用户确认；
- 可以调用哪些脚本和 MCP；
- 输出到哪里；
- 如何校验；
- 失败时 PASS、BLOCKED、SKIP 或 FAIL。

### 2.3 MCP 和脚本提供真实行动能力

LLM 不直接连接数据库和环境，而是通过受控工具完成：

- 数据库查询；
- Redis 查询；
- Swagger 检索；
- 日志检索；
- 测试数据准备；
- 文档和测试产物生成。

### 2.4 状态文件和产物承担记忆

流程状态、来源 hash、freshness、覆盖报告、XLSX、Python 脚本和测试报告都是可复检 Artifact，而不是只存在聊天记录中。

### 2.5 对话承担 GATE 和协商

系统不是纯自动执行。关键范围、来源、测试策略、接口选择、缺口补充和写操作会暂停，等待用户确认后继续。

## 3. 不能直接照搬的部分

### 3.1 不复制内部业务资产

TestMind 只能复用架构思想，不复制内部：

- 业务接口；
- 数据库表与 Redis Key；
- 环境地址和凭证；
- 造数脚本；
- App 专属规则；
- 日志和真实业务数据。

TestMind 的公开 Demo、评测集和测试环境使用虚构业务与合成数据。

### 3.2 不给 Web 用户开放通用 Bash 和文件权限

Claude Code 面向可信开发者和代码工作区。TestMind 面向测试平台用户，权限边界完全不同。

TestMind 首期不能给 Agent 开放：

- 任意 Bash；
- 任意文件读写；
- 任意 SQL；
- 任意 URL；
- 任意 pytest 执行。

### 3.3 不把仓库配置中的明文凭证模式带入 TestMind

TestMind 的模型、数据库、MCP 和测试环境凭证必须使用环境变量、加密存储或 Secret/Vault 机制，不能把真实凭证写入仓库或 Agent 轨迹。

## 4. 三种实现方式对比

### 方案 A：后台直接启动 Claude Code CLI

```text
TestMind 后端
→ 创建子进程运行 claude
→ 解析终端输出
```

不推荐。

问题：

- CLI 输出和权限难以做稳定业务 API；
- 多用户会话、并发和隔离复杂；
- 文件、终端权限过大；
- 审计和结构化 Artifact 困难；
- 认证、费用和进程恢复难治理；
- TestMind 会变成 Claude Code 的包装壳。

### 方案 B：使用 Claude Agent SDK 或 Claude Managed Agents

可行，适合快速原型或 Claude 专用版本。

官方 Claude Platform 当前提供：

- Agent SDK：Agent 运行在你维护的进程中；
- Managed Agents：Agent、Session 和沙箱运行在 Anthropic 基础设施；
- 可配置 system、tools、MCP、skills、session 和事件；
- 可使用自定义工具并接收工具确认事件。

优点：

- 与 Claude Code/Skills 心智模型最接近；
- Agent loop、Session、Skill 和工具机制现成；
- 更快做出对话原型。

缺点：

- 核心能力绑定 Claude；
- TestMind 当前多 Provider 配置需要重新取舍；
- Managed Agents 当前属于 beta 能力，接口和部署策略需要持续跟踪；
- 自定义测试工具、项目权限、Artifact 和业务表仍需自己实现；
- 云沙箱或自托管环境带来额外成本和治理。

### 方案 C：TestMind 自建测试专用 Agent Runtime

推荐。

```text
TestMind 管理会话、Skill、工具、Artifact 和审批
Claude / DeepSeek / 其他模型只作为可替换的大脑
```

优点：

- 与现有 FastAPI、Pydantic、SQLAlchemy 和模型配置衔接；
- 可以同时支持 Claude API 和 OpenAI-compatible 模型；
- 权限、Artifact 和业务操作完全掌握在 TestMind；
- 更适合学习 Agent 原理和展示独立项目能力；
- 后续可以替换 Runtime 实现而不改变业务 Skill。

缺点：

- 需要自己实现会话、工具循环、状态、审批、事件和恢复；
- 首期开发时间更长。

由于用户时间充足并希望系统学习，选择方案 C。

## 5. 产品形态：聊天控制面 + 结构化工作区

TestMind 不做只有气泡消息的普通聊天机器人。

推荐页面：

```text
┌──────────────────────────────────────────────────────────┐
│ 左侧：会话/项目/Skill             右侧：当前上下文        │
├──────────────────────────┬───────────────────────────────┤
│ 中间：Agent 对话          │ Artifact 工作区               │
│                           │ - 覆盖矩阵                    │
│ 用户：为需求 12 生成用例  │ - 候选用例表                  │
│ Agent：已读取需求...      │ - 造数预览                    │
│ Agent：请确认覆盖范围     │ - 缺陷草稿                    │
│ [确认] [修改范围]         │ - 根因证据                    │
│                           │ - 执行报告                    │
└──────────────────────────┴───────────────────────────────┘
```

### 对话负责

- 接收自然语言目标；
- 追问缺失信息；
- 展示进度；
- 暂停等待 GATE；
- 接收局部修改；
- 解释结果。

### Artifact 工作区负责

- 表格化展示；
- 批量勾选；
- 编辑；
- 来源追踪；
- 覆盖矩阵；
- 审批和写入；
- 下载或导出。

结论：聊天是控制面，Artifact 是业务结果，不要把几十条用例塞在聊天气泡里。

## 6. Test Agent 核心对象

面向初学者的完整解释和练习见 `07_AGENT_CORE_OBJECTS_TUTORIAL.md`。

### 6.1 AgentDefinition

一个版本化的测试 Agent 配置：

- name
- model/provider
- system policy
- allowed skills
- allowed tools
- permission policy
- version

### 6.2 AgentSession

一次持续对话：

- session_id
- project_id
- user_id
- selected_agent_version
- current_skill
- status
- context summary
- created_at / updated_at

### 6.3 AgentMessage

用户、Agent、工具和系统事件的可展示消息。

### 6.4 AgentEvent

细粒度事件：

- skill_selected
- phase_started
- tool_requested
- tool_completed
- artifact_created
- approval_required
- approval_resolved
- phase_completed
- session_failed

### 6.5 SkillDefinition

测试领域能力包：

- name / description / version
- trigger intents
- required context
- phases
- gates
- allowed tools
- input/output Schema
- stop conditions
- prompt resources
- evaluator

### 6.6 ToolDefinition

- name / description
- input/output Schema
- read/write
- required permission
- approval policy
- timeout / retry / idempotency

### 6.7 Artifact

Agent 产生的结构化业务结果：

- test_case_set
- coverage_matrix
- data_fabrication_plan
- defect_draft
- root_cause_report
- execution_report

## 7. Skill 目录建议

```text
backend/app/agents/skills/
  case_generation/
    skill.yaml
    instructions.md
    schemas.py
    workflow.py
    prompts/
    evaluators.py
  data_fabrication/
    skill.yaml
    instructions.md
    schemas.py
    workflow.py
    prompts/
    evaluators.py
  defect_drafting/
    skill.yaml
    instructions.md
    schemas.py
    workflow.py
    prompts/
    evaluators.py
  failure_rca/
    skill.yaml
    instructions.md
    schemas.py
    workflow.py
    prompts/
    evaluators.py
```

### 为什么不是只放一个 SKILL.md

Claude Code 宿主已经负责发现、读取和执行 SKILL.md。TestMind 自建 Runtime 后，需要把 Skill 变成可被程序验证和版本管理的对象。

因此：

- `skill.yaml` 保存机器可读配置；
- `instructions.md` 保存给模型看的领域规则；
- `workflow.py` 保存确定性流程与 GATE；
- `schemas.py` 保存结构化合同；
- `evaluators.py` 保存验收和评测逻辑。

## 8. Skill 路由

首期采用显式入口优先、模型路由补充：

### 显式入口

- 用户点击“生成用例”；
- 用户从失败记录点击“分析根因”；
- 用户点击“准备测试数据”；
- 用户点击“生成缺陷描述”。

前端把 skill_code 直接传给 Agent，最稳定、可测试。

### 对话路由

用户在通用对话框输入：

```text
帮我根据登录需求生成测试用例。
```

Skill Router 返回结构化选择：

```json
{
  "skill_code": "case_generation",
  "confidence": 0.96,
  "required_context": ["requirement_id"]
}
```

置信度低或缺少上下文时，只问一个必要问题。

## 9. 对话式用例生成 Skill

```text
用户提出生成目标
→ Skill Router 选择 case_generation
→ Agent 确认来源和范围 [GATE]
→ 读取需求/接口文档和已有用例
→ 生成原子条款和覆盖计划
→ 在 Artifact 区展示覆盖计划 [GATE]
→ 用户确认或修改
→ 生成候选并本地校验
→ 有缺口时局部修正
→ 创建用例集 Artifact
→ 用户勾选并批准保存 [GATE]
```

这里保留实习项目中“先确认范围、再确认策略、最后生成”的优点，但 UI 使用卡片、表格和按钮，不要求用户输入数字选项。

## 10. 造数 Skill 的边界

造数比用例生成风险更高，因为可能修改测试环境。

首期原则：

- 先查询已有测试数据或已有工具；
- 读取操作默认允许；
- 写操作必须展示计划；
- 用户确认后执行；
- 限定测试环境；
- 支持幂等键和清理/回滚说明；
- 保存完整审计事件；
- 不允许模型生成任意 SQL 后直接执行。

首期可先做“造数建议与已有工具选择”，再做真实写入。

## 11. 缺陷描述 Skill

缺陷描述生成不一定需要复杂 Agent loop。

推荐流程：

```text
用户选择失败运行/上传截图/填写现象
→ 工具读取运行日志、请求响应和环境信息
→ Validator 检查必要字段
→ LLM 生成结构化 defect_draft Artifact
→ 用户编辑
→ 用户确认后复制或提交到缺陷系统
```

结构字段：

- 标题；
- 环境；
- 前置条件；
- 复现步骤；
- 实际结果；
- 预期结果；
- 影响范围；
- 附件和证据引用；
- 严重程度建议；
- 待确认信息。

如果只是根据用户已提供的完整信息改写文案，可以走一次 LLM；只有需要主动读取日志和运行证据时才进入 Agent 工具流程。

## 12. LLM Provider 设计

### 12.1 Claude 接入

新增 Anthropic Adapter，通过官方 API/SDK 调用 Claude，不启动 Claude Code CLI。

### 12.2 其他模型

保留现有 OpenAI-compatible Adapter，用于 DeepSeek 等模型。

### 12.3 能力标记

每个模型配置：

- supports_tools
- supports_structured_output
- supports_streaming
- context_window
- max_output_tokens

Skill 可以声明最低能力；不满足时使用程序编排或拒绝运行。

## 13. 首期库选择

### 复用

- FastAPI
- Pydantic
- SQLAlchemy
- MySQL/PyMySQL
- httpx
- pytest
- React / Ant Design

### 新增

- Alembic：数据库迁移
- anthropic：Claude Provider Adapter（只有启用 Claude 时安装）

### 暂不新增

- LangChain / LangGraph
- Pydantic AI
- OpenAI Agents SDK
- Celery / Redis
- 向量数据库

首期重点是实现可测试的 Session、Skill、Tool、Artifact 和 Approval，而不是堆 Agent 框架。

## 14. 分阶段落地

### V2.1-A：对话 Agent Shell

- AgentDefinition
- AgentSession / Message / Event
- Chat UI
- Skill Registry
- Tool Registry
- Artifact 容器
- Approval 事件
- Claude/OpenAI-compatible Provider Adapter

只接一个演示 Skill 和一个只读 Tool，验证闭环。

### V2.1-B：用例生成 Skill

- 需求/接口文档上下文
- 范围 GATE
- 覆盖计划 GATE
- 候选生成和校验
- 覆盖矩阵 Artifact
- 用例集 Artifact
- 人工保存

### V2.2：根因分析 Skill

- 冻结运行证据
- RCA 工具
- 根因报告 Artifact
- 对话追问和证据说明

### V2.3：测试流程扩展和优化

- 造数 Skill
- 缺陷描述 Skill
- 安全、可观测性和 Eval
- 更好的流式事件和恢复

### V2.4：根据真实数据决定

## 15. 安全边界

- Skill 和 Tool 必须版本化并经过审核。
- 仓库或上传的 Skill 属于信任边界，不能自动加载未知来源。
- 所有业务 Tool 在服务端鉴权。
- Secret 不进入 Prompt、Message、Event 和 Artifact。
- 写工具默认 always_ask。
- 工具参数通过 Pydantic 校验。
- 生产环境禁止造数和主动测试。
- Agent 不能自行扩大项目、环境和数据范围。

## 16. 当前决策

| 决策 | 结果 |
|---|---|
| 是否直接内嵌 Claude Code CLI | 否 |
| 是否可以使用 Claude | 可以，作为 Provider Adapter |
| 是否使用 Claude Agent SDK/Managed Agents | 可做独立原型，暂不作为核心 Runtime |
| TestMind 产品形态 | 对话式测试 Agent + 结构化 Artifact 工作区 |
| Agent 类型 | 单 Agent + Skills + 白名单工具 + GATE |
| 首个业务 Skill | 用例生成 |
| 后续 Skills | 根因分析、造数、缺陷描述 |
| 首期是否使用通用 Agent 框架 | 否 |

## 17. 参考

- Claude Managed Agents 的 Agent 配置包含 model、system、tools、MCP 和 skills：<https://platform.claude.com/docs/en/managed-agents/agent-setup>
- Claude Agent SDK 运行在自有进程，Managed Agents 运行在 Anthropic 基础设施：<https://platform.claude.com/docs/en/managed-agents/migration>
- Claude Tool Use 由模型请求工具、应用执行并返回结果：<https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works>
- Claude Managed Agents 支持版本化 Skills，并提示仓库 Skill 属于信任边界：<https://platform.claude.com/docs/en/managed-agents/skills>

## 18. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-01 | v0.1 | 基于实习项目关键模式与 Claude 官方能力确定 TestMind 对话式测试 Agent 架构 |
| 2026-09-02 | v0.2 | V2.1-T04A 实施后回填：第 6 节核心对象已落库/落地（数据模型 + Runtime + Registry + 平台 Service），并记录并发/恢复尚未实现的边界 |
| 2026-09-02 | v0.3 | V2.1-T04B 实施后回填：单 Worker 执行链路（原子抢占/heartbeat/stale 恢复/CLI）已实现，多 Worker 高并发优化不在首期 |
| 2026-09-02 | v0.4 | V2.1-T06 实施后回填：第 9 节对话式用例生成 Skill 已实现（三 GATE + 修正循环 + 双 Artifact + 保存审批 GATE），保存动作与 API 留 T07 |
| 2026-09-02 | v0.5 | V2.1-T07 实施后回填：平台 API 已实现（会话/消息/事件/Run/审批/Artifact/保存），GATE 批准后交回 Worker（waiting_approval→queued），保存单事务与幂等 |

