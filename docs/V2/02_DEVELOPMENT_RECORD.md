# 新 V2 开发记录：对话式 Test Agent

> 更新：2026-09-04。旧路线记录已原文归档，不删除其中最新修复与测试证据。
> 当前状态：V2-R01 与 V2-P01～P08 已完成各自声明范围验收；P09.1～P09.3B.2 已实现并完成自动化回归，P09 浏览器验收仍有 >20 条真实翻页、现场 realtime 与双浏览器场景未覆盖，不进入 P10。
> P05～P10 阶段主题为 Conversation Runtime 收敛 / Conversation API / Test Artifact Core / Artifact Tools / Chat+MindMap+Diff / Context+Approval+Recovery（不沿用旧“Skill / 上下文 / 人工门禁”标题）。

## 1. 当前任务状态

| 编号 | 内容 | 状态 | 证据 |
|---|---|---|---|
| V2-R01 | Agent / LLM 模块目录整理（结构，先于 P01） | 已完成 | 6 条结构测试 + 338 条受影响/回归通过，见 2.1 |
| V2-P01 | 基线与数据合同 | 阶段验收通过（限定合同/纯校验范围） | Codex 实际 90 passed in 5.41s，见 2.10 |
| V2-P02 | 流式 Provider | 阶段验收通过 | P02 54、P01 90、旧 Provider/Gateway 55，见 2.14 |
| V2-P03 | Agent Loop / Tool Executor | 阶段验收通过（纯 Python/Fake 范围） | P03 30 项；P02 54、P01 90、旧 Provider/Gateway 55、ToolRegistry 4 项回归，见 2.15 |
| V2-P04 | 会话存储与迁移 | 阶段验收通过（临时 SQLite/真实事务范围） | P04 20 项；P01 90、P02 54、P03 30、旧平台 100 项回归，见 2.16 |
| V2-P05 | Conversation Runtime 收敛 + Workflow 退役 | 已完成 | B/C/D/E 验收，见 2.18～2.21 |
| V2-P06 | Conversation API + SSE + 基础工作台 | 已完成声明范围 | 见 2.22～2.26 与 P06-R01/R02 |
| V2-P07 | Test Artifact Core | 已完成 | P07/P07.1，见 2.27～2.28 |
| V2-P08 | Artifact Tools + Test Design Skill | 已完成 | 23 项 Tool/Agent 场景 + 24 条 Scripted Eval，见 2.29 |
| V2-P09 | Chat + MindMap + Diff 协作工作台 | 进行中：P09.1～P09.3B.2 实现完成；自动化与单浏览器主流程通过，三类真实浏览器场景待补（见 2.40） | 按 [01](01_DEVELOPMENT_PLAN.md) |
| V2-P10 | Context / Approval / Recovery / E2E | 待实施 | 同上 |

## 2. 2026-09-03 — 重新划分 V2/V3 并阅读 Pi

用户授权：重写 V2 文档为 Pi 基本架构的 Python 实现；测试能力后移到 V3；克隆 Pi 到 D 盘。

实际工作：
- 通过 GitHub 与官方内容 API 阅读 Agent/Loop/消息/Skill/会话/压缩源码；
- git clone https://github.com/earendil-works/pi.git D:\pi 成功，origin 正确，参考 HEAD 为 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6；
- 已检查关键模块与早先读取提交的差异为空，参考仓库工作区干净；没有执行 npm install/build/test；
- 旧 V2 全部文档和旧根入口完整归档，包含旧 02 中创建会话 500 与空响应修复记录；
- 新 V2 任务使用 P 编号，新增 V3 测试路线，原用例代码作为复用资产；
- 仅修改文档，不修改后端/前端代码，不运行真实模型、不操作业务数据库、不额外 git commit/push。

验证：只做归档内容保全、链接/路线一致性和变更范围检查；这是文档检查，不是新 Agent 功能测试。最终检查结果由本次交付说明记录，后续每个任务另写实际命令。

本次检查结果：
- 21 份旧文档快照与调整前工作区正文一致（规范化行结束和 EOF 空白后比较，0 个差异）。
- 22 份当前入口文档中检查 65 个本地 Markdown 链接，0 个断链。
- 当前路线 README/docs 的 git diff --check 通过；原业务代码的未提交改动仍保留。
- D:\pi 的 origin/HEAD 已核对，git status --short 为空；未安装依赖、未运行 Pi 或项目测试。

## 3. 旧成果与未解决问题

[旧开发记录](../archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)保留旧任务编号、日期、测试命令和问题。不要将其中 33/50/102/288 等历史测试数汇总为新 V2 验收数。

可复用：Gateway、Agent 表/Service、原子抢占、用例确定性工具和已有前端。
待补：真正的文本对话循环、模型工具回传、无项目聊天、流式适配、可靠事件恢复、租约/取消、通用 Skill。
现场环境仍须核查：模型空响应原因、模型场景绑定、Worker 启动、MySQL 与孤立业务引用。重规划不等于这些问题已修复。

## 4. 后续任务记录模板

每个 V2-Pxx 追加：授权范围 → 修改前事实 → 上游参考 commit/文件 → 实际文件 → 迁移/兼容 → 实际命令/结果 → 已知差异 → 下一项边界。
新任务证据不得覆盖本次归档。

## 2.1 2026-09-03 — V2-R01 Agent / LLM 模块目录整理

### 授权与范围

纯结构整理：保留 routers/schemas/services/models 分层，在内部按 Agent、LLM 归类。只移动文件、补包导出、更新导入与文档，不改变任何业务行为、API 合同、表结构或 Prompt/审批规则。不动 D:\pi、不接 npm、不操作真实数据库/模型/运行服务。

### 实际文件映射（旧 → 新）

| 类 | 迁移 |
|---|---|
| models/agent | agent_session / agent_message / agent_run / agent_step / agent_event / agent_artifact / agent_approval.py |
| models/llm | llm_provider / llm_model / llm_scene_config.py |
| services/agent | agent_session_service / agent_run_service / agent_artifact_service / agent_approval_service.py |
| services/llm | llm_config_service / llm_client_service / llm_gateway.py |
| schemas/agent | schemas/agent.py → agent/api.py；agent_platform.py → agent/platform.py（api.py 为唯一 API Schema 实现，包 __init__ 仅显式重导出） |
| schemas/llm | llm_config.py、llm_gateway.py |
| routers/agent | agent_router.py |
| routers/llm | llm_config_router.py |

未移动：agent_save_service.py（测试候选保存业务，保留在 services 根，仅更新其内部 import）；app/agents/ 全部（执行内核与既有 Workflow）；app/workers、app/core、app/exceptions、app/utils；用户/项目/用例/执行/报告模块；tests 目录位置。

### 验证

- 迁移前对 23 个文件做 sha256 快照，迁移后逐一比对内容一致（0 差异）。
- 全仓库旧路径引用扫描 = 0；models/__init__.py 原公开模型名指向同一模型类；Base.metadata 无重复注册。
- 新增 `backend/tests/structure/test_v2_r01_structure.py` 结构测试（6 条）：新路径导入、schemas/agent 包级重导出同实现、模型身份与 metadata、路由无重复与关键端点存在、Prompt 仍可加载、llm_client_service monkeypatch 目标即实际模块。
- 实际命令与结果见下；代表性旧功能生成链路（function_case / api_document 生成 service）保留并通过，确认 monkeypatch 仍作用于真实模块。

```text
（backend，项目 venv，隔离 SQLite）
pytest tests/structure/test_v2_r01_structure.py -q
6 passed
pytest tests/structure tests/models/test_agent_platform_models.py tests/migrations/test_agent_platform_migration.py \
       tests/services/test_agent_platform_services.py tests/services/test_llm_gateway.py \
       tests/services/test_function_case_generation_service.py tests/services/test_api_document_generation_service.py \
       tests/providers tests/agents tests/workers tests/api/test_agent_api.py -q
338 passed
```

### 目录说明（结构性分组，不等于依赖解耦）

- `app/services/agent`：Agent 平台应用服务（会话/Run/Artifact/审批数据访问）。
- `app/agents`：执行内核（Runtime/Registry/工具）及既有 case_generation Workflow 资源；与 services/agent 职责不同。
- 分组只解决“文件归属”，未引入 Repository/DDD，也未消除模块间真实耦合；新 V2-Pxx 继续在既有代码上推进。

### 未提交说明

V2-R01 之上仍保留他人/本轮的未提交改动（旧 Agent 空响应可恢复重试与失败诊断、前端失败提示、文档规划与归档等）；未 commit/push，未进入任何 P 任务，等待检查。

## 2.2 2026-09-03 — V2-P01-01 纯文本消息合同（已编码，未做功能测试）

- 授权范围：只定义纯文本消息两个类型，不实现工具/Turn/Event/Loop/Provider/API/持久化；不写、不跑 pytest；不改旧 LLMMessage/Gateway/DB/前端/依赖；不 commit/push。
- 新增文件：
  - `backend/app/agents/conversation/__init__.py`（仅说明，无副作用导入）
  - `backend/app/agents/conversation/messages.py`
- 两个类型最终字段：
  - `TextContent`：`type: Literal["text"] = "text"`、`text: str`（允许空字符串）；`extra="forbid"`。
  - `Message`：`message_id: str`（min_length=1，调用方提供，不生成/不重建）、`schema_version: Literal[1] = 1`、`role: Literal["user","assistant"]`、`content: list[TextContent]`（min_length=1）；`extra="forbid"`。
- 未知版本、非法角色、额外字段与空内容列表由 Pydantic 校验拒绝；正文“你好”是普通文本，非 JSON。
- 参考来源已注释：Pi 固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 的 packages/ai/src/types.ts（TextContent/UserMessage/AssistantMessage）与 packages/agent/src/types.ts（AgentContext）；MIT 版权声明随注释保留，未迁移多模态/thinking/Provider 字段。
- 语法检查（项目根目录，`-I` 隔离，仅 ast 解析不导入业务模块）：
  ```text
  .\.venv\Scripts\python.exe -I -c 'import ast; ... ast.parse(...) ...'
  syntax OK
  ```
- 阶段末待测（本小步不运行）：中文文本往返后 message_id 与内容顺序不变；非法角色/版本/额外字段/空内容列表被拒绝；独立导入不产生数据库或网络副作用。
- 状态：P01 未验收、未勾选；未进入 V2-P01-02。

### P01-01 导师只读复核（2026-09-03）

- 已核实：messages.py 定义 TextContent、Message；conversation/__init__.py 仅说明文字；尚未发现业务模块接入新 Message。新合同未带来浏览器聊天或 Agent Loop 能力。
- 仅记录声称：上方语法检查结果 syntax OK；本次未重跑语法检查或功能测试，不追加通过数。
- 待修：两个模型仅配置 extra="forbid"，没有启用 strict 类型校验；Pydantic 2.9 默认允许部分类型转换，因此未满足提示词的严格类型要求。应限定在本文件补齐严格校验，并核查 schema_version 对 bool/float 等与整数 1 相等值的边界；功能测试仍留阶段末。
- 状态：已编码、静态审查有待修项、P01 未验收；不自动进入下一小步。已形成独立小修正提示词，没有直接修改业务代码。

### P01-01 严格类型校验修正（2026-09-03，已编码未测试）

- 位置：`backend/app/agents/conversation/messages.py`（仅本文件）。
- 处理方式：`TextContent` 与 `Message` 的 `model_config` 由 `extra="forbid"` 改为 `extra="forbid", strict=True`（拒绝隐式类型转换，保留多余字段拒绝）；新增 `schema_version` 的 `field_validator(mode="before")`，用 `type(value) is int` 显式排除 bool/float/str 后要求等于 1。
- schema_version 边界：`True`（bool == 1）、`1.0`、`"1"`、`2` 均拒绝，只接受真正的整数 `1`；字段默认值仍为 1。
- 保持不变的允许行为：`text` 空字符串、正常字符串与列表输入、message_id 往返不重建；未新增通用校验框架、未扩展工具/Turn/Event/Loop。
- 语法检查（项目根目录，`-I` 隔离，仅 ast 解析）：
  ```text
  .\.venv\Scripts\python.exe -I -c 'import ast; from pathlib import Path; p = Path("backend/app/agents/conversation/messages.py"); ast.parse(p.read_text(encoding="utf-8-sig"), filename=str(p)); print("syntax OK")'
  syntax OK
  ```
- 阶段末待测（本步不运行）：正常文本往返保留 ID；`True/1.0/"1"/2/非法角色/额外字段/空内容列表` 被拒绝；独立导入无副作用。
- 状态：修正已编码，功能测试留阶段末，P01 未验收；未进入 P01-02。

### 修正后只读复核与下一步（2026-09-03）

- Codex 核实两个模型都有 strict=True/extra="forbid"，schema_version 前置校验明确拒绝非 int 或非 1 的输入；原静态审查缺口已在源码中补齐，可以继续 P01-02。未重新运行语法检查或功能测试，P01 未验收。
- 用户要求一次适度多做、更多参考 Pi。下一项仍为 P01-02，范围扩展为工具消息、角色约束和历史配对纯校验；原 P01-05 的配对部分前移，后续不重复建设。
- 本轮只准备提示词并补读 Pi 工具调用/结果回传源码，没有修改业务代码，没有执行 P01-02。

### 同轮设计要求收敛（2026-09-03，以此为准）

- 用户进一步明确：严格参照 Pi 的设计思路，只做翻译和轻度适配。
- 上面刚提出、尚未实施的工具结果内容块包装及独立历史配对校验器撤回。P01-02 改为直接对齐 Pi 的 UserMessage / AssistantMessage / ToolResultMessage 联合和 ToolCall；调用 ID 关联及保序在后续翻译 Pi 原有 Loop/Executor 位置落实。
- 经只读检索未发现新 conversation.Message 的业务引用，提示词允许将本阶段尚未接入的教学类收敛为 Pi 风格联合；旧 LLMMessage/业务 API 保持不动。P01-02 尚未实施，功能测试未做。

## 2.3 2026-09-03 — V2-P01-02 消息与工具结果类型翻译（已编码，未测试）

- 授权范围：仅在 `backend/app/agents/conversation/messages.py`（及包 `__init__.py` 说明）按 Pi 翻译消息与工具结果类型；不实现独立历史配对校验器/message_history、不做 Tool Executor、Agent Loop、Provider 适配、事件、数据库或前端；不写不跑 pytest。
- 上游参考（只读）：Pi 固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 的 packages/ai/src/types.ts（TextContent/ToolCall/UserMessage/AssistantMessage/ToolResultMessage/Message）、packages/agent/src/agent-loop.ts（createToolResultMessage 等）、agent-loop.test.ts（仅读）。
- 实际文件：`backend/app/agents/conversation/messages.py`（重写）、`__init__.py`（说明更新）。
- 落地结构：TextContent；ToolCall（type="toolCall"、id、name、arguments: dict[str, Any]）；三种消息共享 `_MessageFields`（message_id/schema_version 真整数 1/timestamp Unix 毫秒，strict + extra=forbid，schema_version 与 timestamp 均带 before 严格校验）；UserMessage（role="user"，content: str | list[TextContent]）；AssistantMessage（role="assistant"，content: list[TextContent | ToolCall]，可为空）；ToolResultMessage（role="toolResult"，顶层 tool_call_id/tool_name/content: list[TextContent]（可为空）/details/is_error）；`Message` 为按 role 判别的 Annotated 联合，`parse_message` 为 TypeAdapter 解析入口。P01-01 的统一 Message 未接入业务，已直接收敛，未保留第二套消息系统。
- 轻适配：snake_case（tool_call_id ← toolCallId、is_error ← isError）；保留 Pi 的 role 名 "toolResult"（Provider 适配时才映射旧接口 tool）；补 message_id/schema_version 与调用方 timestamp。
- 暂未翻译（逐项登记）：Assistant 的 api/provider/model/usage/stopReason/deferred/diagnostics/errorMessage/rawStopReason/endTurn 等元信息；ToolResultMessage 的 usage、addedToolNames；ToolCall 的 thoughtSignature、namespace；ImageContent/thinking 多模态；动态工具发现。不填虚假零用量或默认成功。
- 语法检查（项目根目录，-I 隔离，仅 ast 解析，不导入业务模块）：
  ```text
  .\.venv\Scripts\python.exe -I -c 'import ast; from pathlib import Path; files = list(Path("backend/app/agents/conversation").glob("*.py")); assert files, "No source files"; [ast.parse(p.read_text(encoding="utf-8-sig"), filename=str(p)) for p in files]; print("syntax OK")'
  syntax OK
  ```
- 阶段末待测（本步不运行）：三种消息分别构造/解析；文本与工具混合内容往返保序；ToolResultMessage 顶层关联 ID/名称/is_error 保留；允许空内容形状；未知 role/type 与错误类型拒绝；message_id/schema_version 往返与严格版本校验；独立导入无数据库/网络副作用。结果配对与保序的真实运行测试留对应 Loop 任务。
- 状态：P01 未验收、未勾选；未进入 V2-P01-03。

### P01-02 导师只读审查（2026-09-03）

- 已核实：实际 Python 类型与报告一致；工具请求是 AssistantMessage 的内容块，工具结果是独立 ToolResultMessage；Message 按 role 判别，parse_message 使用 TypeAdapter；源码包含上游固定提交、暂未翻译字段和完整 MIT 文本。未发现新建历史扫描器/执行器或业务调用接入。
- 本轮未运行语法或功能测试；syntax OK 是实施报告/开发记录提供的证据，不作为本轮重跑结果。不能从 git status 推导整个实施过程没有并发编辑。
- 结论：本次核心对象关系未发现阻断性偏差，可继续后续合同翻译；阶段仍未验收，用户理解待反馈。
- 记录一个收尾差异：AssistantMessage/ToolResultMessage 的 content 使用 default_factory=list，允许字段省略，而 Pi 类型声明 content 必填。下一次修改同一消息合同时收敛为必填但允许 []，并在阶段测试区分“缺字段”与“空列表”；不为此单独拆修复轮次。Pi createToolResultMessage 对工具执行返回的缺失 content 做归一化，属于执行器输出构建位置，不等于消息输入字段可省略。

## 2.4 2026-09-03 — V2-P01-03 模型信息、用量与停止原因（已编码，未测试）

- 授权范围：只在 `backend/app/agents/conversation/messages.py`（及包 `__init__.py` 说明）按 Pi 翻译模型信息/Usage/StopReason/DeferredHandle；不新增状态机/事件/Loop/工具执行/Provider 适配/重试/预算器；不写不跑 pytest。
- 上游参考（只读）：Pi 固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 的 packages/ai/src/types.ts（Usage/StopReason/DeferredHandle/AssistantMessage/ToolResultMessage/AssistantMessageEvent）与 packages/agent/src/agent-loop.ts、agent-loop.test.ts（length 截断语义，只读）。
- 实际文件：`backend/app/agents/conversation/messages.py`（扩展）、`__init__.py`（说明更新）。
- 落地：`StopReason = Literal["pending","stop","length","toolUse","error","aborted","deferred"]`；`UsageCost`（input/output/cache_read/cache_write/total，有限非负数字或 None）；`Usage`（input/output/cache_read/cache_write/total_tokens/cost 必填可 None，cache_write_1h/reasoning 可选默认 None）；`DeferredHandle`（provider/model_id/api/id 必填，expires_at/poll_after_ms/data 可选，data 仅 JSON）；`AssistantMessage` 增必填 api/provider/model/usage/stop_reason 与可选 response_model/response_id/deferred/error_message/raw_stop_reason/end_turn；`ToolResultMessage` 增可选 usage（工具执行自身用量）。Assistant/ToolResult 的 content 改为必填但允许 []（移除 default_factory）。
- None 适配：上游必填计数/费用仍须提供，但显式 None 表示未知；不补 0、不加总、不计算价格；bool/负数/NaN/Infinity 拒绝；reasoning 是 output 子集、cache_write_1h 是 cache_write 子集（仅注释）。
- 未译登记：Assistant 的 providerThinkingLevel、diagnostics；ToolResultMessage 的 addedToolNames/动态加载；ToolCall 的 thoughtSignature/namespace；多模态/thinking/AssistantMessageEvent。
- 语义注释：length=截断非成功；toolUse=请求非已执行；pending/deferred 非完成；error/aborted 不自动关闭会话；实际控制流留 Pi Loop 翻译任务。
- 语法检查（项目根目录，-I 隔离，仅 ast 解析）：
  ```text
  syntax OK（backend/app/agents/conversation/*.py）
  ```
- 阶段末待测：模型信息/用量往返；显式 None 与 0 区分；缺必填字段拒绝；未知 StopReason/错误类型/负数/非有限费用拒绝；content=[] 合法而缺 content 拒绝；七种原因保留；可选 DeferredHandle 保留；原角色/调用 ID/版本不回归；导入无副作用。
- 状态：P01 未验收、未勾选；未进入 V2-P01-04。

### P01-03 导师只读审查（2026-09-03）

- 已核实：Usage/UsageCost、StopReason 七值、DeferredHandle、助手模型信息和工具可选用量均已实现；计数/费用显式 None、必填但允许 [] 的 content 已按任务落地。上一步 content 默认值差异已收尾。未运行语法检查或功能测试，syntax OK 仅为实施报告证据。
- 报告示例问题：meta 已含 message_id，AssistantMessage(**meta, message_id="m1", ...) 会重复传同名参数；应从共享 meta 移除 message_id，仅在每条消息构造时给出。这是示例错误，不是消息类缺陷；ast 语法检查不会验证这种运行时参数冲突。
- 待合并收尾：_ensure_json_safe 将 (list, tuple) 都视为数组，data 又为 Any 并原样返回，tuple 会保留为非 JSON 类型。按 Pi JsonValue[] 与当前“仅 JSON 数据”约定，应仅接受 list，不默默把 tuple 转成 list；下一步同文件轻修，阶段末补原始/嵌套 tuple 拒绝场景，不另建通用 JSON 框架。
- 当前状态：P01-03 已编码并只读审查，保留上述 JSON 边界项，阶段未验收。可以继续准备 P01-04 事件合同并合并小修；本轮未开始后续实现。git status 不作为实施全过程无并发编辑的证明。

### 阶段交付方式调整（2026-09-03）

- 用户要求后续不再拆得过细，以完整 V2-Pxx 阶段实施，做好后再学，知识点继续沉淀。
- P01 已有消息合同保留；剩余事件、必要纯工具校验、已知小修、针对性测试和记录合为一份阶段收尾任务，不再单独派发 P01-04/05/06。
- 当前源码仍只有 conversation/messages.py 与包说明，阶段收尾提示词已准备，未执行；本轮未修改业务代码、未运行功能测试。实施者本次被明确要求完成针对性测试，历史“不写不跑测试”只适用于旧小步。

## 2.5 2026-09-03 — V2-P01 阶段收尾：合同补齐、针对性测试与记录

- 授权范围：按完整阶段收尾 P01（不再逐小步暂停）；允许修改 backend/app/agents/conversation/ 与新增 backend/tests/conversation/；不改旧 LLM Gateway/Workflow/ORM/Worker/Router/前端；不连接真实模型/数据库；不做 git 提交。
- 实际新增/修改文件：
  - `backend/app/agents/conversation/messages.py`：修正 DeferredHandle.data 的 JSON 数组边界（只接受 list，tuple 拒绝），保留消息/用量/费用/版本严格校验；
  - `backend/app/agents/conversation/events.py`（新增）：两层事件与外壳；
  - `backend/app/agents/conversation/contracts.py`（新增）：ConversationTurn / ModelTurn 最小纯元数据；
  - `backend/app/agents/conversation/tool_validation.py`（新增）：参数纯校验入口与 ToolResultMessage 纯构造；
  - `backend/tests/conversation/`（新增 6 个文件）：消息、事件、工具校验、合成样例、隔离子进程测试与共享合成样例模块。
- Pi 对应与必要差异（详见 references/PI_SOURCE_AUDIT.md 第 8 节）：AssistantMessageEvent 9 种、AgentEvent 10 种；done.reason 仅 stop/length/toolUse/deferred、error.reason 仅 error/aborted 且与助手消息 stop_reason 一致；thinking_* 不入当前合同；参数分片只作字符串不补齐；事件外壳另带 schema_version/session_id/run_id/message_id/tool_call_id/sequence_no（只校验不分配）；参数校验按既有 ToolRegistry 查询并走输入模型严格校验，不复制 Pi TypeBox 转换。
- 已知修复：`_ensure_json_safe` 原先放行 tuple，现只接受 list（JSON 数组）；报告/测试中的共享 meta 不再混用 message_id（测试均显式逐条构造）。
- 实际命令与结果（backend，隔离运行，禁用自动插件 + confcutdir 排除父级数据库 conftest）：
  ```text
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --confcutdir=tests/conversation tests/conversation -q -p no:cacheprovider
  66 passed in ~2s
  git diff --check -- backend/app/agents/conversation backend/tests/conversation docs/V2 docs/PROJECT_RECORD.md（无空白错误；新增未跟踪文件已人工检查格式）
  ```
- 阶段待验证（真实行为，不在 P01）：工具真实执行零副作用与保序、取消、Provider 流式、持久化、Worker/SSE。合成样例只证明合同数据关联与往返。
- 状态：P01 合同项已勾入 03 验收清单（带“阶段实现及针对性测试完成，待 Codex 审查”）；P02 起未实施；不自动进入 P02。

## 2.6 2026-09-03 — Codex 阶段审查：需集中修正

- 只读审查全部新增合同/纯函数与当前测试；按约定未修改业务代码或测试实现。
- 针对性复跑 test_tool_validation.py、test_events.py、test_isolation.py，使用项目 .venv、confcutdir 和禁用自动插件，得到 37 passed in 2.72s；没有重跑全后端或全部 66 项。原 66 passed 保留为实施记录。
- 隔离进程合成反例复现：内部事件默默转换错误类型/丢弃额外字段；嵌套消息 ID 与工具快照 ID 不一致仍通过；普通输入模型将 "7" 转成 7；无效 input_model 抛 AttributeError；自定义校验错误摘要泄漏合成输入标记。handler 调用计数为 0，无真实工具/模型/数据库操作。
- 隔离测试负向自检：在保护安装后尝试被禁止的 httpx 导入并捕获异常，子进程仍返回 0/ISOLATION_OK；证明“命中禁止项必须失败”的测试机制不完整，并非证明当前实际连接了网络。
- 固定 Pi 源码核对：合成事件样例缺少第二组 turn 边界，并把工具结果当 turn_end.message；需改为符合两次助手响应的原有顺序。
- 审查详情：[P01 审查记录](reviews/V2-P01_REVIEW.md)。集中修正任务：[P01 阶段修正提示词](prompts/V2-P01_STAGE_REPAIR_CLAUDE_PROMPT.md)。本轮仅准备任务，未执行修正，P02 不启动。
- 原子知识点先列待复盘：嵌套合同边界、可信严格校验入口、错误消息也可能带输入、测试门禁的负向自检。待阶段修正复审后按真实实现成文，不提前宣称用户已理解。

## 2.7 2026-09-03 — V2-P01 集中修正（审查缺口修复，79 条针对性测试通过）

- 授权范围：P01 同一阶段集中修正，不进入 P02；只改 conversation 合同/纯函数与 tests/conversation 及本阶段文档；不改旧 Registry/Gateway/Workflow/ORM/API/Worker/前端。
- 审查依据：docs/V2/reviews/V2-P01_REVIEW.md（Codex 复跑 3 个相关文件 37 passed；合成反例确认五类缺口）。
- 逐项修正与新增回归：
  1. 工具安全错误：`_safe_validation_summary` 不再拼接可能含输入值的 error.msg/str(exc)，只输出受控 loc（合法标识符/整数索引，动态键脱敏 ?）与 pydantic 标准错误类型；`input_model` 必须是有效 Pydantic 模型类（否则 invalid_config，不再 AttributeError）；非 ValidationError 的校验/序列化异常 → 固定文案 validation_failed。新增：合成自定义 validator 回显输入、无效 input_model（字符串/普通类/None/数字）、model_dump 抛异常三条回归。
  2. 严格参数入口：`prepare_tool_call` 在 `model_validate(..., strict=True)` 强制严格，不依赖工具作者配置；新增未启用 strict 的 `count: int` 模型回归，证明 "7"/True/1.5 被拒、整数通过、handler 零调用。
  3. 事件内部校验与关联闭合：全部内部事件模型加 strict + extra=forbid；text_*/toolcall_* 的 content_index 必须指向 partial 中同类型块（True/bytes/未知字段/越界/错块类型反例）；toolcall_end 的完整 ToolCall 必须与 partial 同索引快照一致；message_update 外层必须是 assistant 且与嵌套 partial/最终消息同一 message_id（修正原“user 快照嵌套另一 assistant”错误正例）；turn_end.tool_results 改为必填（允许空），缺失拒绝。
  4. Pi 行为样例：四消息场景按两个 Pi turn 重写（turn1 = 工具请求助手消息 + tool_results 单列结果；turn2 = 最终回复），断言关键先后与关联而非硬凑数量。
  5. 隔离门禁：记录每次被禁止导入尝试（收尾即使被捕获也判失败）；负向自检 1 验证被禁模块真的被拦；负向自检 2 阻止 socket.connect/create_connection 且验证保护生效（不发起真实连接）；未通过扩大放行范围。
- 实际命令与结果（backend，隔离运行）：
  ```text
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --confcutdir=tests/conversation tests/conversation -q -p no:cacheprovider
  79 passed in ~2s
  ```
  过程说明：审查报告的 37 passed/合成反例输出保留为“修前失败”的原始证据；本工作区未另存独立的修前失败中间态。修正过程中的两次自身错误（隔离脚本 socket 类整体替换破坏 ssl 导入、样例 nth() 缺默认参数）已在最终版本修复，不计入缺口。
- 已核实/未验证：缺口的修前失败依据 + 修后 79 项全部通过；真实工具执行/保序、Provider 流式、持久化与 Worker/SSE 仍属后续阶段，未验证。
- 状态：P01 集中修正完成，待 Codex 复审；P02 起未实施、未勾选。保留原 66 passed 与审查记录，不篡改历史。

## 2.8 2026-09-03 — Codex 复审：79 项通过，仍有剩余边界

- 实际运行 P01 全部针对性测试，项目 .venv、禁用自动插件、confcutdir 隔离父级 conftest：79 passed in 3.25s；未运行全后端回归。
- 已确认原严格类型入口、内部事件配置、主要消息/工具 ID 关联、两个 turn 等修正已落地。
- 定向合成反例仍确认：合法标识符形式的动态/额外字段键及自定义 error type 泄漏；model_serializer 返回非字典时，PreparedToolCall 构造从 try 外漏出原始 ValidationError。handler 调用为 0。
- 隔离负向探针仍可返回 ISOLATION_OK：正式阶段连接尝试的保护异常被捕获；或 create_connection 被替换成空操作，第二项网络自检未实际验证成功。没有真实连接。
- Pi 固定源码核对发现：openai-completions.ts 的 ensureToolCallBlock 可先发 id 为空的 toolcall_start，当前 ToolCall.id 非空限制误拒绝；已修正的两轮样例仍遗漏工具结果的 message_start/message_end。
- 详情：[P01 集中修正复审](reviews/V2-P01_RECHECK.md)。任务：[P01 复审收尾](prompts/V2-P01_RECHECK_REPAIR_CLAUDE_PROMPT.md)。当前未进入 P02、未修改业务源码/测试。
- 用户最新要求：学习笔记仅在用户明确说整理时更新。本轮未修改 D:\TestAgent node，也未生成知识点。

## 2.9 2026-09-03 — V2-P01 复审收尾：剩余边界修复（90 条针对性测试通过）

- 授权范围：同一 P01 阶段集中收尾，不进入 P02；只改 conversation 合同/纯函数与 tests/conversation 及必要记录；不改学习笔记；不动旧 Registry/Gateway/Workflow/ORM/API/Worker/前端。
- 审查依据：docs/V2/reviews/V2-P01_RECHECK.md（Codex 实跑完整 P01 79 passed in 3.25s，合成反例确认 5 类剩余边界）。
- 修正与新回归：
  1. 错误摘要改为“固定错误码 + 固定文案”，不再转发 loc/type/msg/工具名等动态内容；新反例覆盖动态字典键、extra=forbid 未知字段名、PydanticCustomError 以输入为 type 三种泄露路径（均断言不泄漏标记、错误码稳定）。
  2. 候选构造纳入同一受控边界：校验、序列化结果必须为参数字典（否则 validation_failed），PreparedToolCall 构造失败也转稳定错误；model_serializer 返回字符串/列表回归单独覆盖。
  3. 隔离门禁逐项自检：connect 与 create_connection 各独立布尔；校准自检与正式阶段分段，正式阶段被捕获的连接尝试在收尾判失败；故障注入（把某保护入口替换为空操作）使自检失败；自检 socket 在 finally 关闭。
  4. Pi 合法早期 partial：ToolCall.id 允许空串（Pi ensureToolCallBlock 的 toolcall_start/delta 临时块），最终候选/结果构造/ toolcall_end 仍要求有效 ID；新增“start→delta→end 空 ID 到达齐 ID”合法形状与空 ID 终态拒绝回归。
  5. Pi 工具结果消息事件：合成样例在 tool_execution_end 之后、turn_end1 之前补 tool_result 的 message_start/message_end，并按稳定 message_id 断言先后（依据 Pi agent-loop.ts 的 emitToolResultMessage 顺序）。
- 过程说明：新增反例依据 RECHECK 报告的合成诊断编写；代码修正与回归在同一工作区完成，本工作区未留存独立的“修前失败”中间态，审查报告的 79 passed 与合成反例输出作为修前证据保留。
- 实际命令与结果（backend，隔离运行）：
  ```text
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --confcutdir=tests/conversation tests/conversation -q -p no:cacheprovider
  90 passed in ~5s
  ```
- 已核实/未验证：五类边界修复均通过；真实工具执行/保序、Provider 流式聚合、持久化与 Worker/SSE 仍留后续阶段，未验证。
- 状态：P01 集中收尾完成，待 Codex 复审；P02 起未实施、未勾选。历史 66/79 与两次审查记录保留，不篡改。

## 2.10 2026-09-03 — Codex 最终复审：P01 合同阶段验收通过

- 已核对修正后的工具安全边界、Pi 早期 partial、两层事件关联、完整两轮工具消息事件序列，以及隔离逐项自检和正式尝试记录。
- 使用项目 .venv 实际运行全部 P01 针对性测试，禁用自动插件与字节码写入、confcutdir 排除父级数据库 conftest：`90 passed in 5.41s`，exit 0。未运行全后端回归。
- 上两次审查发现的动态错误回显、非字典序列化漏出、被捕获连接漏记、自检状态复用、早期空 ID 误拒和工具结果消息事件遗漏已在当前合同范围内收敛。
- 结论：P01 阶段验收通过，仅限合同、纯校验和声明范围内的隔离测试；完整 Agent Loop、真实工具执行/取消/保序、Provider 流式与存储/Worker/SSE 仍属后续阶段。
- 验收证据：[P01 验收记录](reviews/V2-P01_ACCEPTANCE.md)。原 66/79/90 运行记录保留，不相加、不反向补造修前失败输出；没有独立留存新 pytest 红测中间态的流程不足如实保留。
- 用户要求后续提示词更详细：明确文件/接口、实施顺序、每个关键分支的输入输出、失败处理、正反测试与预期、验证命令和停止边界，减少实施猜测；仍一次一个完整阶段。
- 本轮未修改业务源码或测试、未调用真实模型/数据库/工具 handler、未整理学习笔记；P02 尚未开始。

## 2.11 2026-09-03 — P02 源码核对与详细任务书准备

- 用户要求说明当前能力并生成更详细的 P02 阶段提示词；本轮只读核对并维护开发文档，不修改业务代码，不运行项目测试或真实请求，不整理学习笔记。
- 当前事实：P01 合同阶段已验收；Gateway 与两 Adapter 仍是同步 complete，异步流入口未实现。旧 Workflow/Worker/前端是复用资产，不代表新对话链路已接通。
- 本地元数据：Python 3.11.9、Pydantic 2.9.2、pytest 8.3.3、httpx 0.27.2、anthropic 1.3.0；Anthropic SDK 内部依赖当前 httpx2 2.12.0。已只读核对 AsyncMessages.create/stream、AsyncStream 关闭与 raw_events、AsyncAnthropic 构造/关闭。
- Pi 参考固定 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 的 Provider 流与消息转换、stop reason 映射、EventStream 和 streamAssistantResponse；未运行或改动 Pi。
- 已核对官方 OpenAI Chat Completions、Anthropic streaming/tool-result 与 HTTPX async 文档；当前 SDK 无 temperature 参数、最终用量块、累计 token 与资源关闭等写入任务书。
- 新任务书：[V2-P02 完整提示词](prompts/V2-P02_STREAMING_PROVIDERS_CLAUDE_PROMPT.md)。包含统一异步入口、两类请求/响应映射、P01 事件复用、私有缓冲、取消/deadline/预算、单层重试、安全诊断、Fake 流和直接相关回归命令。
- 状态：P02 提示词已准备，代码未实施、未验收；没有替用户发送给 Claude，没有进入 P03。

## 2.12 2026-09-03 — V2-P02 流式 Provider（部分实现与针对性测试，未验收）

> 本节保留 Claude 当次完成报告；其中“已验证”的覆盖范围由下一节 Codex 审查进一步校正，不等同于阶段验收。原重复编号 2.9 更正为 2.12。

- 授权范围：按 P02 任务书实现流式；本记录如实标记阶段未完成。
- 实际新增/修改文件：
  - `backend/app/agents/providers/streaming.py`：StreamRequest/ProviderSnapshot/StreamContext/StreamControl/AttemptBudget/AttemptRecord/StreamLimits + 固定错误码；纯请求转换（OpenAI messages/tools、Anthropic system/messages/tools，工具结果必须指回本历史请求，否则安全失败）。
  - `backend/app/agents/providers/openai_stream_adapter.py`：httpx AsyncClient + 原始 SSE 解码（CRLF/LF、注释、连续 data、[DONE]、choices=[] usage），块先入 partial 再发事件，限额在字节进入缓冲时检查。
  - `backend/app/agents/providers/anthropic_stream_adapter.py`：AsyncAnthropic messages.create(stream=True) typed 事件映射（message/content_block_*/message_delta/message_stop），ping 忽略，tool_use partial_json 缓存到块结束。
  - `backend/app/services/llm/llm_stream_gateway.py`：能力预检、共享 AttemptBudget、Gateway 单层重试、取消/退避、预算耗尽/预检失败为 0 请求。
  - `backend/app/agents/conversation/events.py`：事件模型 `type` 增加默认值（保持判别联合可构建；构造不再强制重复传 type）。
  - `backend/tests/providers_streaming/`：转换/DTO/OpenAI 流/Gateway/Anthropic 流测试（tests_streaming_kit.py 合成样例）。
- 实际命令与结果（backend，禁用自动插件 + confcutdir/无父 conftest，零网络 Fake transport）：
  ```text
  pytest --confcutdir=tests/providers_streaming tests/providers_streaming -q   → 24 passed
  pytest --confcutdir=tests/conversation tests/conversation -q                → 90 passed（P01 回归）
  pytest tests/providers/test_openai_compatible_adapter.py tests/providers/test_anthropic_adapter.py \
         tests/services/test_llm_gateway.py -q                               → 55 passed（旧回归）
  ```
- 已验证：OpenAI 文本流（start→text_*→done+usage 空 choices 不漏）、tool_calls 交错 delta 与 toolUse 完成、length 不发布假 toolcall_end、缺 [DONE] 断流为 error、帧超限为 error、非 JSON 协议为 error；Gateway 单次成功/瞬态错误重试成功/预算 1 拦截第二次/预检不支持 tools 0 请求/开始前取消 0 请求/已发出内容不透明重放；Anthropic 文本 end_turn、ping 忽略 + 空文本非成功、tool_use partial_json 完整解析；P01 与旧 provider/gateway 回归未退化。
- 未验证/未实现（如实登记，阶段未验收）：Anthropic 未知 SSE 事件需 raw_events 路径（当前 typed 迭代被 SDK 过滤，差异已登记）；温度显式请求 → unsupported_parameter（anthropic 无该参数，未 extra_body）；index 重映射（thinking 忽略后的本地索引）仅有代码、缺定向测试；跨 UTF-8 分片/CRLF 全矩阵、双 stream 并发隔离、deadline 语义与 Task.cancel、model_serializer 等安全项、SDK/httpx2 全部契约均未完成验证；工具结果构造到 Provider 层的保留（executeToolCallsSequential）未实现（属 P03）。
- 状态：V2-P02 部分实现与测试，待 Codex 复审；不勾选 P02 门禁；P03 起未实施。保留 P01 复审历史。

## 2.13 2026-09-04 — Codex 审查 P02 部分实现：集中续做

- 只读检查四个新增模块、既有 Gateway、测试与固定 Pi 源码；未修改业务源码/测试、未调用真实模型/业务数据库，未整理学习笔记。
- 项目 .venv、禁用自动插件/字节码、隔离父 conftest，并加配置/数据库导入及业务连接保护，实际运行流式套件：`24 passed, 13 warnings in 3.29s`。本轮未重跑 P01 90 项和旧回归 55 项，这两组本次结果仍来自 Claude 报告。
- 额外合成探针确认：OpenAI 请求无 Authorization；合法空对象工具误拒、好坏混合工具仍成功；Anthropic 坏 JSON 正常完成且合法工具重复 end；SSE 多行错误拼接/整帧限额漏检；重试重复 start、共享预算与本次重试次数混淆、真实 httpx.ConnectError 不重试；等响应头取消不生效；关闭外层迭代器后客户端仍未关闭；历史转换接受被打断或重复工具结果。
- 源码确认 AttemptRecord 未接线、错误码/partial 丢失、统一 Gateway async with 入口缺失、Anthropic text_start/toolcall_delta 与 raw 限额未补齐。并发、完整取消/deadline 等仍未验，不作为能力声称。
- 首次审查防护误拦 Windows asyncio 初始化 socketpair，属审查脚本错误；调整保护安装时机后才得到有效结果，不把该次失败计入项目修前失败。详细证据见 [P02 部分审查](reviews/V2-P02_PARTIAL_REVIEW.md)。
- 纠正归属：工具执行属于 P03，但把已有 ToolResultMessage 正确转换进 Provider 历史属于 P02。取消、关闭、鉴权、尝试记录和 raw 限额也是 P02 原始要求。
- 形成 [P02 集中续做提示词](prompts/V2-P02_CONTINUATION_CLAUDE_PROMPT.md)：保留当前模块和合并快照，补现有 LLMGateway 的上下文入口，先固化反例再集中修正和验证。未代替用户发送给 Claude。
- 状态：P02 部分实现，审查未通过；门禁未勾选，不进入 P03。P01 验收结果保留。

## 2.14 2026-09-04 — V2-P02 集中修正与验收通过

- 用户明确授权 Codex 依据集中续做提示词直接修复；本轮修改 P02 流式 Provider、现有 LLMGateway、流式测试和阶段文档，没有进入 P03、没有整理学习笔记。
- 统一入口：现有 `LLMGateway.stream(snapshot, request, *, context, control, limits=None)` 返回异步上下文管理器；内部 LLMStreamGateway 复用原别名/能力解析。当前合并 ProviderSnapshot 作为已记录的轻适配，不额外拆 ModelSnapshot。
- OpenAI 补显式 Authorization、原始有界 SSE、严格多工具聚合、空对象/混合坏参数、缓存用量和 ID；Anthropic 改走 SDK streaming raw response 字节，补 text/tool 完整生命周期、初始块、thinking 索引映射、未知事件和唯一块结束。
- Gateway 补预检、有限总 deadline、cancel/Task.cancel/提前关闭、共享预算与局部重试分离、每物理请求 AttemptRecord、安全 error_code/partial；请求转换补工具结果相邻批次、名称、重复和遗漏校验。
- 审查反例均固化为回归或等价门禁；新增 socket 三入口负向自检在事件循环创建后安装，Fake transport 在禁网状态下仍通过。
- 最终实际结果：P02 `54 passed, 13 warnings in 6.54s`；P01 `90 passed in 7.31s`；旧 Provider/Gateway `55 passed, 13 warnings in 4.95s`。三组分列、不相加；warning 为既有 Pydantic class-based config 弃用提示。
- AST/行尾检查通过；`git diff --check` 无新增空白错误，仅既有 LF/CRLF 提示。无真实网络、模型、数据库、工具 handler、服务启动或 git 操作。
- 结论：P02 在 Fake/内存协议范围验收通过，证据见 [P02 验收记录](reviews/V2-P02_ACCEPTANCE.md)。真实供应商验证留 P10；P03 尚未实施，不自动开始。

## 2.15 2026-09-04 — V2-P03 纯 Agent Loop 与 Tool Executor 验收通过

- 用户明确要求 Codex 直接进入下一阶段并编码。本轮新增 conversation/{loop,tool_executor,budget,policy}.py、tests/agent_loop/，更新 conversation 包说明与阶段文档；没有修改数据库/Worker/API/前端/Skill，不整理学习笔记。
- Loop 参考 Pi runLoop/streamAssistantResponse：把 P02 AssistantMessageEvent 映射成 P01 AgentEvent，完整助手工具请求经串行执行后生成独立 ToolResultMessage 并进入下一次模型历史；普通回复零工具结束。
- Tool Executor 复用 P01 ToolRegistry/prepare_tool_call/build_tool_result_message；策略改参后 strict 重校验。默认策略阻止写工具、需审批和需额外权限的工具；P09 前不伪造授权。
- AgentLoopBudget 分开记录逻辑 turn/model/tool 与 P02 物理 AttemptBudget，四类限额为硬停止；同批工具预算原子预留、调用 ID 去重、结果按源序。取消/截止补全剩余未执行结果，异步策略/工具可中断，迟到 update 被丢弃。
- 实际测试：P03 `30 passed, 13 warnings in 4.36s`；P02 `54 passed, 13 warnings in 6.63s`；P01 `90 passed in 9.20s`；旧 Provider/Gateway `55 passed, 13 warnings in 3.40s`；ToolRegistry `4 passed in 0.05s`。分开统计，warning 为既有 Pydantic 弃用提示。
- 实际修正：迟到 update 竞态先失败后修复；取消补齐剩余结果时 stop 覆盖 canceled 的状态错误先失败后修复。P03 纯导入子进程确认不加载 DB/Web/Worker/HTTP 客户端模块。
- 结论：P03 在纯 Python/Fake 范围验收通过，见 [P03 验收记录](reviews/V2-P03_ACCEPTANCE.md)。同步 handler 无法物理抢占，需及时取消的工具应异步协作；持久化/恢复属 P04。未进入 P04。

## 2.16 2026-09-04 — V2-P04 会话持久化、并发与幂等验收通过

- 用户要求直接进入 P04。新增 `0003_conversation_persistence`、conversation repository/service 和 `tests/conversation_persistence/`；修改 Agent Session/Run/Message ORM、内部/API Schema、旧 session/run 服务与必要旧路由门禁。未进入 P05/P06，不整理学习笔记。
- session 新增 mode 与消息/事件序号游标；conversation session/run 的 project_id 可空。Run 复用为 ConversationTurn，增加 user_message_id 和 active_slot；数据库唯一/check 约束保证一个活跃 Turn，终态释放。
- 用户 P01 消息、queued conversation Run、client_request_id/input_hash 在同一事务保存。相同键同内容复用，同键不同内容冲突；中间失败全部回滚。完整 P01 assistant/toolResult JSON 按序保存并通过 parse_message 恢复。
- 数据库游标使用原子 `UPDATE column = column + 1` 后在同事务读取预留值；双连接取得不重复序号。并发幂等扩测发现查询窗口竞态，已在活跃槽冲突前二次读取幂等记录。
- 旧路由允许 owner 读取 conversation，但禁止项目读者旁路；旧发消息/用例生成入口拒绝 conversation。P05 前旧 Worker selector/claim 跳过 conversation queued Run，避免误报未知 Workflow。
- `0003` 回填旧行为、核验 create_all 重叠 head、拒绝部分结构；downgrade 发现 conversation/版本化消息数据时拒绝有损降级。user_message_id 不建反向 FK，避免与 message.run_id 构成迁移环，归属由同事务服务校验。
- 最终实际结果：P04 `20 passed, 14 warnings in 9.35s`；P01 `90 passed in 9.82s`；P02 `54 passed, 13 warnings in 7.35s`；P03 `30 passed, 13 warnings in 3.93s`；旧 Service/API/Model/Worker `100 passed, 151 warnings in 10.98s`。各组分列。
- 全部数据库验证使用临时/内存 SQLite；未读取或连接真实 MySQL。结论：P04 在声明范围验收通过，见 [P04 验收记录](reviews/V2-P04_ACCEPTANCE.md)。P05 尚未开始。

## 2.17 2026-09-04 — V2-P05-A：Dependency Audit 与阶段边界校正（只读审计 + 文档）

- 授权范围：只做 Dependency Audit、核对 conversation 路径事实、最小修正 01/03 阶段边界；**不实现** ConversationRunner，不改 Worker 执行逻辑，不删除 Workflow，不开始 P06/P07/P08。未修改业务代码；未连接/修改真实数据库（仅读代码与 migration 定义）；本轮无 pytest 运行（无业务代码变更，见"验证"）。

### 六项代码事实核验（以代码为准，2026-09-04）

1. `submit_conversation_turn()`（backend/app/services/agent/conversation_service.py:78）会创建 `workflow_code="conversation"` 的 queued AgentRun：内部调用 `agent_run_service.create_run(db, session, "conversation", …, active_slot=1)`（同文件约 108 行），用户消息 + Run + 幂等键同事务。
2. Worker 的 queued 查询仍显式排除 conversation：`agent_run_service.next_queued_run_id / claim_queued_run` 均带 `AgentRun.workflow_code != "conversation"`（backend/app/services/agent/agent_run_service.py:228、245，注释"P05 前跳过 conversation"）。
3. `AgentWorker` 仍固定构建 `AgentRunner`：`worker main()` 的 `runtime_factory(on_step_boundary)` 返回 `AgentRunner(skill_registry, tool_registry, …)`（backend/app/workers/agent_worker.py:211-216），`run_once()` 在 83 行调用该 runtime。
4. 当前仍不存在 `ConversationRunner`：backend 全量搜索 0 命中。
5. `run_agent_loop()` 尚无生产调用方：仅 conversation/loop.py（定义）与 tests/agent_loop/* 出现；无 Worker/Router/Service 引用。
6. 持久化函数已具备：`persist_conversation_messages()`（conversation_service.py:139，拒绝重复写入用户首消息，校验 run 属于该 conversation 会话）与 `restore_conversation_messages()`（conversation_service.py:168）均已存在并带 owner 校验。

### Legacy 真实调用链（当前唯一被接入的执行路径）

```text
V1 前端 test-agent 悬浮台
  → api.createAgentSession / appendAgentMessage / createAgentRun（api/agent.js:5/17/29 → POST /agent/sessions、/agent/sessions/{id}/messages、POST /agent/runs/case-generation）
  → AgentRouter（backend/app/routers/agent/agent_router.py：mode=legacy_workflow + project_id 强制校验，如 271/291 行；284 行创建 queued Run）
  → agent_worker CLI（worker main()：SkillRegistry + ToolRegistry + LLMGateway）
  → AgentRunner（agents/runtime/runner.py：按 run.workflow_code 解析 Skill，循环 next_step/execute_step）
  → CaseGenerationWorkflow（agents/skills/case_generation/workflow.py：load_source → … → scope_gate/coverage_gate/save_gate）
  → 逐 step 写 AgentStep/AgentEvent/AgentArtifact/AgentApproval；会话 mode=legacy_workflow
```

前端事实：`useAgentSession.js` 每次发送先 `createAgentSession`（134 行）→ `appendAgentMessage`（159 行）→ `createAgentRun`（163 行，无条件 case_generation），随后 poll Run/Events/Steps/Artifacts/Approvals（38-39、53-66 行）。即前端仍全链路依赖 legacy Workflow；无 conversation 端点调用、无脑图/Diff 组件。

### Conversation 真实调用链（当前断点）

```text
（尚无 HTTP 入口：不存在 /agent/conversations 路由）
conversation_service.submit_conversation_turn()          # 已实现，只被 tests/conversation_persistence 与 api 测试驱动
  → queued AgentRun（workflow_code="conversation", active_slot=1）
  → Worker claim 显式跳过 → Run 永久 queued             # P05 待接通的断点
run_agent_loop() / loop.py + tool_executor/policy/budget # 已实现，无生产调用方
```

### Backend 审计清单（标识符 → 位置 → 角色）

- `CaseGenerationWorkflow`：agents/skills/case_generation/{workflow.py（定义）,definition.py（build_case_generation_skill）,__init__.py}；tests/agents/skills/case_generation/*（定义/流程测试）。
- `AgentRunner`：agents/runtime/runner.py（定义）；workers/agent_worker.py:199-212（唯一生产构造点）；runtime/__init__.py 提示显式导入。
- `next_step/execute_step`：agents/runtime/contracts.py（AgentWorkflow 协议）、agents/runtime/runner.py（驱动）、agents/skills/case_generation/workflow.py（实现）；tests 的 Fake workflow 亦使用。
- `workflow_code`：models/agent/agent_run.py（列 + uq + active_slot check 约束）；alembic 0002（建列）/0003（conversation 约束）；agent_run_service（create/claim/transition 校验）；router/schema 各层。
- `legacy_workflow`：models/agent/agent_session.py（mode 默认值 + ck 约束 mode IN ('legacy_workflow','conversation') + ck mode='conversation' OR project_id IS NOT NULL）；alembic 0003；agent_session_service（默认值）；agent_router（mode 门禁）；schemas/agent/{api,platform}.py。
- `case_generation`（业务字符串/路由）：agents/bootstrap.py（build_default_skill_registry 注册 case_generation Skill）；routers/agent/agent_router.py（POST /runs/case-generation、save-candidates 等）；workers/agent_worker.py；models/agent_run 注释；schemas。
- 注意：backend/app/services/function_case_generation_service.py、api_document_generation_service.py 与 routers/function_case_router.py、api_document_router.py 是 V1 一代同步生成服务（无 AgentRun/workflow_code），不属于 Agent Platform legacy Workflow 链路（仅文件名含 case_generation，勿混入迁移范围）。
- AgentArtifact/AgentApproval 使用方（legacy 侧）：agents/runtime/errors.py、routers/agent/agent_router.py、schemas/agent/platform.py、services/agent_save_service.py（连同 models/ 与两个 platform service）。
- tests 依赖 legacy runtime：tests/agents/test_agent_runtime.py、test_agent_runtime_heartbeat.py、tests/workers/test_agent_worker.py、tests/agents/skills/case_generation/*、tests/api/test_agent_api.py（HTTP 全生命周期）。conversation 侧测试：tests/conversation/*、tests/agent_loop/*、tests/conversation_persistence/*、tests/providers_streaming/*。
- Run 状态机原语已具备（agent_run_service：transition_status / save_output_json / mark_finished_at / heartbeat / mark_interrupted；start_step/finish_step/append_event 为 legacy step 驱动专用，P05-B 需评估哪些仅用于 step 模型）。

### Database / migration 事实（只读）

- agent_sessions.mode：default legacy_workflow；CK mode IN ('legacy_workflow','conversation')；CK conversation 允许 project_id NULL 而 legacy_workflow 必填（models/agent/agent_session.py:12-13,20）。
- agent_runs.workflow_code：NOT NULL，值 case_generation / conversation；CK active_slot 仅 conversation；UQ (session_id, workflow_code, idempotency_key)。
- alembic 0002：agent 平台表 + workflow_code；0003：mode/project_id nullable/序号游标/active_slot/user_message_id，downgrade 对存在 conversation 数据拒绝。历史行兼容意义：既有行保持 legacy_workflow + project_id 必填约束不变；迁移不得让无项目 conversation 行破坏旧约束。

### Legacy 内容 A/B/C 分类（本轮只识别、不迁移、不删除）

- A. Deterministic capability（未来 → Tool / Domain Service，P07/P08；本轮不迁移）：load_source / load_project_context / load_existing_cases（context tools：agents/tools/ 下 test_case_context/validation 等）、validate（agents/tools/ 校验工具 + validators/）、deduplicate、compute_coverage、save（agent_save_service + 候选保存链路）。
- B. Test knowledge / Prompt knowledge（未来 → skills/test-design/SKILL.md，P08；本轮不创建）：agents/skills/case_generation/ 下的测试点分析、边界/状态分析、用例修正 prompt 与 workflow.py 内的阶段指导文本。
- C. Orchestration（未来退役）：runtime/contracts.py 的 AgentWorkflow(next_step/execute_step) 协议、runtime/runner.py、workflow.py 的 phase 图与 repair loop、scope_gate/coverage_gate/save_gate、case_generation 的 Skill 注册（bootstrap.py:62）。本轮全部保留。

### 阶段边界文档修正（问题 A/B/C，最小修改）

- 01_DEVELOPMENT_PLAN.md V2-P05 Scope #6："停止新建 legacy_workflow 行"改为"新的 V2 Conversation 路径不得新建 legacy_workflow；仍被旧兼容入口使用的 legacy Workflow 在 P06 替换旧前端之前允许继续创建"，避免破坏 V1/legacy 页面（问题 C）。
- 01_DEVELOPMENT_PLAN.md V2-P05 Scope #8：测试迁移标注为"最终退役清单，随 legacy 下线执行；legacy 存活期内保留既有测试，P05 不删除测试"。
- 01_DEVELOPMENT_PLAN.md V2-P05 Acceptance：完成定义拆为"P05 只验收 Runtime 收敛相关项（queued Run 消费、Runner→Loop、lease/heartbeat/fencing、cancel、follow-up、legacy 隔离、P01～P04 回归、Runner 不决定业务步骤）"+"仅属架构约束、随 P07/P08/P09 落地的项（Artifact 编辑/P07、Coverage-Dedup-Validation Tool 与 Skill 无 phase/P08、UI 不展示 phase/P09）"，不再作为 P05 功能验收（问题 A）。
- 03_ACCEPTANCE_CHECKLIST.md P06 最后一条："两个用户并行编辑不同 Artifact"类 Artifact 验收移出 P06，改为注明 Artifact 跨用户/并发隔离在 P07 Artifact 域 / P09 UI 域验收（问题 B）。

### P05-B 实现建议（本轮未实现，供下轮决策）

最小代码改动范围建议：

1. 新增 `backend/app/agents/conversation/runner.py`：ConversationRunner，职责 5 步——restore Conversation messages（复用 conversation_service.restore_conversation_messages）→ 构建 Context/RuntimeContext（对接 loop.py 现有接口）→ 调用 `run_agent_loop()` → persist 新 Message（persist_conversation_messages）与事件 → finalize AgentRun（复用 agent_run_service transition_status/mark_finished_at，需确认其对 conversation Run 的校验是否齐全）。不得出现 next_step/execute_step/phase/CaseGenerationWorkflow/业务决策。
2. `backend/app/services/agent/agent_run_service.py`：放开/改造 claim 语义——conversation queued Run 允许被 Worker 抢占（去掉 228/245 的 `!= "conversation"` 过滤，或提供 conversation 专用 claim 入口）；沿用 lease/heartbeat/fencing 原语。
3. `backend/app/workers/agent_worker.py`：run_once 按 workflow_code 分发——`conversation` → ConversationRunner；其余（case_generation 等）→ 现有 AgentRunner legacy 路径（runtime_factory 保持）。先保持 legacy 行为不回归。
4. 前端/路由本轮不动；P06 才替换前端发送路径。

风险提示（记录，不处理）：agent_run_service 的 step 专用函数（start_step/finish_step/append_event 等）围绕 AgentStep 语义设计；conversation 的 Run 需要的是"消息/事件持久化 + 终态"而非 step 推进；P05-B 落地时应以 conversation_service 的持久化函数为准，避免把 ConversationRunner 做成 AgentRunner 的 step 变体。

### 验证

- 无业务代码改动 → 未运行 pytest（不能把未运行测试写成通过）。
- 文档静态检查：01/03 修改仅调整文案与验收归属，未新增/删除被引用的标题锚点；docs/V2 链接扫描此前已通过（本次无新文件链接）。

## 2.18 2026-09-04 — V2-P05-B：ConversationRunner 最小生产执行桥（已实现并测试）

- 授权范围：只实现 ConversationRunner 及其测试；不实现 Worker 分发 / claim 规则修改 / lease / heartbeat / fencing / follow-up；不删除 legacy Workflow；不开始 P06/P07/P08；不改 frontend / Alembic / DB schema / V3。

### 新增文件

- `backend/app/agents/conversation/runner.py`：ConversationRunner（生产执行适配器，新增，未接线到 Worker）。
- `backend/tests/agents/conversation/test_runner.py`：Runner 测试（内存 SQLite + Fake Provider，8 项）。
- 未修改任何既有模块；`conversation/__init__.py` 未改动（仓库习惯是从具体模块显式导入）。

### Runner 合同（真实实现）

- 构造注入：gateway（提供 async `.stream(snapshot, request, *, context, control, limits)`）、ProviderSnapshot、ToolRegistry、system_prompt、AgentLoopLimits / AttemptBudget / StreamLimits、policy、id/timestamp factory。
- 执行身份：`run.requester_user_id`，并要求 == 会话 owner；从不接受模型提供的身份；user/project 不来自消息内容。
- `async run(db, run_id, cancel_event=None) -> ConversationRunOutcome`；允许启动状态 queued/running（queued 由 Runner 经 transition_status 置 running，不做 claim SQL）；终态经 transition_status/mark_finished_at/save_output_json；计数器 llm_calls_used/tool_calls_used 递增。
- restore：复用 `conversation_service.restore_conversation_messages()`（不重写 ORM→Domain 转换）；校验恢复历史以本 Run 用户消息结尾（user_message_id 比对）。
- AgentLoop 调用：`run_agent_loop(prompts=[], context=...)`，历史（含当前 Turn 用户消息）在 submit 时已入库，置于 context.messages；不复制 while 循环。
- 生命周期事件复用既有 DB event_type：run_started / run_succeeded / run_failed / run_cancelled（与 legacy AgentRunner 同名单，未新造事件类型）。AgentLoop 执行事件（agent_start/message_*/turn_*/tool_*）本轮只在内存收集（outcome.loop_events），逐条落库留到 P06 SSE。
- 终态映射：completed→succeeded；aborted+canceled→cancelled；error / limit / stopped / waiting / 非取消 aborted→failed（stopped/waiting 会话级语义本轮无产品路径，见 Deferred）。
- 执行/恢复阶段异常：不落伪消息，best-effort 置 failed（error_code=runner_execution_error，error_message 为固定文案不泄露原始异常），不向上抛；校验阶段异常（非 conversation Run、终态不可启动、owner 不符）向上抛给调用方。

### Message 增量持久化策略

- `run_agent_loop` 返回 `result.new_messages`；因本模块以 prompts=[] 调用，历史消息只存在于 context.messages，不会再次出现于 new_messages —— 结构上杜绝整段重写历史。
- 显式保险：过滤 UserMessage（persist 合同禁止重复写用户首消息）；按 message_id 排除已持久化行；随后一次性调 `persist_conversation_messages()`。
- 不依赖 DB unique（session_id, message_id）作为主要去重逻辑（该约束仅作最后防线）。

### 事务边界（真实实现）

- 网络等待期间不持有 DB 事务：① start 短事务（running + run_started）立即 commit；② restore 只读后立即 rollback；③ run_agent_loop 网络等待期无任何 DB 事务；④ 收尾：persist_conversation_messages 自带一次提交，事件+终态在随后一次 commit。
- 已知妥协（记录，未重构）：persist_conversation_messages 内部自提交导致"新消息提交"与"run 终态提交"是两个事务；若两次之间进程崩溃，可能出现消息已写而 Run 停在 running 的中间态 —— 该中间态语义上等价于 interrupted 恢复场景（P05-C/D 的 recovery 职责），本轮按复用优先原则接受。

### 测试（实际命令与结果，backend，项目 venv，禁插件缓存）

- 新增 Runner：`pytest tests/agents/conversation/test_runner.py -q` → 8 passed
- P01 回归（纯合同，confcutdir 隔离父 conftest）：`pytest --confcutdir=tests/conversation tests/conversation -q` → 90 passed
- P03 回归：`pytest --confcutdir=tests/agent_loop tests/agent_loop -q` → 30 passed
- P04 回归：`pytest tests/conversation_persistence -q` → 11 passed
- 全后端：`pytest tests -q --ignore=tests/conversation/test_isolation.py` → 539 passed；隔离测试单独 `pytest --confcutdir=tests/conversation tests/conversation/test_isolation.py -q` → 3 passed
- 覆盖场景：无 Tool 单轮；一次 ToolCall（calculator，工具结果回到第二次模型请求）；多轮恢复（历史顺序 user/assistant/user，只新增本轮消息）；Provider 抛异常 → failed 且无伪助手消息；模型 error 终态 → failed；cancel_event 预置 → cancelled 且零模型请求；终态 Run 不可再启动；legacy(case_generation) Run 被拒。

### Deferred（未实现，留给后续）

- Worker 分发（conversation → ConversationRunner；legacy → AgentRunner）与 queued claim 规则放开（P05-C）；
- lease / heartbeat / fencing / follow-up / 队列暂停（P05-C/D）；
- cancel 的 Worker 层传播与 DB cancelled 状态同步（P05-D）；
- AgentLoop 执行事件逐条落库与 SSE 推送（P06）；
- stopped / waiting 终态的会话级语义（工具显式终止、审批等待恢复；P10 Approval 相关）；
- 模型 Provider snapshot/配置来源（Runner 已注入；由 Worker/配置中心在 P05-C/P06 提供）。

## 2.19 2026-09-04 — V2-P05-C：Worker Dispatch + Conversation Run Claim（已实现并测试）

- 授权范围：Worker 分发 + conversation claim；不实现 P05-D heartbeat/fencing/stale recovery，不实现 P05-E follow-up；不删除 legacy Workflow；不改 frontend / Alembic / DB schema / V3。

### Claim 修改（backend/app/services/agent/agent_run_service.py）

- `next_queued_run_id()` / `claim_queued_run()`：去掉 `workflow_code != "conversation"` 过滤，conversation 与 legacy 共用同一 queued 队列（按 id 升序）；claim 语义不变（原子条件 UPDATE，queued→running + worker_id + heartbeat_at + started_at，调用方立即 commit）。active_slot 语义由 P04 的 UQ(session_id, active_slot) 约束保证，claim 不绕过。
- 测试更新：conversation_persistence 的"P05 前 selector 跳过 conversation"旧断言随特性改为"P05-C 后 selector/claim 可领取 conversation queued Run"。

### Worker Dispatch（backend/app/workers/agent_worker.py）

- `AgentWorker.__init__` 新增可选 `conversation_runner_factory`（缺省 None → conversation Run 报 agent_unknown_workflow 落 failed，安全失败）。
- `_run_once()` claim 后按 `run.workflow_code == "conversation"` 分发：conversation → `_run_conversation()`（`asyncio.run(conversation_runner.run(db, run_id))`，同步 Worker 内每 Run 独立事件循环）；其余 → 既有 `runtime_factory(on_step_boundary)` 的 legacy AgentRunner 路径（行为不变）。
- Worker 异常边界与 legacy 同一策略：Runner 外部 unexpected exception → rollback → 仅当 Run 仍 running 时 `_mark_failed(agent_runtime_error)`（幂等，不重复 finalize 已终态 Run）。ConversationRunner 内部执行期异常自行收敛为 failed outcome，Worker 不重复处理。

### queued→running ownership（结论）

- **claim = queued→running + worker ownership**（status/worker_id/heartbeat_at/started_at，不写任何事件）——legacy 与 conversation 统一；
- **Runner = 生命周期事件与终态**：ConversationRunner `_start_run()` 对 running 不再 transition，只写一次 `run_started`（claim 不产生事件 → 每个 Run run_started 恰好一个）；run_succeeded/failed/cancelled 由 Runner 收尾。legacy AgentRunner 行为未改动（其 queued→running 分支只服务直调场景，claim 后为 running 不重复事件）。

### Provider / ToolRegistry 注入来源（真实实现）

- worker main() 复用同一 `build_default_tool_registry()`；conversation runner factory 注入：统一 `LLMGateway()` + 由 Settings（LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）构造的 `ProviderSnapshot`；不 hardcode Key。
- 已知 transitional 限制（记录）：conversation 当前与 legacy 共用默认 ToolRegistry（含 T05 九个用例工具，只读或需审批者会被默认 Policy 拦截）；conversation 工具白名单与模型场景绑定（agent_chat 场景/配置中心）属 P06，本轮不做。

### Transaction boundary

- Worker 在 claim 后立即 commit，进入 Runner 前无 claim 事务；ConversationRunner 网络等待期间无 DB 事务（start 短事务 commit → restore/assert 只读后显式 `db.rollback()` → run_agent_loop → 收尾两段提交）。新增 P05-C 最小修复：`_assert_history_ends_with_current_user_message()` 后再 `db.rollback()`，避免进入 await 前 autobegin 悬挂读事务；用共享单连接 SQLite 探测测试验证模型等待期间另一 Session 可正常查询。

### 测试（实际命令与结果，backend，项目 venv）

- 新增 `tests/workers/test_agent_worker_conversation.py`（8 项）：Worker claim+执行 conversation E2E（submit→run_once→succeeded+assistant 入库+run_started 唯一+流期间无 DB 事务）；dispatch 路由 conversation→ConversationRunner / legacy→AgentRunner（spy）；无 queued → idle；runner unexpected exception → failed 且 Worker 存活、单一 finalize；未配置 conversation factory 安全失败；claim service 不再排除 conversation；conversation+legacy 同一队列按 id 排序。
- runner 回归 `tests/agents/conversation/test_runner.py` 9 项（含新"模型等待期无 active transaction"探测）。
- 回归：`pytest tests/workers tests/agents tests/conversation_persistence tests/api tests/services` 通过；P01（confcutdir）90、P03（confcutdir）30。
- 全后端：`pytest tests -q --ignore=tests/conversation/test_isolation.py` → 548 passed；isolation 单独 3 passed。

### Deferred（未实现，留给后续）

- P05-D：heartbeat / lease refresh / fencing / stale recovery / long-LLM protection；Worker cancel 状态传播。
- P05-E：follow-up queue / failed-head handling / conversation continuation semantics。
- 其他：同步 Worker 内 asyncio.run 的异步化候选（P05-D 评估）；conversation 工具白名单与模型场景绑定（P06）；conversation AgentLoop 执行事件逐条落库与 SSE（P06）。

## 2.20 2026-09-04 — V2-P05-D：Worker Execution Ownership Reliability（已实现并测试）

- 授权范围：lease/fenced heartbeat/stale recovery/fencing token/Worker 层 cancel propagation；不实现 P05-E follow-up；不开始 P06；不重构 Worker Pool；不改 frontend/V3。

### 新增 DB 字段（最小迁移）

- `agent_runs.execution_token`（Integer，nullable）：P05-D fencing 执行代次。Alembic `0004_agent_run_execution_token`（down_revision=0003），与 create_all 先建表场景幂等（存在且 nullable 即返回）；downgrade 只删该列；历史行保持 NULL（旧数据安全），任何新 claim 起都会获得 token。未新增队列表。

### Execution ownership model（真实代码）

- claim（agent_run_service.claim_queued_run）原子获得 worker_id + heartbeat_at + started_at + execution_token；token 由 `COALESCE(execution_token,0)+1` 在条件 UPDATE 中递增，随后同事务 SELECT 读回返回给调用方（`int | None`，None=竞争失败）。两个 Worker 不可能拿到同一代次。
- heartbeat（agent_run_service.heartbeat）改为 fenced：WHERE status='running' AND worker_id=… AND execution_token=…；rowcount=0 表示 ownership lost/非 running。
- assert_execution_ownership：Runner 关键写前复核，不匹配抛 error_code=agent_ownership_lost。
- Worker control（agent_worker.py）：conversation 执行时并行 `_ownership_control` task —— 每 tick（默认 AGENT_HEARTBEAT_INTERVAL_SECONDS=10.0，测试 0.02）用**独立 Session + 短事务**做 fenced heartbeat，并对 rowcount=0 做 SELECT 复核区分：cancelled（用户取消）→ cancel_event；lost（仍 running 但 worker/token 不匹配）或 finalized（他人已终结）→ cancel_event。heartbeat 异常（连续 heartbeat_failure_limit 次，默认 1）→ 安全中止，不假装 ownership 正常。control 不写 AgentEvent（不制造噪声事件）。
- Runner（conversation/runner.py）：run() 增加 worker_id/execution_token 参数；恢复/执行后、任何消息持久化与终态写入前用标量 SELECT 复核 `_execution_state`（不走 ORM 身份映射，避免读到旧 ownership）——terminal（已被外部终结）→ 不再写任何状态（run_finalized=False，outcome 镜像 cancelled/succeeded/already_terminal）；lost → outcome failed/ownership_lost/run_finalized=False，不写消息不覆盖新 owner；ok 才 persist/finalize。AgentLoop 保持纯 P03（只知 cancel/deadline/budget/tools/provider，无 fencing/SQL）。

### Cancel propagation（真实路径）

- 来源：现有 API `POST /agent/runs/{id}/cancel`（transition running→cancelled + 一次 run_cancelled 事件，取消方写入，不加新字段）。
- 传播：Worker control 每 tick 观察到 status=cancelled → cancel_event.set() → SlowGateway/AgentLoop 协作中止（aborted/canceled）→ Runner 发现 terminal → 不再写（run_cancelled 不重复、run_started 仍唯一）。协作式取消：Provider 不做即时杀死，若 Provider 不支持取消只能在模型调用结束检查（本轮 Fake 为协作式，真实 Provider 限制如实记录）。

### Stale recovery

- 复用既有 recover_stale_runs / mark_interrupted：running + heartbeat 超时 → interrupted（条件 UPDATE WHERE status='running'），保留 worker_id 供排查；不自动 requeue（遵循现有状态机）；interrupted 后旧 token 心跳必然失败；重新排队后再次 claim token 递增（测试覆盖 token1→2）。

### 配置

- core Settings 新增 AGENT_HEARTBEAT_INTERVAL_SECONDS=10.0 / AGENT_STALE_THRESHOLD_SECONDS=300.0（heartbeat interval << stale threshold）；Worker 构造参数 heartbeat_interval_seconds 缺省读取 Settings。

### Transaction boundary

- heartbeat 每 tick 独立 Session 短事务立即 commit；模型网络等待期间无长 DB 事务（P05-C 探测测试保持通过）；Runner 所有权复核与写事务分离。

### Tests（实际命令与结果，backend，项目 venv）

- 新增 `tests/workers/test_agent_worker_reliability.py` 7 项：claim token 单调递增（token1→重新 claim token2）；fenced heartbeat 正确/旧 token/非 owner；长 LLM 等待（0.18s）期间 heartbeat 持续刷新且另一 Session 查询不被阻塞；stale recovery → interrupted + 旧 token 失效 + 不自动 requeue；ownership 执行中被替换（token 1→2）→ 旧 Worker 不 finalize/不写消息/新 owner 不被覆盖；DB cancel → cancel_event → AgentLoop abort → Run cancelled（run_started/run_cancelled 各一次，无成功/失败事件）；Runner 直调级 ownership_lost outcome.run_finalized=False。
- 全后端：`pytest tests -q --ignore=tests/conversation/test_isolation.py` → 555 passed；isolation 单独 3 passed。迁移测试 head 更新至 0004（含 overlap create_all 幂等路径）。

### 已知限制（记录）

- ownership 复核为"关键写前单点校验"：校验与随后的消息/终态提交间隔毫秒级，极端并发下仍可能有窗口，未做行级条件 UPDATE 写入（后续如需可把终态/事件写成 fenced 条件 UPDATE）。
- 同步 Worker 内每 conversation Run 一个 asyncio.run 事件循环（P05-C 保留）；异步化候选留后续评估。
- legacy 仍为 step-boundary fenced heartbeat（步骤间心跳），conversation 为 interval control heartbeat——两种节奏的临时差异已记录；CaseGenerationWorkflow 本身无行为变化（仅 step_hook 心跳带上了 execution_token 条件）。
- cancel 后 AgentLoop 的响应速度取决于 Provider 协作取消能力。

### Deferred（未实现，留给后续）

- P05-E：follow-up queue / failed-head handling / continuation ordering / steering / interrupt user message。
- 其他：cancel 的 SSE/前端表达（P06）；conversation 工具白名单与模型场景绑定（P06）。

## 2.21 2026-09-04 — V2-P05-E：Conversation Follow-up Queue 与连续 Turn 调度（已实现并测试，P05 complete）

- 授权范围：follow-up 队列与连续 Turn 调度；不做 steer/SSE/前端/Artifact/Skill/compaction/新 Approval；不删 legacy。

### P05-D preflight（本轮修复）

- A（stale TOCTOU）：`mark_interrupted` 增加可选 `stale_before`——提供时 UPDATE 自身重新包含 stale 条件（heartbeat 超时或 null-heartbeat+started 超时），杜绝 find→mark 窗口内被新心跳的误中断；Worker recover 传入 stale_before。回归测试：fresh heartbeat 后 mark 返回 False、Run 保持 running。
- B（MySQL rowcount=0）：ownership probe 在 heartbeat rowcount=0 后重新 SELECT——若 status=running 且 worker_id/execution_token 仍匹配则视为 ok（并以复核作为续期），不再误判 lost。

### Follow-up 持久化与 active_slot 语义

- `submit_conversation_turn(queue_mode="reject"|"follow_up")`：默认 reject 保持 P04 409 语义；follow_up 在 head 运行时保存 UserMessage + queued AgentRun（active_slot=NULL）。幂等合同不变（同 key 同内容 replay、不同内容 conflict）。
- active_slot 最终语义：**head（可执行）= active_slot=1**（queued/running 均持槽）；**queued follow-up = active_slot=NULL**；终态（transition_status 对 conversation）自动清槽；UQ(session_id, active_slot) 保证同会话最多一个 active。

### Promotion（原子）

- `conversation_service.promote_next_conversation_run(session_id)`：pause 守卫（最新终结 head ∈ {failed,interrupted} → 返回 None，不提升）→ 选最早 queued follow-up → 条件 UPDATE active_slot: NULL→1（同候选并发只有先到者满足条件；不同候选并发由 UQ 裁决，IntegrityError 回滚返回 None）→ 返回 promoted run id。
- Worker：conversation 执行终态 succeeded/cancelled 后调用 promote（failed/interrupted 不调用=暂停）；queued follow-up 被用户 cancel（queued→cancelled）后 promotion 自动跳过。

### Run-bounded Context Restore

- `restore_conversation_messages(..., until_sequence_no=)` + 新逻辑顺序恢复：每条消息按**所属 Turn 的用户消息序号（owner sequence）**归组，只保留 owner <= 当前 Run 用户序号的行，并按 (owner, sequence_no) 排序。因此：A 执行期间已入库的 B/C 用户消息不会泄漏给 A；A 的助手消息即使晚于 B/C 用户消息落库（sequence 更大），A 与后续 B/C 仍按逻辑 Turn 顺序看到完整上下文。
- ConversationRunner 以本 Run `user_message_id` 的 sequence_no 为上界调用 bounded restore。

### queue_state（派生，无新 DB status）

- `conversation_queue_state(session_id)` → {state: idle|executable|paused, head_status, queued_follow_ups}：无 head 且最新终结 head failed/interrupted 且有 follow-up → paused；P06 前端直接消费。

### 语义汇总（终态队列）

- succeeded → promote next；cancelled（含执行中用户取消）→ promote next；failed/interrupted → pause（不 promote，P06 解释）；queued follow-up cancel → promotion 跳过。

### 测试（实际命令与结果，backend，项目 venv）

- 新增 `tests/conversation_persistence/test_conversation_followup.py`（11 项）：head running 时 follow-up 持久化且不可 claim/不阻塞全局候选；B/C 顺序稳定；promotion 只提升最早一个且逐级推进；不同 Conversation 互不阻塞；failed/interrupted pause（服务与 Worker 两层）；cancelled head promote；queued follow-up cancel 跳过；幂等 replay/conflict；run-bounded restore A 不见 B（服务层）；并发 promotion 最终唯一 active_slot；Worker E2E（A 慢执行期间提交 B/C → A 成功后 B、C 顺序执行、消息与上下文顺序正确、不并行）。
- `tests/workers/test_agent_worker_reliability.py` 增 TOCTOU 回归（8 项）。
- 全后端：`pytest tests -q --ignore=tests/conversation/test_isolation.py` → **567 passed**；isolation 单独 3 passed。

### Deferred

- P06：HTTP/SSE/前端表达（含 paused/executable 展示、取消 UI）、conversation 工具白名单与模型场景绑定；legacy 入口替换收尾（AgentRunner/CaseGenerationWorkflow/legacy API 保留 compat）。P05 范围全部完成。

## 2.22 2026-09-04 — V2-P06：Conversation API + SSE + 基础持续聊天工作台（后端完成并测试；前端接入+build；浏览器 E2E 待验收）

- 授权范围：新 Conversation API/SSE/前端 Chat；不做 TestArtifact/MindMap/Artifact Tool/SSE 之外的 UI。

### Preflight

- 文档：01 状态更新为 P05 已完成 / P06 当前。
- queued active head cancel：新增 `conversation_service.cancel_conversation_run`（单一 conversation cancel 边界）——head（queued 或 running）取消 → run_cancelled 事件 + 同事务原子 promote 下一个 queued follow-up；queued follow-up 取消只取消自身、不误 promote C；非 owner/非 conversation/已终态按合同报错。HTTP 与 service 测试覆盖。

### 后端实现

- `routers/agent/conversation_router.py`：POST/GET /agent/conversations、GET /{id}（快照）、GET /{id}/messages（after_sequence/limit，结构化 content）、POST /{id}/turns（202，复用 submit_conversation_turn，queue_mode follow_up/reject）、GET /{id}/events（SSE：DB AgentEvent 游标轮询，Bearer 统一鉴权，Token 不进 URL，keep-alive，断线带 after_sequence 续传）、POST /conversation-runs/{id}/cancel、GET /conversation-capabilities。所有权一律 404（不泄露存在性）；configuration_not_ready → 503。
- `services/agent/conversation_service.py`：cancel_conversation_run、conversation_snapshot、list_messages_since、list_events_since。
- `services/agent/conversation_provider.py`：agent_chat 场景解析 → ProviderSnapshot（配置中心），未配置抛 configuration_not_ready；capabilities 用 is_conversation_model_ready。
- `agents/tools/conversation_safe_tools.py`：Conversation 工具白名单（calculator，只读无副作用）；Worker 不再把 legacy T05 工具暴露给 Conversation。
- `workers/conversation_event_persister.py` + worker 接线：AgentLoop 事件经 sink 安全落库为 AgentEvent 行（conversation_tool_started/finished、conversation_message_committed、conversation_text_delta 聚合 0.25s/400 字符；run 生命周期沿用既有 run_* 名）；文本增量聚合非逐 token；不落隐藏 reasoning/原始日志；独立 Session 短事务，best-effort 不阻断主执行。
- `runner.py`：新增 event_persister 钩子（compose sink）。
- Worker main：conversation factory 使用白名单 registry + 每 Run 经 conversation_snapshot_factory 解析 agent_chat 快照。

### 前端实现（build 验证，浏览器未运行）

- `components/v2-chat/`：conversationApi.js（含 fetch+ReadableStream SSE、Bearer 头不进 URL）、useConversationChat.js（idle/queued/running/paused/failed/interrupted/cancelled 状态、follow-up 提交、SSE 增量渲染、断线重连、refresh restore、Stop）、V2ChatPanel.jsx（会话列表/新建/消息/工具活动/流式文本/Queued/Paused/Stop/错误）、v2Chat.css（文本渲染不使用 dangerouslySetInnerHTML）。
- App.jsx 入口从 TestAgentWidget（旧固定 Workflow 悬浮台，保留文件并标注 deprecated）切换到 V2ChatPanel。`npm run build` 通过。

### 测试（实际命令与结果，backend，项目 venv）

- 新增 `tests/api/test_conversation_api.py`（11 项）覆盖 §24 场景 1-20：创建/owner/list、cross-user 404、turn 202/幂等/409、follow_up/reject、messages 游标与结构化 ToolCall/ToolResult、快照 queue_state、cancel（running head/queued head promote/follow-up 仅取消）、SSE auth/cross-user/游标续传去重、capabilities 无 Secret、HTTP+Worker+Fake 验收故事（17→calculator→22→refresh→17）、provider error 快照一致性。
- 全后端：`pytest tests --ignore=test_isolation.py` → 578 passed；isolation 3 passed。

### 已知限制 / Deferred（如实记录）

- 浏览器级 E2E（§26）未运行：本仓库无 vitest/Playwright 前端测试基建，本环境无浏览器；前端仅 build 验证。
- SSE 为 DB 轮询 + 持久化事件（Worker 与 API 独立进程下的唯一跨进程通道）；文本增量按聚合行持久化（非"transient only"，见 persister 注释）。
- capabilities.worker_status 恒为 unknown（跨进程健康检查留 P10，不伪报 online）。
- agent_chat 场景需要在模型管理配置后 model_ready 才为 true（真实供应商验证留 P10）。
- 前端 lint 未运行（仓库无 lint 脚本基线噪音评估）；旧 legacy 悬浮台文件保留 deprecated，V1 入口未物理删除。
- 未触碰 docs/V2 根目录 P06/P07_EXECUTION_GUIDE.md（非本轮创建，未提交为正式规范）。

### P06-R01 交互与可靠性修正（2026-09-04）

- 前端将消息游标与事件游标彻底分离；SSE 与普通 API 统一使用 `VITE_API_BASE_URL`，并补齐 401 登录失效处理和重连定时器清理。
- SSE 后端释放请求级读事务，每次轮询使用独立短 Session，避免 MySQL REPEATABLE READ 下看不到新事件。
- `conversation_message_committed` 不再由内存 `message_end` 提前伪报；消息、committed 事件、用量和 Run 终态在 ownership 行锁下同事务提交。
- 执行期增量/工具事件写入也携带 worker_id + execution_token 做 fencing，旧 Worker 失去所有权后停止写事件。
- Conversation Chat 改为独立浮窗：可拖动、原生自由缩放、最小化、最大化；按用户保存模式、位置和尺寸，小屏自动贴合视口。
- 截图复核后修正文案与布局：移除 `Revision/Idle/tools` 混合文案，改为中文状态/工具名；用户消息右对齐；按钮颜色与间距显式定义；失败/中断不再被 refresh 覆盖成空闲。
- 无回答根因经只读查询确认：现有 Run 5/6 均被 Worker 消费，但因缺少 `agent_chat` 场景以 `configuration_not_ready` 失败。默认场景现包含“Agent 对话”；仅有一个可用模型时首次初始化自动绑定，多模型不猜测。当前本机已初始化为 `agent_chat → model_id=1`，`model_ready=true`，未发起真实模型请求。
- 最小化使用独立 launcher 坐标，每次点击最小化先吸附右下角，之后仍可单独拖动；恢复时保留大窗口原位置与尺寸。
- 验证：相关后端 62 passed（含默认场景单/多模型选择边界与 Worker 配置错误码保留）；新前端文件 ESLint 通过；`vite build` 通过。电脑操作复核未发现可复用的已登录浏览器标签，真实登录/真实模型交互仍需人工 E2E。

### P06-R02 回复延迟与流式订阅修正（2026-09-05）

- 实际耗时依据：只读查询最近成功的 conversation Run 7/8/9，started_at→finished_at 分别为 3/4/4 秒；事件表中首批文字比 run_started 晚约 2–3 秒。数据库 created_at 与 Python 时间存在时区差异，未用两者直接相减计算排队时间。
- 确认前端缺口：25 秒正常 SSE 超时被累计为重连失败，空闲超过五次后不再订阅；网络异常仅报错而不触发重连；异步初始化、旧会话回调与重连定时器可能在切换/卸载后继续生效。
- 新增单一事件订阅器，正常超时持续续接、网络异常有上限间隔退避、按事件游标去重、取消关闭 reader 与定时器。Hook 加入会话代次隔离，合并终态/消息通知触发的刷新，文字保持到最终消息加载；回答中每两秒核对快照，作为断流兜底。
- 确认并修复数据库连接占用：Runner rollback 后读取 run.id、SSE rollback 后读取 current_user.id 都会触发 ORM 隐式查询并重新持有事务。改为使用已取得的标量，新增直接检查 in_transaction 的回归；旧 Runner 测试先失败后通过。
- SSE 等待改为异步 sleep，仅短数据库查询在线程中完成，空闲流不再持续占用 FastAPI 同步请求线程。
- 验证：39 项受影响后端测试通过；6 项前端流测试通过（空闲超过五次、断网/读中断恢复、UTF8 分片即时展示、取消重连、401、迟到事件）；修改文件 ESLint 与前端构建通过。
- 真实模型短探测：合成“只回复 OK。”、max_tokens=64、禁用重试；放行网络后一次调用首字 1.364 秒、结束 1.366 秒、stop，无错误。该数字只代表模型接口探测，不是浏览器端到端耗时；首次沙箱探测返回 network_error，不作为模型性能样本。
- 确认无 queued/running 任务后重启现有 API 和 Worker，新进程健康检查通过。浏览器端真实消息的端到端耗时未新增测量。

## 2.29 2026-09-06 — V2-P08 Artifact Tools + Test Design Skill + 第一版 Agent Eval

### A. Artifact Tool 清单

- Read：`get_current_artifact`、`read_artifact_outline`（depth/max_nodes）、`read_artifact_nodes`（最多 20）、`search_artifact`（keyword/type/tag/limit）、`get_artifact_diff`（最近 1～10 Revision，输出变更上限）、`read_requirement`（仅绑定来源且正文有长度上限）。
- Write：`add_artifact_node`、`update_artifact_node`（受控 patch）、`delete_artifact_node`、`move_artifact_node`、`batch_apply_artifact_operations`（最多 10 个增量 operation、一次 Revision）。没有注册 replace/save_full_tree/restore Tool。
- Quality：`validate_test_artifact`、`find_duplicate_cases`、`analyze_test_coverage`。另有受控 `load_skill`；加既有 calculator 后 Conversation 白名单共 16 个 Tool。
- Handler 参数均经 Pydantic strict + extra=forbid；成功/业务失败同时写入模型可见 JSON 文本与 `details`，ToolResult 的 call_id/name 仍由 P03 原调用闭合。

### B. RuntimeContext / C. Artifact binding

- `AgentSession.context_json.focused_artifact_id` 是可恢复的可信绑定；新增 `POST /agent/conversations/{conversation_id}/artifacts/{artifact_id}/focus`，owner、项目和 Artifact 可读性由服务端校验，Snapshot 返回 focused_artifact_id。
- ConversationRunner 从持久化 Session 读取绑定，释放读事务后由 `build_artifact_runtime_context` 实时计算 Artifact read/write 权限，注入 user/conversation/project/artifact/run、worker_id/execution_token 和 Session factory。模型参数不能覆盖这些字段。
- Tool 每次执行重新核对 Session owner、mode、focused Artifact；生产写入还在同一事务中复核 execution ownership。

### D. Application Service 边界 / I. Events

- Tool handler 不直接新增/修改 Artifact ORM；所有写入只调用 P07 `artifact_service.apply_operations()`，人工 API 与 Agent 共用同一写入口。Requirement 读取复用既有 requirement service。
- Agent Revision 写入 actor_type=agent、actor_user_id、conversation_id、run_id、summary；同事务写 `artifact_revision_created` 与 `artifact_diff_created` 事件，Artifact Revision 不是聊天消息。

### E. Revision conflict / F. Policy

- stale expected_revision 返回 `{status:error,error_code:revision_conflict,data:{expected_revision,current_revision},retryable:true}`，不在 Tool Executor 内自动重试；Fake Agent 已验证收到冲突后 read 当前节点并有限重试成功。
- Action Risk：read/quality 允许；单 add/update/move 允许；小删除允许；删除影响节点 >=10、batch 增加 >5 或总影响 >5 返回 `approval_required` + impact 且不落库。完整 Approval persistence/suspend/resume 留 P10。

### G. Test Design Skill

- `backend/skills/test-design/SKILL.md` 含测试维度与 read-before-write、minimal-edit、respect-user-structure、no-mandatory-path 等规则，没有 phase/next_step/固定 coverage 流程。
- Skill Catalog 只加载注册名 `test-design`，校验 name/version/description、32KiB 上限、路径必须在白名单 root 内，记录 SHA256；`load_skill` 不接受任意路径、不执行脚本、不扩张 Tool 权限。System prompt 只注入摘要，正文按需加载一次。

### H. Quality Tools

- validate：空标题、test_case 缺 steps/expected 等规则型诊断；duplicate：规范化标题/关键字段后 exact 或 SequenceMatcher 阈值候选；coverage：positive/negative/boundary/state/permission/timing/idempotency/consistency 的标题与 tags 规则识别。
- 三者只读取 Tree，不调用 apply_operations；测试同时断言 current_revision 不变。没有 embedding/vector DB/RAG。

### J. 8 类对话与最终故事

- 8 类 Fake Provider 场景逐项通过：空 Artifact 测试点、局部分支三用例、单节点最小修改、最近 Diff 定位“第二个”、move、只查重、coverage 后下一轮补缺口、直接补用例不强制测试点。
- 最终故事通过：Revision 1→2（测试点）→3（三条边界）→4（删除第二条）→5（修改 TC021）；随后 duplicate/coverage 均保持 Revision 5。另测 revision conflict→read→retry→成功。

### K. Eval

- `backend/evals/p08/` 提供独立 24-case Scripted Eval 与指标计算：Task Success、Tool Selection、Tool Argument、Artifact Edit、Unintended Modification、Instruction Following、Revision Conflict Recovery、Quality Non-Mutation。
- 本次 scripted baseline：case_count=24；除 unintended modification rate=0.0 外，其余指标=1.0。结果仅证明固定期望/脚本和指标基础设施可用，不代表真实模型效果；真实模型 Eval 留 P10。

### L. Tests

- P07/P07.1 前置复验：Service/API/Migration `53 passed`。
- P08 Tool + Agent 场景：`23 passed`；最终故事与冲突恢复包含在内。
- P08 + P07 + P03 + P05/P06 组合回归：`135 passed`（后续权限/输出收紧后 P08+P03+Conversation API 再跑 `64 passed`）。
- isolation：`3 passed`。Eval：24 cases 全部满足 scripted baseline。
- 完整 backend：首次 `664 passed, 1 failed`；失败为既有 SQLite 双线程 promotion 用例的 `results` 列表偶发为空，数据库仍只有一个 active_slot；该单项立即复跑 `1 passed`。不把它写成全绿，也不累计测试数。
- `git diff --check` 通过。未调用真实模型、未修改真实 Artifact 数据。

### M. Deferred / Stop boundary

- P09：MindMap、Diff/History UI、Node Inspector、人工 Artifact 编辑 UI及实时联动。
- P10：Context compaction、完整 Approval suspend/resume、真实模型 Eval、MySQL 并发/恢复最终验证。
- 未实现 API 执行、RCA、Test Data、Defect Agent、RAG、multi-agent；这些属于 V3。P08 完成后停止，未进入 P09。

## 2.23 2026-09-05 — P06 Frontend UX Hardening + Visual Redesign（Turn 数据层/Bug 修复/契约补充）

- 授权范围：修复 Conversation Chat UX/归属 Bug 并做开发者工作台风视觉收敛；不改 Agent Runtime/follow-up/Worker/AgentLoop 语义；不动 P07/MindMap。

### 前端现状核对（并行工作区已存在的基础）

v2-chat 已含浮动窗口（min/max/launcher）、SSE 订阅（eventStream.js 自动续期/重连/去重）、错误文案表、后端快照已带 latest_run。缺口与本次交付：消息仍按物理 sequence 平铺、Tool 活动是 Conversation 级尾部列表（Bug1/2）、无滚动策略（Bug3）、标题恒为"新对话"（Bug4）、New Chat 已在侧栏顶部（Bug5 现状已满足）。

### 后端最小合同补充（仅为前端正确归组所需，未动 Runtime）

- `GET /conversations/{id}/events` 事件项补 `run_id`（AgentEvent 行本就有 run_id；schema ConversationEventItem 同步）。
- 新增 `PATCH /agent/conversations/{id}`（body `{title}`），owner-only（隐藏存在性 404），service `conversation_service.rename_conversation`。

### Bug1/Turn 归组（核心）

- 新增纯函数 `v2-chat/turnModel.js::buildConversationTurns({messages, events, overrides})`：
  归组主键 = 消息/事件的 `run_id → 该 Run 的 user message sequence`（owner sequence）；缺失 run_id 的旧行才退化为"归属最近 sequence 更小的 user"（不参与主路径）。输出 `[{ownerSequence, runId, userMessage, userText, assistantTexts, assistantMessage, toolActivities, status, streamingText}]`，按 owner sequence 排序。Tool 事件按 `tool_call_id` 合并为单条 ToolActivity（running/success/error），按 run_id 挂到所属 Turn。
- UI 只消费 Turns（`ChatTurn`/`ChatTimeline`），不再直接遍历原始 messages/activity；流式文本挂在 active run 的 Turn 内。
- hook：SSE 事件（含 run_id）留存最近 500 条 → turns memo（overrides 含 activeRunId 与流式文本）；open 时重置。

### Bug2/Tool 归属

`conversation_tool_started/finished`（现在带 run_id）→ 合并 ToolActivity → 只出现在产生它的 ChatTurn；下一轮不再重复。UI 低干扰：`ToolActivity.jsx` 单行"○/✓/✕ toolName + 状态"，默认折叠，仅可展开 error_code，不渲染参数/日志/原始结果。

### Bug3/滚动策略

- 纯函数 `scrollPolicy.js`（isNearBottom/threshold 80px；shouldAutoScroll 场景判定）。
- `ChatTimeline`：打开/切换/自己发送强制到底（rAF 内，避开 effect 内同步 setState）；流式仅在近底部跟随；用户上滚出现浮动"↓ 回到最新"；绝不无条件拉回。

### Bug4/Conversation Title

- 首条用户消息提交成功后自动命名（确定性：去空白、trim、≤24 字，无需 LLM）；创建仍用"新对话"。
- 支持双击标题 → prompt 重命名（走新 PATCH 接口）；hook `setTitle`/`renameIfNeeded` 同步会话列表与激活项。

### Bug5/Sidebar

核对现状：＋ New chat 已在侧栏顶部、历史列表紧随其后，无"另一处新建"；本轮未重复重构。

### 组件树与样式

- 新增组件：ChatTimeline / ChatTurn / ToolActivity / ChatComposer；纯函数 turnModel / scrollPolicy。
- CSS 追加开发者工作台风格（白色画布、灰阶、轻边框、内容 860px 居中、用户右侧浅灰块、assistant 自然文本、tool 弱化行、composer 聚焦边框、Queued/Paused/Failed 只对异常/等待出徽标）；保留既有窗口 chrome（暗色 header/launcher 由并行工作区设计，未改）。

### 测试与构建（真实结果）

- `npm test`（node:test，新增 tests/turnModel.test.mjs）：6 项全过——Bug1 交错 sequence 归组、Bug2 tool 只属 A、started/finished 合并、follow-up queued、终态事件状态、scrollPolicy 判定。
- `npm run lint`：0 errors（8 个 warning 均为既有旧 pages 的 hooks 依赖提示）。
- `npm run build`：通过。
- 后端回归：`tests/api/test_conversation_api.py` + `conversation_persistence` → 34 passed（含新 PATCH/事件 run_id 未破坏原合同）。

### 已知限制/说明

- 浏览器人工验收尚未执行（无自动化浏览器基建；需按 §25 场景手测，通过后再关闭 P06 剩余 UI 门禁）。
- 双击重命名为 prompt 实现（保持简单）；删除会话无后端接口，未造 UI。
- 视觉大改以追加 token 方式覆盖聊天内容区；窗口级视觉（header/launcher）沿用并行工作区的既有设计语言，未做推翻式重画。

## 2.24 2026-09-05 — P06 FE 修复轮（浏览器实测反馈）

- 实测问题与修复：
  1. 上一轮工具记录反复出现在新回答后 → 根因：无 run_id 事件走"挂最新 Turn"兜底，随刷新迁移。修复：删除该兜底（只接受 DB run_id 或事件到达时解析的 toolOwners），工具只在产生它的 Turn 显示且位于回答之前。
  2. 所有对话仍叫"新对话" → 依赖后端 PATCH /conversations/{id}（旧进程未加载时静默失败）；代码已就绪，需重启后端生效；前端自动命名/双击重命名已实现。
  3. 新增/历史未统一顶部 → 侧栏头部统一为 TestMind 品牌 + ＋New chat，历史列表紧随其后。
  4. 无法上滑看历史 → 滚动高度链缺 min-height 约束；补 .v2chat-main/.v2-timeline min-height + overflow-y:auto；打开/切换会话强制到底、近底部才跟随、上滚出现"回到最新"。
- 验证：lint 0 errors；node:test 6/6；vite build 通过。

## 2.25 2026-09-05 — P06 空白页 hotfix（全量刷新暴露 TDZ 崩溃）

- 现象：浏览器整页刷新后白屏（HMR 增量更新不触发，全量刷新首次暴露）。
- 根因：`useConversationChat` 中 `refresh` 的 `useCallback` 依赖数组引用了其**之后**才声明的 `const backfillToolOwners`（TDZ）。首次渲染即抛 `ReferenceError: Cannot access 'backfillToolOwners' before initialization`；无 Error Boundary → 整棵 React 树卸载 → 白屏。lint/build 均无法发现（运行时语义错误，非语法/未用变量）。
- 修复：将 `resolveOwnerForRun` + `backfillToolOwners` 定义移到 `refresh` 之前（二者只依赖 refs，无循环）。
- 验证：ESLint 通过；headless Chrome（CDP）注入真实登录态整页加载复现/回归：修复前捕获到该 ReferenceError 且 `#root` 空；修复后 0 exception，侧栏菜单 + 主页面 + V2 Chat 悬浮球正常渲染。
- 教训（写给自己）：同一 hook 内 `const` 之间的交叉引用必须保证声明顺序先于使用；此类 bug 应补一条静态自检（后续可加 no-use-before-define 或构建期 TDZ 检查）。

## 2.26 2026-09-05 — P06 Chat 前端 Bug Fix + UI Polish（纯前端，未触碰 Agent Runtime）

### Bug1/Stop 取消错 Run
- 根因：`send()` 把 `runRef` 指向最新提交的 follow-up；Stop 取消 B 而不是正在跑的 A。
- 修复：删除 runRef；新增纯函数 `stopTargetRun(snapshot) = snapshot.active_run.id`；`cancel()` 只取消 active head。A running + B queued 时 Stop 作用于 A。

### Bug2/全局 phase 覆盖 Turn
- 根因：submit 后按 submission.queue_state 把全局 phase 改成 queued，顶部错误显示"排队中"。
- 修复：新增 `conversationState(snapshot)`（active_run.status > queue_state executable=queued > paused > 终态 > idle），顶部状态一律由 snapshot 派生，事件仅做瞬时修正（run_started→running，终态→scheduleRefresh）。B 的 queued 由 turnModel 显示（非 active、无终态、无回复）。
- 顺带修复：active head 无已落库 assistant 文本（流式在途）时不再误标 queued → 一律 running。

### Bug3/切换会话滚动
- 删除 `openedOnce` per-conversation 逻辑；每次 activeId 变化都置 force 滚到底（rAF 内），流式仅近底部跟随、上滑不拉回，保留"↓ 回到最新"。

### Bug4/Title 同步
- 新增纯函数 `mergeRenamedConversation`；自动命名与手动改名共用 `applyRenameTitle`，同时更新 conversations list 与 active（header 数据源），不再只改 sidebar。

### Bug5/Markdown
- 新增纯函数 `markdownRender.js`：输出结构化数据（paragraph/bold/inline code/code block/list），组件映射 React 元素；零 HTML 输出 + 文本节点渲染 → 原始 HTML 无法注入；未闭合符号容错。ChatTurn/流式文本均走渲染。

### Bug6/快速连续发送
- 发送门禁 `canSendMessage` 只由 active/paused/modelReady 决定；网络 busy 从发送路径剥离（busy 仅用于"新建对话"操作锁）。Running 中输入框与 Send 均可用，连续 Enter 提交 follow-up 入队。

### Bug7/工具加固
- 合并键由 tool_call_id 改为 (run_id, tool_call_id)（不同 Run 复用同一 callId 不再互相覆盖终态）；同一 Turn 多 Tool 按事件 sequence_no 排序（非 callId 字典序）；React key 同步 run+call。

### UI Polish
- v2Chat.css 整体重写为开发者工作台：白/低饱和灰阶、细边框、少阴影；黑色大标题栏 → 46px 白色细栏（品牌/居中会话标题/运行态细 chip/窗口按钮）；New chat 改紧凑文字按钮；sidebar 240px、激活项浅灰；主内容/Composer 最大 800px 居中；User 浅灰气泡、Assistant 无卡片；Tool 小型灰 inline；去掉常驻"状态/可用工具"调试信息；字体栈 Inter/system-ui/PingFang SC 等；悬浮球改白卡。未复制任何商标。

### 测试与构建（真实结果）
- `npm test`：25/25 通过（原 6 + 新增 19：Stop 目标、conversationState、canSendMessage、mergeRenamed、跨 Run 同 callId 不串 Turn、seq 排序、流式 active running、markdown 5 项）。测试脚本改为 `node --test tests/{turnModel,chatState,markdownRender}.test.mjs`。
- `npm run lint`：0 errors（7 个既有 warning，均在旧 pages）。
- `npm run build`：通过（chunk>500KB 提示为既有）。
- headless Chrome CDP 整页回归：0 exception，主应用 + V2 Chat 正常渲染（防白屏回归）。

## 2.27 2026-09-05 — V2-P07 Test Artifact Core（后端领域，无 Agent/无 LLM）

### 目标与边界
建立首期长期测试资产领域 TestArtifact（Artifact≈repository、Revision≈commit、Operation≈patch），完全独立于 Agent/Conversation/LLM 即可可靠支持：create → add/update/delete/move node → Revision → Diff → Undo → Restore → 乐观冲突。本轮不实现 Artifact Tools / AgentLoop 调用 Artifact / MindMap（P08/P09）。

### 落地结构（轻适配仓库分层；Artifact Domain ≠ agents/conversation）
- models：`app/models/test_artifact/`{test_artifact,artifact_node,artifact_revision,artifact_operation}.py（已注册进 `app/models/__init__.py`）。
- schemas：`app/schemas/test_artifact/`{__init__,api,content}.py（test_case 强 schema：preconditions/steps/expected_results/priority P0-P4/tags；root/group/test_point 只允许空 content；source_refs 数据合同校验）。
- services：`app/services/test_artifacts/`{errors,domain,repository,diff,artifact_service}.py。
- routers：`app/routers/test_artifact_router.py`（薄壳，已挂 main `/test-artifacts`）。
- migration：`alembic/versions/0005_test_artifact_core.py`（down=0004，upgrade create/verify、downgrade 反依赖删表）。
- tests：`tests/services/test_test_artifact_service.py`（§27 32 项 + §28 E2E）、`tests/api/test_test_artifact_api.py`（7）、`tests/migrations/test_test_artifact_migration.py`（5）。

### 语义决策（05 留白/需归一处）
- 表名单数：test_artifact/artifact_node/artifact_revision/artifact_operation。
- order_key=Integer 同 parent 兄弟序号（新增=末尾自增，move 可显式指定）；非 fractional（P07 最简单可测试方案）。
- status 值域（05 未给）：active/archived；actor_type：user/agent/system；operation_type：add_node/update_node/delete_node/move_node/restore。
- root 唯一性：`test_artifact.root_node_id` 为指针列（不建 FK 避免与 artifact_node 双向环），唯一性由事务内 Service 校验保证（新增/verify 防第二 root；root 不可 delete/move/带 parent）。
- revision/conversation_id、run_id 为 nullable 审计整型（不建 FK，Artifact 不耦合 Conversation）。
- Undo/Restore = plan-reconcile：把“当前可见态”对齐到“目标 Revision 重放态”（diff.replay_to_state），生成反向 primitive op（add/update/delete/move/restore），经同一 apply_operations 产出**一个新 Revision**；历史从不物理删除。目标态=当前态时 no-op（不产生空 Revision、不 400）。
- Batch 内支持 add_node 携带 ref、后续 op 用 `@ref` 引用先前节点 id（同批建 group→point→TC 仍“恰好一个 Revision”）。
- Diff 一律由 Operation.before/after 派生（added/updated/deleted/moved），不重比整树。

### 关键机制
- 唯一写入口 `artifact_service`：Router/测试（及未来 UI/Agent Tool）不得直接 db.add Node。
- 一次 operation batch = 一个事务 + 恰好一个 Revision；任何 op 失败 → 抛错由调用方 rollback（全批无痕）。
- 乐观并发：写带 expected_revision；前置快速失败 + 末尾权威条件 `UPDATE test_artifact SET current_revision=+1 WHERE current_revision=expected` 行裁决（rowcount=0 → RevisionConflictError，payload {expected,current}），HTTP 409 带 {error_code,expected_revision,current_revision}；不做 last-write-wins。
- 删除=逻辑删除（deleted_revision=当前 Revision），tree 默认隐藏、不可作 parent/target；restore 恢复时校验 parent 链/内容 schema。
- 服务端控制字段（id/artifact_id/owner_user_id/node_type/created_revision/deleted_revision/created_by/parent_id/order_key 等）不可被客户端 update patch / add 伪造（拒绝测试覆盖）。
- 权限：无项目 Artifact owner-only（跨用户读/写按不存在 404 隔离）；有项目走 permission_service 读写；project 只读(如 viewer)写 → 403 artifact_permission_denied。

### 测试（真实结果，全部 SQLite，不连真实 MySQL/不启 Worker/不调 LLM）
- `python -m pytest tests/services/test_test_artifact_service.py -q` → **36 passed**（含 §28 E2E：create=1 → 一批建组/点/TC=2 → update=3 → move=4 → delete=5 → undo=6（TC001 added 恢复）→ restore rev3=7，历史 1..7 保留）。
- `python -m pytest tests/api/test_test_artifact_api.py -q` → **7 passed**（create 201/tree/批量一 Revision/409 载荷/400/owner 404/forged 字段 400/undo+restore 端点）。
- `python -m pytest tests/migrations/test_test_artifact_migration.py tests/migrations/test_agent_platform_migration.py -q` → **14 passed**（create/downgrade/re-upgrade/overlap verify/结构不一致明确失败；HEAD 更新为 0005）。
- 回归：structure 结构测试 + agent services/API + llm defaults + conversation API/persistence → 73 + 34 passed（agent 全 API 36 项含 Fake Worker）。
- 备注：`tests/conftest.py` 的 db_session 在 drop 前临时 `PRAGMA foreign_keys=OFF`——SQLite DROP TABLE 对自引用 FK 表（artifact_node.parent_id）做隐式 DELETE 时触发 immediate FK 违约；重建后恢复外键。

### Deferred（明确未实现，P08 起）
- Artifact Tools（read/add/update/delete/move/validate/coverage）、Test Design Skill、Agent 调用 Artifact、AgentToolPolicy/Approval、MindMap、SourceRef 解析/追溯 UI、内容类型扩展（api_test_design 等）。全部按 §30 停止边界未进入 P08。

## 2.28 2026-09-05 — P07.1 TestArtifact Hardening（代码审查修正，无功能扩展、不进入 P08）

### 1) get_tree 全层级排序
- 构树完成后对**所有节点**的 children 统一 `sort(key=(order_key, id))`（原先只排 root/orphan 层，nested 层依赖 DB 返回顺序）。
- 新增 ≥3 层嵌套乱序插入测试（root→group→test_point→test_case，显式 order_key 与插入序相反）验证每层顺序。

### 2) restore Tree Integrity 与 add/move 一致
- 抽出共享 `_require_parent()`（parent 存在/同 artifact/存活或本批恢复中/test_case 不可为父；None 仅 root 语义），add/move/restore 三处统一引用，防规则漂移。
- `_apply_restore()` 补全：visible 父节点 node_type 检查、同批恢复中 test_case 父节点检查、root 不可经 restore 恢复、非 root 快照必须有父、parent 链环检测（A↔B 拒绝）。
- restore 改为**内部操作**：`/operations` API 直接 400 拒绝客户端提交 arbitrary restore（undo_latest / restore_revision 端点内部生成并执行不受影响）；Service 层保留能力供 undo/restore 使用。

### 测试（真实结果，SQLite）
- service 40 + API 8 = **48 passed**（新增：嵌套多层级排序、restore 挂可见 test_case 拒绝、restore 挂同批恢复 test_case 拒绝、A↔B 环拒绝、public operations 拒绝 internal restore + undo 端点仍可用）。
- 回归：migration 14 + structure + conversation API = **32 passed**。

## 2.30 2026-09-06 — P08.1 Hardening（代码审查修正；无新 Agent 能力、未进入 P09）

### 1) focus guard：运行中禁止切换 focused Artifact
- `focus_conversation_artifact` 增加 active-run guard（P08.1）：存在 queued/running 的 active head（active_slot=1）时，
  切换到不同 Artifact → `ConversationConflict`（409 conversation_conflict）；同 Artifact 重聚焦 → 幂等成功；run 终态后允许切换。
- 新增 Service 3 例 + HTTP API 2 例（含 owner 404）。

### 2) SourceRef ≠ Requirement 读取授权
- 写入口（add/update/restore 的 source_refs）增加 Requirement 项目绑定校验：`requirement/requirement_doc` 类型引用必须指向
  当前 Artifact 项目的存续 Requirement（数字 source_id；projectless Artifact 一律拒绝）——SourceRef 保持 provenance 语义，
  模型写入任意 source_id 不能扩大读取范围。
- `read_requirement` 权威改为「Conversation context 明确绑定的 Requirement + effective project（Artifact.project）复验 +
  can_read_project」；不再把 node 树上的 source_refs 当作 allowed ids。
- 测试：同项目绑定可读；跨项目引用写/读均拒；双项目权限用户不能借 Artifact A 读 Project B；forged source_ref 不扩权。

### 3) NodePatch null 合同
- 合同：title/content/source_refs 显式 null 一律拒绝（schema `reject_explicit_null` + Service `_apply_update` 双防线）；
  `source_refs=[]` 表示清空；未出现字段不改动。
- Handler（单条与 batch 共用 NodePatch）只剔除“未设置字段的模型默认 None”，不再可能静默吞掉用户语义。
- 测试：单条/batch 显式 null 均拒且 Revision 不推进；`source_refs=[]` 单条与 batch 均清空；title+source_refs=[] 同 patch 同时生效。

### 4) duplicate 规模保护
- `find_duplicates` 增加 `MAX_DUPLICATE_CANDIDATES=200`（可传 candidate_cap 覆盖）；超限只分析前 N 个确定性候选，
  返回新增 `total_cases / analyzed_cases / truncated`。不引入 embedding/vector DB。
- 大 fixture 测试：65 cases、cap=40 → analyzed 40、truncated=True、cap 内重复对发现、cap 外重复对（61/62）不出现；cap=400 → 全量分析。

### 回归（真实结果）
- 受影响套件（P07 service/API、artifact tool、focus service/API、quality）：67 passed。
- 全后端 `pytest tests`（排除同名 test_isolation.py 文件冲突的既有基建问题）：680 passed；
  `tests/conversation/test_isolation.py` 单独 3 passed；并发 promotion 用例在满载后有 1 次时序抖动，连跑 3 次均通过（非本次改动路径）。
- P08 Scripted Eval `python -m evals.p08.run_eval`：24 cases，task_success/tool_selection/tool_argument/artifact_edit/
  instruction_following/revision_conflict_recovery/quality_tool_non_mutation 全部 1.0，unintended_modification_rate 0。

## 2.31 2026-09-06 — P08.2 Hardening（边界加固；无新 Agent 能力、未进入 P09）

### 1) Run-scope Artifact Context Snapshot
- `agent_runs` 新增 `artifact_context_json`（0006 迁移；create_all 兼容）；submit Turn（head 与 queued follow-up 同路径）
  对当前可信 context 固化快照 `{artifact_id, project_id, requirement_id}`。
- ConversationRunner 不再读可变的 `session.context_json.focused_artifact_id`，一律使用 Run 快照
  （`conversation_service.artifact_context_from_run`）。Session focus 只决定未来新 Turn。
- 测试：submit under A → 会话 focus 改 B → Run 仍 A；queued follow-up 快照 = 提交时 focus；requirement 绑定后新 Turn 快照含 requirement_id。

### 2) Artifact Write Fencing（消除 check→commit TOCTOU）
- `handlers._assert_write_fence`：Artifact 写事务提交前对 AgentRun 行 `SELECT ... FOR UPDATE`
  并验证 status=running / worker_id / execution_token 仍匹配；与 cancel/claim 的 UPDATE 在同一行串行化。
  锁只覆盖实际 Artifact DB 写事务（不跨越 LLM 等待）。AgentError(agent_ownership_lost) 在 tool 边界翻译为
  `ownership_lost`（不再误报 artifact_service_error）。
- 测试：旧 token（claim 重赋值后）→ 写被拒、Revision 不提交；cancel 竞态（run 已终态）→ 写被拒。

### 3) 可信 Requirement Binding 生产入口
- `focus_conversation_requirement`（Application Service）+ `POST /agent/conversations/{cid}/requirements/{req_id}/focus`
  （owner-only）：验证 Requirement 存在且存活、用户可读、项目与 Conversation 一致（不一致 409，无项目按
  Requirement 提升）；客户端不能直接写 arbitrary context_json。绑定只影响未来新 Turn 的 Run 快照。
- 测试：绑定 200/幂等、项目不一致 409、绑定后新 Turn 快照 requirement_id。

### 4) Historical restore 允许历史 provenance
- 新 SourceRef 写入仍严格验证当前 Requirement 存活/项目；internal undo/restore 以
  `enforce_requirement_live=False` 回放历史 provenance（Requirement 后 soft-delete 仍可恢复）。
  `read_requirement` 对已删除 Requirement 仍 `requirement_not_found`。
- 测试：rev N 引用 → 软删 Requirement → 清空 refs → undo 恢复 refs 成功 → read 拒绝。

### 5) duplicate metadata 语义
- `find_duplicates` 返回 `total_cases / eligible_cases（有内容候选总数）/ analyzed_cases（实际进入两两比较）/
  truncated（仅当确有候选被 cap 截断）`。测试断言 eligible/analyzed/truncated 语义。

### 回归（真实结果）
- P07/P08/Conversation/Worker/Migration 相关套件 + 全后端：`pytest tests`（排除同名 test_isolation 收集冲突）→ **688 passed**；
  isolation 单独 3 passed；P08 Scripted Eval 24 cases 全过（task_success 等 1.0、unintended_modification_rate 0）。

## 2.32 2026-09-06 — P08.3 Hardening（Runner/Tool 全面切换到 Run Snapshot；无新能力）

### 1) ConversationRunner 真正使用 Run Snapshot
- Runner 已不再读取 Session focus/context：artifact_id / project_id / requirement_id 全部来自
  `artifact_context_from_run(run)`（project 缺省回退 run.project_id 兼容旧行）；requirement_id 同时
  传入 application_context_factory 与 AgentLoop metadata。
- 测试：submit under A → 会话 focus 改 B → Run 仍 A；binding R1 submit（含 queued follow-up）→ 会话改绑 R2
  → 已提交 Run 仍 R1、重绑定后新 Turn 为 R2。

### 2) Artifact Tool 不再依赖当前 Session focus
- `_context()` 改为：runtime.run_id → AgentRun → artifact_context_json.artifact_id == runtime.artifact_id，
  并验证 run.session_id == conversation_id、run.requester_user_id == user_id；Session 只校验 owner/mode
  （run_id 缺失的直连测试路径仍校验 session focus 一致）。Write fencing 保持。
- 测试：跨用户仍拒；同用户改 Session focus 后工具按 Run 快照继续；A 运行中排队 follow-up → A 终态 → 切 B →
  promote 后新 head（快照 A）工具读写仍作用于 A。

### 3) Requirement binding 保持 Project invariant
- `focus_conversation_requirement` 增加：若已 focus Artifact，则 artifact.project == requirement.project，
  否则 409（不再把 projectless Artifact + 项目 Requirement 提升成不一致 scope）。
- 测试：Artifact→Requirement（projectless 后绑项目 → 409；同项目 → ok）与 Requirement→Artifact
  （绑 R1 后 focus P2 Artifact → 409；同项目 → ok）正反序均保持同一 project scope。

### 回归（真实结果）
- `pytest tests`（排除同名 test_isolation 收集冲突）→ **691 passed**；isolation 3 passed；
  P08 Scripted Eval 24 cases 全过（各指标 1.0，unintended_modification_rate 0）。
- 结论：P08（含 P08.1/2/3 hardening）完成 → **P09 ready**。

## 2.33 2026-09-06 — P09.1 Artifact Workspace + 只读 MindMap（前端；后端 Domain 未改）

### 范围
在既有 V2 Chat 浮窗上首次把 Conversation + Focused TestArtifact + Artifact Tree 放进同一工作台：
Workspace Layout、Artifact API Client、Artifact Store、Create/List/Focus、只读 MindMap、Node Selection、
只读 Inspector、Basic View State。不做：人工编辑/Diff/History/Undo/Conflict UI/Agent 实时联动（P09.2/P09.3）。

### 结构（frontend/src/components/v2-workspace/）
- `mindMapModel.js`：纯函数 Tree→MindMap（buildMindMap/buildMindMapView/确定性垂直布局；node key=`n<id>`、edge=`e<p>-<c>` 稳定；collapse 只影响视图）。
- `artifactWorkspaceModel.js`：竞态裁决/409 消息/树加载 stale 判定（纯逻辑，测试覆盖）。
- `hooks/useArtifactWorkspace.js`：store（artifacts/active/tree/currentRevision/loading/error/unavailable/focusError；
  会话与 Artifact 两级序号+会话代次丢弃 late response；focus 走 POST focus，成功才更新，409 保留旧视图；
  create→auto focus→tree）。
- `hooks/useArtifactViewState.js`：collapsed/selected 按 Artifact id 各自维护（session 内，不写 DB）。
- `ArtifactWorkspace.jsx`/`ArtifactPanel.jsx` + `artifact/{ArtifactMindMap,NodeInspector,EmptyArtifactState}.jsx`。
- API client：`src/api/testArtifact.js`（list/create/get/tree）；conversationApi 增 `focusConversationArtifact`；
  全部复用 axios request wrapper（无组件内裸 fetch）。
- 挂载：V2ChatPanel `.v2chat` 内追加第三列 `<ArtifactWorkspace>`（仅真实会话，local draft 不渲染）；
  默认窗 1180×720、min 800×480。P06 Chat 组件与能力未重构、未破坏。
- MindMap：`@xyflow/react`（新增依赖）+ 纯递归垂直布局；pan/zoom/fit（首次打开/切换/创建/手动刷新触发，不随 streaming fit）；
  无坐标写回、无 MindMap→DB。

### 关键行为
- Focus Guard：409（conversation_conflict/运行中切换）→ 显示后端消息、保留旧 Artifact 与旧 MindMap（无 optimistic 切换）。
- F5/Conversation 切换：focused Artifact 一律来自后端 snapshot（顶层 focused_artifact_id），不依赖 localStorage 猜测。
- 404 focused → 清展示 + unavailable（不无限 retry）；普通加载失败 → Retry。
- Inspector 数据来自整树一次 GET /tree（内含 content/source_refs，无 200 个单节点请求）。

### 测试/构建（真实结果）
- `npm test`：36 passed（新增 mindMapModel.test.mjs：nodes/edges、nested 排序稳定、collapse、200+ 节点确定性布局、
  race/409 纯逻辑）。
- `npm run lint`：0 errors（8 warnings 均既有 pages）。
- `npm run build`：通过（chunk>500KB 提示为 antd+xyflow 既有性信息）。
- headless 整页加载：无 JS 异常（运行中后端未应用 0005/0006 迁移时 /test-artifacts 不可用属预期，错误态有 UI 兜底）。

### 人工验收前置
浏览器验收前需在真实 MySQL 授权执行 alembic upgrade head（0005 TestArtifact 表 + 0006 agent_runs 列），
并在模型管理中确认 agent_chat 场景后按 §43 流程走查。

### Deferred（P09.2/P09.3）
Manual add/update/delete/move UI、Revision Diff UI、History/Undo/Restore UI、revision conflict UI、
Agent artifact_revision 实时联动、ChatTurn Change Summary、200+ 浏览器级硬化、完整 E2E。

## 2.34 2026-09-06 — P09.1 Functional Case Domain Convergence（产品方向调整后实施）

### 方向
P09 停止「独立 Chat + Artifact 右栏」扩展；新形态：V1「功能用例管理」页为主工作区，V2 Agent/TestArtifact 能力内嵌。
**NO DUAL-WRITE**：TestArtifact/ArtifactNode/Revision/Operation 是 Module+TestCase 唯一 Source of Truth。

### node_type 收敛（root/module/test_case）
- models/schemas/service/restore/move/工具 schema/quality/评估 fixtures 全量同步；group/test_point 不再是合法值。
- Domain invariant：root 唯一不可删/移；module 可挂 root/module（任意深度嵌套）；test_case 只能属于 module（不能父 root、不能作父）。
- 无模块 Case：apply 内同批自动创建唯一一级「默认模块」并把 Case 放入（只产生一个 Revision；条件写裁决并发）。
- `default module` 唯一由 revision 条件写保证；测试覆盖多次隐式添加后仍单实例。

### 数据/API
- Alembic `0007_artifact_module_convergence`：node_type group/test_point→module；新增 UNIQUE(project_id, artifact_type)（每项目一份主 Functional Artifact，NULL project 私有不受限）；迁移测试含存量行转换与 downgrade（module→group 损失性回退）。
- Application Service：`get/ensure_project_functional_artifact`、`get_or_create_default_module`；`POST /test-artifacts/ensure-project-functional`。
- 编号：统一 `TC-{ArtifactNode.id:06d}`（后端 app/services/test_artifacts/case_number.py 与前端 caseNumber.js 同格式）；移动/排序不变、无抢号。
- TestCase content 强 schema：preconditions[]、steps[{step_no?,action,data?}]、expected_results[{step_no?,expected}](兼容字符串迁移归一)、priority P0–P3 默认 P1、tags；禁止 Optional[Any] 进入写路径。
- Requirement 生成保存（save_generated_function_cases）：ensure Project Artifact → 解析/创建 Module → 批量 add test_case（**一个 Revision**）→ requirement 写入 source_refs；不再写 function_cases（V1 表 deprecated 标记，物理清理留 P10）。
- Legacy：/modules*、/function-cases* 保留 Router（旧引用不炸）但新页面不再调用；save-candidates 保持兼容不动（P10 cleanup）。

### 前端
- V2ChatPanel 移除 ArtifactWorkspace 第三列（恢复纯 Agent Conversation UI）；保留可复用纯函数与组件供 P09.2。
- FunctionCasePage 重写：Project Select → ensure/加载 Functional Artifact → 左侧 Module Tree（来自 Artifact tree，只含 module）+ 右侧 Case List（编号/模块/名称/前置摘要/步骤摘要/预期摘要/优先级，点击行只读结构化 Detail）；无模块入口删除；空项目自动建主 Artifact；切换项目含序号防旧树覆盖；F5 由后端 focused/snapshot 恢复。
- 纯函数：caseView.js（buildModuleTree/collectScopeCases/摘要）、caseNumber.js（与后端同格式）。
- 保留：mindMapModel/artifactWorkspaceModel/testArtifact API client（P09.2 复用）。

### 测试（真实结果）
- 后端全量（排除同名 isolation 收集冲突）：**701 passed**；isolation 3 passed；迁移 15 passed（含 0007 转换/降级）；P08 Eval 24 cases 全过（指标 1.0）。
- 新增：module 嵌套/默认模块唯一/项目主 Artifact 唯一(唯一约束+并发)/编号移动稳定/需求生成→单 Revision/legacy 表未写 等专项测试。
- 前端：npm test **40 passed**（新增 caseView/caseNumber 等）、lint **0 errors**、build 通过。

## 2.35 2026-09-06 — P09.1.1 Hardening（权限/事务边界/创建入口/表格与空项目）

### 1) Project-scoped Artifact 权限服从 Project ACL
- artifact_service `_readable/_writable/list`：project_id != null → 完全服从 can_read/can_operate_project（owner 不再例外）；projectless → owner 权限。
- 测试：创建者被移出项目后读/写均不可（404）；viewer 可读不可写（403）；projectless owner 正常；admin/tester 正常。

### 2) Application Service 事务边界恢复
- 移除 `ensure_project_functional_artifact` / `get_or_create_default_module` 及生成保存内部的 `db.commit()`；commit/rollback 一律在最外层 Router/调用方。
- Requirement 生成保存改为：Module 缺失时 `add module(ref)` + N 条 `test_case(parent=@ref)` 放进**同一个 apply_operations()** → 一次保存 = 一个 Revision；任一步失败整体 rollback（新增 rollback 测试：仅 root、无新 Revision）。Artifact 首次创建 Revision 1 独立。
- Router（/test-artifacts/ensure-project-functional、/function-cases/save-generated）在最外层 commit/rollback。

### 3) FunctionCasePage 表格摘要
- 步骤列改用 `stepsSummary()`（action/data 正确摘要），预期列改用 `expectedSummary()`；前置用字符串数组 join；不再用通用 textLines 的 item.expected 渲染 steps。

### 4) Viewer 空项目
- 页面先 `GET listArtifacts` 读取当前项目 Functional Artifact：exists → 加载；not exists + 非 viewer → ensure；not exists + viewer → 只读空态（不再无条件 POST ensure）。

### 5) 收口 Project Artifact 创建入口
- 普通 `POST /test-artifacts`：project-scoped `test_design` 已存在 → 明确 `artifact_already_exists` → HTTP 409（不再 IntegrityError 500）；项目主 Artifact 只允许 ensure-project-functional。新增 API 测试 409。

### 6) TestCase schema 加固
- steps.step_no 唯一（缺失自动补最小未用正数）；expected_results.step_no 非 null 必须引用存在的 step。新增校验测试。

### 回归（真实结果）
- 后端全量（排除同名 isolation 收集冲突）：**708 passed**（另 worker 并发时序抖动用例单跑通过，与改动无关）；isolation 3 passed；Eval 24/24。
- 前端：npm test 40 passed、lint 0 errors（8 warnings 既有）、build 通过。

## 2.36 2026-09-06 — P09.2（Module/Case Editing + MindMap + Revision Workspace）实现记录

### Preflight（P09.1.1 遗留）
- Service 外层事务保护：`ensure_project_functional_artifact` / `get_or_create_default_module` 内部改用 `db.begin_nested()`（SAVEPOINT）；不再对调用方 Session 执行 `db.rollback()`；补「caller 未提交修改在并发冲突后不被回滚」测试。
- 创建入口统一：普通 `POST /test-artifacts` 对 `project_id != null` 一律 400 `artifact_project_ensure_required`；project primary artifact 只经 `ensure-project-functional`（内部 `allow_project=True`）。测试与全部 fixture 切换到 ensure 入口。

### Frontend（已实现并 build/lint/test）
- `FunctionCasePage` 重写为编辑工作台：
  - List/MindMap 视图切换；MindMap 复用 `ArtifactMindMap`（@xyflow/react，ReactFlowProvider），按 `scopeId` 显示整棵或 module subtree；Scope 切换在 List/MindMap 间保持。
  - Module CRUD：Tree 节点 hover/右键菜单（新增子模块/重命名/移动/删除）；删除确认显示子模块数与用例数；移动父候选排除自身子树；全部经 `/operations`。
  - Case CRUD：结构化 Editor Modal（名称/所属模块/优先级/Tags/前置/步骤增删排序/预期 step_no 引用），无 Module 时可自动进默认模块；行点击直接进入编辑。
  - 写合同：保存携带 expected_revision；409 → Conflict Modal（显示 版本10/11），保留草稿 + “加载最新版本”；不覆盖。
  - History Drawer（actor/summary/time）→ Diff；最近变更；Undo latest 确认；Restore（新 Revision 提示）；Diff 渲染 added/updated/deleted/moved（真实后端 diff）。
  - Viewer：只读（不显示写按钮/操作），保留 List/MindMap/History/Diff。
  - MindMap 节点 test_case 显示 `TC-000123`。
- API client 扩展：applyArtifactOperations/getArtifactRevisions/getArtifactDiff/undoArtifact/restoreArtifact。
- 纯模型 `caseEditorModel.js`（steps 补号唯一/编辑→Operation/Module ops/父候选/scopeRoot）+ 新测试。

### 测试/构建（真实结果）
- 后端全量（排除同名 isolation 冲突）：**710 passed**（Preflight 后含新增 SAVEPOINT/入口/ACL 测试）。
- 前端：npm test **45 passed**（含 caseEditorModel）；npm run lint **0 errors**（7-8 条既有 warnings）；npm run build 通过；headless 整页加载无异常。
- 尚未执行：浏览器人工验收（§37 流程）与双浏览器冲突验收（§38）→ 因此 P09.2 未标记 complete（待验收后更新 01/02/03）。

## 2.37 2026-09-06 — P09.2.1 Hardening（Undo/Restore 乐观并发 + 编辑器加固）

### 1) Undo/Restore optimistic concurrency
- API 合同：`POST /undo {expected_revision}`、`POST /restore {target_revision, expected_revision}`；Service reconcile 前校验 current==expected，否则 `revision_conflict`（payload expected/current）。
- 测试：B 持 rev10 → A 写 rev11 → B undo(10)/restore(expected10) → 409，不撤销/不恢复新版本；Service 层 stale 与 API 层各一组。

### 2) Steps reorder / step_no 映射
- 纯函数 `renumberStepsAndExpected(steps, expected)`：移动后按 UI 顺序重编号 1..N；expected 绑定跟随“逻辑步骤行”映射新 step_no；删除绑定步骤时 expected 降级为整体（step_no=null）；新增步骤编号连续。
- 页面步骤 ↑↓/删除/新增全部接入该纯函数；删除前先清除被删步骤的 expected 引用。
- 纯函数测试：1,2,3 移 3→1 重映射；删除后整体化+连续；新增连续（新增 3 条，FE 共 51 项）。

### 3) selectedNodeId
- 状态由保存 Node object 改为 `selectedNodeId`；`selectedNode` 每次从 `index.get(selectedNodeId)` 派生 → tree 刷新后 Inspector 自动读取最新节点；删除后 selection 自动清空（并显式清 selectedNodeId）。
- 覆盖：edit case → refresh 展示新内容；delete selected → 清空。

### 4) Module Move 到 root + Diff 显示
- Module Move 首选项「项目根（一级模块）」(value=tree.root.id)；test_case 移动走 Case 编辑（不含 root 选项）；后端仍是 parent/cycle 权威。
- Diff：后端 deleted/updated change 增补 node_type/title；前端仅 `test_case` 显示 TC-xxxx，module 行显示标题，不再对 module 行渲染用例编号。

### 测试（真实结果）
- 后端全量（排除同名 isolation 冲突）：**711 passed**（此前 710 + 新增 stale undo/restore 等；含 1 次 timing 抖动用例，非本次改动路径）。
- P08 Eval：24/24。
- 前端：npm test 48 passed（含 renumber 3 条，共 48 passed）；lint 0 errors（7-8 既有 warnings）；build 通过。

## 2.38 2026-09-06 — P09.3A Conversation × Functional Artifact Context（实现与针对性测试完成，浏览器人工待验收）

范围：不新增 AI 界面；让现有 Conversation Agent 安全知道「功能用例管理」的 Project/Functional Artifact/选中 Module/TestCase，随 Turn snapshot，并在聊天中据此工作；不做实时刷新/Change Summary/View Changes/Conflict UX（P09.3B）。

实现（工作区既有 + 本轮核对）：
- 后端：`AgentRun.workspace_context_json`（alembic 0008 `agent_run_workspace_context`）；`WorkspaceContext` schema（selected_module_id/selected_case_id:int|null、current_view: list|mindmap|null，拒绝任意 dict/Optional[Any]）；`conversation_service.validate_workspace_context`（focused artifact 存在、节点属于该 Artifact、node_type module/test_case、未删除、case 必须是所选 module 的直接子节点、strict parent 规则）；`submit_conversation_turn` 原子保存 UserMessage + queued Run + workspace snapshot，`request_hash` 含 workspace（同 key 不同 workspace → conflict）；`focus_conversation_artifact`（同 artifact 幂等、active queued/running head 时切不同 artifact → 409 conversation_conflict、终态后允许切换、Artifact/Conversation 项目一致）；Runner 从 `AgentRun.workspace_context_json` 恢复，只注入 short system/runtime hint（module/case/view ID，绝不塞节点正文），RuntimeContext 增 selected_module_id/selected_case_id/current_view 且 artifact/project/run 仍来自 immutable Run snapshot；Artifact Tool runtime 透传该 hint，Tool 仍必须显式 read（read-before-write）。
- 前端：`FunctionalWorkspaceProvider`（App 级，无 Redux/Zustand）+ `useFunctionalWorkspace/setWorkspace/leaveWorkspace` 共享 page/FunctionCasePage 选中 Module/Case/View 与 artifact/project，FunctionCasePage 与 V2ChatPanel 仅经共享 context 交互；`chatContextModel.planWorkspaceSubmission/buildContextIndicator`（focus authority + workspace selection；页面与 AI context 区分、mismatch 不误导、invalid_workspace_context 清除 stale selection）；V2ChatPanel 渲染轻量 ContextIndicator。
- 技能与约束：SKILL.md 增加 workspace hint 语义（“这里/这个模块/这个用例”优先解析为 selected id 后仍 read；scope 明确不重复问、不明确才读 outline 后询问；不把节点正文注入 prompt；Tool 不隐式读 selection，显式参数可审计）。
- 本阶段明确不做：FunctionCasePage 实时刷新、Chat Change Summary、View Changes、Conflict UX、approval 持久化（P09.3B）。

本轮验证命令/结果（backend，禁用插件+字节码，未连真实库；frontend node）：
```text
pytest tests/api/test_conversation_api.py tests/api/test_conversation_focus_api.py \
      tests/api/test_workspace_context_api.py tests/services/test_workspace_context.py \
      tests/artifact_tools/test_agent_scenarios.py \
      tests/migrations/test_agent_platform_migration.py tests/migrations/test_test_artifact_migration.py -q
56 passed
node --test tests/*.test.mjs（frontend）→ 74 passed（含 functionalWorkspace 9）
npx eslint（P09.3A 前端改动文件）→ exit 0
```
覆盖：workspace snapshot 持久且输入对象不可再变异（Run 不可变快照）；module 属于 focus artifact 成功 / 属其它 artifact 400 / 用 test_case 当 module 400 / case 与直接父 module 校验 / deleted selection 400 / 任意 dict 与非法 view 拒绝 / 同 key 不同 workspace 409；focus 幂等、busy 切换 409、owner 隔离、requirement 绑定项目一致；Runner 注入 hint；Agent 场景“这里补边界→先 read module 再写”“scope 不明确→读 outline 后询问不写”“明确唯一模块→直接 read 不强迫询问”。

状态：P09.3A 代码与针对性测试完成；浏览器人工/真实 MySQL（alembic upgrade head 至 0008）验收与 P09.2 浏览器项仍待执行；P09.3B 未开始。不把 P09 整体标记 complete。

## 2.39 2026-09-06 — P09.3B 进行中记录（Agent Realtime 后端闭环 + 前端语义核，未完成）

已交付并验证（本轮）：
- 后端事件收敛（§2.4）：`artifact_revision_created` / `artifact_diff_created` 只携带 compact 元数据（artifact_id/project_id/from_revision/to_revision/run_id/conversation_id/summary/change_counts），不再携带完整 changes[]；完整 Diff 仍走 GET /test-artifacts/{id}/diff。仍在写事务内 append + fencing 后统一 commit（rollback/fencing 失败不留事件）。
- ACL（§2.2）：`conversation_snapshot` 对 project-scoped focused Artifact 校验当前用户 Project read，撤销时 focused=null（不泄漏 project/artifact 名称）；新增薄只读接口 GET /agent/conversation-runs/{id}/artifact-changes（owner + Artifact 当前 ACL，返回 compact 聚合，供历史恢复 §39）。
- 前端语义核（纯模块 + node 测试，避免与并发改写的整页 wiring 冲突）：artifactRealtimeModel（按 Artifact 过滤/revision guard/21-23 coalesce/markRefreshed 防 stale）、editorConcurrencyModel（editor.baseRevision 保存、realtime 不覆盖 Draft、保存仍用 baseRevision → 409）、artifactChangeSummaryModel（按 run 聚合/不混 run/文案）、artifactMismatchGuard（普通 continuation 白名单 vs 资产指令保守阻断）。

验证：backend artifact/conversation 相关套件 55 passed（事件收敛/ACL/端点在既有路径不回归）；frontend 新 realtime 模型测试 7 passed。

第二轮接续（并发已随 commit 4a32d83 P09.3A 收敛）：新增 agentArtifactEventBus（订阅/发布仅 Artifact compact 事件）；useConversationChat 在 SSE 收到 artifact_revision_created/artifact_diff_created 时归一后 publish；FunctionCasePage 订阅 bus：按 Artifact 过滤、revision guard/21→23 coalesce、100ms debounce 后 GET tree/revisions（bounded retry，markRefreshed 防 stale），刷新后自动清理被删除的 selectedNode/scope；全部 dialog opener 记录 baseRevision，runWrite 保存使用 baseRevision（后端 409 主导 conflict）；chatContextModel mismatch 分支接入 artifactMismatchGuard（普通 continuation 放行、资产指令保守阻断）。验证：eslint 0；frontend node 81 passed（74+7 realtime 语义）；npm run build ok。

仍待完成：Chat Change Summary 卡片与 View Changes 导航（含 pendingArtifactNavigation）、历史恢复 UI 读取 run artifact-changes、编辑器冲突 warning 文案接入、MindMap 不 fitView 约束确认、Test Design Skill 冲突有限重试文案、相应回归与 Browser E2E（真实 MySQL alembic→0008）。P09.3B 未完成、P09 未 complete。

第三轮（Change Summary / View Changes 链路）：useConversationChat 暴露 `artifactSummaries`（由 SSE 持久化事件按 run 聚合，重连/重新打开游标重放即可恢复）；V2ChatPanel 在对话区顶部渲染轻量 Changes 行（文案按 change_counts 派生 + Revision 区间），「查看变更」仅当页面 Artifact 与变更一致时可用，点击经 `agentArtifactNavigation` 发布 diff 意图；FunctionCasePage 消费意图：Artifact 匹配才消费并调用 `getArtifactDiff(from,to)` 打开真实后端 Diff，跨 Artifact 不消费；Skill rule 7 收紧为“read 最新 → 有限重试最多 2 次 → 目标已不存在/意图不明不重建不猜，改为询问”。验证：eslint 0；frontend node 81 passed；build ok。P09.3B 仍未 complete（历史恢复经 run artifact-changes 的显式 UI、MindMap 不自动 fitView 的显式守卫测试、P09 全回归与 Browser E2E 待后续）。

收尾：MindMap fit 守卫修正为页面显式 `fitNonce`（仅首次/Artifact 切换/人工写、undo、restore 成功后 +1；Agent realtime 刷新不加，画布不跳，§14）；node 语义测试扩至 84 项；P09 相关后端回归（artifact_tools、conversation API/focus/workspace、TestArtifact service、migrations、conversation_persistence、workers）= 185 passed in ~33s。前端 eslint 0 errors（MindMap 一例既有 useMemo deps warning 非本轮引入）。P09.3B 仍不标 complete：浏览器 E2E 与部分显式 UI（历史聚合接口前端拉取按钮）未做。

真实 MySQL 验证（2026-09-06，用户显式授权）：ALEMBIC_ALLOW_MYSQL=1 执行 alembic current = 0007_artifact_module_convergence → upgrade head 成功（0008_agent_run_workspace_context: snapshot FunctionCasePage selection per Turn，非破坏 DDL）；alembic_version=0008；`agent_runs.workspace_context_json` 与 agent_sessions mode/next_message_sequence/next_event_sequence 均存在。浏览器级 E2E（双浏览器/人工走查）仍无浏览器基础设施 → NOT VERIFIED。

收尾（无浏览器环境，浏览器项按 NOT VERIFIED 跳过）：编辑器打开期间若 tree 已前进（Agent realtime 20→21），页面顶部显示轻量提示「测试资产已更新。当前编辑内容基于 Revision X」；功能用例页无 Artifact（加载/空/无权限）时普通聊天放行，资产型/引用型指令返回明确「当前项目尚无可用的功能测试资产。」（chatContextModel action=no-artifact + hook 文案）。frontend node 84 passed / eslint 0 / build ok。**浏览器级 E2E（§47-62）跳过并标记 NOT VERIFIED**（无浏览器基础设施，不假装完成）。

P09.3B.1（审查修正）：
1. mismatch 分类重写为 5 级顺序（workspace/reference → asset（含问句形式）→ continuation 白名单 → 明确知识问答 → 默认 block）；资产型问句“登录模块有哪些用例？”等一律 block，“什么是边界值测试？”等知识问答放行；不再用“任意 ? 结尾”放行。
2. 引入 artifactStatus（loading/ready/empty/error，FunctionCasePage 由 loading/error/artifact 推导并传入 workspace）；移除 useConversationChat.send 里 artifactId==null 无条件 return，统一走 planWorkspaceSubmission（loading+资产→workspace-loading；empty+知识→submit；empty+资产→no-artifact）。
3. Change Summary 只消费 artifact_revision_created（artifact_diff_created 不参与 run 聚合）→ 同一次 write 不再双计数（+3/1 revision）。
4. Cross-page View Changes：App 订阅 agentArtifactNavigation，收到意图切 functionCases 并 storeProjectId；FunctionCasePage 收到跨项目意图先 setProjectId 再加载，待 artifact 匹配后消费意图并打开真实 Diff。
5. Stale Artifact race：refreshContent/openRangeDiff 写 state 前校验 artifactRef.current===请求 artifact（晚返回旧 Artifact 响应不污染当前页）。

验证：frontend node 88 passed（含新增 14 条 P09.3B.1 反例：mismatch 分类/artifactStatus/summary dedupe）；eslint 0 errors；build ok。Browser E2E 无浏览器环境 → 继续 NOT VERIFIED；P09.3B implemented、Browser E2E pending、P09 not complete。

## 2.40 2026-09-06 — P09.3B.2 UI / Interaction Hardening

实现与根因：
- Module 菜单改为页面级 `openMenuNodeId` 单一受控状态；浏览器走查额外发现接线时误用纯模型参数签名，修正为显式 open/close action，并移除多余 contextMenu 阻断。父/子模块切换后仅一个 Dropdown 可见，Escape/空白在关闭动画后均不可见。
- Conversation 继续以 `run_id` 构建 Turn；User、去重后的 Tool、Assistant、Artifact Changes 与 Run Error 只在各自 Turn 渲染。Run failed 不再挂在 User bubble 或全局 banner；全局错误仅保留初始化/网络类错误。
- Revision/Diff 两类 compact event 以 run+artifact+to_revision 去重，缺失 `from_revision` 时由 `to_revision-1` 恢复；领域计数优先使用后端基于 operation node_type 生成的 `domain_change_counts`，旧事件回退 change_counts，避免真实写入显示“无变更”或“? → N”。
- Tool Activity 以 run_id+tool_call_id 合并 started/finished/replay；主文案映射为“读取测试结构 / 读取测试用例 / 批量修改测试资产 / 检查测试覆盖 / 检查重复用例”，raw tool_name 只留开发者详情。ToolCall 不再拼进 Assistant 正文。
- Conversation 标题把空值和纯标点视为无效，依次回退首条有效 UserMessage、`新对话`。
- MindMap 空白真实根因是 `.v2w-mindmap` 在 FunctionCasePage 非 flex 宿主下高度约为 0；修为宿主直接子容器 520px。数据链为 Artifact tree → scope subtree → deterministic left-to-right layout → React Flow；root/module/case 分层、case 只显示编号与标题，折叠只改 view state，realtime 不递增 fitNonce。
- List 采用过滤后前端分页，20/50/100、筛选重置第 1 页、数据减少时 clamp；List/MindMap 状态独立。业务可见文案收敛为中文，AI 浮窗布局/尺寸/位置未修改。

验证：
```text
frontend: node --test tests/*.test.mjs -> 94 passed
frontend: npm run lint -> 0 errors（6 条其它旧页面 hook warnings）
frontend: npm run build -> passed（仅既有大 chunk warning）
backend: artifact_tools + workspace API/service + conversation events -> 76 passed
backend: P09.3A/Artifact/migration 组合回归 -> 63 passed
P08 scripted eval -> 24 cases；成功/选择/参数/编辑/遵循/冲突/非修改均 1.0，unintended modification rate 0.0（仅脚本基线）
```

真实浏览器：使用本地已登录 `测试1 / 功能测试` 数据走查。已验证父子 Module 菜单单开；历史 Conversation 的 Tool/Assistant/Changes/Error 按 Turn 归属；旧事件因没有 node_type 领域计数，诚实显示“新增 6 项，更新 1 项，移动 1 项，版本 3→7”和“新增 12 项，版本 7→11”，新事件才按 `domain_change_counts` 区分模块/用例；内部 tool_name 未作为主文案；纯标点标题回退“新对话”；MindMap 从白屏恢复为 21 个真实节点的项目→模块→用例横向树；双击折叠后节点 21→1 且版本仍为 11；分页控件显示 20/50/100 条/页。当前真实项目只有 13 条用例且 Agent 为失败态，因此未通过“不污染数据”的方式现场验证 >20 条第 2 页和 Agent 新增后的 realtime；双浏览器并发也未执行。P09.3B.2 代码完成，P09 整体仍不标 complete，不进入 P10。

## 2.41 2026-09-07 — P09 功能用例页 UI follow-up

- 修复项目记忆失效：`resolveProjectId` 的返回值本身就是 number，旧调用却读取 `initial.id`，导致进入功能用例页后 projectId 仍为空；现直接设置并保存返回 ID，失效 ID 回退首个可访问项目。
- 分页默认调整为 15 条，选项统一为 15/30/50/100；过滤与 realtime 后的页码重置/clamp 语义保持不变。
- 移除全局原生 button 的黑色默认背景，改为透明/浅灰 hover；AI 发送键继续由更具体规则保持黑色。模块“全部模块”和 Chat“查看变更”增加 scoped 浅色规则，避免选择子模块或显示修改记录时出现黑块。
- 功能用例页白色 Card 扩至视口边缘；新增用例按钮移入搜索工具栏右侧；表格与模块树顶部对齐。编号列压缩为 92px，模块/名称允许换行，优先级固定靠右，释放宽度给前置条件/步骤/预期。
- 去除用例正文 120 字摘要与 64px 高度裁剪；编号、模块、名称、前置条件、步骤、预期均可换行并完整撑开行高，正文不再被遮挡或截断。
- 按用户要求未执行浏览器验收。自动化：`node --test tests/*.test.mjs` 96 passed；ESLint 0 errors（6 条其它旧页面 warning）；Vite build passed；`git diff --check` 无错误。

## 2.42 2026-09-07 — P09 MindMap 编辑交互 follow-up

- MindMap 单击 Module 只更新 `selectedNodeId`，不再隐式修改左侧 `scopeId`，因此不会自动切入 Module subtree；scope 仍只由左侧模块树控制。
- TestCase 节点移除 TC 编号，名称作为主信息，priority 以低饱和 badge 放在节点最后一行右下角；Module 保留独立折叠按钮，折叠仍只影响 View State。
- 单击 TestCase 直接复用现有 Case Editor；同时修复 Editor adapter：兼容列表行 `nodeId` 与 Artifact 原始节点 `id`，始终从 Tree index 读取完整 content/parent，避免脑图或列表编辑时字段空白、target id 丢失。
- MindMap 右键 Module 仅显示“新增模块 / 新增用例 / 删除模块”，右键 TestCase 仅显示“删除”；菜单由单一 `openMenuNodeId` 控制。双击 Module 打开重命名 Modal，双击 TestCase 打开完整编辑器，可直接修改名称。
- 按用户要求未执行浏览器验收。自动化：frontend node 97 passed（新增 priority/context-menu 纯模型断言），ESLint 0 errors（6 条其它旧页面 warning），Vite build passed，`git diff --check` 无错误。

## 2.43 2026-09-07 — P09 MindMap 用例详情链 follow-up

- 每个 TestCase 在纯 view model 中稳定派生三个只读虚拟节点，形成 `用例 → 前置 → 步骤 → 预期` 水平链；虚拟节点不进入 Artifact index、不响应选择/编辑/右键，也不产生 Operation/Revision。
- 前置、步骤、预期读取真实 case content，按逻辑项换行；空值显示“未填写”。详情框依据最长一行估算 188～300px 宽度，超过宽度继续换行，并将估算高度纳入逐行布局，避免相邻用例详情重叠。
- 用例名称节点扩至 202px，priority badge 位于名称右侧垂直居中；所有 React Flow edge 改为 straight，同一用例及其三个详情节点按中心线水平对齐，层级间距增至 340px。
- 200+ Artifact fixture 现在生成 689 个可视节点（209 Artifact + 480 只读详情）与 688 条边，稳定 key、finite position、重复布局一致；frontend 全量 node 97 passed，ESLint 0 errors（6 条其它旧页面 warning），Vite build passed。延续用户要求，未执行浏览器验收。

## 2.44 2026-09-07 — P09 MindMap 卡片层级细化

- 用例名称卡改为淡蓝底/浅蓝边框；`caseNameMetrics` 按中英文显示宽度稳定计算 1/2/3 行，高度分别为 44/60/76px，CSS 最多显示三行且完整 title 保留 tooltip，priority 继续位于名称右侧垂直居中。
- “前置 / 步骤 / 预期”标签从详情内容流中移除，绝对定位到入线与内容框左边界的交界处；标签透明无背景，详情长方形内部只保留真实内容。详情高度估算同步去除标签占位，换行与中心线布局保持稳定。
- frontend 全量 node 97 passed（含 1/2/3 行高度断言、689 nodes/688 edges 与中心线断言）；ESLint 0 errors（6 条其它旧页面 warning）；Vite build passed；延续用户要求未执行浏览器验收。

## 2.45 2026-09-07 — P09 MindMap 空详情与分层连线修正

- `caseDetailText` 空值返回空串，view model 只为非空字段生成详情节点和详情边；前置/步骤/预期任一项未填写时，对应标签、内容框与连线全部不存在，不再显示“未填写”。
- Artifact 层级边标记为 `hierarchy` 并使用 smoothstep 树形连线；Case 详情边标记为 `detail` 并保持 straight。详情 target handle 左移并隐藏，使直线在透明标签左侧终止，不再穿过“前置/步骤/预期”文字。
- 用例名称卡的宽度估算校准为每行 24 display units，高度档位压缩至 34/50/66px，同时减少纵向 padding，降低一两行名称卡的无效留白。
- 新增反例：仅填写步骤时只生成“步骤”节点和一条 detail edge；无 `未填写` 占位。frontend 全量 node 98 passed，ESLint 0 errors（6 条其它旧页面 warning），Vite build passed；延续用户要求未执行浏览器验收。

## 2.46 2026-09-07 — 管理页面视觉基线统一

- 以 FunctionCasePage 为密度与信息层级模板，为 RequirementPage、ApiDocPage、CasePage、ScenePage 增加统一 `management-template-page` 样式入口；不修改四页查询、筛选、CRUD、执行或 ModuleTree 逻辑。
- 四页统一为扩大后的白色工作区、透明紧凑工具栏、蓝色主操作、250px 左模块栏、12px 布局间距、浅灰列表卡与表头；表格统一 18px 表头、16px 正文、顶部对齐并支持长文本换行。
- 原黑色主按钮、灰色大模块按钮和多层大圆角 Card 在该作用域内收敛为功能用例页的蓝色/浅灰状态；抽屉、Modal 与其它管理页面不受影响。1400px 内仍保持左右布局，900px 以下才切单列。
- frontend 全量 node 98 passed；ESLint 0 errors（6 条既有页面 hook warning）；Vite build passed；`git diff --check` 无错误。未执行浏览器验收。

P10.1（进行中，第一增量）：
- Audit 完成（恢复/loop/system/artifact/usage/summary 现状见 §报告）。
- 新增 context_builder.py（纯函数）：ContextBudgetConfig（recent_message_limit/context_token_budget/reserved_output/summary/artifact 分项，chars_per_token=3 保守估算，未知≠0）、estimate_text_tokens/estimate_message_tokens、原子交换组切分（assistant ToolCall+对应 ToolResult 同组同取舍）、build_prepared_context（尾部按组收集 + count/token 双限、当前 UserMessage 无条件保留、summary 存在则超预算即停并注入 system 侧 summary 块、无 summary 发生裁切标 context_limit 由调用方降级、输出 included/omitted/diagnostics，不返回 ORM）。
- 测试 tests/conversation/test_context_builder.py 6 passed：短会话不压缩、工具对不拆（窗口切对边界）、summary 压缩且原消息不变、无 summary 超限 context_limit、估算非 0、omitted 记录。
P10.1 剩余：Summary 持久化模型+迁移 0009（through_sequence 单调防旧覆盖）、Runner 接入 PreparedContext、Incremental Summary（只总结 31..K）与失败降级、Artifact metadata/relevant nodes/recent diff 组装、context_prepared/context_compacted 事件、follow-up 隔离与乐观并发、200+ 消息测试与回归。P10.1 未 complete；P10.2 Approval next。

P10.1-B（进行中，A 边界修复完成）：
- Budget 语义：ContextBudgetConfig 改为 model_context_window/reserved_output_tokens/…，property max_input_tokens = window - reserved（只扣一次）。
- Token estimator：CJK≈1 token/字、ASCII≈4 chars/token、每条消息 +envelope；ToolCall name/id/arguments JSON 全参与；非空输入恒>=1。
- 巨大当前 User：system+current > window → context_limit reason=current_turn_too_large，消息不截断不删除。
- Multi ToolCall 组：Assistant 一组调用 + 连续对应结果同组同取舍；orphan ToolResult 独立成组并 diagnostics malformed_exchange（不伪造、不修历史）。
- Summary 固定 Runtime wrapper（含 “does not override … / Artifact may be stale / read before modify”）已入 system 侧并有断言。
- 测试：tests/conversation/test_context_builder.py 10 passed（估算/预算/巨用户/多调用组/orphan/wrapper/limit/omitted）。
P10.1-B 剩余：ConversationSummary 持久化模型+0009 migration+service（UNIQUE、through 单调、并发安全）、ConversationSummarizer 接口+Fake+有界 1 次调用与 accounting、Incremental cut point、Runner 接入 PreparedContext（全量 restored 不再直传 Loop）、follow-up upper-bound 隔离、DB 事务两阶段、长会话/失败降级测试与回归。P10.1-B 未 complete；P10.1-C next；P10.1 overall NOT complete；P10.2 未开始。

P10.1-B2（部分完成）：新增 ConversationSummary 模型（agent_sessions FK RESTRICT、UNIQUE(conversation_id)、through_sequence_no>=0、source_message_count/schema_version/provider/model/时间戳）并注册；Alembic 0009_conversation_summary（upgrade/downgrade/upgrade 已随既有 migration 测试跑通，HEAD=0009）；summary 仓储层（get/create 唯一冲突安全重读/conditional_update 单调 WHERE expected_old AND through<:new）；增量选择 select_incremental_inputs（只处理 existing_through 之后、cut 落在完整 exchange 组边界、尾部按消息数+整组多留）；SummaryResult 与 validate（空/空白/超预算=invalid）。测试：tests/services/test_conversation_summary.py 8 passed（persist/单调/冲突单行/组边界 cut/只增量/校验）+ context_builder 10 + migration 24 全绿。剩余：ConversationSummarizer（Fake+有界 1 次与 usage 记录）、Runner 接入 PreparedContext 与 context_limit 错误映射、follow-up upper-bound 隔离接线、DB 两阶段编排、200 消息集成。P10.1-B 未 complete；P10.1-C next。

P10.1-B3（部分完成）：create_summary 唯一冲突改为 SAVEPOINT（begin_nested），不再回滚调用方外层事务；新增 ConversationSummarizer 抽象 + 固定中文 Summary Prompt（不绑定 SDK）；新增 SummaryOrchestrator（bounded history → 不加 summary 先试全量 fit；超预算才触发；已有 summary 时 select_incremental_inputs 只传 existing 之后并按 exchange 边界 cut；max_compaction_calls_per_run=1；冲突时采用 winning Summary 不再调模型；失败 fallback 保留旧 summary + recent；输出 PreparedContext + diagnostics（compaction_model_calls/summary_refreshed/refresh_failed））。测试：orchestrator 5（短对话 0 调用/首次建 summary/增量只发 after-existing/冲突不重调/四种失败不无限）+ summary 8 + context 10 + migration 6 = 29 passed。剩余：Runner 真正接入 PreparedContext 与 context_limit 错误映射、follow-up A/B visibility 审计与接线、context_prepared/context_compacted 事件、Artifact metadata 注入、200 消息集成与 §44 全回归。P10.1-B 未 complete。

## 2.47 2026-09-07 — P10.1-B3 complete：Summarizer Orchestration + Runner Integration

> P10.1-B 本轮全部完成；P10.1 overall 仍 NOT complete（P10.1-C：Relevant Artifact Context + Recent Diff + 200+ 消息最终加固 + P10.1 final acceptance，未开始；P10.2 Approval 未进入）。

**Preflight 审计结论（#1/#18）**
- create_summary 唯一冲突路径：既有 SAVEPOINT 方案有真 bug——begin_nested 内 flush 失败后 SQLAlchemy 已自动把 pending 行移出 Session（旧实现手动 expunge 会抛 InvalidRequestError 中断），且 MySQL REPEATABLE READ 下普通 SELECT 可能读不到刚提交的胜者。修复：冲突后 expunge 加 InvalidRequestError 保护 + FOR UPDATE 当前读重读 winning；绝不 rollback 调用方外层事务（隔离测试构造“外层同事务先写 unrelated 行 → summary 唯一冲突 → commit 成功”验证，见 test_summary_unique_conflict_keeps_caller_transaction_and_related_row）。
- Follow-up A/B visibility：既有 restore 语义（owner=Run user_message_id seq 分组、(owner, seq) 逻辑序）本身正确。但审计发现**物理 sequence marker 在 follow-up 插队时会把逻辑上未覆盖的用户消息误判为已覆盖**（例：A 执行期间 B/C 用户行先落库、A 助手行后落库；B 的压缩 marker 按物理上界可越过 B 用户行，后续 Run 按“物理 seq > marker”过滤时 B/C 用户消息被永久丢弃）。定稿：through_sequence_no = **逻辑位置（run-bounded 逻辑序 rank）**，增量选择只处理 rank > marker；普通无插队会话 rank==物理 seq，与既有测试/数据兼容。可见行查询下推到 SQL（owner 边界两段式查询），不在 Python 过滤未来消息（#16/#17）；与 restore 语义逐行一致测试覆盖（test_run_visible_rows_logical_order_across_queued_followups）。

**实现清单**
- conversation_summary_service：SAVEPOINT 冲突隔离修复 + rank 语义定稿（模块 docstring/selector/marker 注释）；source_message_count = 最新 marker（累计覆盖原始消息数，稳定语义，#13）。
- conversation_repository：新增 list_run_visible_message_rows（SQL 侧 owner 边界 + 逻辑序）。
- summarizer.py：ConversationSummarizer 接口定稿；固定中文 Summary Prompt（保留目标/约束/已完成与未解决/模块用例指代/近期修改；丢弃寒暄/大 Tool JSON/delta/debug/hidden reasoning；Do not invent / Artifact may be stale / 非 Artifact authority；短文本、无 Markdown 报告）；ProviderConversationSummarizer 复用 gateway.stream（无第二套 SDK；usage/cost→SummaryResult.usage；error/length/empty 抛错=一次失败）。
- summary_orchestrator：current_turn_too_large 短路（0 次 Summarizer）；已有 summary 增量一次；首建/冲突采用 winning；刷新成功后最终上下文 = summary(≤cut)+cut 后原始行（连续覆盖、不留空洞）；最终合法性复核（摘要+尾部放不进预算 → context_limit，绝不静默丢行）；compaction_model_calls≤1；usage/provider/model/estimated 进入 diagnostics（#8）。
- conversation_context_service（新）：ConversationContextPreparer（读→释放→Summarizer→短写→重建）、DbSummaryIO（每调用独立短事务）、ConversationContextLimitError（reason 映射 current_turn_too_large/summary_unavailable/working_context_too_large）、build_artifact_runtime_section（artifact id/title/**当前 revision**/module/case/view，ACL 同 P09.3B §2.2，不含 Node 内容/Diff，#27/#28）。
- runner.py：run() 全面接入 PreparedContext（AgentLoopContext.messages = prepared.messages；system_prompt = prepared.system_prompt()，全量 transcript 不再直传 AgentLoop，Context 准备不改历史行）；取消检查前置（模型/摘要 0 调用）；context_prepared/context_compacted 事件（fenced 短事务，只在使用压缩上下文时落库，payload 脱敏）；context_limit → Run failed(error_code=context_limit) + context_limit 事件同事务；_fail_run 支持 extra_event；ownership/terminal 复核跨 Summarizer 等待；db.rollback 释放复核读事务（保持“网络等待无悬挂事务”契约）。

**测试（新增 27 个测试函数 + 预算修正既有 5 个 orchestrator 测试）**
- tests/agents/conversation/test_runner_context_compaction.py 15 passed：#33 短对话 0 次摘要+无 summary 行+Provider 全量；#34 100+ 消息首次压缩（through<当前 user rank、source_count==through、Provider 不再见全量 raw、事件脱敏）；#35 第二次增量（Summarizer 只收到 existing 后 rank 区间 raw：不含 ≤old raw、不含尾部窗口；事件 old/new through+usage）；#36 200+ 消息+多 ToolCall+大 ToolResult（DB 行数原样、预算内、exchange 同组完整、Chat History 完整）；#39 超大当前轮（摘要 0 调用、主 Provider 0 调用、Run=context_limit、UserMessage 保留）；#40 失败四态 × 有/无旧摘要（有旧摘要回退成功+summary_refresh_failed；无旧摘要 context_limit reason=summary_unavailable；均 ≤1 次调用）；#41 follow-up A/B（A 请求绝不含 B；B 看到 A terminal assistant+tool result+B 自己；顺序正确）；#42 stale summary（metadata section revision25 实时 vs 摘要内 revision20，wrapper may be stale）。
- tests/agents/conversation/test_provider_summarizer.py 6 passed（成功文本+usage/cost 提取；error/length/empty/gateway 异常 → 一次失败；请求走 StreamRequest 无 tools、max_tokens=summary 预算）。
- tests/services/test_conversation_context_service.py 6 passed（#38 事务隔离；DbSummaryIO winning/首建/单调；owner 边界逻辑序与 restore 逐行一致；未来消息 SQL 层排除；#28 metadata 实时 revision）。
- tests/conversation/test_summary_orchestrator.py 更新预算为非病态窗口后 5 passed；tests/services/test_conversation_summary.py 8 passed（rank 语义兼容）。
- 既有回归不回归：runner 9、workers conversation 全量、follow-up 持久化 11（注：test_conversation_followup.py 两个线程并发用例在 HEAD 基线即偶发失败——stash 后 HEAD 实测 4 次中 2 次失败，与本轮改动无关；SQLite 单连接 + 线程时序的既有 flake，已在多次独立重跑通过）、migrations 16（test_test_artifact_migration.py 的 HEAD_REVISION 常量随 0009 链头更新为 0009_conversation_summary）、conversation 全量、artifact_tools/scenario/providers/api 等。
- 全回归命令与结果：`pytest tests/ --ignore=tests/manual --ignore=tests/conversation/test_isolation.py` → 773 passed / 1 failed（该 1 failed 为上述 pre-existing 线程 flake，重跑通过）；`pytest tests/conversation/test_isolation.py` → 3 passed（与 tests/agent_loop/test_isolation.py 同名文件冲突为 HEAD 既有收集问题：两文件同名且无包结构，pytest 单进程收集后者报 import file mismatch，非本轮引入）。

**P10.1-B 完成条件核对**：Summary model abstraction ✅ incremental compaction ✅ no long DB transaction ✅ monotonic persistence ✅ Runner uses PreparedContext ✅ full transcript 不再直传 ✅ context_limit ✅ summary fallback ✅ follow-up isolation ✅ B 见 A terminal ✅ 200+ messages ✅ 全回归 ✅ → **P10.1-B complete**。下一阶段 P10.1-C（Relevant Artifact Context + Recent Diff + 200+ 最终加固 + P10.1 final acceptance）；不进入 P10.2 Approval。

## 2.48 2026-09-07 — P10.1-B3 三项收尾审计（通过，P10.1-B 正式 complete）

> 结论：3 项审计全部通过。仅审计修复，未扩展功能，未实现 P10.1-C / P10.2。

**审计 1：through_sequence_no 语义与命名**
- 实际语义确已为 run-bounded 可见逻辑序 rank，但旧列名掩盖语义 → 全量改名：
  DB 列/ORM 属性/服务函数/SummaryStoreView/DbSummaryIO/事件 payload/诊断键
  统一为 through_visible_rank（术语“sequence_no”从 ConversationSummary 表面移除，
  迁移 0009 尚未落真实库，同迁移内定稿）。
- 新增 through_message_id String(64) 稳定 cursor：边界最后一条被摘要消息的
  message_id，与 rank 同写同读（create/conditional update/winning 冲突保留）；
  ConversationContextPreparer 读阶段校验锚点位置（错位 → agent_run_data_invalid）。
- invariant 已写入测试：未来新 Run/消息只追加在已覆盖 prefix 之后，锚点消息的
  rank 与 prefix 内每条消息的位置永不改变（多层 follow-up 插队 + 追加未来 Run 后
  重算可见序验证）；corrupt anchor 会被 prep 检出。
- 测试：prefix 稳定性 + 锚点一致性 + corrupt 检出 + winning 锚点不漂移（services
  test_conversation_context_service 8 passed）。

**审计 2：build_summary_input_text 截断不得 over-claim**
- 原实现做整体尾部截断（cut=K 但模型未必收到 ≤K 全部消息）→ 已废除。
- 新规则：渲染绝不整条丢弃 Message；超大 Tool payload 单条内部缩写并保留
  tool_name/id/is_error/长度省略等语义标记（_render_message/_preview）。
- 超预算（新预算项 ContextBudgetConfig.summarizer_input_max_chars=48_000）时由
  summarizer_coverable_messages 按完整 exchange 组从最新端裁减，Orchestrator 只把
  chunk 交给 Summarizer，marker（rank+through_message_id）只推进到 chunk 末条。
- 测试：渲染完整性（超大 user/result/toolcall 都有结构化表示+省略标记）、整组裁
  减不切散多调用 exchange、至少覆盖一组的保证、渲染度量与预算一致（纯测试 5）；
  orchestrator over-claim 防回归（小输入预算下被 marker 覆盖的每条消息都在 fake
  收到的输入里、锚点==末条、增量场景同验证）（2）。

**审计 3：Summary provider 的 cancellation / ownership**
- Summarizer 经 runtime_context 携带 Run cancel_event/deadline：调用前已取消立即
  失败（0 次 Provider 请求）；流中取消/超时由 P02 协调器经同一 StreamControl 帧间
  观察快速中断（adapter 测试验证 cancel 后 2s 内失败 + control 接线断言）。
- Runner：Summarizer 返回后复核 ownership/终态；prep 中 cancel_event 已置 → 快速
  取消路径（含 context_limit 型异常的取消优先映射）；事件写入前保持 execution
  token fencing。
- 判定：**ConversationSummary = monotonic derived cache**——写只允许 through 单调
  向前（SAVEPOINT 唯一 + expected_old 条件更新），stale worker 的摘要只覆盖真实
  历史 prefix、不可能覆盖更新的 winning 值，因此 Summary write 不需要 fencing；
  Run 生命周期事件仍必须 fencing（Runner 事件写前 assert_execution_ownership）。
- 测试：runner 级 cancel-during-summary（run=cancelled、无 context 事件、摘要不回
  退）、terminal-mid-summary（no-write + summary 作为 cache 允许存在）、
  ownership-lost-mid-summary（run 原样 running、无事件）（3）+ provider adapter 3。
- 顺手确认：Summary 请求 tools=[]（只接受最终文本）；usage 记录经
  compaction_model_calls/summary_* 可区分，总成本聚合留 P10.1-C。

**回归**：conversation/services/agents/migrations/workers 相关套件 349 passed +
bounding/orchestrator/provider 新测试全绿；全量回归
`pytest tests/ --ignore=tests/manual --ignore=tests/conversation/test_isolation.py`
通过（同一 pre-existing 线程 flake 备注同 §2.47）。

**结论：P10.1-B 正式 complete。下一阶段 P10.1-C（Relevant Artifact Context +
Recent Diff + 200+ 最终加固 + P10.1 final acceptance）；不进入 P10.2。**
