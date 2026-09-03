# V2 开发主计划：Pi 架构的 Python 实现

> 生效：2026-09-03。用户已确认：V2 只做 Agent 基本架构，测试能力扩展全部归入 V3。
> 状态：规划完成，V2-P01～P10 尚未实施；已有旧版代码只作为复用基线。
> 路线：V1 既有平台 → V2 Python 对话 Agent 基础 → V3 测试领域 Skills。
> 本文件替代旧 V2.1/V2.2/V2.3 任务路线，不代表 Pi 全功能复刻或官方 Python 移植。

## 0. Claude Code 执行协议

1. 阅读 [总项目记录](../PROJECT_RECORD.md)、本计划、[架构](06_TEST_AGENT_PLATFORM_ARCHITECTURE.md)、[源码对照](10_PI_SOURCE_AUDIT.md)、[新开发记录](02_DEVELOPMENT_RECORD.md) 和 [验收清单](03_ACCEPTANCE_CHECKLIST.md)。
2. 只实施用户指定的一个 V2-Pxx；先核验源码并简短说明文件范围、验证和风险，然后直接编码，不重复索要同一范围的确认。
3. 文档只是开发计划，不授权立刻实施全部任务。新增依赖、真实模型费用/数据出站、真实数据库变更及破坏性操作单独确认。
4. 保留用户/其他 AI 的未提交修改。不得 reset/checkout/restore 覆盖，不启动或停止用户正在运行的服务。
5. 先运行新增和直接相关测试；不为每个小改动重跑全部后端测试。P10 才组织一次版本级回归。
6. 不能用改测试期望掩盖行为退化；不能把旧版测试数当成新 V2 的验收结果。
7. Python 代码写在 TestMind；D:\pi 仅作源码参考，不作为运行依赖，不安装/执行 Pi，不复制其 Node.js 环境。
8. 旧 V2.1-Txx 提示词已归档，不再作为当前开发指令。业务用例生成、根因分析、造数、缺陷生成禁止混入 V2。

## 1. V2 交付定义

登录后打开悬浮工作台，无需项目、需求或接口文档即可正常多轮对话。Agent 可决定直接回复、追问、加载已审核的通用 Skill，或调用白名单工具；工具结果回到上下文后可继续回复。普通回复不是 JSON 产物，单次失败不关闭整个会话。

V2 必须具备：
- user / assistant / tool 多轮消息和可重建上下文；
- 文本、工具调用及流式事件的统一模型合同；
- 有界 Agent Loop、参数校验、权限门禁和工具结果反馈；
- 会话持久化、独立执行、流式 UI、取消、有限恢复；
- 受控 Skill 发现/按需加载，以及上下文整理/压缩；
- 启动预检、可观察诊断、故障测试和版本门禁。

不是 V2：
- 测试用例生成/覆盖/代码生成、失败根因分析、造数和缺陷描述的新增或改造；
- 任意 Shell/SQL/URL/宿主文件工具、自动下载扩展、npm 插件体系、TUI；
- 完整复刻 Pi 的会话树、分支、多模态、OAuth 登录、全部 Provider、多 Agent。
这些非基础能力不因为 Pi 存在就自动纳入；测试业务转 V3，其余留后续独立决策。

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
| V2-P01 | 源码行为基线、消息/事件/工具合同 | V2-R01 | 待实施 |
| V2-P02 | 文本 + 工具调用 + 流式模型适配 | P01 | 待实施 |
| V2-P03 | 纯 Python Agent Loop 与执行器 | P01、P02 | 待实施 |
| V2-P04 | 无项目会话、Turn 持久化、并发/幂等迁移 | P01、P03 | 待实施 |
| V2-P05 | Worker 分发、租约、取消和消息排队 | P03、P04 | 待实施 |
| V2-P06 | 对话 API + 悬浮前端 + SSE | P02、P04、P05 | 待实施 |
| V2-P07 | 通用 Skill 加载与选择 | P03、P06 | 待实施 |
| V2-P08 | 上下文预算、摘要和安全恢复 | P04、P07 | 待实施 |
| V2-P09 | 人工门禁、隔离与故障加固 | P05～P08 | 待实施 |
| V2-P10 | 真实环境验证、回归和 V2 验收 | P01～P09 | 待实施 |

里程碑 A：P03 后，Fake 模型能多轮聊天并调用无副作用工具。
里程碑 B：P06 后，浏览器能正常聊天、展示真实消息、刷新恢复，不需要任何测试文档。
里程碑 C：P10 后，基础架构验收；届时才启动 V3.1 用例生成接入。
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

参考：Pi agent/src/types.ts、ai/src/types.ts、agent-loop.test.ts、agent.test.ts。

新增建议：
- backend/app/agents/conversation/contracts.py、messages.py、events.py
- backend/tests/conversation/test_contracts.py、fixtures/（合成模型响应）
- docs/V2/10_PI_SOURCE_AUDIT.md 的实施映射及第三方来源记录

内容：
- 定义 ConversationTurn（一条用户请求）、ModelTurn（一次模型推理）、ToolCall/ToolResult，避免与旧 Skill Run 混淆；
- 消息含稳定 ID、角色、text/tool_call/tool_result 内容块、tool_call_id；工具响应不能冒充系统消息；
- 事件含 session_id、run_id、message_id、tool_call_id、sequence_no、schema_version，按事件类型约束必填字段；
- 明确模型结束原因、空结果、截断、错误、取消、预算的区别；
- 数据类型与纯函数不依赖数据库连接，不触发 create_all 或 import-time 建库。

验收：文本/混合工具内容往返；未知事件拒绝；截断参数不执行；不把普通字符串作为用例 JSON 解析。
不做：业务工具、网络调用、数据库迁移。

### V2-P02 — 统一流式 Provider 边界

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

### V2-P05 — Worker、租约、取消和排队

范围：workers/agent_worker.py、agent_run_service.py、conversation 持久化运行桥接及针对性测试。

内容：
- 一个 Worker 入口按 workflow_code 分发 ConversationRunner 和旧 Workflow Runner；不要建立两个都抢所有 queued 行的 Worker；
- 运行时禁止在 FastAPI --reload startup 隐式启动常驻 Worker；
- 心跳不再只依赖步骤完成：独立轻量机制、短事务和独立 DB Session，长模型调用不应被误判；
- 抢占租约/执行代次（fencing token）与条件写入，失去租约的执行器不能继续落消息或产生后续副作用；
- 默认一个会话一个活跃 Turn，新消息可显式 follow_up 入队；当前 Run 失败/中断后后续队列暂停，给用户恢复/取消选择；
- abort 传递到模型流与合作式工具；不可中止的外部副作用必须如实标注，不把数据库 cancelled 等同于物理回滚；
- 进程崩溃标记 interrupted；不自动重放未知是否成功的调用；
- 暴露安全的 Worker 健康状态，队列无人消费时前端能解释。

验收：两个 Worker 竞争、长调用 heartbeat、取消、过期 Worker 写入被拒、进程中断、队列排序、旧任务分发不回归。
首期不实现自动抢占式 steer 修改正在执行的工具；Pi 的 steer 也不等于回滚已经发生的动作。

### V2-P06 — 真正的对话 API 与悬浮前端

范围：新增 conversation_router.py / conversation_service.py；前端 API 与现有 test-agent 组件，保持原登录流程。

拟定 API（最终 DTO 在任务实施时固化，不声称已经存在）：
- POST /agent/conversations：登录用户创建，可无 project_id；
- POST /agent/conversations/{id}/turns：content、client_request_id、可选 skill_code、queue_mode，返回 202 + run_id + user_message_id；
- GET /agent/conversations/{id}：快照和当前 Turn；
- GET /agent/conversations/{id}/messages?after_sequence=...；
- GET /agent/conversations/{id}/events?after_sequence=...：SSE；
- POST /agent/conversation-runs/{id}/cancel；
- GET /agent/conversation-capabilities：当前模型/工具能力及 Worker 可用性，不含密钥。
既有 /agent/sessions 和 /runs/case-generation 保留，不静默改变旧调用方语义。

内容：
- 普通对话使用独立 agent_chat 场景或明确选定的会话模型；复用配置中心，不能暗用 requirement_to_function_case 或第一个模型；
- 配置未就绪在启动前返回明确提示，不先等范围审批；启用聊天入口不自动初始化真实 Key；
- 登录即可聊天；前端“发送”只提交 Turn，不再先 appendMessage 再无条件 createCaseRun；
- 助手回复由模型生成并持久化；进度与错误是独立 UI，不伪装成模型答复；
- SSE 用可携带现有 Bearer 的 fetch 流或明确鉴权方案，不把 Token 放 URL；
- FastAPI 从数据库事件日志转发 Worker 事件；序号去重、断线续传、终态快照恢复，不能仅用进程内队列；
- Markdown 禁止危险 HTML，流式末尾按稳定 message_id 合并；最小化继续执行，失败后仍可发新消息；
- 未完成 P07 前不展示可用的测试 Skill，旧生成入口仅兼容保留。

验收：浏览器至少两轮聊天、0 业务写入、无来源也成功、刷新恢复、取消、重复提交、SSE 重连、错误后再聊、跨用户访问拒绝。
先 Fake HTTP+Worker，再授权真实模型；不可把 Fake 演示冒充正式配置验证。

### V2-P07 — Skill 加载与调用选择

参考：Pi harness/skills.ts、coding-agent/core/agent-session.ts 的 Skill 调用展开。

新增：conversation/skills/loader.py、catalog.py、resolver.py；受控资源目录；合成 notes_summary Skill 和 loader 测试。

内容：
- Skill 是任务说明/资源，不要求每个 Skill 都实现 Python Workflow；
- 只读取显式配置的审核目录；name/description/版本/hash、文件大小、重复名和 frontmatter 错误有诊断；
- 支持显式 /skill:name 与模型调用 load_skill(name)；只按名称取注册资源，不接受任意 path；
- 模型只先看到 Skill 摘要，需要时加载正文；参考资源须限制在该 Skill 根目录内，解析真实路径防穿越/链接逃逸；
- Skill 不能扩大工具权限：配置允许集合 ∩ 用户权限 ∩ 本次会话策略；
- 不自动执行 Skill scripts、不扫描 .claude 或实习目录、不安装第三方包；
- 使用实际 YAML 安全解析器前检查现有依赖；必要新增需授权并固定版本，不手写宽松 YAML 解析冒充兼容。

验收：无需 Skill 的聊天、显式/按需加载、未知 Skill 澄清、摘要 Skill、多轮保留、恶意说明不越权；V2 默认 catalog 无测试领域 Skill。
V3 再将旧 case_generation 包装为独立业务能力。

### V2-P08 — 上下文预算、摘要与会话恢复

参考：Pi compaction.ts、SessionManager 的上下文构建。

内容：
- 区分展示历史与提交模型的工作上下文；保留原始消息，不为压缩删除历史；
- 先确定性整理：去 UI-only 事件、压缩过长工具结果、保留 system 策略与完整工具对；
- 达到上下文阈值后生成摘要记录（模型/版本、输入范围、hash、usage、保留尾部），摘要是派生信息不是系统指令；
- 不截断 tool_call/tool_result 配对，不合并其他用户/项目上下文；
- 摘要失败可退回安全窗口或明确 context_limit，不无限重试/重复计费；
- 摘要和普通模型调用共用 Run 预算；压缩中取消要取消流、保留原上下文并停止发布迟到摘要；
- 活跃 Run 不允许切换项目；空项目会话绑定项目时仅允许 owner 明确操作，并验证权限；
- 本版线性会话即可，Pi tree/branch 导航不在完成条件内。

验收：超长合成对话、工具对不丢、摘要失败/取消、重启重建、脱敏、不同会话隔离、摘要不改变审批记录。

### V2-P09 — 人工门禁与故障加固

参考：Pi beforeToolCall/afterToolCall/shouldStopAfterTurn；权限和多用户安全采用 TestMind 自身策略。

内容：
- 通用 approval_request 合同含操作名、参数 hash、run/tool_call_id、有效期和解析结果；
- 仅用户鉴权端点能批准，模型和 Skill 不持有“自我批准”工具；
- 用内存假副作用工具验证待审批/拒绝/过期/幂等，仍不接测试保存或外部写入；
- 审批恢复重新校验参数、权限和当前 Run，失败不能静默落写；
- 对取消/断流/权限变更/重连/消息重复/中断恢复做故障注入；
- 清理已知敏感键并测试嵌套结构；不以关键词脱敏宣称所有 Secret 安全；
- 审计记录工具、版本、预算、事件与安全错误，不记录隐藏思维链；Provider 的隐藏 reasoning 不是前端事件。

验收：未审批零副作用、模型伪造 approval 无效、租约丢失不执行、参数变化需重新审批、跨用户/项目拒绝、费用尝试计数无遗漏。

### V2-P10 — 基础版本验收和可重复启动

内容：
- 完成 [验收清单](03_ACCEPTANCE_CHECKLIST.md)，对照上游关键行为而非目录相似度；
- 新增明确的本地启动说明/脚本：FastAPI、Worker、前端三个进程与配置预检；不再让用户靠猜启动缺失服务；
- 隔离 Fake 端到端验证后，单独授权测试 MySQL + 小额真实模型测试，记录实际 Provider、模型、版本、调用次数、延迟、错误；
- 同一合成脚本覆盖普通聊天→工具→Skill→解释结果→失败后继续；不需要任何测试用例表有数据；
- 仅此发布任务做一次受影响 V1/旧 Agent 综合回归；
- feature flag 保留可回退入口。回退代码不等于降级数据库，带新数据的迁移回退须预检；
- 记录上游适配清单、已知差异和未实现项，完成后才允许 V3 业务接入。

未获得真实环境授权时，可交付“隔离验收通过”，但 P10 真实环境项保持未完成，不使用 unlimited 重试等待。

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
| 旧 T05～T08 用例工具/Workflow/审批 UI | V3.1 | 代码保留，V2 新聊天不自动调用 |
| 旧 T09 用例影子评测 | V3.1 业务验收 | 不用替代 V2 基础行为评测 |
| 旧 V2.2 根因分析 | V3.2 | 待 V2 通过 |
| 旧 V2.3 测试数据、缺陷描述 | V3.3 / V3.4 | 待对应业务权限方案 |
| 通用安全、会话隔离、预算 | V2 必须 | 不因业务后移而延期 |
| 测试数据写入安全、结果质量评测 | V3 对应任务 | 使用具体业务门禁 |

旧记录和提示词见 [归档说明](../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，新业务路线见 [V3 主计划](../V3/01_TEST_CAPABILITY_PLAN.md)。
