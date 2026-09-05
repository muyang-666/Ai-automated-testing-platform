# 新 V2 开发记录：对话式 Test Agent

> 更新：2026-09-04。旧路线记录已原文归档，不删除其中最新修复与测试证据。
> 当前状态：V2-R01 结构整理已完成；V2-P01～P04 已分别通过各自声明范围验收（P01 见 2.10、P02 见 2.14、P03 见 2.15、P04 见 2.16）。
> 2026-09-04：P05 起按 [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)（V2-P05～P10 任务卡）实施，尚未开始；P05～P10 阶段主题已改为 Conversation Runtime 收敛 / Conversation API / Test Artifact Core / Artifact Tools / Chat+MindMap+Diff / Context+Approval+Recovery（不再沿用“Skill / 上下文 / 人工门禁”旧标题）。

## 1. 当前任务状态

| 编号 | 内容 | 状态 | 证据 |
|---|---|---|---|
| V2-R01 | Agent / LLM 模块目录整理（结构，先于 P01） | 已完成 | 6 条结构测试 + 338 条受影响/回归通过，见 2.1 |
| V2-P01 | 基线与数据合同 | 阶段验收通过（限定合同/纯校验范围） | Codex 实际 90 passed in 5.41s，见 2.10 |
| V2-P02 | 流式 Provider | 部分实现，审查未通过，待集中修正 | Codex 复跑 24 项通过，合成反例确认基础缺口，见 2.13 |
| V2-P03 | Agent Loop / Tool Executor | 阶段验收通过（纯 Python/Fake 范围） | P03 30 项；P02 54、P01 90、旧 Provider/Gateway 55、ToolRegistry 4 项回归，见 2.15 |
| V2-P04 | 会话存储与迁移 | 阶段验收通过（临时 SQLite/真实事务范围） | P04 20 项；P01 90、P02 54、P03 30、旧平台 100 项回归，见 2.16 |
| V2-P05 | Conversation Runtime 收敛 + Workflow 退役 | 待实施 | 按 [01](01_DEVELOPMENT_PLAN.md) |
| V2-P06 | Conversation API + SSE + 基础工作台 | 待实施 | 同上 |
| V2-P07 | Test Artifact Core | 待实施 | 同上 |
| V2-P08 | Artifact Tools + Test Design Skill | 待实施 | 同上 |
| V2-P09 | Chat + MindMap + Diff 协作工作台 | 待实施 | 同上 |
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
