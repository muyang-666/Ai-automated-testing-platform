# Pi 源码阅读与 Python 实现对照

> 本文来自实际源码阅读，不只依据 README。检索日期：2026-09-03。
> 上游目录：D:\pi；origin：https://github.com/earendil-works/pi.git。
> 参考 commit：f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6，标题：fix(coding-agent): update interactive mode test fixture。
> 状态：P01 当前范围合同已翻译与轻适配，并通过 Codex 阶段复审（实际 90 项测试通过）；未安装 Pi npm 依赖、未运行上游测试。
> 2026-09-04：阶段语义已按 [新路线](../01_DEVELOPMENT_PLAN.md) 重排（P07=Test Artifact、P08=Artifact Tools + Test Design Skill、P10=Context/Approval/Recovery），下表“任务”列引用新阶段；本文件继续负责 Agent Core 的 Pi 对照，Artifact/MindMap/Diff 属 TestMind 自研业务层，不硬找 Pi 一一对应。

## 1. 固定版本的方法

先通过 GitHub 官方内容 API 阅读 bea67d90d1a74dde8852c63cac72d476013d3879 的 8 个关键文件；随后完整克隆仓库，HEAD 为以上参考 commit。已用 git diff 检查两个提交间 packages/agent、ai/src/types.ts、coding-agent/core/agent-session.ts 和 session-manager.ts 无差异。下方统一链接到克隆的参考提交。

只读查看命令（不切分支、不执行源码）：

~~~powershell
git -C D:\pi rev-parse HEAD
git -C D:\pi show f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6:packages/agent/src/agent-loop.ts
git -C D:\pi show f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6:packages/agent/test/agent-loop.test.ts
~~~

实施者必须对照固定提交。若需要升级基线，单独记录差异，不用 main 的浮动行号证明旧版本行为。

## 2. 源码层次与采纳范围

| 上游源码（固定链接） | 已核查的关键符号/行为 | Python 目标 | 任务 |
|---|---|---|---|
| [ai/src/types.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/ai/src/types.ts) | TextContent、ToolCall、AssistantMessage、ToolResultMessage、Usage、StopReason；文本和工具块分开 | 复用并扩展 LLMMessage/Result；协议边界归一化 | P01/P02 |
| [agent/src/types.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/types.ts) | AgentContext、AgentTool、AgentEvent、before/afterToolCall、prepareNextTurn、shouldStopAfterTurn | conversation/contracts.py、events.py、policy.py | P01/P03 |
| [agent/src/agent.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/agent.ts) | prompt、continue、steer、followUp、abort、waitForIdle；活跃调用与队列区分，reset 不能污染运行中 transcript | 对话实例、取消令牌、显式 follow_up；steer 首期不开放 | P03/P05 |
| [agent/src/agent-loop.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/agent-loop.ts) | runLoop、streamAssistantResponse、prepareToolCall、executePreparedToolCall；工具结果回到下一轮 | 有界 loop + executor；不带 ORM | P03 |
| [agent/src/harness/skills.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/harness/skills.ts) | loadSkills/loadSourcedSkills、formatSkillInvocation、frontmatter 和诊断 | 审核目录 catalog、load_skill 工具、按需注入；Skill=领域知识+行为规则 | P08（test-design） |
| [agent/src/harness/compaction/compaction.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/harness/compaction/compaction.ts) | estimateContextTokens、findCutPoint、prepareCompaction、compact；摘要与保留尾部 | context_policy.py、compaction.py；保留历史 | P10（Context） |
| [coding-agent/core/agent-session.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/coding-agent/src/core/agent-session.ts) | 高层 prompt/Skill 调用、事件订阅、重试/压缩/abort 协调；不是 Agent Loop 本身 | conversation_service + ConversationRunner | P04（持久化）/P06（Runner 接线） |
| [coding-agent/core/session-manager.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/coding-agent/src/core/session-manager.ts) | SessionEntry、parentId、compaction entries、buildSessionContext、appendMessage、版本化会话文件 | MySQL Repository + schema_version；首期线性历史 | P04/P10 |
| [agent/src/index.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/index.ts) | 导出 core、harness、skills、compaction、session 等，说明当前分层不只在 coding-agent 包中 | 明确依赖方向，禁止工具层反向引用前端 | P01 |
| [LICENSE](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/LICENSE) | MIT，Copyright (c) 2025 Mario Zechner | 翻译上游代码时保留声明并记录来源 | 全部 |

以上是 TestMind 的选择性映射，不是对每个上游模块的完整审计。没有读取全部 Provider 实现，不承诺全供应商兼容。

## 3. 真正要迁移的是行为，不是目录

Pi 的基本闭环允许模型不调用工具而直接回复；工具调用后生成对应结果消息，再交回模型。TestMind 的 conversation 模式必须遵守这个分离，而不是强行进入需求→覆盖→用例状态机。

重点差异：
- 上游有不受固定轮次约束的循环结构；TestMind 在每次物理模型调用/工具执行前检查预算和取消。
- 上游支持并行工具；TestMind 首期串行，避免 SQLAlchemy 会话共享与副作用顺序问题。
- 上游会话支持树/文件存储；TestMind 首期数据库线性会话，保留未来分支扩展但不建设 tree UI。
- 上游文件资源发现面更广；TestMind 只允许显式白名单资源根目录，禁用自动安装与脚本执行。
- beforeToolCall 可改变参数；TestMind 改后重新校验，防止绕过边界。
- 上游可能处理 thinking 内容；TestMind 不将隐藏推理保存为消息或展示。
- TestMind 的用户、项目权限、审批、Worker 租约、审计属于产品责任，不能从“使用 Pi 思路”推导已经安全。

## 4. 按上游测试提取行为样例

已检查 [agent-loop.test.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/test/agent-loop.test.ts)、[agent.test.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/test/agent.test.ts) 的测试名称和对应关键实现；尚未运行上游测试。

| 上游行为样例 | TestMind 验收样例 |
|---|---|
| transformContext 在 convertToLlm 前执行 | UI-only 事件先过滤，完整工具对再转换到 Provider |
| tool calls and results | call_id 不串配；工具结果可改变下一轮自然语言回复 |
| length-truncated assistant message 不执行工具 | 即使参数看似能解析也不能执行截断调用 |
| 工具完成顺序与结果持久化顺序区分 | 首期串行稳定；未来并行仍按原调用顺序重建模型上下文 |
| 参数预处理与 beforeToolCall | 类型校验、权限、审批逐层检查，修改后再校验 |
| 消息排队在合适边界处理 | follow_up 不制造同会话并行 Run；不撤销已完成动作 |
| await subscriber / waitForIdle | 关键结果落库成功后才发布可恢复的终态 |
| 工具结束后迟到 update 被忽略 | 取消、代次变化、租约丢失后不追加幽灵消息 |
| reset / prompt during processing | API 返回明确忙碌/队列语义，不破坏 transcript |
| shouldStopAfterTurn / terminating tool results | 明确预算和等待边界，不重复催促工具形成无限循环 |

测试目录已确认另有 skills.test.ts、sdk-skills.test.ts、agent-session-compaction.test.ts、agent-session-concurrent.test.ts。P08（Skill）/P10（Context）实施时还需阅读这些文件的具体测试正文；目录存在不等于已验证内容。

## 5. 移植记录与许可证

- 本次只产生规划，没有复制上游实现进入业务代码。
- 每个新模块若翻译上游实现，记录来源文件、commit、改动范围、行为差异和对应 Python 测试。
- 改编代码保留上游版权与 MIT 许可说明；后续提交相应第三方说明文件。
- 对外表述为“参考 Pi 架构的 Python TestAgent”，不称“Pi 官方 Python SDK”，不声称兼容 Pi 全部扩展。
- 前端仍为 React/JavaScript；“Python 实现”指服务端内核，不是把 Web UI 改写为 Python。

## 6. V2-P01-01/02 已落地映射（2026-09-03，编码未测）

上游（f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6）→ Python 对应：

| 上游 | Python（backend/app/agents/conversation/messages.py） | 差异/说明 |
|---|---|---|
| TextContent（ai/types.ts） | class TextContent | type 固定 "text"；text 可为空字符串 |
| ToolCall | class ToolCall | type="toolCall"、id、name、arguments（Record<string,any> → dict[str, Any]）；thoughtSignature/namespace 未译 |
| UserMessage | class UserMessage | content: string \| TextContent[]；role="user" |
| AssistantMessage | class AssistantMessage | content: list[TextContent \| ToolCall]，同一列表可混合两种块且保序、可为空；api/provider/usage/stopReason 等元信息未译 |
| ToolResultMessage | class ToolResultMessage | 独立消息 role="toolResult"，tool_call_id/tool_name/content/details/is_error；usage/addedToolNames 未译 |
| Message 联合 | Message = Annotated[Union[…], Field(discriminator="role")] + parse_message(TypeAdapter) | 按 role 判别解析 |
| createToolResultMessage（agent-loop.ts） | 本轮仅按对象关系翻译类型，函数执行逻辑留对应 Loop 任务 | 未实现执行/保序运行 |
| agent-loop.test.ts（工具结果源序/完成序测试） | 只读语义依据 | 运行测试留 Loop 任务 |

轻适配：Python snake_case（tool_call_id←toolCallId、is_error←isError）；补应用层 message_id/schema_version（真整数 1 严格校验）与调用方 timestamp（Unix 毫秒）；role 名保留 "toolResult"，Provider 适配时才映射旧接口 tool。

许可：改编自上游类型结构，保留 MIT 许可与 Copyright (c) 2025 Mario Zechner（完整文本已随 messages.py 注释与开发记录 2.3 记录）；未复制其他上游正文。

只读审查补充：timestamp 为 Pi 原有字段，Python 当前另限制为非负整数；应用层新增项是 message_id/schema_version。当前 Assistant/ToolResult 的 content 默认 [] 比 Pi 类型的必填字段更宽，后续同文件修改时收敛；Pi 执行器构造结果时对缺失 content 的归一化应留在对应构建位置。未运行功能测试。

## 7. V2-P01-03 字段映射与 None 适配（2026-09-03，编码未测）

| 上游（ai/types.ts，f41f804…） | Python（conversation/messages.py） | 说明 |
|---|---|---|
| StopReason（7 值） | StopReason = Literal[…] | 保留原值，未知拒绝，不默认为 stop，不含 Run 预算状态 |
| Usage + Usage.cost | Usage、UsageCost | snake_case（cacheRead→cache_read…、totalTokens→total_tokens）；上游必填仍须提供，允许显式 None=未知；cost 可 None；cache_write_1h/reasoning 可选默认 None |
| Usage 计数/费用 | _ensure_count_or_none / _ensure_finite_number_or_none（before 校验） | 非负整数/有限非负数字；bool/负数/NaN/Infinity 拒绝 |
| DeferredHandle | DeferredHandle | provider/model_id/api/id 必填；expires_at/poll_after_ms/data 可选；data 仅 JSON |
| AssistantMessage 模型元信息 | api/provider/model/usage/stop_reason 必填；response_model/response_id/deferred/error_message/raw_stop_reason/end_turn 可选 | providerThinkingLevel、diagnostics 未译 |
| ToolResultMessage.usage | usage: Usage \| None = None | 工具执行自身用量；addedToolNames 未译 |
| Assistant/ToolResult content 必填可空 | content 无默认值，允许 [] | Pi 对缺失 content 的归一化留结果构建函数 |

P01-03 只读复核：上一节 content 默认 [] 的差异现已收尾。DeferredHandle.data 的 _ensure_json_safe 当前还接受 tuple，并以 Any 原样保留，与上游 JsonValue[] 的数组表达及本项目“仅 JSON 数据”约定不符；下一次同文件修改时仅保留 list 分支，不引入额外规范化框架。以上为静态审查，未执行功能测试。

## 8. V2-P01 阶段收尾映射（2026-09-03，针对性测试 66 条通过）

| 上游（f41f804…） | Python（conversation/） | 差异/说明 |
|---|---|---|
| AssistantMessageEvent（9 种） | events.py 内 9 个事件模型 + AssistantMessageEvent 判别联合 | 字段 snake_case（content_index←contentIndex）；thinking_* 不入合同，未知 type 拒绝；done.reason 仅 stop/length/toolUse/deferred、error.reason 仅 error/aborted，并校验与消息 stop_reason 一致；partial 里保留 AssistantMessage 中间形状，toolcall_delta 的 delta 只作字符串 |
| AgentEvent（10 种，agent/src/types.ts） | events.py 内 10 个事件模型 + AgentEvent 判别联合 | agent_start/end、turn_start/end、message_start/update/end、tool_execution_start/update/end；message/toolResult 复用 messages.py 类型 |
| 事件应用层字段（项目轻适配） | AssistantEventEnvelope / AgentEventEnvelope | 外壳携带 schema_version/session_id/run_id/message_id/tool_call_id/sequence_no；按类型校验 message_id/tool_call_id 并能从内层核对；sequence_no 只校验正整数不分配 |
| validateToolCall/validateToolArguments（ai/src/utils/validation.ts，含 TypeBox 转换） | tool_validation.py 的 prepare_tool_call / validate_tool_calls_from_final_message | 只按既有 ToolRegistry 查名并走输入模型 Pydantic 严格校验；不复制 TypeBox 类型转换器；未知工具/无输入模型/参数错误安全失败，不回显敏感值 |
| failToolCallsFromTruncatedMessage / createToolResultMessage（agent-loop.ts） | tool_validation.py 的 not_complete 守卫与 build_tool_result_message | length/pending/error/aborted/deferred 阻断；stop/toolUse 均可携带工具块；结果构造 ID/名称取自原 ToolCall，content=None 归一化为 [] |
| DeferredHandle.data JsonValue[] | messages.py _ensure_json_safe | 阶段收尾修正：JSON 数组只接受 list，tuple/set 等拒绝（上一节静态审查登记已处理） |

已保留许可：MIT License / Copyright (c) 2025 Mario Zechner（完整文本随 conversation/messages.py 模块头）。真实执行保序/零副作用、Provider 流式与取消留 P02/P03。

## 9. P01 阶段审查修正项（2026-09-03）

第 8 节为实施者提交的映射与测试记录，不代表通过验收。Codex 实际反例表明：事件内部字段/嵌套关联校验不完整；参数入口未强制 strict、错误摘要可回显自定义校验器中的输入；无效输入模型不能安全失败；隔离测试缺少禁止尝试记录与负向自检。

Pi streamAssistantResponse 的 message_update 使用同一个助手快照；runLoop 的 turn_end 携带当轮助手消息与工具结果，下一次模型响应另有 turn_start/turn_end。当前合成正例与这些产生点有差异，需按源代码纠正，不增加独立历史扫描器。详见 [P01 审查证据](../reviews/V2-P01_REVIEW.md)。

## 10. V2-P01 集中修正映射（2026-09-03，79 条通过，待 Codex 复审）

| 审查缺口 | 修正（conversation/） | 差异/说明 |
|---|---|---|
| 错误摘要回显参数值/模型配置异常 | tool_validation.py：_safe_validation_summary 只输出受控 loc+标准 type；_is_valid_input_model 预检；非 ValidationError → validation_failed 固定文案 | 不复制 Pi validation.ts 的原始错误输出；配置问题(invalid_config)与参数问题(invalid_arguments/validation_failed)可区分 |
| 严格参数依赖模型配置 | prepare_tool_call 入口 model_validate(..., strict=True) | 本项目既定严格策略在可信边界强制，不依赖工具作者；保留模型 extra/字段策略 |
| 内部事件宽松/关联未闭合 | events.py：全部内部事件 strict+forbid；content_index 指向同类型块；toolcall_end 与 partial 快照一致；message_update 同 assistant message_id；turn_end.tool_results 必填 | 与 Pi streamAssistantResponse/runLoop 的实际产生位置一致；thinking_* 仍拒绝 |
| 合成样例 turn 语义 | test_synthetic_sample.py 两 Pi turn 事件序列 | turn_end.message=当轮助手消息、tool_results 单列；依据 runLoop（f41f804…）事件顺序 |
| 隔离自检缺失 | test_isolation.py：禁止尝试记录 + 导入/网络负向自检 | 网络保护只拦 socket.connect/create_connection，不破坏标准库导入；非宿主沙箱证明 |

## 11. V2-P01 复审收尾映射（2026-09-03，90 条通过，待 Codex 复审）

| 复审缺口 | 修正（conversation/） | 差异/说明 |
|---|---|---|
| 动态 loc/type/工具名回显 | tool_validation.py：对外固定错误码+固定文案，删去正则可信字段摘要 | 不转发 loc/type/msg/str(exc)/工具名；动态字典键、未知字段名、PydanticCustomError 自定 type 一律不回显 |
| 候选构造漏出 ValidationError | PreparedToolCall 构造纳入 try；model_dump 结果必须为 dict，否则 validation_failed | 覆盖校验、序列化形状、候选构造三段；错误码区分 invalid_arguments/validation_failed |
| 隔离网络逐项与尝试记录 | test_isolation.py：connect/create_connection 独立布尔、正式阶段尝试记录并判失败、故障注入自检 | 不破坏标准库导入（只拦方法）；非宿主沙箱声明不变 |
| Pi 合法早期 partial 空调用 ID | messages.py ToolCall.id 允许空串；toolcall_end 与候选/结果构造要求有效 ID | 依据 ensureToolCallBlock（openai-completions.ts，f41f804…）；不伪造 ID、不用 model_construct |
| 工具结果消息生命周期事件 | test_synthetic_sample.py 补 tool_result 的 message_start/message_end（在 tool_execution_end 与 turn_end 之间） | 依据 agent-loop.ts emitToolResultMessage（800–803 行）；按稳定 message_id 断言 |

历史 66/79 passed 与两次审查记录保留；真实执行/Provider 流式/持久化仍留后续阶段。

## 12. P01 最终复审（2026-09-03）

Codex 已核对第 10 节当前实现与回归，并实际运行完整 P01 套件：90 passed in 5.41s。当前约定的合同/纯校验范围验收通过，见 [验收证据](../reviews/V2-P01_ACCEPTANCE.md)。历史章节中的“待修/待复审”描述对应当时快照；后续 Provider 聚合、错误协议诊断与实际执行仍须在相应阶段验证，不以本次合同验收宣称完整 Pi 兼容。

## 13. V2-P02 流式 Provider 映射（2026-09-03，部分实现并测试，未验收）

| 需求（P02 任务书） | 实现 | 状态/差异 |
|---|---|---|
| 流入口/事件输出 | providers/streaming.py + openai/anthropic stream adapter，输出 P01 AssistantMessageEvent | OpenAI 与 Anthropic typed 路径已测基础文本/工具；unknown raw SSE 差异已登记 |
| 请求转换（两类历史） | streaming.py 纯转换 | 四消息历史 openai/anthropic 已测，含 tool_result 分组与错配拒绝 |
| 单层重试/预算/取消 | services/llm/llm_stream_gateway.py | 已测重试/预算/预检/取消/不重放 |
| OpenAI SSE 解析/限额/usage/[DONE] | openai_stream_adapter.py | 已测文本/工具/空 choices usage/断流/帧限/非 JSON |
| Anthropic messages.create typed 事件 | anthropic_stream_adapter.py | 已测 end_turn、ping+空、tool_use partial_json |
| 高级矩阵（并发/取消 task/索引重映射/raw SSE/httpx2 契约等） | 未完成定向测试 | 登记为阶段未验证项 |

## 14. V2-P02 集中修正与最终映射（2026-09-04，Fake 范围验收通过）

第 13 节保留首次实现快照。本节记录其后集中修正后的事实；固定上游仍为 `f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6`。

| Pi / 协议行为 | TestMind Python 实现 | 轻适配与验收证据 |
|---|---|---|
| `ensureToolCallBlock` 按供应商 index 建块并在增量时更新 | `openai_stream_adapter._OpenAIAssembler` | 允许早期空 ID；两个调用交错、ID 延后、start/end 唯一；终态严格 JSON 对象，`{}` 合法，任一坏调用令整条消息失败 |
| OpenAI Chat Completions 原始 SSE、`[DONE]`、最后 usage 块 | `OpenAIStreamAdapter` + `BoundedSSEDecoder` | 显式 Bearer；多 data 行以换行连接；frame/tool/累计输入按 UTF-8 字节有界；等待完整终止证据和 choices=[] usage |
| Anthropic `content_block_start/delta/stop` 与 raw SSE | `AnthropicStreamAdapter` + `_AnthropicAssembler` | SDK `with_streaming_response.create` 只负责真实请求/响应生命周期，原始字节由共享解码器消费；未知事件可见失败；thinking 过滤并重映射本地索引 |
| AssistantMessageEvent 唯一 start/终态 | 两 Adapter 输出 P01 事件，LLMStreamGateway 抑制隐藏重试的重复 start | 每块 start/delta/end 完整且快照深拷贝；一个逻辑流唯一 done/error，不输出 AgentEvent |
| `convertMessages` 中工具调用/结果关联 | `streaming.to_openai_messages_and_tools` / `to_anthropic_system_messages_and_tools` | snake_case；按相邻批次核对 ID、名称、重复和遗漏；Anthropic 结果合为 user tool_result；不执行工具 |
| Provider 单次请求与上层重试分层 | `LLMStreamGateway`，由现有 `LLMGateway.stream` async context manager 管理 | capability_overrides/别名复用；共享 AttemptBudget 与本地 retry_no 分开；每物理请求一个 AttemptRecord；提前退出确定关闭 |
| Pi Usage 的独立 input/cache/output 语义 | 两聚合器生成 P01 Usage | OpenAI prompt_tokens 减已知 cached_tokens 得非缓存 input；Anthropic 累计 usage 覆盖；未知为 None，不计算费用 |
| 上游取消与事件流关闭语义 | `await_controlled` + Gateway 上下文 | cancel_event 覆盖等响应头/读块/退避；有限总 deadline；Task.cancel 重抛；残留等待任务收尾 |

Python 额外门禁为项目既定安全适配：严格终态 JSON、固定错误文案、不保存隐藏 thinking、显式资源限额、无环境凭证回落、响应 ID 与请求跟踪 ID 分离。没有复制 Pi 的兼容供应商全集、价格表、deferred/pause/server tools 或 Agent Loop。

最终证据：P02 54 项、P01 90 项、旧 Provider/Gateway 55 项分别通过，见 [P02 验收记录](../reviews/V2-P02_ACCEPTANCE.md)。未调用真实供应商；线上兼容性留 P10。改编模块保留 MIT 与 Copyright (c) 2025 Mario Zechner 说明。

## 15. V2-P03 Agent Loop 与工具执行映射（2026-09-04）

| Pi 固定提交符号 | TestMind Python | 保留与适配 |
|---|---|---|
| `runLoop` | conversation/loop.py `run_agent_loop` | 模型→工具→结果→下一模型；Agent/Turn/Message 事件顺序；steering/follow-up/持久化分别留 P05/P04 |
| `streamAssistantResponse` | loop.py `_stream_assistant` | P02 start→message_start、块事件→message_update、终态→message_end；Provider 不发 AgentEvent |
| `prepareToolCall` / `validateToolArguments` | P01 prepare_tool_call + P03 policy/evaluate_policy | 复用 ToolRegistry/Pydantic；策略改写参数后再次 strict 校验是项目加固 |
| `executeToolCallsSequential` | tool_executor.execute_tool_call + loop 串行 for | 首期只串行；结果按调用源序，重复 ID 执行前拒绝；不导入 SQLAlchemy Session |
| `executePreparedToolCall` 更新回调 | ToolHandlerContext.report_update | handler 完成瞬间停止接收 update；取消/截止清理异步任务，迟到更新丢弃 |
| `createToolResultMessage` / `emitToolResultMessage` | P01 build_tool_result_message + P03 message_start/end | ID/名称取原调用；校验/策略/工具异常形成固定安全结果供下一轮修正 |
| `AgentToolResult.terminate` | ToolExecutionResult.signal | 扩为 continue/stop/wait；P03 不实现审批等待的持久恢复 |
| AbortSignal | asyncio.Event + monotonic deadline | 异步策略/工具可协作取消；同步 handler 只能调用前后检查，不能物理抢占 |
| 上游无本项目四项统一硬限制 | AgentLoopLimits / AgentLoopBudget | max_turns/model_calls/tool_calls/deadline；P02 AttemptBudget 单独计物理请求 |

默认策略阻止 `requires_approval`、`required_permission` 和非只读工具，不把模型请求当成授权；Approval 按动作风险接入（P10，不再以“P09 固定门禁”表述）。取消/截止会为批次中剩余工具建立关联的“未执行”结果，保证之后可识别每个 call_id；这是为持久恢复做的 Python 适配。

验收见 [P03 验收记录](../reviews/V2-P03_ACCEPTANCE.md)：P03 30 项、P02 54 项、P01 90 项、旧 Provider/Gateway 55 项、ToolRegistry 4 项分别通过。没有真实模型/数据库/业务工具调用；Calculator/Echo 都是内存测试夹具。改编代码保留 MIT 与 Copyright (c) 2025 Mario Zechner 说明。

## 16. V2-P04 会话持久化与恢复映射（2026-09-04）

| Pi 固定提交行为 | TestMind P04 | 差异/原因 |
|---|---|---|
| SessionMessageEntry 保存完整 AgentMessage | AgentMessage.content_json 保存 P01 消息，另存 message_id/schema_version/timestamp_ms | 关系表便于 owner、Run、幂等与游标查询；恢复仍经 P01 parse_message |
| appendMessage 追加并推进 leaf | 数据库 next_message_sequence 原子分配后 INSERT | P04 只做线性历史；不复制树 leaf/parentId |
| buildSessionContext 按路径重建消息 | restore_conversation_messages 按 sequence_no 重建 | compaction 留 P10；损坏版本或 ID 不静默跳过 |
| Session header version | 每条消息 schema_version + session.mode | 兼容旧平台表；既有 session 回填 legacy_workflow |
| 本地 JSONL 会话文件 | SQLAlchemy AgentSession/Run/Message + Alembic 0003 | TestMind 已是多用户 Web 平台，需要事务、并发约束和 owner 隔离 |

项目新增的数据库规则：conversation project_id 可空；用户消息、queued Run 和幂等键同事务；Run 的 active_slot 唯一/check 约束限制一个活跃 Turn；消息/事件序号由会话行原子游标分配。user_message_id 不建反向 FK，避免与 message.run_id 形成循环外键，服务在同事务核对关联。

旧 Workflow 行为保持：旧会话 mode=legacy_workflow 且 project_id 必填；旧发消息/用例生成入口拒绝 conversation；项目读者不能读取别人的 conversation Run；P05 前旧 Worker 不抢 conversation queued 行。

迁移 head 为 `0003_conversation_persistence`，down_revision=`0002_agent_platform_tables`。升级回填旧模式/游标，head 重叠结构需核验；有 conversation/版本化消息数据时 downgrade 拒绝有损转换。验收见 [P04 验收记录](../reviews/V2-P04_ACCEPTANCE.md)。仅使用临时 SQLite，未验证真实 MySQL；不声称兼容 Pi 分支树。
