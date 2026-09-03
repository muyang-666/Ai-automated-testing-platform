# V2-P01：源码行为基线与消息、事件、工具合同

> 2026-09-03。单任务实施提示词；尚未执行，不是完成报告。

你在 Windows 项目 D:\Ai-test-assistant 中实施 TestMind V2-P01。用户有 Python 和接口自动化基础，正在边开发边学习。

先核验真实源码并输出简短实施摘要，然后直接编码，无需等待二次确认；完成本任务后停止，不自动进入下一任务。

## 1. 任务目标与版本边界

只完成 V2-P01：建立可独立导入、可验证的纯 Python 对话数据合同和合成行为基线，为 P02 Provider 与 P03 Agent Loop 提供接口。

V1 既有测试平台保持兼容。V2 最终是能持续交流、按需使用 Skill 的 Python Agent；普通聊天不要求项目、需求文档或 JSON 回复。测试用例生成、根因分析、造数与缺陷描述属于 V3。通用权限、审批、预算属于 V2，但 P01 仅固定本任务需要的合同，不实现后续执行机制。

P01 完成不代表浏览器已经能聊天，也不代表已有 Agent Loop 或真实模型验收。

## 2. 交接时已核实的事实与待核查项

Codex 已于 2026-09-03 只读检查，开始实施时仍须复核：

- 新计划和开发记录将 P01～P10 标为待实施；未发现 backend/app/agents/conversation 和 backend/tests/conversation。
- backend/app/schemas/llm/llm_gateway.py（V2-R01 目录整理后的位置）已有 LLMMessage、LLMToolCall、LLMResult；支持 text/json/pydantic，工具参数现为 arguments_json 字符串。LLMMessage 尚无新对话稳定消息 ID、版本化有序内容块合同。
- backend/app/agents/runtime/contracts.py 的 RuntimeContext 带 db、project_id；AgentWorkflow 提供 next_step/execute_step。runtime/runner.py 按 Workflow 推进，不是新对话循环。
- registry/tool_registry.py 已有 ToolDefinition、ToolRegistry，包含输入/输出模型和权限、只读、审批等声明；不要另建同职责注册系统。
- AgentSession/AgentRun 的 project_id 仍非空；AgentMessage 有 content/content_json；AgentEvent 使用字符串 event_type 和 payload_json。数据表及迁移本任务不修改。
- frontend/src/components/test-agent/useAgentSession.js 的 send 仍校验来源/项目，先 appendAgentMessage 再 createAgentRun；现有入口仍是用例工作流。
- 工作区有用户未提交修改，包括 Gateway 空响应重试、Runner 诊断、对应测试及前端提示。它们不是新 P01 成果，也没有在本轮重新验证。原样保留。
- backend/app/core/database.py 在模块顶层调用 ensure_mysql_database_exists；backend/tests/conftest.py 会导入数据库和全部模型并初始化隔离 SQLite。不能用普通测试环境已加载数据库的事实证明新内核无副作用。
- 项目解释器为 D:\Ai-test-assistant\.venv\Scripts\python.exe；仅用元数据核实 Python 3.11.9、Pydantic 2.9.2、pytest 8.3.3，未运行项目测试。
- Pi 位于 D:\pi，核实 HEAD 为 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6；仅只读参考。

仍待你核查：当前 git status、适用的项目指引、是否有人已新增 P01、包导入链、pytest 收集隔离方式、具体字段/状态定义及其与旧 DTO 的映射。若已有增量，接续而不覆盖；若 P01 已实施，审查缺口，不重复重建。

真实模型绑定、Worker 是否启动、真实 MySQL 与历史空响应问题均未在本轮验证，不能宣称已解决。不要为核查这些问题扩大 P01。

## 3. 必读资料与固定上游参考

先读 D:\Ai-test-assistant 下：

1. docs/PROJECT_RECORD.md
2. docs/V2/README.md
3. docs/V2/01_AGENT_DEVELOPMENT_PLAN.md（重点 P01 及 P02/P03/P04 边界）
4. docs/V2/04_AGENT_SHELL_PRD.md
5. docs/V2/06_TEST_AGENT_PLATFORM_ARCHITECTURE.md
6. docs/V2/10_PI_SOURCE_AUDIT.md
7. docs/V2/02_DEVELOPMENT_RECORD.md
8. docs/V2/03_ACCEPTANCE_CHECKLIST.md
9. docs/V2/08_LEARNING_BACKLOG.md

然后读取上一节列出的相关源码，重点看完整小调用链，不递归扫描 .claude 或读取凭证文件。旧 docs/archive/PRE_PI_V2_2026-09-03 内的 V2.1-Txx 只作历史证据，不按其“下一步”实施。

Pi 只读命令示例：

```powershell
git -C D:\pi show f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6:packages/ai/src/types.ts
```

用同一固定提交读取这些文件及相关函数/测试正文：

- packages/ai/src/types.ts：TextContent、ToolCall、AssistantMessage、ToolResultMessage、Message、StopReason、AssistantMessageEvent。
- packages/agent/src/types.ts：AgentContext、AgentTool、AgentEvent。
- packages/agent/src/agent-loop.ts：runLoop、streamAssistantResponse、failToolCallsFromTruncatedMessage；只提取与合同有关的行为。
- packages/agent/src/agent.ts：prompt、abort、waitForIdle，用于核对一次运行与持续会话的区别。
- packages/agent/test/agent-loop.test.ts：should handle tool calls and results；should not execute tool calls from a length-truncated assistant message；should apply transformContext before convertToLlm。
- packages/agent/test/agent.test.ts：异步订阅完成、忙碌时 prompt、工具结束后迟到更新的相关测试。只记录后续约束，不提前实现队列或取消。
- LICENSE。

已核实的重要差异：Pi 的 turn 是一次助手响应加本轮工具调用/结果；不是 TestMind 一次用户输入的 ConversationTurn。Pi 的 agent run 还可吸收 follow-up，不能与 TestMind 的一请求一 Run 强行一一对应。Pi 消息角色 toolResult 在 TestMind 对外 Provider 合同中可映射为 tool。Pi 核心消息不统一提供 TestMind 所需的应用层稳定 message_id；AgentEvent 也不自带产品会话游标等字段，这些需要我们补充。

## 4. 允许修改的范围

- backend/app/agents/conversation/：以 contracts.py、messages.py、events.py 为建议职责划分，必要的 __init__.py 保持无副作用。文件数量不是硬指标，不为凑目录拆空模块。
- backend/tests/conversation/：纯合同测试、隔离导入测试及少量合成 fixtures；如需局部 conftest，只服务本目录且不得加载数据库。
- 本任务的 docs/V2 文档、docs/PROJECT_RECORD.md 状态摘要、当前提示词文档。
- 若实际改编上游实现，允许添加最小第三方来源/许可说明，保留固定提交对应版权与 MIT 文本。

默认不修改旧 Gateway/Provider、Workflow Runner/Registry、ORM/Service、Worker、Router、前端、数据库迁移和依赖文件。新模块可以复用经确认无副作用的纯类型，但不得为复用 DTO 引入配置/数据库初始化。超出上述范围先说明实际必要性和影响，获取授权。

## 5. 必须固定的合同

“合同”指程序各部分交换数据时共同遵守的字段、类型与校验规则。使用现有 Pydantic 2 实现运行时校验，不只写类型注解。

### 5.1 消息与处理单位

- ConversationTurn：一次用户输入及其完整处理过程，关联 session_id、run_id、user_message_id；未来复用 AgentRun 存储，本任务不创建表、不调用 ORM。
- ModelTurn：该过程中一次逻辑模型请求及响应，关联所属 run_id、明确的 model_turn_id/序号。工具执行结果可促成下一个 ModelTurn。Provider 的物理重试尝试另行计数，不能靠 ModelTurn 数冒充实际调用成本；P02 实现尝试统计。
- Message：稳定 ID、schema_version、role、有序内容块；至少支持 text、tool_call、tool_result。用户纯文本、助手纯文本、助手“文本 + 多个工具调用”、工具成功/失败结果都可表达。
- user 消息不携带 tool_call/tool_result；tool_call 属于 assistant；tool_result 属于 tool 并引用 tool_call_id。系统策略与工具/用户数据分离；不把工具返回的文本提升为 system。若表示 system 消息，只允许可信内部构造的文本策略，不实现用户可自选 role 的入口。
- 明确 ID 类型、唯一性作用域、生成职责与未来旧整型 ORM ID 的映射，选定一致方案，不使用任意 int/str 混合或静默强转。序列化往返必须保留 ID 和内容块顺序，不在读取时重新生成 ID。
- schema_version 初始为明确支持版本；未知角色、块类型、版本、非法字段组合必须拒绝。无关额外字段采用明确策略；关键协议模型优先 forbid。
- 普通回复“你好”按 text 保存，不能被解析为用例 JSON。内部消息使用 JSON 序列化，不意味着回复正文必须是 JSON。

### 5.2 工具调用与结果

- ToolCall 至少包含调用 ID、名称、完整参数对象；ToolResult 至少包含对应 tool_call_id、结果内容、成功/失败标识及安全错误码。身份和权限不从模型参数中取得。
- 原始参数分片与最终完整参数区分。分片可作为事件中的字符串保存，不做容错补全、不转换为已验证调用。
- 添加最小纯校验入口：仅在助手响应完整结束、结束原因允许工具请求、参数是合法 JSON 对象且通过对应输入模型校验时，产出“参数已验证的候选调用”。未知工具/无输入模型等情况明确失败，不绕过校验。
- 候选调用不等于获得执行许可；实际权限、审批、预算检查与 handler 执行由 P03/P09 等任务完成。本任务的入口不调用任何 handler，不实现 Tool Executor。
- 输出截断 length、未结束、错误、取消等响应不能产出候选调用，即使参数恰好是合法对象也必须拒绝。不要把只判断 JSON 能否解析当完整性检查。
- 对历史工具结果提供必要纯校验：必须对应同一历史/Turn 内先前的调用；拒绝孤立结果、重复结果、重复调用 ID 和错配。同一助手可有多个调用，按原调用顺序表示结果。待工具结果的中间历史可保存，但与可再次提交模型的完整工具对视图区分；不要拒绝所有合法中间状态。
- 输入模型严格校验，不为通过测试修改原有业务断言；P03 中 hook 修改参数后仍须重新校验，P01 记录此约束即可。

### 5.3 事件与结束原因

- Event 是运行通知，不自动加入模型消息历史。选定一套含义明确的事件命名，区分 conversation_turn 与 model_turn，不机械复制 Pi 的 turn_start 名称。
- 最小覆盖本轮所需的处理开始/结束、模型开始/结束、消息开始/文本增量/结束、工具参数增量、工具执行开始/结束。仅定义数据，不实现发布器、SSE、执行引擎或完整事件回放器。
- 统一事件外壳包含 schema_version、session_id、run_id、message_id、tool_call_id、sequence_no；涉及模型时关联 model_turn_id。字段可以按事件类型允许空值，但不允许“全部 Optional 所以任何载荷都通过”。消息事件必须关联 message_id，工具事件必须有 tool_call_id；明确工具事件的 message_id 指请求消息还是结果消息。
- sequence_no 是会话内事件游标；校验正整数，说明由持久化层分配。本任务不实现 max+1、全局计数器或数据库序号分配；消息序号与事件序号不要混用。
- 用有限事件联合类型/明确解析入口拒绝未知事件、缺字段和错误载荷；delta 指向同一个稳定消息，不能一片一个新消息。
- 分开表示模型结束原因、消息完整性和 ConversationTurn 终态。至少区分正常文本结束、工具请求、空结果、length 截断、Provider 错误/断流、拒绝、取消与预算耗尽。预算耗尽是执行层停止原因，不伪装成模型返回；未知原因保留安全诊断且不默认成功。普通文本截断标记 incomplete。
- 空文本但含完整工具调用合法；文本和工具都没有的空响应不得算正常成功。未知 token 用 None，不用 0 冒充已测量。这里仅定义语义，不实现重试或预算执行器。
- 当前 Turn 失败/取消不意味着 Session 关闭；工具失败结果不自动意味着整个 ConversationTurn 失败。终态之后不应再接受该执行的迟到增量，实际拦截在后续任务实现，本任务记录约束。
- 不定义或保存隐藏思维链字段，不透传任意 Provider 原始响应/密钥到事件。

## 6. 正常、异常与兼容验收

围绕合成聊天/echo/计算数据测试，不用测试用例生成作为基础示例。计算结果是静态夹具，本任务不实现 calculator。

必须提供可追踪的测试：

1. 中文普通消息与助手回复序列化/反序列化相等；正文不是 JSON 也成功；ID、版本不变化。
2. 助手混合文本和两个工具调用往返保序；成功/失败工具结果正确关联；拒绝角色冒充、孤立/重复/错配 ID；合法待结果状态可表示。
3. 完整工具请求且空文本通过候选参数校验；非法 JSON、非对象参数、输入模型不匹配、未知工具被拒绝。
4. 参数分片未完成不能产出候选；length 即使携带合法参数也不能产出候选；error/aborted 同样阻断。本任务只证明纯校验边界，实际工具零执行验收留 P03。
5. 未知事件类型/版本、缺少按类型必填的 message_id/tool_call_id、错误载荷、非法 sequence_no 被拒绝。
6. 正常结束、合法工具请求、空结果、截断、失败、拒绝、取消和预算停止可区分；错误组合不能变成 succeeded；未知用量仍为 None。
7. 提供一个“一次用户请求 → 两次 ModelTurn → 一次工具结果 → 最终回复”的合成消息/事件样例，验证引用关系和往返。明确这是预期轨迹数据，不是 Loop 已经运行的证据。
8. 在全新子进程中，导入全部新 conversation 模块之前就设置禁止数据库/配置/网络客户端导入或连接的保护，导入后验证未加载 app.core.database、app.models、真实 Provider 等。不能仅在已加载数据库的父 pytest 进程查 sys.modules，也不能导入后才 patch。该保护出现禁止导入必须让测试失败。

兼容要求：旧 complete、LLMMessage/LLMResult、旧 Workflow/业务入口行为不变。说明新旧字段映射，但不提前实现 Provider 适配或 ORM 转换。不要重跑全部后端测试或把历史 passed 数量算入 P01；如果确实触碰旧公共模块，先满足范围授权，再补直接相关回归。

## 7. 项目环境下的验证命令

先静态核验测试导入路径。新目录测试不使用旧数据库 fixtures；以下命令通过 confcutdir 排除父级 tests/conftest.py，通过禁用第三方 pytest 自动插件减少隐式初始化。不能只写命令而不运行。

```powershell
Set-Location D:\Ai-test-assistant
git status --short
& .\.venv\Scripts\python.exe -I -c 'import sys, importlib.metadata as m; print(sys.version); print({p: m.version(p) for p in ["pydantic", "pytest"]})'

Set-Location D:\Ai-test-assistant\backend
$p01OldPluginSetting = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
try {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    & ..\.venv\Scripts\python.exe -m pytest --confcutdir=tests/conversation tests/conversation -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'P01 targeted tests failed; inspect and fix within scope.' }
}
finally {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $p01OldPluginSetting
}

Set-Location D:\Ai-test-assistant
git diff --check -- backend/app/agents/conversation backend/tests/conversation docs/V2 docs/PROJECT_RECORD.md
git status --short
```

目录需先由本任务实现创建；若你的实际命名有小幅调整，报告对应实际命令及理由。diff --check 不覆盖未跟踪文件，新增文件需另行检查。对检查发现的既有无关问题如实记录，不扩大修复范围。新合同导入隔离的证据来自第 8 项子进程测试，不来自 confcutdir 选项本身。

只用项目 .venv，不用全局 pip，不安装新依赖，不运行 Pi 测试、不启动任何服务、不调用真实模型或真实数据库。

## 8. 文档更新

- docs/V2/10_PI_SOURCE_AUDIT.md：追加 P01 上游文件/符号 → Python 合同/纯函数 → 对应测试映射；记录 Pi turn 语义与稳定 ID/事件外壳等差异；说明是设计参考还是实际代码改编，改编则保留来源和许可。
- docs/V2/02_DEVELOPMENT_RECORD.md：记录本任务实施范围、实际文件、真实命令、结果和未验证事项；完成状态写“已实施/针对性测试通过，待导师审查”，不得代替用户或导师宣称最终验收。
- docs/V2/03_ACCEPTANCE_CHECKLIST.md：只更新有证据的 P01 项，关联测试；其他 P 项保持未完成。
- docs/V2/08_LEARNING_BACKLOG.md：分别记录“代码实践”和“用户理解”；实现通过不能写成用户已掌握。
- docs/V2/01_AGENT_DEVELOPMENT_PLAN.md、docs/V2/README.md、docs/PROJECT_RECORD.md：仅同步 P01 实际状态，保留 P02～P10 待实施，不重写版本边界或历史记录。
- 当前提示词若有必要只附实际执行说明，不把尚未执行的计划改写为测试事实；不改旧归档。

## 9. 完成报告与停止边界

完成报告按此顺序：

1. 面向用户的 2～4 句：这次增加什么、用户现在可以验证什么、浏览器尚不能因此获得什么能力。
2. 实际修改文件与职责；与既有未提交修改的关系。
3. 最终合同字段/状态与一段合成消息轨迹；解释 ConversationTurn 与 ModelTurn 的区别。
4. Pi 固定提交、来源文件/函数、采纳内容、有意差异及许可处理。
5. 实际执行命令、退出结果、用例范围；分别列已核实、仅设计、未运行/受阻事项。不编造通过数。
6. 兼容性、导入无副作用的测试证据、已知限制。
7. 更新文档与一个学习复盘点；“用户理解待确认”。
8. P01 是否具备提交导师审查的证据；下一项只建议 P02，不执行。

新增依赖、真实数据库操作、真实模型调用/费用、破坏性操作或任务越界时，说明具体动作与原因并获取授权。普通范围内编码不重复确认。不要 git commit/push/reset/checkout/restore，不丢弃用户改动，不恢复旧任务路线，不启停用户服务，不读取/输出 API Key、Token、数据库密码，不使用实习项目数据或 Skill，不创建其他 AI 任务。

完成 P01 后停止，等待用户带回报告供导师审查。
