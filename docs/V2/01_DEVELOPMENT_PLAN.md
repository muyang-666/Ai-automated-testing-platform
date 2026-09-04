# V2 开发主计划（Development Plan）

> 生效：2026-09-03（Pi 架构 Python 实现路线）；2026-09-04 起调整 P05 及之后路线为“对话式 Test Agent + TestArtifact 协作编辑”。方向决策已执行，ADR 原文归档为 archive/V2_DIRECTION_ADR_2026-09-04.md。
> 状态：V2-P01～P04 已通过各自范围的 Codex 验收；P05（Conversation Runtime 收敛 + Legacy Workflow 退役）起尚未实施。
> 本文件是 V2 **唯一开发路线 Source of Truth**：P01～P10 的 Goal / Scope / Key implementation / Acceptance / Stop boundary 全部在此。实现级数据模型与工具合同见 [05_TECHNICAL_DESIGN.md](05_TECHNICAL_DESIGN.md)，产品行为见 [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md)。
> 本文件替代旧 V2.1/V2.2/V2.3 任务路线，不代表 Pi 全功能复刻或官方 Python 移植。

## 0. Claude Code 执行协议

1. 首次接手阅读总项目记录、本开发计划、技术设计（05）、开发记录（02）与验收清单（03）；后续按当前阶段提示词读取必要章节与实际源码，不每次重复全量阅读。Agent Core 相关阶段额外对照 [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)。
2. 最新协作方式：一次交付一个完整 V2-Pxx 阶段，阶段内实现、必要修正、针对性测试和记录连续完成，不再逐小步交接。先核验源码并简短说明范围，然后直接实施；完成指定阶段后停止，不自动跨到下一阶段。
3. 文档只是开发计划，不授权立刻实施全部任务。新增依赖、真实模型费用/数据出站、真实数据库变更及破坏性操作单独确认。
4. 保留用户/其他 AI 的未提交修改。不得 reset/checkout/restore 覆盖，不启动或停止用户正在运行的服务。
5. 阶段交付必须编写并运行新增/直接相关测试，必要修正在阶段内完成。旧小步“不写不跑测试”限制只描述历史任务，不适用于当前阶段收尾。未测试不算验收；P01 验证后才接 P02；P10 才组织版本级回归。
6. 不能用改测试期望掩盖行为退化；不能把旧版测试数当成新 V2 的验收结果。
7. Python 代码写在 TestMind；D:\pi 仅作源码参考，不作为运行依赖，不安装/执行 Pi，不复制其 Node.js 环境。
8. 旧 V2.1-Txx 提示词已归档，不再作为当前开发指令。固定 case_generation Workflow 不作为新 Agent 的执行主链（退役步骤见本文 [V2-P05](#v2-p05--conversation-runtime-收敛--legacy-workflow-退役)）；基础测试设计与用例协作编辑属于 V2，API 测试、根因分析、造数、缺陷辅助等更高级测试领域归 V3。
9. 协作顺序：Codex 先读固定 Pi 源码 → 生成阶段提示词 → Claude 完成实现/针对性测试/记录 → Codex 复审。只有用户明确要求“整理笔记”时才更新 D:\TestAgent node 或生成知识点，不随完成报告自动整理。用户理解、代码完成、测试结果分别记录。
10. 最新设计原则：严格沿用 Pi 固定源码的对象关系、职责和调用顺序，实施选定范围的 Python 翻译与轻适配，不额外设计替代内核。轻适配限于语言/类型系统、现有 Python Web/存储边界和用户明确要求的预算/权限/审批；差异记录依据。一次交付一个相关功能组合，测试仍在阶段末进行。
11. 学习笔记按阶段组织：每个阶段一个文件夹，该阶段全部知识点写在一份《学习笔记.md》。文档内按原子知识点分小节，用短解释、关键源码和例子说明；不再逐知识点建文件。用户要求提前补笔记时可先整理，但明确标注待修与未验证内容。
12. 后续阶段提示词更详细具体：写清实际源码事实、允许文件/模块、实施先后、关键函数/字段合同、默认值/未知值、正常与异常分支、正反测试输入及预期、实际命令、完成报告和停止边界。必要时给短伪代码；不要只说“参考 Pi 自行实现”，也不为细化指令扩展阶段范围。

## 1. V2 交付定义

V2 交付一台可持续对话、并围绕 Test Artifact 持续协作编辑的 Test Agent（产品定义见 [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md)）。登录后用户可与 Agent 连续对话，创建或打开测试 Artifact；Agent 根据当前用户意图自主决定直接回复、读取资料、加载 Skill 或调用 Artifact 工具。测试设计不存在强制固定路径：用户可以先生成测试点、直接补用例、修改现有用例、检查覆盖或局部重构。所有测试资产修改以增量 Operation 产生 Revision 和 Diff，并实时反映到脑图工作区。

P10 完成后，用户应能在浏览器中完成“创建/打开 Artifact → 持续聊天 → AI 动态调用 Tool 修改 Artifact → 脑图实时展示 → 查看 Diff → 继续修改/撤销 → 刷新恢复”的完整闭环（E2E 故事见本文 [V2-P10 验收](#v2-p10--context--approval--conflict--recovery--e2e)）。

V2 必须具备：
- user / assistant / tool 多轮消息和可重建上下文；登录后无项目即可开始；
- 文本、工具调用及流式事件的统一模型合同；
- 有界 Agent Loop、参数校验、权限门禁和工具结果反馈；
- 会话持久化、独立执行、流式 UI、取消、有限恢复；
- Test Artifact 一等业务对象：Case Tree / Node / Revision / Operation / Diff / Undo / 乐观锁（数据合同见 05 §6～§10）；
- Artifact 读写 Tool 与 Tool Policy：Approval 绑定动作风险，而不是固定 Workflow gate（05 §5 / §12）；
- 受控 Skill 发现/按需加载（Skill = 领域知识 + 行为规则，不是 phase 状态机），以及上下文整理/压缩（05 §11）；
- Chat + MindMap + Diff 工作台，AI 与人工修改同一 Artifact（产品交互见 04_PRODUCT_PRD.md，协议见 05 §15）；
- 启动预检、可观察诊断、故障测试和版本门禁。

不是 V2：
- 把固定 case_generation Workflow 重新作为新 Agent 的执行主链；确定性能力迁移为 Tool/Service，流程编排退役（见 V2-P05）；
- 把 AgentArtifact 当作长期编辑的 TestArtifact；前者保留为执行产物/历史兼容（见 05 §6）；
- API 测试执行、失败根因分析、测试造数、缺陷辅助等更高级测试领域（归 V3，复用同一 Conversation + Agent Loop + Tools + Artifact 模型，不再各建 Workflow Runtime）；
- 任意 Shell/SQL/URL/宿主文件工具、自动下载扩展、npm 插件体系、TUI；
- 完整复刻 Pi 的会话树、分支、多模态、OAuth 登录、全部 Provider、多 Agent。

## 2. 源码基线与复用决策

Pi 仓库已克隆到 D:\pi：
- origin：https://github.com/earendil-works/pi.git
- 参考提交：f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6（2026-09-03）。
- 不跟随 main 自动更新；开发前使用 git show <参考提交>:<路径>，不要为了看旧文件修改仓库分支。
- 精确文件、符号、测试与 Python 对应见 [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)。
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
| V2-P01 | 源码行为基线、消息/事件/工具合同 | V2-R01 | 阶段验收通过，见 reviews/V2-P01_ACCEPTANCE.md |
| V2-P02 | 文本 + 工具调用 + 流式模型适配 | P01 | 阶段验收通过，见 reviews/V2-P02_ACCEPTANCE.md |
| V2-P03 | 纯 Python Agent Loop 与执行器 | P01、P02 | 阶段验收通过，见 reviews/V2-P03_ACCEPTANCE.md |
| V2-P04 | 无项目会话、Turn 持久化、并发/幂等迁移 | P01、P03 | 阶段验收通过，见 reviews/V2-P04_ACCEPTANCE.md |
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

### 代码目录（V2-R01 结构整理后，当前后端事实；P05 起按目标结构演进，见 [05 §13](05_TECHNICAL_DESIGN.md#13-worker--queue--recovery)）

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

### 验证环境分层（阶段 → 环境）

| 层次 | 环境 | 验证重点 |
|---|---|---|
| P01～P03 | 纯 Python + Fake Provider/Tool | 文本/工具循环、事件顺序、预算和取消 |
| P04～P05 | 临时 SQLite，外键 ON，真实 Repository/Worker | 幂等、串行、租约、持久化、Conversation 主路径接通与 Workflow 退役 |
| P06 | 独立开发入口 + Fake 模型 + 实际 HTTP/SSE/Worker | 持续聊天、流、重连、Tool activity |
| P07 | 同左 + Artifact Domain | 建 Artifact、Revision/Diff/Undo、conflict（确定性测试） |
| P08 | 同左 + Fake Provider 对话 | Agent 动态 read/add/edit/delete/move、8 类对话场景 |
| P09 | 同左 + 前端脑图/Diff | 同一 Artifact、Diff/Undo、刷新恢复、双浏览器冲突 |
| P10 | 经授权的测试 MySQL + 小额真实模型 | DDL/并发/供应商协议及真实延迟 |
| P10 | 现有回归套件 | 旧业务与新入口兼容 |

隔离入口不得更改正式登录依赖、读取真实 Key 或连接生产库；联调验收场景逐条见 [03_ACCEPTANCE_CHECKLIST.md](03_ACCEPTANCE_CHECKLIST.md)。

## 4. 任务实施卡

### V2-P01 — 行为基线与合同

执行节奏：P01 已验收，证据见 [P01 验收记录](reviews/V2-P01_ACCEPTANCE.md)。阶段收尾及修正提示词保留历史，不再重复派发；下一阶段是 P02，按新的详细任务书接续。

参考：Pi agent/src/types.ts、ai/src/types.ts、agent-loop.test.ts、agent.test.ts。

新增建议：
- backend/app/agents/conversation/contracts.py、messages.py、events.py
- backend/tests/conversation/test_contracts.py、fixtures/（合成模型响应）
- references/PI_SOURCE_AUDIT.md 的实施映射及第三方来源记录

内容：
- 定义 ConversationTurn（一条用户请求）、ModelTurn（一次模型推理）、ToolCall/ToolResult，避免与旧 Skill Run 混淆；
- 核心消息结构直接对齐 Pi 的 UserMessage / AssistantMessage / ToolResultMessage 联合；文本与 ToolCall 是内容块，工具反馈是独立消息，通过 tool_call_id 关联，不能包装成系统消息。应用层稳定 ID 和版本是轻适配；Provider 边界再映射到旧 tool 角色；
- 事件含 session_id、run_id、message_id、tool_call_id、sequence_no、schema_version，按事件类型约束必填字段；
- 明确模型结束原因、空结果、截断、错误、取消、预算的区别；
- 数据类型与纯函数不依赖数据库连接，不触发 create_all 或 import-time 建库。

验收：文本/混合工具内容往返；未知事件拒绝；截断参数不执行；不把普通字符串作为用例 JSON 解析。
不做：业务工具、网络调用、数据库迁移。

### V2-P02 — 统一流式 Provider 边界

P02 已按集中续做提示词完成修正，并通过阶段验收（Fake 流式套件 54 项、P01 回归 90 项、旧 Provider/Gateway 回归 55 项分别通过，详见 [02 开发记录](02_DEVELOPMENT_RECORD.md)）；真实供应商验证留 P10。

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

状态：已在纯 Python/Fake 范围验收通过。实现位于 conversation/{loop,tool_executor,budget,policy}.py；P02 Fake HTTP 集成链证明工具结果进入第二次模型请求。

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

状态：已在临时 SQLite/真实 ORM 事务范围验收通过。conversation Run 当前保持 queued，旧 Worker 不会误抢；P05 统一分发与租约尚未开始。

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

### V2-P05 — Conversation Runtime 收敛 + Legacy Workflow 退役

> 本阶段吸收原“Legacy Workflow 迁移计划”（2026-09-04，全文已归档）。目标：P04 之后新 Conversation Agent 只有一条明确运行链：ConversationTurn → Worker → ConversationRunner → Agent Loop；固定测试 Workflow 不再作为新架构执行路径。

#### Goal

打通持久化到执行的桥接：Worker 消费 conversation queued Run，并启动 ConversationRunner 运行 Agent Loop；完成旧 case_generation Workflow 的依赖审计与隔离/删除决策。

#### 起点现状（2026-09-04 源码审计，供实施对账）

- `agents/conversation/` 已有 contracts/messages/events/loop/tool_executor/policy/budget/tool_validation，纯 Python/Fake 范围验收过，但没有任何 Worker/Router/Service 在生产调用 `run_agent_loop`；当前**不存在 ConversationRunner**；
- `conversation_service` 能持久化 conversation Turn 为 queued Run，但 Worker claim 查询目前按 `workflow_code != "conversation"` 主动跳过，这些 Run 停在 queued；
- 真正被接入的仍是旧执行核：`agents/runtime/runner.py` 的 AgentRunner + `agents/skills/case_generation/`（next_step / execute_step、phase/gate），由 `agent_worker` CLI 与 `/agent/runs/case-generation` 路由驱动，逐 step 写 AgentStep/Event/Artifact/Approval；会话 `mode=legacy_workflow`；
- `agent_artifact` 是整棵 JSON payload + 整数 version 的浅版本（update_payload 原地覆盖），没有 Revision/Diff/Undo，也不存在 TestArtifact/ArtifactNode/ArtifactRevision/artifact_operation；
- 前端 test-agent 悬浮台仍“每次发送都无条件创建 case_generation Run”，无 conversation 入口、无脑图/Diff 视图；
- Alembic 已有 0002（agent 平台表）/ 0003（conversation 持久化：mode、project_id 可空、序号游标、active_slot）。

#### Scope / Key implementation

1. **Dependency Audit（先于一切删除）**：搜索 CaseGenerationWorkflow / AgentRunner / workflow_code / legacy_workflow / case_generation / next_step / execute_step，列出：API 调用方、Worker 调用方、前端引用、tests 依赖、database 历史行值。没有审计结果前不物理删除任何 Workflow 代码。
2. **旧 Workflow 内容三分类**：
   - A. 可复用确定性能力（load_requirement、load_existing_cases、validate、deduplicate、coverage、save）→ 抽成 Tool / Domain Service（随 P07/P08 落地；若内部已有可靠 service，Tool 直接调用 service）；
   - B. 测试方法与 Prompt 知识（怎么分析测试点、怎么考虑边界、怎么生成高质量用例）→ 迁移到 `skills/test-design/SKILL.md`（P08）；
   - C. Orchestration（phase、next_step、repair loop、coverage_gate、save_gate）→ **删除**。
   - 禁止：新 Tool 内部继续整链调用 CaseGenerationWorkflow（不允许“表面删除、实际藏进 Tool”）。
3. **Worker**：保留并完成 queued Run 抢占、lease、heartbeat（独立轻量机制 + 短事务 + 独立 DB Session，长模型调用不误判）、fencing token 条件写入（失去租约的执行器不能继续落消息或产生副作用）、cancellation / interrupted、同会话一个 active Turn、follow-up 队列（当前 Run 失败/中断后后续队列暂停，给用户恢复/取消选择）。
4. **Runner**：新增 ConversationRunner，职责仅 4 步：从 Repository 重建会话 Context → 构造 RuntimeContext → 调用 `run_agent_loop()` → 持久化最终 Message / Event / Run status；**不自己决定测试业务步骤**。
5. **Workflow 处理**：新代码禁止 `if workflow_code == "case_generation"` 进入 Conversation 路径。旧 case_generation 二选一：仍被 V1 依赖 → 迁移到 legacy/compat 区域（明确标记 deprecated、not used by V2 conversation），只服务旧入口；确认无调用方 → 删除。不允许为了兼容把它挂在新 Worker 主分发路径。
6. **历史入口与数据库**：V1 页面若仍依赖旧 `/runs/case-generation`，Option A 短期保留 legacy 兼容 / Option B 仅当前端、API、数据迁移、测试全部满足时直接下线。mode/workflow_code 字段 P05 保留；**新的 V2 Conversation 路径不得新建 legacy_workflow，仍被旧兼容入口（/agent/runs/case-generation、V1 前端）使用的 legacy Workflow 在 P06 替换旧前端之前允许继续创建**，不因本表述破坏 V1/legacy 页面。新 Test Agent 数据从 P07 起使用 conversation + TestArtifact + ArtifactRevision；P10 统计真实 legacy 调用后决定是否删除 legacy Runner/数据只读保留。“删除 Python Workflow 类”与“删数据库历史字段”不强绑定为同一提交。
7. **Approval 迁移**：scope_gate / coverage_gate / save_gate 不再作为固定流程阶段，改由 Tool Policy 按动作风险裁决（见 05 §12）。
8. **测试迁移（最终退役清单，随 legacy 下线执行；legacy 存活期内保留既有测试，P05 不删除测试）**：workflow orchestration tests → 删除；domain algorithm tests → 移到 Tool/Service tests；prompt quality tests → Skill/Eval tests；legacy endpoint tests → compat tests（若仍保留）。
9. **目录目标**（05 §13 同）：`agents/conversation/{loop,runner,context,tool_executor,...}`、`agents/legacy/case_generation/`（可选临时兼容）、`test_artifacts/` 业务域目录从 P07 开始。

#### Acceptance

- Fake Provider 可以通过 Worker 完成 3 个连续 Turn；conversation queued Run 被消费而非永远排队；
- 长模型调用 heartbeat 不丢 lease；过期执行器写入被 fencing 拒绝；cancel 能终止当前 Turn；
- Follow-up 顺序稳定且不并行写同一会话；失败/中断后队列暂停；
- 新 Conversation 路径（Turn → ConversationRunner → Agent Loop）不经过 case_generation / next_step / execute_step；Dependency Audit 结果有记录；
- ConversationRunner 只做“重建上下文 → run_agent_loop → 持久化”，不自己决定测试业务步骤；
- Workflow 隔离后 P01～P04 回归通过（conversation 90 + P02 54 + P03 30 + 旧平台回归；legacy 存活期测试保留）。

> **P05 验收边界**：以下能力只有 P07/P08/P09 才能真正完成，**不属于 P05 功能验收**，作为长期架构约束随各阶段落地——Artifact 修改能力 / TestArtifact 编辑行为、Artifact 写操作独立于 Run phase（P07 Revision 机制落地后成立）；Coverage/Dedup/Validation Artifact Tools 可单独调用、测试设计只经 Agent Loop + Tools、Skill 不含 phase 状态机（P08）；UI 不展示 Workflow phase（P09）。Tool Executor 是模型动作统一门禁由 P03 已提供，扩展到 Artifact Tools 属 P08。旧调用方“已删除或明确隔离”从 P05 的依赖审计与隔离开始，P06 替换旧前端、P10 统计后收尾。

#### Non-goals / Stop boundary

- 不实现自动抢占式 steer 修改正在执行的工具；Pi 的 steer 也不等于回滚已发生的动作；
- 不删除 agent_sessions.mode / workflow_code 数据库历史字段（P10 再统计决定）；
- 不同步启动 P06（Conversation API/前端入口在本阶段只做内部验证）；
- 不接真实模型、不动 V1 业务表。

### V2-P06 — Conversation API、SSE 与基础持续聊天工作台

#### Goal

让浏览器真正成为一个持续会话 Agent，而不是“生成任务 UI”。

#### Scope / Key implementation

- 新增 conversation_router / conversation_service 的对话入口：
  `POST /agent/conversations`、`POST /agent/conversations/{id}/turns`、`GET /agent/conversations/{id}`、`GET /agent/conversations/{id}/messages`、`GET /agent/conversations/{id}/events`（SSE）、`POST /agent/conversation-runs/{id}/cancel`；`POST /agent/conversations/{id}/artifacts/{artifact_id}/focus` 用于设置当前工作 Artifact（首期可延到 P07）。既有 /agent/sessions 与 /runs/case-generation 保留，不静默改变旧调用方语义。
- 前端“发送”只提交 Turn（content、client_request_id、可选 skill_code、queue_mode → 202 + run_id + user_message_id），不再先 appendMessage 再无条件 createCaseRun。
- 普通对话使用独立 agent_chat 场景或明确选定的会话模型；配置未就绪在启动前提示；不自动初始化真实 Key。
- 流式展示、Tool activity 独立展示（不是伪装的模型答复）、停止/排队状态、失败后仍可发新消息。
- SSE 技术协议（Bearer 鉴权、游标重连、去重、快照恢复、Markdown 安全）按 [05 §15](05_TECHNICAL_DESIGN.md#15-frontend--sse-integration) 实现。

#### Acceptance

至少完成如下真实场景：

```text
User: 记住数字 17
Assistant: ...
User: 加 5 是多少
Agent → calculator
Assistant: 22
refresh
User: 我刚才最开始给你的数字是什么
Assistant: 17
```

- 登录后不选项目可连续聊天至少三轮，回复来自模型而非前端状态模板；
- 0 业务写入、无来源也成功；重复提交幂等；取消生效；
- SSE 断线重连后消息与终态一致；错误后继续聊；跨用户访问拒绝；
- P06 暂不要求完整脑图，只要求多轮 / Streaming / Tool activity / Refresh restore / Error 后继续聊 / Session list / Cancel。

#### Non-goals / Stop boundary

- 不接入完整 MindMap 与 Artifact（P07/P09）；
- 真实模型验证留 P10；不把 Fake 演示冒充正式配置验证。

### V2-P07 — Test Artifact Core

#### Goal

建立新的长期业务对象 TestArtifact，替代“一次 Run 生成一个完整用例 JSON”的产品中心地位。它是用户与 Agent 长期共同维护的对象，可 Diff、可版本化、可撤销。

#### Scope / Key implementation

- 领域对象：TestArtifact / ArtifactNode / ArtifactRevision / ArtifactOperation / Diff / Undo / expected_revision 乐观并发；Node 类型首期 root / group / test_point / test_case；TestCase content_json 允许不同 schema；SourceRef 支持追溯（需求 clause / 快照 hash）。完整数据合同见 [05 §6～§10](05_TECHNICAL_DESIGN.md#6-test-artifact-domain)。
- Revision：每一次逻辑修改（一个或多个 operation）推进 Revision，线性即可（首期不做 Git DAG）；Diff 是 Revision 的派生结果，同时供 UI 与 Agent 最近上下文使用。
- Undo：支持 undo latest revision / restore to revision N，通过生成反向 Revision 实现，不物理删除历史。
- 并发：所有写操作要求 expected_revision，版本不匹配返回 conflict（409 / revision_conflict），不允许静默覆盖用户刚刚的人工修改。
- **重要边界**：脑图不是底层存储格式；正确关系是 TestArtifact → MindMap View / Table View / JSON-API View；视图坐标放独立 view_state。
- AgentArtifact 保留为执行产物/证据/临时生成结果（legacy/compat），不让一个表承担两种语义（05 §6）。
- 迁移：新增 Alembic（领域表），保留 V1/既有表；Agent Tool 与人工 UI 最终调用同一个 Artifact Application Service（05 §6/§14）。

#### Acceptance

- 创建空 Artifact；添加 20 个节点；修改单节点；移动分支；删除节点；
- Revision 连续；Diff 正确；Undo 到上一 Revision；stale revision 写入被拒；
- Batch operation 原子（全部成功才 commit）；
- project/user owner 隔离；
- 不需要 LLM 也能完整测试 Artifact Domain（确定性测试）。

#### Non-goals / Stop boundary

- 不做 Git 式分支/合并、多人实时 CRDT（P09/P10 也不做）；
- 不把 MindMap 布局当业务数据入库；
- 不实现 Agent 编辑工具（P08）。

### V2-P08 — Artifact Tools 与 Test Design Skill

#### Goal

Agent 第一次真正具备“像 Coding Agent 改代码一样改测试资产”的能力：由模型根据用户意图动态选择工具，而不是 Workflow 固定顺序调用。

#### Scope / Key implementation

首期 Tools（合同与输入/输出示例见 [05 §5](05_TECHNICAL_DESIGN.md#5-tool-system)）：
- Read：get_current_artifact / read_artifact_outline / read_artifact_nodes / search_artifact / get_artifact_diff / read_requirement；
- Write：add_artifact_node / update_artifact_node / delete_artifact_node / move_artifact_node / batch_apply_artifact_operations；
- Quality：validate_test_artifact / find_duplicate_cases / analyze_test_coverage —— **是能力，不是固定流程**（只改一条预期时不强制跑 coverage；coverage Tool 不得自动偷偷新增用例）。

Tool Contract（写 Tool 必须）：
- 从 RuntimeContext 获取 user/project/artifact，不接受模型伪造 owner/user_id/project_id；
- 携带 expected_revision；返回 applied revision + machine-readable diff summary；写 audit；遵守 Tool Policy；
- update 只能 patch 指定字段；delete 返回影响范围（如 descendant_count=43）供 Policy/Approval 决策；batch 有 max_operations / max_nodes_affected / 事务（全部成功才 commit）。

Test Design Skill（新增 skills/test-design/SKILL.md，规则见 [05 §11](05_TECHNICAL_DESIGN.md#11-test-design-skill)）：
- 描述测试设计方法与检查维度（正向/异常/边界/状态转换等）；
- 行为规则：read before write、minimal edit、respect user structure、no mandatory generation path（禁止“任何任务都必须先测试点→再用例→再查重”）、不擅自删除大量人工用例、不为了格式统一重写整棵树；
- Skill 不含固定 phase 状态机；通用 Skill 加载/注入基础若前序阶段未落地，随本阶段一并提供。

Agent 运行示例（路径由模型决定）：
```text
User: 先列登录模块测试点，暂时不要展开详细用例
LLM → read_requirement → get_current_artifact → add_artifact_node × N → final

User: 锁定这个节点展开成详细用例
LLM → read_artifact_nodes(lock-node) → read_requirement(lock clauses) → add_artifact_node × N → final
```

#### Acceptance

至少覆盖 8 类对话（Fake Provider）：
1. 从空 Artifact 增加测试点；
2. 只展开指定分支；
3. 修改单条用例；
4. 删除“第二个”（多轮指代，结合 Message + 最近 Diff；歧义大就追问而不是猜）；
5. 移动节点；
6. 查重但不修改；
7. Coverage 后按用户要求补缺口；
8. 用户要求直接补用例，不强制先生成测试点。

- 所有 Tool 先有纯确定性测试（schema invalid / unknown node / cross-project / stale revision / permission denied / cancel / approval / batch rollback / diff / 恶意参数），再测 Agent + Fake Provider 工具选择；**不要只通过“LLM 最终回答看起来对”验收**。

#### Non-goals / Stop boundary

- 不做 replace_entire_artifact 作为主要写入方式；
- Quality Tool 不改 Artifact；模型不得自我批准写操作；
- 不做 Chat+MindMap 工作台 UI（P09）。

### V2-P09 — Chat + MindMap + Diff 协作工作台

#### Goal

实现 TestMind 最核心的产品体验：一边对话，一边看到 AI 对测试资产的实际修改；用户也可以在脑图中直接人工编辑，下一轮 Agent 基于最新版本继续。

#### Scope / Key implementation

- 页面结构：左侧 Chat（消息 + Tool activity + Diff card）+ 右侧 MindMap + Node Inspector；底部/侧栏 Revision 状态、Diff、History、Undo（产品细节见 [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md)）。
- AI 修改后三视图同源：Chat 解释 + Changes/Diff（added/updated/deleted/moved，字段级 before/after）+ MindMap 对应节点出现，都来自同一个 Revision。
- 人工编辑（改标题/前置/步骤/预期、拖拽、新增/删除）也必须生成 ArtifactOperation → Revision 25 → 事件 → MindMap 更新；AI 下一轮读到的是最新 Revision。
- Undo/History：Revision 列表（谁/何时/改了什么），Undo 生成反向 Revision，不抹除历史。
- 大范围操作（如删除整分支 43 条）：UI 展示 impact preview，并可进入 Approval（Approval UX 见 04）。
- Streaming 与 Artifact 写分离：聊天文字可流式；Artifact 写操作按完整 ToolCall 成功后一次提交 Revision，不做“token 边流边半成品写库”（05 §15）。
- 工作对象切换：可切换 Artifact，但正在运行的 Turn 不允许静默切换。

#### Acceptance

- Chat 和脑图同 Artifact；AI 添加节点无需刷新出现；
- 人工修改后 AI 下一轮看到最新版本；
- Diff 与 Revision 一致；Undo 后 UI 和 DB 一致；
- 两个浏览器同时编辑产生 revision conflict 而非静默覆盖；
- 200+ 节点基本交互可用。

#### Non-goals / Stop boundary（首期不做）

- 无限画布高级排版、多人实时 CRDT、Git 式分支、评论系统、多 Artifact 同屏、自动合并复杂冲突、全功能 XMind 兼容。

### V2-P10 — Context / Approval / Conflict / Recovery / E2E

#### Goal

把前面能力加固成可以长期工作的 Agent，而不是 Demo；完成 V2 真实 E2E 验收与发布证据。

#### Scope / Key implementation

**Context**：模型输入不应每轮塞整个 Artifact，采用 System + Loaded Skills + Conversation Summary + Recent Messages + Current Artifact metadata + Relevant Artifact nodes + Recent Diff；需要更多内容时由 Agent 调 read_artifact_nodes / search_artifact（与 Coding Agent 不每轮把整个仓库塞进 Prompt 同一思想）。

**Context Compaction**：保留原始消息、Artifact Revision、ToolCall/ToolResult、最近关键 Diff；摘要只用于模型工作上下文，不删除原历史；摘要失败可退回安全窗口或 context_limit，不无限重试/重复计费；摘要与普通模型调用共用 Run 预算；本版线性会话即可。

**Approval（从固定 gate 改为 Action Risk）**：

| 动作 | 默认策略 |
|---|---|
| read | allow |
| add 1～5 nodes | allow |
| update 1 node | allow |
| delete 1 node | allow / configurable |
| batch delete 30 nodes | approval |
| overwrite artifact / replace_entire_artifact | approval |
| export / write to formal project | approval |

- 审批属于 Tool execution，不属于流程 phase；approval_request 保存 tool_call_id、arguments_hash、artifact_revision、affected_nodes、expires_at；用户批准后必须重新校验 revision / 权限 / 参数 hash / lease / cancel（实现见 05 §12）。

**Recovery 验证场景**：Provider 断流；Worker 崩溃；Revision 冲突；Tool timeout；Approval 后恢复；Cancel；SSE 重连；Context summary 失败；Artifact 写入成功但 final response 失败。任何情况下都不得把“聊天失败”错误解释成“已经完成的 Artifact 写入被回滚”。

**真实环境与发布**：本地启动说明/脚本（FastAPI + Worker + 前端三服务、配置预检、健康检查）；授权测试 MySQL 验证迁移/并发/恢复；小额真实模型验证普通聊天、工具调用和流式协议（记录实际 Provider/模型/调用次数/延迟/错误）；一次受影响 V1/旧 Agent 综合回归；feature flag 保留可回退入口（回退代码 ≠ 降级数据库）。

#### Acceptance（最终 E2E 故事，必须真实跑通）

```text
1.  创建 Conversation
2.  创建 Test Artifact
3.  User: 根据这段登录需求先列测试点
4.  Agent 动态读取需求并添加节点
5.  MindMap 展示修改
6.  User: 锁定部分展开详细用例
7.  Agent 局部读取并修改
8.  User: 第二个不要
9.  Agent 正确删除对应节点
10. User: 检查一下还有哪些边界没覆盖
11. Agent 调 coverage/read tools
12. 用户同意后补充
13. 查看 Diff
14. Undo 一次
15. Refresh
16. Conversation + Artifact + Revision 全部恢复
```

满足这一故事才算 V2 完成。未获得真实环境授权时，可交付“隔离验收通过”，但真实环境项保持未完成，不使用 unlimited 重试等待。

#### Non-goals / Stop boundary

- 不进入 V3 领域能力（API 测试/RCA/造数/缺陷）；不改 V1 业务行为；
- 不实现 Pi 树/branch 会话导航、steer、多 Agent。

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
| 旧 case_generation Workflow（AgentRunner / next_step / execute_step / phase/gate） | V2-P05 退役或隔离 | A 类确定性能力 → Tool / Domain Service（P07/P08），B 类测试方法 → skills/test-design（P08），C 类编排 → 删除；详细步骤见本文 V2-P05 |
| 旧 T05～T08 用例工具与审批 UI | 能力并入 V2 | Tool/Service 复用；不再作为独立 V3.1 桥接任务 |
| 旧 T09 用例影子评测 | V2 test-design Skill 质量门禁（P08/P10） | 基础用例/测试点生成现在是 V2 纵向闭环的验收内容 |
| 旧 V2.2 根因分析 | V3.2 Failure RCA | 复用 Conversation + Agent Loop + Tools + Artifact |
| 旧 V2.3 测试数据、缺陷描述 | V3.3 Test Data / V3.4 Defect | 复用同上 |
| 通用安全、会话隔离、预算 | V2 必须 | 不因业务后移而延期 |
| API 测试执行、CI 集成等 | V3.1 / V3.5 等高级测试能力 | V2-P10 后按新 V3 路线规划 |

旧记录和提示词见 [历史归档](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)；更高级测试能力路线见 [V3 主计划](../V3/01_TEST_CAPABILITY_PLAN.md)。
