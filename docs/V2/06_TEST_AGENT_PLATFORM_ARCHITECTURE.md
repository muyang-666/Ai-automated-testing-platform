# V2 对话式 Test Agent 平台架构

> 生效：2026-09-03（Pi 架构 Python 实现）。2026-09-04 调整：P05 起的主执行链从“Conversation → 旧 Workflow Runner”收敛为“Conversation → ConversationRunner → Agent Loop → Tool Executor → Artifact Tools → TestArtifact Domain”，固定 case_generation Workflow 退役为 legacy / compatibility path。
> Pi 参考提交及源码证据见 [10_PI_SOURCE_AUDIT.md](10_PI_SOURCE_AUDIT.md)。本节“设计/目标”部分是拟实现蓝图；“现状”段是源码事实。

## 0. 核心原则与执行主链

> Model controls sequence. Program controls capability and safety. Artifact stores the evolving result.

```text
User
  ↓
Conversation（Session / Message / Context / Turn）
  ↓
ConversationRunner（重建 Context → RuntimeContext → run_agent_loop → 持久化）
  ↓
Agent Loop（模型决定下一步）
  ↓
Tool Executor（校验 / 权限 / Policy / Approval / Budget / Cancel）
  ↓
Artifact Tools（read / search / add / update / delete / move / validate / coverage）
  ↓
TestArtifact Domain（Node / Revision / Operation / Diff / Undo / 乐观锁）
  ↓
ToolResult → Agent Loop 继续
```

Legacy Workflow（AgentRunner + case_generation）不再作为新 V2 Agent 的主执行链，只作为 legacy / compatibility path 单独画在旁路：

```text
Legacy API（/agent/runs/case-generation）→ Legacy Runner → CaseGenerationWorkflow
（mode=legacy_workflow；P05 审计后隔离或删除，见 16）
```

## 1. 组件边界

~~~text
React 工作台（Chat | MindMap | Diff | History | Undo）
  │ HTTP + 鉴权 SSE
FastAPI Conversation API（身份、预检、Turn 持久化、事件转发）
  │
MySQL Repository：Session / Message / Run / Event
                 TestArtifact / ArtifactNode / ArtifactRevision / ArtifactOperation
  │
独立 Agent Worker（一个入口、按类型分发）
  ├─ ConversationRunner → 纯 Python Agent Loop（run_agent_loop）
  │     ├─ LLM Gateway → Provider
  │     ├─ Context / Compaction（P10）
  │     ├─ Skill Catalog / load_skill（领域知识，P08 起 test-design）
  │     └─ Tool Executor → Tool Policy / Approval
  │           └─ Artifact Tools → TestArtifact Application Service
  └─ [legacy] Legacy Runner —— 只服务旧 /agent/runs/case-generation 入口（P05 处理）
~~~

模型决定回复还是请求工具，程序决定是否允许执行。Tool 不直接调用 UI；Provider 不读取业务数据库；内核不持有 ORM Session；Markdown Skill 不获得宿主执行权限。Agent 使用 Artifact；Artifact Domain 不依赖 Agent。

## 2. 职责分层

### Agent Core
Message / Provider / Context / Agent Loop / ToolCall / ToolResult / Policy / Budget / Cancel。

### Artifact Domain（业务领域，独立于 agents/）
TestArtifact / ArtifactNode / Revision / Operation / Diff / Undo / SourceRef / 项目与 owner 边界 / 乐观并发。所有写操作要求 `expected_revision`，成功后推进 Revision 并产生结构化 Diff。

### Tools（模型动作的统一门禁）
Artifact 读写 / 需求读取 / 质量诊断（validate / deduplicate / coverage）。Tool 是模型能力的边界：LLM 只能提出 ToolCall，执行与否由系统裁决。

### Skill
领域知识 + 行为规则（例如 test-design：怎么提炼测试点、补边界、增量编辑、不要无理由重写整棵树）。Skill 横向影响 Agent 行为，**不控制循环顺序**，不是固定 phase 状态机。

### UI
Chat / MindMap / Diff / History / Undo / Approval。Chat 与视图来自同一 Revision。

## 3. Session / ConversationTurn / ModelTurn / TestArtifact

- Session（Conversation）：持续会话，独立历史、owner、可选项目、当前工作 Artifact；一次失败后仍可聊天。
- ConversationTurn：一次用户输入及其处理过程，复用 AgentRun（workflow_code=conversation）；预算与取消围绕它。
- ModelTurn：该处理过程中的一次模型调用，可能返回文本和多个工具调用。
- ToolCall / ToolResult：有 call_id 的具体动作与模型可消费结果，不是直接拼成 system。
- TestArtifact：长期存在、持续编辑的测试资产（类似代码仓库/文档），用户与 Agent 共同修改；产生 Revision / Diff / Undo。
- Skill：何时/如何完成某类任务的领域知识 + 行为规则，不等于固定 Workflow。
- Workflow：不再是 V2 Agent Core 的业务控制方式；必要的确定性内部流程只存在于 Tool/Service 内部，不控制整轮 Agent 对话路径。Legacy case_generation 仅作兼容（16）。

不要把 agent_end 解释成整个会话关闭。conversation succeeded 表示本轮回复完成；Artifact 写入成功由 Revision 与业务结果证明，两者解耦。

## 4. 消息、事件、产物三个通道

消息：用户文本、模型助手文本、工具调用与结果；稳定 ID、版本化内容块，角色由服务端确定。
事件：排队/执行/流式增量/工具/Revision 创建/Diff/Approval/压缩/中断/失败，不自动成为模型历史；同会话递增游标。
产物：TestArtifact 是 V2 的一等业务对象（见 [13_TEST_ARTIFACT_CASE_TREE_DESIGN.md](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md)）。AgentArtifact 保留为执行产物/历史兼容（一次 Run 的候选/覆盖快照），但长期测试设计由 TestArtifact + Revision 管理，不再把脑图 JSON 当底层存储。

流式增量只有临时意义：终止时写最终 message 状态；连接断开通过事件游标和消息/Artifact 快照重建。执行已取消、失去租约或 message 已完成时拒绝迟到增量。Artifact 写操作不逐 token 半成品落库：Tool 参数完整 → 校验 → 单事务 → Revision 提交 → 发布 artifact_revision_created。

## 5. 模型接入

复用现有 Gateway 的 text/json/pydantic 与 P02 新增 async stream。保留同步 complete 供旧用例链路使用，直到 legacy 退役。
普通聊天不受用例 Schema 约束。已确认的 tool_call 才解析参数；空文本但有完整工具调用不是空回复。length 截断禁止执行工具。
模型配置是独立问题：新建通用 agent_chat 场景由管理员绑定模型；缺绑定/禁用/不支持时启动前提示；只读诊断返回安全 provider/model/finish_reason/request_id/usage，不输出 Key 与原始敏感数据。重试与摘要计同一成本预算。

## 6. 存储与迁移边界

沿用现有 Agent 表，扩展 conversation 语义与 Artifact 领域：
- agent_sessions.mode：legacy_workflow / conversation；conversation 的 project_id 可空；旧生成接口项目与来源仍必填。
- agent_runs.workflow_code：conversation 与 case_generation 分流；P05 起 Worker 消费 conversation queued Run。
- P07 起新增 TestArtifact / ArtifactNode / ArtifactRevision / ArtifactOperation 领域表（字段以 [13](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md) 为据）；Revision 代表一次逻辑提交，Diff 是其派生结果。
- 请求幂等、同会话单执行者、sequence_no 分配、Worker 抢占、Revision 冲突判断用真实数据库约束/事务，不只靠 Python 全局锁或前端 disabled。
- Session/Run/Event 与 Artifact 读权限先按 owner；绑定项目不自动公开给所有项目读者；旧 /agent/runs/{id} 等路径必须识别 conversation mode。
- 增量 Alembic 保留 V1 表；不把“删除 Python Workflow 类”与“删数据库历史字段”强绑定为同一个提交（16 §5）。

## 7. 执行生命周期

接收 Turn → 预检 → 原子持久化（用户消息 + queued Run + 幂等键）→ Worker 抢占 → running → 每 ModelTurn：Agent Loop 调模型 → 完整助手消息 → Tool 校验/权限/Approval → 执行 Artifact 操作（expected_revision 校验）→ Revision → ToolResult → 下一 ModelTurn → completed / failed / cancelled / interrupted / waiting_approval。

执行器持租约，心跳不依赖模型返回；条件更新带执行代次（fencing token），过期执行器不能覆盖新状态；检查取消读取可信新状态。普通工具异常可回传模型并在预算内处理；不可恢复错误终止当前 Turn，但 Conversation 仍 active。follow_up 是后续消息队列；前项失败/中断先暂停队列。Approval 按动作风险（read→allow、小批量增改→allow、批量删除/覆盖→approval、写正式项目→approval），批准后必须重新校验 revision / 权限 / 参数 hash / lease / cancel。

关键事务不覆盖网络等待：SQLAlchemy 同步调用走短事务 Repository，线程/异步任务间不共享 Session。

## 8. Skill 与工具安全

Skill 是领域知识与行为规则（P08 起提供 test-design），不是 phase 状态机；加载仍受控：审核目录、name/hash/version 注册、资源根限定、防穿越/外链、不自动执行脚本。Skill 不扩大工具权限：可用工具 = 平台允许 ∩ 用户权限 ∩ 本次会话策略。
Tool arguments 用 Pydantic 严格校验；身份/user_id/project_id/owner 从 RuntimeContext 注入，不接受模型声明。写 Artifact Tool 必须：携带 expected_revision、返回 applied revision 与 machine-readable diff、写 audit、遵守 Tool Policy。模型可以申请审批，只有经过身份校验的人类决议能放行；拒绝/过期/参数变化不能自动重试成批准。工具不直接调用 UI；Provider 不读业务库；内核不持有 ORM Session；不展示隐藏 reasoning。

## 9. 上下文与恢复

存储保留全部授权消息与 Artifact Revision；提交模型的工作上下文可裁剪。模型输入每轮不整棵塞入 Artifact：System + Loaded Skills + Conversation Summary + Recent Messages + Artifact 元数据 + 相关节点 + 最近 Diff；需要更多由 Agent 调 read_artifact_nodes / search_artifact。确定性整理先排除 UI-only 事件与过长工具结果，再按完整轮次裁剪，不拆坏工具调用对。摘要带源范围/版本/usage，是派生信息不是系统指令；摘要失败退回安全窗口或 context_limit，不删除历史、不无限压缩。首期线性历史即可。

## 10. 目标目录（P05 起逐步落地，16 §9）

~~~text
backend/app/agents/
  conversation/
    contracts.py messages.py events.py tool_validation.py
    loop.py      tool_executor.py policy.py budget.py
    context.py   runner.py
  providers/   registry/
  skills/test-design/
  tools/artifact/  tools/requirement/  tools/quality/
  legacy/                    # 旧 case_generation 兼容区，P10 前决定去留
backend/app/test_artifacts/  # Artifact 业务领域，不放进 agents/
  models/  schemas/  services/  repository/  diff/
backend/app/services/conversation_service.py  conversation_repository.py
backend/app/routers/conversation_router.py
backend/app/workers/agent_worker.py
backend/tests/conversation/  tests/artifacts/  tests/agent_loop/
frontend/src/components/test-agent/
~~~

不要让 `agents/` 同时承担 Artifact 数据领域本身；Agent 使用 Artifact，Artifact 不依赖 Agent。V2 不添加 Node.js 后端。

## 11. 运行与发布

正式使用仍需前端、FastAPI、独立 Worker 三个服务；P10 提供可复现启动、预检与健康检查。新对话入口用独立 feature flag；旧 /agent/runs/case-generation 入口在 legacy 存活期内保留但不注册到 conversation catalog。
V2 验收覆盖基础 Agent + Test Artifact 协作编辑闭环；API 测试执行、失败根因、造数、缺陷辅助等更高级测试领域属于 [V3](../V3/README.md)，复用同一 Conversation + Agent Loop + Tools + Artifact 模型。

## 12. 现状（2026-09-04 源码审计，供 P05 对账）

- `agents/conversation/`：已有 messages/events/contracts/loop/tool_executor/policy/budget/tool_validation（P01～P03，纯 Python/Fake 验收）；**当前无 ConversationRunner**，生产代码没有任何地方调用 `run_agent_loop`。
- `conversation_service`：P04 持久化 conversation Session/Turn 为 queued Run（workflow_code=conversation）；Worker claim 目前 `workflow_code != "conversation"`，这些 Run 停在 queued —— 正是 P05 要接通的断点。
- Legacy 执行核（真实接入）：`agents/runtime/runner.py` 的 AgentRunner + `agents/skills/case_generation/`（next_step/execute_step、phase/gate），由 agent_worker CLI 与 `/agent/runs/case-generation` 路由驱动，逐 step 写 AgentStep/Event/AgentArtifact/AgentApproval；会话 mode=legacy_workflow。
- `agent_artifact`：整棵 JSON payload + 整数 version 浅版本（update_payload 原地覆盖）；尚无 TestArtifact / ArtifactNode / ArtifactRevision / artifact_operation，无 diff/undo。
- 前端 test-agent 悬浮台：每次发送仍无条件创建 case_generation Run；无 conversation 端点、无脑图/Diff 视图。
- Alembic：0002 agent 平台表；0003 conversation 持久化（mode / project_id 可空 / 序号游标 / active_slot）。

目录分组（V2-R01 结构整理后）：后端保留 routers / schemas / services / models 分层，内部按 Agent、LLM 归类；`services/agent` 是平台应用服务，`agents/` 是执行内核。分组是结构整理，不等于依赖已解耦；上述蓝图需在 V2-Pxx 内逐步落地。
