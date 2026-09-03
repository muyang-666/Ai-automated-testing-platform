# V2 Python Agent 基础架构

> 生效：2026-09-03。替代旧测试 Workflow 优先的 V2 架构。
> Pi 参考提交及源码证据见 [源码对照](10_PI_SOURCE_AUDIT.md)；以下为拟实现设计，不是当前代码现状。

## 1. 组件边界

~~~text
React 悬浮工作台
  ├─ 真实对话消息、流式输出、队列/错误 UI
  └─ Skill 选择与通用审批卡（不默认生成测试用例）
          │ HTTP + 鉴权 SSE
FastAPI Conversation API
  ├─ 身份、权限、配置预检
  ├─ 同事务保存用户消息、幂等请求和 queued Turn
  └─ 读取持久化事件并转发
          │
MySQL Repository：Session / Message / Run / Event / Step / Approval
          │
独立 Agent Worker（一个入口、按类型分发）
  ├─ ConversationRunner → 纯 Python Agent Loop
  │                       ├─ LLM Gateway → Provider
  │                       ├─ Context/Compaction
  │                       ├─ Skill Catalog / load_skill
  │                       └─ 白名单 Tool Executor → Policy / Approval
  └─ Legacy Workflow Runner（兼容旧业务，不作为新对话入口）
~~~

模型决定回复还是请求工具，程序决定是否允许执行。Tool 不直接调用 UI；Provider 不读取业务数据库；内核不持有 ORM Session；Markdown Skill 不获得宿主执行权限。

## 2. Session / ConversationTurn / ModelTurn

- Session：持续会话，拥有独立历史、owner、可选项目；一次任务失败后仍可聊天。
- ConversationTurn：一次用户输入及其处理过程，复用 AgentRun；预算与取消围绕这个单元。
- ModelTurn：该处理过程中的一次模型调用，可能返回文本和多个工具调用。
- ToolCall：有 call_id 的一次具体动作；ToolResult 是模型可消费结果，不是直接拼成 system。
- Skill：何时/如何完成某类任务的说明与受控资源，可调用工具但不等于固定 Workflow。
- Workflow：保留的确定性业务执行器，V3 才接回 TestAgent。

不要把 agent_end 解释成整个会话关闭，也不要把 succeeded 固定显示成“用例已保存”。conversation succeeded 表示本次回复完成，业务写入成功由对应业务结果证明。

## 3. 消息、事件、产物三个通道

消息：用户文本、模型助手文本、工具调用与结果；稳定 ID，版本化内容块，角色由服务端确定。
事件：排队/执行/流式增量/工具/压缩/中断/失败，不自动成为模型历史；同会话递增游标。
产物：有结构的业务结果；V2 只预留引用合同，测试候选/覆盖矩阵在 V3。

流式增量只有临时意义：终止时写最终 message 状态；连接断开通过事件游标和消息快照重建，不能仅在内存保存。执行已取消、失去租约或 message 已完成时拒绝迟到增量。
事件允许合并小分片并设字节上限，不能每个字符单独无限落库；游标过期需明确 resync_required 并读取快照。

## 4. 模型接入

复用现有 Gateway 的 text/json/pydantic；新增 async stream 合同。保留同步 complete 供旧用例链路使用，不为“迁移 Pi”重写全部 Provider。

普通聊天不受用例 Schema 约束。已确认的 tool_call 才解析参数；空文本但有完整工具调用不是空回复。length 截断禁止执行工具，普通文本截断也标记 incomplete，不宣称完成。

模型配置是独立问题：
- 新建通用 agent_chat 场景（迁移/初始化只建立无 Key 的配置记录），由管理员明确绑定模型；
- 缺少绑定/模型禁用/能力不支持时启动前提示；
- 不静默选第一个模型、不自动套旧生成场景、不把配额问题统称 JSON 失败；
- 只在已授权范围使用真实模型，返回诊断包含安全 provider/model/finish_reason/request_id/usage，不输出 Key 和原始敏感数据。
- 有界重试、摘要都计入同一成本预算；不能仅统计最终成功调用。

## 5. 存储与迁移边界

优先扩展已有 Agent 表，不另造一套重复 Session：
- agent_sessions.mode：现有行默认 legacy_workflow，新会话显式 conversation；
- conversation Session/Run 的 project_id 可空；user_id/owner 必需；旧生成接口项目与来源仍必需；
- workflow_code=conversation 与 case_generation 共存，不把历史任务重命名；
- messages.content_json 存统一内容块、call_id、最终状态、schema_version；旧 content 文本可转兼容消息；
- 追加预算/租约/幂等及序号分配所需字段或独立记录，P04 以实际 schema 定稿；
- Session/Run/Event 读权限都先按 owner；绑定项目不自动把私人聊天公开给所有项目读者；
- 旧 /agent/runs/{id} 等仍可按 ID 访问的路径也必须识别 conversation mode，不能通过旧项目读权限规则旁路新会话隔离；
- NULL 项目聊天不可调用 project_required 工具。

请求幂等、同会话单执行者、sequence_no 分配和 Worker 抢占用真实数据库约束/事务，不只靠浏览器 disabled 或 Python 全局锁。
新的 DTO/Service 旁路旧 create_session 的强制项目规则；不要为了匿名项目聊天削弱旧函数的业务校验。
增量 Alembic 保留 V1 表。旧 0001 仍是 no-op 基线，空库全量接管缺口未自动解决；P04/P10 显式记录处理边界。

## 6. 执行生命周期

接收 Turn → 预检 → 原子持久化 → queued → Worker 抢占 → running → completed/failed/cancelled/interrupted 或 waiting_approval。

执行器持租约，心跳不依赖模型返回。条件更新带执行代次；过期执行器不能覆盖新状态。检查取消必须读取可信新状态，而非长期缓存 ORM 对象。
普通工具异常可回传模型并在预算内处理；不可恢复错误终止当前 Turn，但会话仍 active。
follow_up 是后续用户消息队列，不是新开多个并行处理器。前项失败/中断时先暂停后续队列，避免在不确定上下文上继续操作。
用户显式重试创建有关联的新 Turn 或恢复安全检查点；不能重放已成功或结果不明的写工具。

关键事务不能覆盖网络等待：SQLAlchemy 同步调用通过短事务 Repository 执行，线程/异步任务间不共享 Session。输出流的取消关闭 HTTP 连接；非合作式工具不能假装已物理停止。

## 7. Skill 与工具安全

Skill 目录只允许审核路径，以 name/hash/version 注册。资源加载先验证真实路径、后缀、尺寸，拒绝穿越/外部链接。用户上传文档是数据，不是可安装 Skill。
load_skill 返回说明，但可用工具始终取“平台允许 ∩ 用户权限 ∩ 会话策略”；Skill 正文或模型不得修改这个交集。
默认只有纯计算/文本等无副作用工具，用于验证平台。通用 Shell/HTTP/文件读写不纳入 V2。
Tool arguments 用 Pydantic 校验，身份和项目从 RuntimeContext 注入而不是接受模型声明。
模型可以申请审批，只有经过身份校验的人类决议才能放行；拒绝/过期/参数变化不能自动重试成批准。

## 8. 上下文与恢复

存储保留全部授权消息；提交模型的工作上下文可裁剪。先排除 UI 事件与过长结果，再按完整轮次裁剪，不能拆坏工具调用对。
摘要记录源范围和版本，保留最近消息和待处理动作；摘要不是新的高优先级指令，不能覆盖审批或身份。
摘要失败/取消保留旧历史，安全窗口仍超限则返回 context_limit；不删除历史、不无限压缩。
首期线性历史即可，不复制 Pi 的树分支浏览。

## 9. 拟定目录（未来实现，不是已存在文件）

~~~text
backend/app/agents/
  conversation/
    contracts.py  messages.py  events.py
    loop.py       tool_executor.py  budget.py  policy.py
    context_policy.py  compaction.py
    skills/loader.py  skills/catalog.py
  runtime/           # 保留旧 Workflow Runner
  registry/          # 复用，明确通用 Tool 与旧 Workflow Skill
  providers/         # 扩展 async stream，不破坏同步入口
backend/app/services/
  conversation_service.py  conversation_repository.py
backend/app/routers/conversation_router.py
backend/app/workers/agent_worker.py
backend/tests/conversation/
frontend/src/components/test-agent/
~~~

新模块名称可在 P01 小幅调整，但职责边界、数据合同、权限和测试不能省略。V2 不添加 Node.js 后端。

## 10. 运行与发布

正式使用仍需前端、FastAPI、独立 Worker 三个服务；P10 提供可复现启动和健康检查。
新聊天入口用独立 feature flag；保留旧生成入口但不自动注册到 conversation catalog。
V2 验收只检查基础 Agent 行为；用例质量、RCA 正确率、造数安全与缺陷模板属于 V3。

## 现状目录（V2-R01 结构整理后）

后端分层保留 routers / schemas / services / models，内部已按 Agent、LLM 归类：
`models/{agent,llm}`、`services/{agent,llm}`、`schemas/{agent,llm}`、`routers/{agent,llm}`；`app/agents` 仍是执行内核与既有 Workflow，`services/agent` 是平台应用服务（会话/Run/Artifact/审批数据访问）。`agent_save_service.py`（候选保存业务）保留在 services 根。目录分组是结构整理，不等同于依赖解耦；上述设计蓝图仍需在 V2-Pxx 内逐步落地。
