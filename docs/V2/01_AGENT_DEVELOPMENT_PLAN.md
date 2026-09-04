# V2 开发主计划：对话式 Test Agent 与可持续测试资产

> 生效：2026-09-03（Pi 架构 Python 实现路线）。2026-09-04 修正：P05 起按 [方向 ADR](11_V2_DIRECTION_ADR.md)，不再采用“V2 只做通用 Agent 基础、测试能力全部归入 V3”的旧边界；改为在 V2 内完成“可持续编辑 Test Artifact”的纵向闭环。
> 状态：V2-P01～P04 已通过各自范围的 Codex 验收；P05（Conversation Runtime 收敛 + Legacy Workflow 退役）起按新路线实施，尚未开始。
> 路线：V1 既有平台 → V2 对话式 Test Agent（Agent Core + 持续对话 + Test Artifact + Artifact Editing Tools + Revision/Diff/Undo + Chat/MindMap/Diff 工作台）→ V3 更高级测试能力（API 测试 / RCA / 造数 / 缺陷 / 执行）。
> P05～P10 详细里程碑与任务书以 [12_POST_P04_DEVELOPMENT_PLAN.md](12_POST_P04_DEVELOPMENT_PLAN.md) 为准，本文件只保留阶段定位与既有 P01～P04 记录。
> 本文件替代旧 V2.1/V2.2/V2.3 任务路线，不代表 Pi 全功能复刻或官方 Python 移植。

## 0. Claude Code 执行协议

1. 首次接手阅读总项目记录、主计划、架构、源码对照、开发记录和验收清单；后续按当前阶段提示词读取必要章节与实际源码，不每次重复全量阅读。
2. 最新协作方式：一次交付一个完整 V2-Pxx 阶段，阶段内实现、必要修正、针对性测试和记录连续完成，不再逐小步交接。先核验源码并简短说明范围，然后直接实施；完成指定阶段后停止，不自动跨到下一阶段。
3. 文档只是开发计划，不授权立刻实施全部任务。新增依赖、真实模型费用/数据出站、真实数据库变更及破坏性操作单独确认。
4. 保留用户/其他 AI 的未提交修改。不得 reset/checkout/restore 覆盖，不启动或停止用户正在运行的服务。
5. 阶段交付必须编写并运行新增/直接相关测试，必要修正在阶段内完成。旧小步“不写不跑测试”限制只描述历史任务，不适用于当前阶段收尾。未测试不算验收；P01 验证后才接 P02；P10 才组织版本级回归。
6. 不能用改测试期望掩盖行为退化；不能把旧版测试数当成新 V2 的验收结果。
7. Python 代码写在 TestMind；D:\pi 仅作源码参考，不作为运行依赖，不安装/执行 Pi，不复制其 Node.js 环境。
8. 旧 V2.1-Txx 提示词已归档，不再作为当前开发指令。固定 case_generation Workflow 不作为新 Agent 的执行主链（退役计划见 [16_LEGACY_WORKFLOW_MIGRATION_PLAN.md](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)）；基础测试设计与用例协作编辑属于 V2，API 测试、根因分析、造数、缺陷辅助等更高级测试领域归 V3。
9. 协作顺序：Codex 先读固定 Pi 源码 → 生成阶段提示词 → Claude 完成实现/针对性测试/记录 → Codex 复审。只有用户明确要求“整理笔记”时才更新 D:\TestAgent node 或生成知识点，不随完成报告自动整理。用户理解、代码完成、测试结果分别记录。
10. 最新设计原则：严格沿用 Pi 固定源码的对象关系、职责和调用顺序，实施选定范围的 Python 翻译与轻适配，不额外设计替代内核。轻适配限于语言/类型系统、现有 Python Web/存储边界和用户明确要求的预算/权限/审批；差异记录依据。一次交付一个相关功能组合，测试仍在阶段末进行。
11. 学习笔记按阶段组织：每个阶段一个文件夹，该阶段全部知识点写在一份《学习笔记.md》。文档内按原子知识点分小节，用短解释、关键源码和例子说明；不再逐知识点建文件。用户要求提前补笔记时可先整理，但明确标注待修与未验证内容。
12. 后续阶段提示词更详细具体：写清实际源码事实、允许文件/模块、实施先后、关键函数/字段合同、默认值/未知值、正常与异常分支、正反测试输入及预期、实际命令、完成报告和停止边界。必要时给短伪代码；不要只说“参考 Pi 自行实现”，也不为细化指令扩展阶段范围。

## 1. V2 交付定义

V2 交付一台可持续对话、并围绕 Test Artifact 持续协作编辑的 Test Agent（见 [11_V2_DIRECTION_ADR.md](11_V2_DIRECTION_ADR.md)）。登录后用户可与 Agent 连续对话，创建或打开测试 Artifact；Agent 根据当前用户意图自主决定直接回复、读取资料、加载 Skill 或调用 Artifact 工具。测试设计不存在强制固定路径：用户可以先生成测试点、直接补用例、修改现有用例、检查覆盖或局部重构。所有测试资产修改以增量 Operation 产生 Revision 和 Diff，并实时反映到脑图工作区。

P10 完成后，用户应能在浏览器中完成“创建/打开 Artifact → 持续聊天 → AI 动态调用 Tool 修改 Artifact → 脑图实时展示 → 查看 Diff → 继续修改/撤销 → 刷新恢复”的完整闭环（E2E 故事见 [12](12_POST_P04_DEVELOPMENT_PLAN.md#8-v2-p10--contextapprovalrecovery-与完整验收)）。

V2 必须具备：
- user / assistant / tool 多轮消息和可重建上下文；登录后无项目即可开始；
- 文本、工具调用及流式事件的统一模型合同；
- 有界 Agent Loop、参数校验、权限门禁和工具结果反馈；
- 会话持久化、独立执行、流式 UI、取消、有限恢复；
- Test Artifact 一等业务对象：Case Tree / Node / Revision / Operation / Diff / Undo / 乐观锁（[13](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md)）；
- Artifact 读写 Tool 与 Tool Policy：Approval 绑定动作风险，而不是固定 Workflow gate（[14](14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL.md)）；
- 受控 Skill 发现/按需加载（Skill = 领域知识 + 行为规则，不是 phase 状态机），以及上下文整理/压缩；
- Chat + MindMap + Diff 工作台，AI 与人工修改同一 Artifact（[15](15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md)）；
- 启动预检、可观察诊断、故障测试和版本门禁。

不是 V2：
- 把固定 case_generation Workflow 重新作为新 Agent 的执行主链；确定性能力迁移为 Tool/Service，流程编排退役（[11](11_V2_DIRECTION_ADR.md) / [16](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)）；
- 把 AgentArtifact 当作长期编辑的 TestArtifact；前者保留为执行产物/历史兼容（[13 §10](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md#10-与现有-agentartifact-的关系)）；
- API 测试执行、失败根因分析、测试造数、缺陷辅助等更高级测试领域（归 V3，复用同一 Conversation + Agent Loop + Tools + Artifact 模型，不再各建 Workflow Runtime）；
- 任意 Shell/SQL/URL/宿主文件工具、自动下载扩展、npm 插件体系、TUI；
- 完整复刻 Pi 的会话树、分支、多模态、OAuth 登录、全部 Provider、多 Agent。

## 2. 源码基线与复用决策

Pi 仓库已克隆到 D:\pi：
- origin：https://github.com/earendil-works/pi.git
- 参考提交：f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6（2026-09-03）。
- 不跟随 main 自动更新；开发前使用 git show <参考提交>:<路径>，不要为了看旧文件修改仓库分支。
- 精确文件、符号、测试与 Python 对应见 [源码对照](10_PI_SOURCE_AUDIT.md)。
- 复用架构思想；若翻译上游实现，记录源文件/commit 并保留 MIT 版权许可，不能宣称完全原创。

TestMind 已有但不等于完整对话内核：
- Gateway 有 text/json/pydantic 和 tool_calls 数据合同，目前主要是同步 complete；
- Runner 是按 next_step/execute_step 推进的用例 Workflow，并非自由对话循环；
- Session、Run、Message、Step、Event 等可复用，但项目外键非空、消息 max+1 序号、步骤边界心跳需要调整；
- 前端每次发送固定创建 case_generation Run，必须替换为独立会话 turn 入口；
- 旧业务代码和测试保留，不在本轮删除或“重新标记成未实现”。

## 3. 实施顺序与里程碑

| 任务 | 交付 | 依赖 | 状态 |
|---|---|---|---|
| V2-R01 | Agent / LLM 模块目录整理（结构，先行） | 无 | 已完成（2026-09-03，见 02 记录 2.1） |
| V2-P01 | 源码行为基线、消息/事件/工具合同 | V2-R01 | 阶段验收通过，见 P01_ACCEPTANCE.md |
| V2-P02 | 文本 + 工具调用 + 流式模型适配 | P01 | 阶段验收通过，见 V2-P02_ACCEPTANCE.md |
| V2-P03 | 纯 Python Agent Loop 与执行器 | P01、P02 | 阶段验收通过，见 V2-P03_ACCEPTANCE.md |
| V2-P04 | 无项目会话、Turn 持久化、并发/幂等迁移 | P01、P03 | 阶段验收通过，见 V2-P04_ACCEPTANCE.md |
| V2-P05 | Conversation Runtime 收敛：Worker/租约/取消/队列，Workflow 退役 | P03、P04 | 待实施 |
| V2-P06 | Conversation API + SSE + 基础持续聊天工作台 | P02、P04、P05 | 待实施 |
| V2-P07 | Test Artifact Core：Case Tree / Node / Revision / Operation / Diff / Undo / 乐观锁 | P04、P06 | 待实施 |
| V2-P08 | Artifact Tools + Test Design Skill：read/add/update/delete/move/validate/coverage | P07 | 待实施 |
| V2-P09 | Chat + MindMap + Diff 协作工作台 | P06、P07、P08 | 待实施 |
| V2-P10 | Context / Compaction / Approval / Conflict / Recovery / E2E | P05～P09 | 待实施 |

里程碑 A：P03 后，Fake 模型能多轮聊天并调用无副作用工具（已完成）。
里程碑 B：P06 后，浏览器能持续聊天、流式展示、刷新恢复，不需要任何测试文档。
里程碑 C：P10 后，V2 的对话式 Test Artifact 闭环通过真实 E2E 验收；届时 V3 开始接入 API 测试等更高级测试能力。
里程碑不是版本完成状态，不承诺未验证工期。

### 代码目录（V2-R01 结构整理后，当前后端事实）

分层保留 routers / schemas / services / models，内部按 Agent、LLM 归类：

~~~text
backend/app/models/    agent/{agent_session,agent_message,agent_run,agent_step,agent_event,agent_artifact,agent_approval}.py
                       llm/{llm_provider,llm_model,llm_scene_config}.py
backend/app/services/  agent/{agent_session_service,agent_run_service,agent_artifact_service,agent_approval_service}.py
                       llm/{llm_config_service,llm_client_service,llm_gateway}.py
                       agent_save_service.py（保留根：候选保存业务）
backend/app/schemas/   agent/{api,platform}.py   llm/{llm_config,llm_gateway}.py
backend/app/routers/   agent/agent_router.py  llm/llm_config_router.py
backend/app/agents/    执行内核（Runtime/Registry/工具）与既有 case_generation Workflow 资源，未移动
~~~

注意：`services/agent` 是平台应用服务；`agents/` 是执行内核；目录分组是结构整理，不等于依赖已解耦。

## 4. 任务实施卡

### V2-P01 — 行为基线与合同

执行节奏：P01 已验收，证据见 [P01 验收记录](reviews/V2-P01_ACCEPTANCE.md)。阶段收尾及修正提示词保留历史，不再重复派发；下一阶段是 P02，按新的详细任务书接续。

参考：Pi agent/src/types.ts、ai/src/types.ts、agent-loop.test.ts、agent.test.ts。

新增建议：
- backend/app/agents/conversation/contracts.py、messages.py、events.py
- backend/tests/conversation/test_contracts.py、fixtures/（合成模型响应）
- docs/V2/10_PI_SOURCE_AUDIT.md 的实施映射及第三方来源记录

内容：
- 定义 ConversationTurn（一条用户请求）、ModelTurn（一次模型推理）、ToolCall/ToolResult，避免与旧 Skill Run 混淆；
- 核心消息结构直接对齐 Pi 的 UserMessage / AssistantMessage / ToolResultMessage 联合；文本与 ToolCall 是内容块，工具反馈是独立消息，通过 tool_call_id 关联，不能包装成系统消息。应用层稳定 ID 和版本是轻适配；Provider 边界再映射到旧 tool 角色；
- 事件含 session_id、run_id、message_id、tool_call_id、sequence_no、schema_version，按事件类型约束必填字段；
- 明确模型结束原因、空结果、截断、错误、取消、预算的区别；
- 数据类型与纯函数不依赖数据库连接，不触发 create_all 或 import-time 建库。

验收：文本/混合工具内容往返；未知事件拒绝；截断参数不执行；不把普通字符串作为用例 JSON 解析。
不做：业务工具、网络调用、数据库迁移。

### V2-P02 — 统一流式 Provider 边界

P02 已按 [集中续做提示词](prompts/V2-P02_CONTINUATION_CLAUDE_PROMPT.md)完成修正，并通过 [阶段验收](reviews/V2-P02_ACCEPTANCE.md)。历史 [原任务书](prompts/V2-P02_STREAMING_PROVIDERS_CLAUDE_PROMPT.md)与 [首次审查](reviews/V2-P02_PARTIAL_REVIEW.md)保留。Fake 流式套件 54 项、P01 回归 90 项、旧 Provider/Gateway 回归 55 项分别通过；真实供应商验证留 P10。下一阶段为 P03，尚未实施。

参考：Pi ai/src/types.ts、agent-loop.ts 的 streamAssistantResponse。

修改范围：现有 llm_gateway.py、schemas/llm_gateway.py、agents/providers/；新增流式专用模块及测试。保留旧 complete 和旧 wrapper 合同。

内容：
- 用 asyncio / httpx.AsyncClient 或 SDK 的实际异步接口扩展流式调用；不要在 FastAPI 事件循环中直接调用同步 SDK；
- 首期实现现有 OpenAI-compatible、Anthropic 两类适配，按真实版本核验协议，不增加第三套模型接入；
- text_delta、tool_call_delta、message_end、usage、finish_reason、request_id 归一化；
- 工具参数分片只缓存，完整消息到达且未截断、参数校验通过后才能执行；
- 文本模式不要求 JSON；只有显式结构化产物使用 response_model；
- 空 content + 完整工具调用合法；空内容/仅推理内容/length 截断/拒绝/网络断流分别诊断；
- 重试集中在一层并受本次 Run 预算约束；部分文本已发出或工具可能已执行时不透明重放；
- 能力三态保留：已确认不支持 tools 则不发送；未知可受控尝试并明确失败，不声称兼容。

验收：Fake 流分片、工具参数交错、空内容但有工具、length/断流、取消关闭连接、两 Adapter 合同；每次物理模型尝试计数，token 未知记未知而非 0。
不调用真实模型，不改当前配置记录。

### V2-P03 — Agent Loop 与通用工具执行

状态：已在纯 Python/Fake 范围验收通过，见 [P03 验收记录](reviews/V2-P03_ACCEPTANCE.md)。实现位于 conversation/{loop,tool_executor,budget,policy}.py；P02 Fake HTTP 集成链证明工具结果进入第二次模型请求。P04 持久化尚未开始。

参考：Pi agent.ts、agent-loop.ts（runLoop/prepareToolCall/executePreparedToolCall）。

新增：conversation/loop.py、tool_executor.py、policy.py、budget.py，测试同目录映射。

内容：
- 核心只接收消息、Provider、Tool Registry、事件接收器及停止信号，不依赖 ORM；
- 每轮按“上下文整理 → 模型 → 完整助手消息 → 工具校验/权限 → 工具结果 → 下一轮”执行；
- 默认串行工具，预留只读并行接口；不得并发共享 SQLAlchemy Session；
- 先用内存 calculator（Decimal，不使用 eval）/echo 等通用测试夹具验证，不查项目业务数据；
- 未知工具/参数错误作为明确工具失败反馈给模型；基础设施失败/预算耗尽则结束本 Turn；
- 补 max_model_calls、max_tool_calls、max_turns、wall_clock_deadline，防模型重复调用同一工具失控；
- 工具结果按原调用顺序写入，tool_call_id 一一对应；工具可返回通用停止/等待信号；
- 钩子修改参数后在 TestMind 中重新校验（与 Pi 的相关测试行为有意不同）。

验收：普通聊天 0 工具；工具→回复；多步工具；恶意/未知工具；失败后有限修正；截断工具绝不执行；超限与取消；结果完成后的迟到事件被丢弃。
不把每条消息硬编码路由到 case_generation；也不靠关键词 if/else 假装 Agent 决策。

### V2-P04 — 会话持久化与迁移

状态：已在临时 SQLite/真实 ORM 事务范围验收通过，见 [P04 验收记录](reviews/V2-P04_ACCEPTANCE.md)。conversation Run 当前保持 queued，旧 Worker 不会误抢；P05 统一分发与租约尚未开始。

参考：Pi SessionManager/buildSessionContext 的重建语义；不照搬本地 JSONL 为产品唯一存储。

范围：AgentSession/Run/Message/Event、相关 Schema/Service、增量 Alembic、SQLite 外键开启测试。

设计：
- 会话新增 mode=conversation/legacy_workflow；既有记录默认 legacy_workflow；
- conversation Session/Run 的 project_id 允许 NULL；旧生成入口仍由服务端强制项目与来源校验；
- 不创造 project_id=0 或占位项目，不改变 V1 业务表归属；
- Run 复用为一次 ConversationTurn，workflow_code=conversation，和旧 case_generation 明确分流；
- messages.content_json 存版本化内容块，模型工具消息必须完整保存并重建；既有文本消息仍可读；
- 用户消息 + queued Run + 幂等键同事务；相同键同内容返回原 Run，不同内容 409；
- 同一会话序号分配/活跃 Turn 串行化必须有数据库约束或锁，不能沿用 max+1 裸写；
- 项目为空时只可通用聊天与无项目工具，身份从登录态取得，不能信任模型传入 user_id/project_id；
- 新旧入口都按会话 mode 校验：旧 /agent/runs/{id} 等通用查询不能绕过 conversation 的 owner 隔离；旧生成接口不得把无项目 conversation Session 当合法业务会话；
- 明确增量 revision 的真实 next id，不能假定库仍停在 0002；
- 降级若已有 NULL 项目等新数据，必须预检后拒绝或提供无损处理方案，不自动删会话凑旧约束。

验收：无项目聊天、旧会话兼容、owner 隔离、双连接并发、重试幂等、消息恢复、失败事务回滚、临时库 migration upgrade/downgrade。
真实 MySQL 只在 P10 明确授权测试库验证。注意 database.py 导入当前可能执行建库，不能把导入当作只读检查。

### V2-P05 ～ V2-P10（2026-09-04 新路线，任务书见 12）

> P05～P10 的详细范围、目录、验收一律以 [12_POST_P04_DEVELOPMENT_PLAN.md](12_POST_P04_DEVELOPMENT_PLAN.md) 为准；Legacy Workflow 退役步骤见 [16_LEGACY_WORKFLOW_MIGRATION_PLAN.md](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)。本小节只保留阶段定位与实施边界，不再展开旧 P05～P10 任务卡，避免新旧两套路线并存。原“P07 通用 Skill 加载 / P08 上下文压缩 / P09 人工门禁”等旧规划不再作为本阶段标题。

#### V2-P05 — Conversation Runtime 收敛 + Legacy Workflow 退役

起点现状（2026-09-04 源码审计，供实施对账）：
- `agents/conversation/` 已有 contracts/messages/events/loop/tool_executor/policy/budget/tool_validation，纯 Python/Fake 范围验收过，但没有任何 Worker/Router/Service 在生产调用 `run_agent_loop`；当前**不存在 ConversationRunner**；
- `conversation_service` 能持久化 conversation Turn 为 queued Run，但 Worker claim 查询目前按 `workflow_code != "conversation"` 主动跳过，这些 Run 停在 queued；
- 真正被接入的仍是旧执行核：`agents/runtime/runner.py` 的 AgentRunner + `agents/skills/case_generation/`（next_step / execute_step、phase/gate），由 `agent_worker` CLI 与 `/agent/runs/case-generation` 路由驱动，逐 step 写 AgentStep/Event/Artifact/Approval；会话 `mode=legacy_workflow`；
- `agent_artifact` 是整棵 JSON payload + 整数 version 的浅版本（update_payload 原地覆盖），没有 Revision/Diff/Undo，也不存在 TestArtifact/ArtifactNode/ArtifactRevision/artifact_operation；
- 前端 test-agent 悬浮台仍“每次发送都无条件创建 case_generation Run”，无 conversation 入口、无脑图/Diff 视图；
- Alembic 已有 0002（agent 平台表）/ 0003（conversation 持久化：mode、project_id 可空、序号游标、active_slot）。

实施要点：
1. 先按 [16 §4 Step 1](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md#4-p05-执行步骤) 做 Dependency Audit（CaseGenerationWorkflow / AgentRunner / workflow_code / case_generation / legacy_workflow / next_step / execute_step），列 API / Worker / 前端 / tests / DB 历史行的调用方，审计前不物理删除；
2. 新增 ConversationRunner：从 Repository 重建 Context → 构造 RuntimeContext → `run_agent_loop()` → 持久化最终 Message/Event/Run status；不自行决定测试业务步骤；
3. Worker 主分发只服务新 Conversation 主路径；旧 case_generation 迁到 `legacy/` 兼容区或确认无调用后删除；禁止新 Artifact Tool 内部整链调用 CaseGenerationWorkflow；
4. 复用 Worker 现有 lease/heartbeat/fencing/claim 资产，补齐 conversation 取消、follow_up、同会话单活跃 Turn。

验收见 [12 §3](12_POST_P04_DEVELOPMENT_PLAN.md#3-v2-p05--conversation-runtime-收敛与-workflow-退役)：Fake Provider 经 Worker 连续 3 Turn、长调用 heartbeat 不丢 lease、cancel 终止当前 Turn、follow-up 保序、新对话不引用 case_generation、Workflow 隔离/删除后 P01～P04 回归通过。

#### V2-P06 — Conversation API、SSE 与基础持续聊天工作台

新增 conversation_router / conversation_service 的对话入口：`POST /agent/conversations`、`POST /agent/conversations/{id}/turns`、messages、events(SSE)、cancel 等；浏览器真正持续聊天、流式、刷新恢复；前端“发送”改为提交 Turn，不再先 appendMessage 再无条件 createCaseRun；Artifact 聚焦端点（`.../artifacts/{id}/focus`）首期可延到 P07。详细 API 建议与 UI 首期、验收见 [12 §4](12_POST_P04_DEVELOPMENT_PLAN.md#4-v2-p06--conversation-apisse-与基础工作台)。

#### V2-P07 — Test Artifact Core

TestArtifact 提升为 V2 一等业务对象（取代“一次 Run 生成整棵用例 JSON”）：ArtifactNode 树（root/group/test_point/test_case）、ArtifactRevision、ArtifactOperation（add/update/delete/move/restore）、结构化 Diff、Undo、`expected_revision` 乐观并发。脑图只是视图不是底层存储；Agent 与人工写操作必须走同一 Artifact Application Service。AgentArtifact 保留为执行产物/兼容，不作为长期编辑对象。数据模型与最小验收见 [13_TEST_ARTIFACT_CASE_TREE_DESIGN.md](13_TEST_ARTIFACT_CASE_TREE_DESIGN.md) 与 [12 §5](12_POST_P04_DEVELOPMENT_PLAN.md#5-v2-p07--test-artifact-core)。

#### V2-P08 — Artifact Tools 与 Test Design Skill

Agent 改为动态调用 Tool 修改 Artifact，而不是 Workflow 固定顺序：read（get_current_artifact / read_artifact_outline / read_artifact_nodes / search_artifact / get_artifact_diff / read_requirement）、write（add/update/delete/move/batch_apply_artifact_operations）、quality（validate_test_artifact / find_duplicate_cases / analyze_test_coverage —— 是能力、不是必经流程）。所有写 Tool 遵守 Tool Contract：身份由 RuntimeContext 注入、携带 `expected_revision`、返回 applied revision + machine-readable diff、写 audit、遵守 Tool Policy。Skill 改为领域知识 + 行为规则（skills/test-design/SKILL.md），不含固定 phase；通用 Skill 加载/注入基础若前序阶段未落地，随本阶段一并提供。工具合同、行为规则与 8 类对话验收见 [14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL.md](14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL.md) 与 [12 §6](12_POST_P04_DEVELOPMENT_PLAN.md#6-v2-p08--artifact-tools-与-test-design-skill)。

#### V2-P09 — Chat + MindMap + Diff 协作工作台

实现“一边对话、一边看到 AI 对 Artifact 的实际修改”：Chat / MindMap / Diff / History / Undo 读取同一 Revision；人工在脑图编辑同样产生 ArtifactOperation 与 Revision；AI 下一轮读取最新版本；大范围删除展示 impact preview 并按动作风险进入 Approval。产品体验与验收见 [15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md](15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md) 与 [12 §7](12_POST_P04_DEVELOPMENT_PLAN.md#7-v2-p09--chat--mindmap--diff-协作工作台)。

#### V2-P10 — Context / Compaction / Approval / Recovery / E2E

把闭环加固成可长期工作的 Agent：模型每轮不整棵塞入 Artifact（元数据 + 相关节点 + 最近 Diff，不足再 read/search/compaction）；原始历史保留、摘要不删除历史；Approval 由固定 gate 改为按 Action Risk 的 Tool Policy（read→allow、add/update 小批量→allow、批量删除/覆盖→approval、写正式项目→approval）；恢复与故障注入覆盖 Provider 断流 / Worker 崩溃 / Revision 冲突 / Tool timeout / Approval 后恢复 / Cancel / SSE 重连 / Artifact 已写入但 final response 失败等，任何情况下不得把“聊天失败”误报成“Artifact 写入被回滚”；最后按 [12 §8 E2E 故事](12_POST_P04_DEVELOPMENT_PLAN.md#8-v2-p10--contextapprovalrecovery-与完整验收) 组织真实闭环验收，并完成真实 MySQL + 小额真实模型验证与可重复启动、受影响旧功能回归。真实环境项仍按授权执行。

## 5. 技术选型与实现约束

- Python / FastAPI / SQLAlchemy / MySQL / Pydantic / pytest 沿用现有栈，前端 React 沿用。
- asyncio 做模型流和内核协作；同步 SQLAlchemy 通过短事务 Repository 使用，不跨任务共享 Session；线程桥接必须每次自建/关闭 Session。
- V2 不引入 Pi npm、Node 后端、LangChain/LangGraph、Redis/Celery。先实现需要的机制，不一次堆所有框架。
- 不给所有消息强加 JSON；工具参数和需被程序消费的结构才严格校验。
- 单次最大输出和模型上下文配置不能写死覆盖用户设置；模型返回不足时保留安全诊断。
- 本计划任务涉及未来迁移和配置，但这次文档调整没有执行它们。

## 6. 跨版本交接

| 旧计划事项 | 新去向 | 当前处理 |
|---|---|---|
| 旧 T01～T04 Gateway/模型/Worker | V2 复用输入 | 审计并补缺口，不重复搭同名基础设施 |
| 旧 case_generation Workflow（AgentRunner / next_step / execute_step / phase/gate） | V2-P05 退役或隔离 | 按 [16](16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)：A 类确定性能力（load_requirement/validate/deduplicate/coverage/save 等）→ Tool / Domain Service（P07/P08），B 类测试方法 → skills/test-design（P08），C 类编排 → 删除 |
| 旧 T05～T08 用例工具与审批 UI | 能力并入 V2 | Tool/Service 复用；不再作为独立 V3.1 桥接任务 |
| 旧 T09 用例影子评测 | V2 test-design Skill 质量门禁（P08/P10） | 基础用例/测试点生成现在是 V2 纵向闭环的验收内容 |
| 旧 V2.2 根因分析 | V3.2 Failure RCA | 复用 Conversation + Agent Loop + Tools + Artifact |
| 旧 V2.3 测试数据、缺陷描述 | V3.3 Test Data / V3.4 Defect | 复用同上 |
| 通用安全、会话隔离、预算 | V2 必须 | 不因业务后移而延期 |
| API 测试执行、CI 集成等 | V3.1 / V3.5 等高级测试能力 | V2-P10 后按新 V3 路线规划 |

旧记录和提示词见 [归档说明](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，V2-P05～P10 新路线见 [12_POST_P04_DEVELOPMENT_PLAN.md](12_POST_P04_DEVELOPMENT_PLAN.md)，更高级测试能力路线见 [V3 主计划](../V3/01_TEST_CAPABILITY_PLAN.md)。
