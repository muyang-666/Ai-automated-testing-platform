# V2 技术设计（Technical Design）

> 本文件是 V2 **唯一技术设计 Source of Truth**，回答“架构和代码应该怎么实现”。它合并了原 06 平台架构、13 Artifact 数据模型、14 Agent×Artifact 工具协议与 09 联调中的技术协议部分，去重后按主题重新组织；一个概念只定义一次。
> 产品行为见 [04_PRODUCT_PRD.md](04_PRODUCT_PRD.md)；开发计划（阶段/验收）见 [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)。Agent Core 的 Pi 源码对照见 [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)。

---

## 1. Architecture Overview

### 1.1 核心原则

> Model controls sequence. Program controls capability and safety. Artifact stores the evolving result.

中文表述：模型决定“下一步做什么”；程序保证“动作怎么安全、正确地执行”；Artifact 保存“我们共同做出了什么”。Skill 提供领域知识与行为指导，但**不控制循环顺序**；Workflow（固定 phase 状态机）不再作为业务控制方式，必要的确定性内部流程只存在于 Tool/Service 内部。

### 1.2 执行主链

```text
User
  ↓
Conversation（Session / Message / Context / Turn）
  ↓
ConversationRunner（重建 Context → RuntimeContext → run_agent_loop → 持久化）
  ↓
Agent Loop（模型决定下一步；一次 Turn 内可多次 ModelTurn）
  ↓
Tool Executor（校验 / 权限 / Policy / Approval / Budget / Cancel）
  ↓
Artifact Tools（read / search / add / update / delete / move / validate / coverage）
  ↓
TestArtifact Domain（Node / Revision / Operation / Diff / Undo / 乐观锁）
  ↓
ToolResult → Agent Loop 继续
```

### 1.3 分层与组件边界

```text
Frontend：Chat | MindMap | Diff | History | Undo | Approval 卡
FastAPI：身份/权限/预检、Turn 持久化、SSE 事件转发
MySQL Repository：Session / Message / Run / Event + TestArtifact 领域表
Worker：ConversationRunner（主）/ [legacy] Legacy Runner（旁路，仅旧入口）
  ├─ Agent Loop（run_agent_loop）→ LLM Gateway → Provider
  ├─ Context / Compaction
  ├─ Skill Catalog / load_skill
  └─ Tool Executor → Tool Policy / Approval → Artifact Tools → Artifact Application Service
Legacy：Legacy API（/agent/runs/case-generation）→ Legacy Runner → CaseGenerationWorkflow（退役中，见 01 P05）
```

边界规则：Tool 不直接调用 UI；Provider 不读取业务数据库；内核（Agent Loop）不持有 ORM Session；Markdown Skill 不获得宿主执行权限；**Agent 使用 Artifact，Artifact Domain 不依赖 Agent**（`agents/` 与 `test_artifacts/` 是两个目录，不允许 agents/ 承担 Artifact 数据领域本身）。

### 1.4 职责分层

| 层 | 职责 |
|---|---|
| Agent Core | Message / Provider / Context / Agent Loop / ToolCall / ToolResult / Policy / Budget / Cancel |
| Artifact Domain | TestArtifact / Node / Revision / Operation / Diff / Undo / SourceRef / 项目与 owner 边界 / 乐观并发 |
| Tools | 模型动作的统一门禁；Artifact 读写 / 需求读取 / 质量诊断 |
| Skill | 领域知识 + 行为规则（如 test-design），横向影响行为，不成为控制循环 |
| UI | Chat / MindMap / Diff / History / Undo / Approval；所有视图来自同一 Revision |

---

## 2. Conversation Model

### 2.1 对象

- **Session（Conversation）**：持续会话，拥有独立历史、owner、可选 project_id、当前工作 Artifact；一次任务失败后仍可聊天。产品层复用 AgentSession（mode=conversation）。
- **ConversationTurn**：一次用户输入及其处理过程，复用 AgentRun（workflow_code=conversation）；预算与取消围绕该单元；同会话同时最多一个活跃 Turn。
- **ModelTurn**：一次模型推理，可能返回文本与多个工具调用。
- **ToolCall / ToolResultMessage**：有 call_id 的一次具体动作提案；工具结果是模型可消费的独立消息（role="toolResult"，顶层 tool_call_id/tool_name/content/details/is_error），不包装成 system。
- **Message**：UserMessage / AssistantMessage / ToolResultMessage 联合；文本与 ToolCall 是 Assistant 内容块（同一列表混合保序）；稳定 message_id + schema_version + timestamp_ms。截断（length）绝不执行工具。
- **事件 ≠ 消息**：事件是执行进度（排队/流式增量/工具/Revision 创建/Diff/Approval/中断/失败），不自动成为模型历史；同会话递增 sequence_no 游标。

### 2.2 终止语义

模型结束原因区分：stop / length（截断非成功）/ toolUse（请求非已执行）/ error / aborted / deferred。不要把一个 Turn 的 succeeded 解释成“用例已保存”或整个会话关闭；conversation succeeded 只表示本轮回复完成，业务写入成功由对应 Revision/业务结果证明。工具可返回 continue / stop / wait 信号；基础设施失败或预算耗尽结束本 Turn，Conversation 仍 active。

---

## 3. Agent Runtime

### 3.1 Agent Loop

核心 `run_agent_loop()` 只接收消息、Provider、Tool Registry、事件接收器与停止信号，不依赖 ORM。每轮顺序：上下文整理 → 模型 → 完整助手消息 → 工具校验/权限 → 工具结果 → 下一轮，直到自然回答或安全停止。

- 首期串行工具，预留只读并行接口；不得并发共享 SQLAlchemy Session。
- 未知工具/参数错误作为明确工具失败反馈给模型（模型可在预算内有限修正）；基础设施失败则结束本 Turn。
- 工具结果按原调用顺序写入，tool_call_id 一一对应；同批预算原子预留、调用 ID 去重。
- 钩子（hook）修改参数后必须重新做 strict 校验（与 Pi 相关测试行为有意不同）。
- 取消/截止为批次中剩余工具生成关联“未执行”结果，保证之后每个 call_id 可识别。

### 3.2 预算

AgentLoopLimits/Budget：max_turns（8）、max_model_calls（8）、max_tool_calls（16）、wall_clock_deadline，均为硬停止（Turn 开始前原子预留）。P02 的 AttemptBudget 单独计物理模型请求（每物理请求一条 AttemptRecord，token 未知记 None/未知而非 0）。重试、摘要与普通调用共用同一预算；不允许无界重试。

### 3.3 上下文与 Compaction

展示历史与提交模型的工作上下文分离。确定性整理：去 UI-only 事件 → 压缩过长工具结果 → 保留 system 策略与完整工具对（绝不拆散 tool_call/tool_result）。达到阈值后生成摘要记录（模型/版本、输入范围、hash、usage、保留尾部），摘要只用于模型工作上下文，**原始历史与 Artifact Revision 不删除**。摘要失败退回安全窗口或明确 context_limit，不无限重试/重复计费；压缩中取消要取消流、保留原上下文并停止发布迟到摘要。P10 起模型每轮输入采用：System + Loaded Skills + Conversation Summary + Recent Messages + Artifact 元数据 + 相关节点 + 最近 Diff；更多内容由 Agent 调 read/search，而不是整棵 Artifact 入 prompt。

---

## 4. Provider / Event

### 4.1 Provider

复用现有 Gateway 的 text/json/pydantic，新增 async stream 合同：`LLMGateway.stream(...)`（异步上下文管理器，内部 LLMStreamGateway）。首期 OpenAI-compatible 与 Anthropic 两类适配（按真实版本核验协议，不增加第三套）。

- 归一化：text_delta / tool_call_delta / message_end / usage / finish_reason / request_id；Anthropic 无温度参数等能力差异显式诊断（unsupported_parameter）。
- 工具参数分片只缓存；完整消息到达、未截断且参数校验通过后才能执行；`{}` 合法、任一坏调用令整条消息失败。
- 空 content + 完整工具调用合法；空内容/仅推理/length/拒绝/网络断流分别诊断。
- 单层重试（受 AttemptBudget 约束）；部分文本已发出或工具可能已执行时不透明重放。
- 能力三态：已确认不支持 tools 则不发送；未知可受控尝试并明确失败。
- 物理模型调用用 SDK/httpx 异步接口，不在 FastAPI 事件循环中同步调用。

### 4.2 事件流

两层事件（AssistantMessageEvent / AgentEvent）+ 应用层信封（session_id / run_id / message_id / tool_call_id / sequence_no / schema_version）。流式增量只有临时意义：终止时写最终 message 状态。连接断开通过事件游标 + 快照重建，不能只在内存保存；游标过期返回 resync_required 读快照。取消/失租约/message 已完成时拒绝迟到增量。Artifact 写事件（artifact_revision_created / artifact_diff_created / approval_requested / approval_resolved / revision_conflict）与模型 Message 分离；事件不等于模型消息，前端不得展示隐藏 reasoning。

---

## 5. Tool System

### 5.1 ToolCall 是动作提案，不是执行授权

LLM 只有 ToolCall；系统裁决顺序：Tool 存在 → 参数有效（Pydantic strict）→ 身份/项目权限 → Artifact 权限 → revision 有效 → Policy → Approval → Budget/deadline/cancel → 执行 → ToolResult。

### 5.2 RuntimeContext（服务端注入，模型不可覆盖）

```text
user_id / conversation_id / project_id / artifact_id / run_id / permissions / tool_policy / deadline / cancel_token
```

模型传参中的 user_id / project_id / owner_user_id / created_by / current_revision 一律忽略或拒绝，由 Runtime 注入。

### 5.3 禁止整树替换

主要写入方式**不允许**是 `replace_entire_artifact(tree_json)`：误删无关节点、token 大、diff 难、undo 难、并发冲突、审批粒度粗、模型难表达“只改这一个”。默认使用原子/小批量增量编辑（见 §8）。

### 5.4 Tool 清单

Read：get_current_artifact（metadata）、read_artifact_outline（轻量 outline：node_id/type/title/children count）、read_artifact_nodes（按 node_id 全量）、search_artifact（keyword/node_type/tag/source_ref）、get_recent_artifact_diff（最近改动）、read_requirement。

Write：add_artifact_node、update_artifact_node（只 patch 指定字段）、delete_artifact_node（返回影响范围，如 `{"descendant_count": 43}`，供 Policy/Approval 决策）、move_artifact_node（循环引用/parent type/order/revision 检查）、batch_apply_artifact_operations（一个意图的一批小修改合为一个 Revision；必须 max_operations、max_nodes_affected、全成功才 commit）。

Quality（只读，**不修改 Artifact**）：validate_test_artifact、find_duplicate_cases、analyze_test_coverage；返回诊断 gaps（如 `{"type":"boundary","description":"缺少锁定时间结束瞬间"}`）。coverage Tool 不得自动偷偷新增用例——补缺口必须由 Agent 提议、用户允许后调写 Tool。Quality Tool 是能力不是必经流程。

### 5.5 ToolResult

同时服务 LLM / UI / audit：

```json
{ "status": "ok", "summary": "Added 3 test cases under account locking",
  "data": { "revision": 22, "affected_node_ids": ["TC021","TC022","TC023"] },
  "diff_ref": "diff:21..22" }

{ "status": "error", "error_code": "revision_conflict",
  "message": "Artifact changed after it was read.",
  "data": { "expected_revision": 21, "current_revision": 22 }, "retryable": true }
```

模型根据错误决定 re-read → retry；Runtime 不自动无限重放。错误文案固定（不转发 loc/type/msg/str(exc)/工具名等动态内容，防注入回显）。

### 5.6 工具注册与校验

ToolRegistry + `prepare_tool_call`：输入模型必须为有效 Pydantic 模型且 strict 校验；校验/序列化/候选构造各段异常都收敛为固定错误码（invalid_arguments / validation_failed / invalid_config）。事件快照深拷贝，防止迟到 update 污染。

---

## 6. Test Artifact Domain

### 6.1 Artifact 是业务对象，不是聊天消息

错误：`AssistantMessage.content = 整棵测试用例 JSON`。正确：Conversation ↔ Agent ↔ Tools ↔ TestArtifact。聊天解释修改，Artifact 保存修改。**AI 写入与人工 UI 写入必须调用同一个 Artifact Application Service**；禁止“AI 一套 DB 逻辑、前端另一套”。

### 6.2 Artifact 与 View 解耦

```text
            TestArtifact
        ─────────┬─────────
   MindMap View  Table View  JSON/API View
```

数据库不存某 UI 库的坐标/组件结构作为业务真相；视图坐标如需保留放独立 view_state。前端实现可任选 React Flow / X6 / MindElixir 等。

### 6.3 AgentArtifact 与 TestArtifact 的语义边界

AgentArtifact ≈ 某次 Agent Run 产生的一份结构化产物快照（execution output / evidence / legacy 候选覆盖矩阵），现存实现为整棵 JSON payload + 整数 version 浅版本；TestArtifact ≈ 用户长期维护的可编辑业务对象。不让一张表承担两种语义：P07 新增 TestArtifact 领域表；AgentArtifact 保留为执行产物/历史兼容，未来确认无需保留时可迁移后再合并。

### 6.4 TestArtifact 字段

```text
id / project_id / owner_user_id / title / artifact_type / status /
current_revision / root_node_id / schema_version / created_at / updated_at
```

首期 artifact_type=test_design，可扩展 api_test_design / test_plan / rca_report。

### 6.5 领域目录

```text
backend/app/test_artifacts/
  models/  schemas/  services/  repository/  diff/
```

Agent 使用 Artifact；Artifact 不依赖 Agent。

---

## 7. ArtifactNode / Case Tree

### 7.1 Node 字段与类型

```text
id / artifact_id / parent_id / node_type / order_key / title /
content_json / source_refs_json / created_revision / deleted_revision? /
created_by / created_at / updated_at
```

node_type 首期：root / group / test_point / test_case。示例：

```text
登录测试
├─ 功能
│  ├─ 正常登录                test_point
│  │  ├─ TC001 手机号+密码成功  test_case
│  │  └─ TC002 邮箱+密码成功
│  └─ 密码错误
└─ 状态
   └─ 账号锁定
      ├─ 第4次失败
      ├─ 第5次失败
      └─ 30分钟解锁
```

### 7.2 test_case content_json

不要摊平成宽表；首期建议（不同类型节点允许不同 schema）：

```json
{
  "preconditions": ["账号存在且未锁定"],
  "steps": [ { "action": "输入正确账号", "data": "user@example.com" },
             { "action": "连续输入错误密码 5 次" } ],
  "expected_results": ["第 5 次失败后账号进入锁定状态", "锁定时间为 30 分钟"],
  "priority": "P1",
  "tags": ["边界", "状态转换"]
}
```

### 7.3 SourceRef

```json
{ "source_type": "requirement", "source_id": "REQ-123", "fragment_id": "clause-7", "snapshot_hash": "..." }
```

一个节点可关联多个来源。用途：Agent 解释“为什么有这条用例”、需求变化影响分析、Coverage 不依赖纯文本相似度、后续 Requirement→TestCase Traceability。

---

## 8. ArtifactOperation

每个 Revision 包含一组 operation（记录 id / revision_id / op_index / operation_type / target_node_id / payload_json / before_json / after_json）。

支持类型：add_node / update_node / delete_node / move_node / restore。示例：

```json
// add_node
{ "operation_type": "add_node", "parent_id": "TP_LOCK",
  "node": { "node_type": "test_case", "title": "29分59秒仍保持锁定" } }

// update_node（只 patch 指定字段；服务端控制字段不可传）
{ "operation_type": "update_node", "target_node_id": "TC023",
  "patch": { "title": "30分钟整允许重新登录" } }

// move_node
{ "operation_type": "move_node", "target_node_id": "TC023",
  "new_parent_id": "TP_TIME_BOUNDARY", "new_order_key": "3" }
```

所有写操作都要求 `expected_revision`（见 §10）。人工 UI 编辑与 Agent 编辑最终都落到这些 operation；事件（artifact_revision_created）由提交后发布。

---

## 9. Revision / Diff / Undo

### 9.1 为什么不能只 update 当前 JSON

只存 `artifact.payload_json = latest tree` 会失去：谁改了什么、Agent 是否误删、Undo、Diff、冲突判断、按 Revision 构建 Context、AI+人工协作的可靠性。

### 9.2 ArtifactRevision

```text
id / artifact_id / revision_no / base_revision /
actor_type(user|agent|system) / actor_user_id /
conversation_id / run_id / summary / created_at
```

类比 Git：Artifact ≈ repository/document；Revision ≈ commit；Operation ≈ patch。首期只做线性 revision，不做 Git DAG。

```text
Revision 17 → ArtifactOperation(s) → Revision 18
```

### 9.3 Diff

Diff 是 Revision 的派生结果（operation 直接可得），供 UI 与 Agent 最近上下文使用：

```json
{ "artifact_id": 12, "from_revision": 17, "to_revision": 18,
  "changes": [
    { "change": "add", "node_id": "TC021", "parent_id": "TP_LOCK" },
    { "change": "update", "node_id": "TC012",
      "fields": { "expected_results": {
          "before": ["锁定后无法登录"],
          "after": ["锁定期间正确密码仍无法登录"] } } }
  ] }
```

### 9.4 Undo

首期：undo latest revision / restore to revision N。通过生成“反向 Revision”实现（17→18 AI add→19 user update→20 revert revision 19），**不物理删除历史**，审计不消失。

---

## 10. Optimistic Concurrency

写工具携带 expected_revision；版本不匹配 → 409 revision_conflict（ToolResult 含 expected/current，retryable=true），不允许静默覆盖用户刚刚的人工修改：

```text
Agent 读取 revision=17 → 用户手工修改 → current revision=18
→ Agent 以 expected_revision=17 更新 → 409 revision_conflict
→ 模型重新读取相关节点，而不是覆盖用户修改
```

双浏览器/双入口并发在数据库约束/事务层裁决，不依赖前端 disabled 或 Python 全局锁。

---

## 11. Test Design Skill

Skill = 面向某类任务的领域知识、策略、检查清单与行为说明；**不再包含 `phase A → phase B → phase C`**。

- 机制（沿用受控加载）：审核目录注册（name/hash/version/frontmatter 诊断/大小/重复名）、`load_skill(name)` 只按注册名取值（不接受任意 path）、资源根限定防穿越/外链、Skill 不扩张工具权限（可用工具 = 平台允许 ∩ 用户权限 ∩ 会话策略）、不自动执行 Skill scripts。模型只先见摘要，需要时加载正文。
- 内容（skills/test-design/SKILL.md，P08 交付）：测试设计方法与检查维度（正向/异常/边界/状态转换）；从需求提炼测试点；优先增量修改现有 Artifact；修改前先 read 相关节点；不无理由重写整棵树；大范围删除需解释并触发 Approval。
- 硬性行为规则：
  1. **Read before write**：要改已有节点先读相关节点（除非上一 ToolResult 已含完整最新内容）；
  2. **Minimal edit**：用户说“把 TC003 预期改一下”时禁止重写整个模块；
  3. **Respect user structure**：除非用户要求重构，不擅改节点分类、大量重命名、重排整棵树；
  4. **No mandatory generation path**：禁止“任何测试设计任务都必须先测试点→再用例→再查重”；可写“需求范围大且尚无结构时可以先提炼测试点；若用户明确要求直接补用例，按用户目标工作”。

---

## 12. Approval / Policy

Approval 从“固定 Workflow Gate”改为 **Action Risk** 的 Tool Policy，属于 Tool 执行，不属于流程 phase。

```python
if operation == "read":                          allow
elif affected_nodes <= 5 and operation in {"add","update"}:   allow
elif operation == "delete" and affected_nodes >= 10:  require_approval
elif operation == "replace_artifact":            require_approval
```

| 动作 | 默认策略 |
|---|---|
| read | allow |
| add 1～5 nodes | allow |
| update 1 node | allow |
| delete 1 node | allow / configurable |
| batch delete 30 nodes | approval |
| overwrite / replace artifact | approval |
| export / write to formal project | approval |

approval_request 保存：tool_call_id、arguments_hash、artifact_revision、affected_nodes、expires_at。只有经过身份校验的人类决议能批准（模型与 Skill 不持有“自我批准”工具）；用户批准后必须重新校验 revision、权限、参数 hash、lease、cancel；拒绝/过期/参数变化不能自动重试成批准；失败不能静默落写。审批恢复属 P10 故障场景之一。

---

## 13. Worker / Queue / Recovery

- **单入口 Worker**：claim 最旧 queued Run（原子条件 UPDATE：worker_id + heartbeat_at），按类型分发；运行时禁止 FastAPI --reload startup 隐式启动常驻 Worker。P05 起 conversation queued Run 由 Worker 消费（现状是 claim 查询 `workflow_code != "conversation"` 跳过，见 01 P05 起点现状）。
- **lease/heartbeat/fencing**：独立轻量心跳机制、短事务、独立 DB Session（长模型调用不误判）；条件更新带执行代次（fencing token），失去租约的执行器不能继续落消息或产生后续副作用；检查取消读取可信新状态而非长期缓存 ORM 对象。
- **队列**：默认一个会话一个活跃 Turn（active_slot 唯一约束 + DB 事务）；follow_up 是后续用户消息队列，不制造同会话并行处理器；前项失败/中断时暂停后续队列。
- **取消/中断**：cancel 传递到模型流与合作式工具（asyncio.Event + deadline；同步 handler 只能调用前后检查，不能物理抢占）；不可中止的外部副作用如实标注；进程崩溃标 interrupted，**不自动重放未知是否成功的调用**；abort 后迟到的 update 被丢弃。
- **Recovery 场景**（P10 验证）：Provider 断流 / Worker 崩溃 / Revision 冲突 / Tool timeout / Approval 后恢复 / Cancel / SSE 重连 / Context summary 失败 / Artifact 已写入但 final response 失败。任何情况下不得把“聊天失败”解释成“已完成的 Artifact 写入被回滚”。
- Worker 健康状态可安全暴露，队列无人消费时前端能解释。

---

## 14. Persistence

- 沿用 Agent 平台表扩展：agent_sessions.mode（legacy_workflow/conversation，既有行默认 legacy_workflow）、conversation Session/Run 的 project_id 可空（旧生成入口项目仍必填）、Run 复用为 ConversationTurn（workflow_code=conversation，user_message_id、active_slot 唯一/check 约束）、messages.content_json 存版本化内容块（模型工具消息完整保存并经 parse_message 重建）、序号游标（原子 `UPDATE col = col + 1` 后同事务读预留值）保证无重复序号。
- 幂等：用户消息 + queued Run + 幂等键（session_id, workflow_code, idempotency_key）同事务；同键同内容返回原 Run，不同内容 409。
- 权限：Session/Run/Event/Artifact 读先按 owner；旧 /agent/runs/{id} 等通用路径必须识别 conversation mode，不能通过旧项目读权限旁路；NULL 项目聊天不可调用 project_required 工具。
- P07 起新增 TestArtifact / ArtifactNode / ArtifactRevision / ArtifactOperation 表（字段见 §6～§9；ArtifactOperation 存 before_json/after_json 供 Diff/审计）。
- 增量 Alembic，保留 V1 表；downgrade 若存在新数据（NULL 项目/版本化消息/Revision）必须预检拒绝有损降级；**不把“删除 Python Workflow 类”与“删数据库历史字段”强绑定为同一提交**（Legacy 字段按 01 P05/P10 节奏处理）。
- 同步 SQLAlchemy 走短事务 Repository；线程/异步任务间不共享 Session；关键事务不覆盖网络等待。

---

## 15. Frontend / SSE Integration

### 15.1 API

Conversation：
```text
POST /agent/conversations
POST /agent/conversations/{id}/turns           # content、client_request_id、可选 skill_code、queue_mode → 202 + run_id + user_message_id
GET  /agent/conversations/{id}                # 快照与当前 Turn
GET  /agent/conversations/{id}/messages?after_sequence=...
GET  /agent/conversations/{id}/events?after_sequence=...   # SSE
POST /agent/conversation-runs/{id}/cancel
POST /agent/conversations/{id}/artifacts/{artifact_id}/focus   # 设置当前工作 Artifact（首期可入 P07）
GET  /agent/conversation-capabilities         # 模型/工具能力与 Worker 可用性，不含密钥
```

Test Artifact（Agent Tool 与人工 UI 共用同一 Application Service，禁止两套写入逻辑）：
```text
POST /test-artifacts
GET  /test-artifacts/{id}
GET  /test-artifacts/{id}/tree
GET  /test-artifacts/{id}/nodes/{node_id}
GET  /test-artifacts/{id}/revisions
GET  /test-artifacts/{id}/diff?from=&to=
POST /test-artifacts/{id}/operations          # 携带 expected_revision
POST /test-artifacts/{id}/undo
```

既有 /agent/sessions 与 /agent/runs/case-generation 保留给旧调用方，不静默改变语义。

### 15.2 SSE 与事件同步

- SSE 用可携带现有 Bearer 的 fetch 流（Token 不进 URL）；FastAPI 从数据库事件日志转发 Worker 事件，不能仅用进程内队列。
- 游标断线续传 + sequence 去重；游标过期 resync_required → 读消息/Artifact 快照恢复。
- 普通对话使用独立 agent_chat 场景或明确选定模型；缺配置在启动前提示，不自动初始化真实 Key。
- 前端展示消息与 Tool activity / Revision 事件分离；Markdown 禁止危险 HTML；流式末尾按稳定 message_id 合并。
- **Artifact 写不逐 token 落库**：tool arguments 完整 → validate → transaction → revision committed → 发布 artifact_revision_created → UI（Chat/Diff/MindMap）从事件更新。
- 前端“发送”只提交 Turn；不先 appendMessage 再无条件 createCaseRun（现状代码需替换）。

---

## 16. Security Boundary

- 身份/项目/owner 全部由服务端从登录态注入 RuntimeContext；不接受、不信任模型传入的 user_id/project_id；每次业务/工具调用重新检查用户/项目/环境权限（不因“会话里说过”而授权）。
- 工具可用集 = 平台配置 ∩ 用户权限 ∩ 会话策略 ∩ Tool Policy；Skill 正文与模型都不得修改该交集。
- 审批只允许真实人类鉴权端点；参数 hash / revision / 权限 / lease 在批准时重新校验；模型或 Skill 无“自我批准”能力。
- NULL 项目聊天不获得跨项目搜索权；项目绑定只在 owner 明确操作时进行并验证权限。
- 资源加载限制在显式审核目录内（真实路径、后缀、尺寸校验，防穿越/外链）；不自动执行 Skill scripts、不安装第三方包、不扫描宿主/实习目录。
- 隐藏 reasoning 不是消息也不是前端事件：不保存、不展示；日志只含安全诊断与可观察事件。清理已知敏感键并测试嵌套结构；不以关键词脱敏宣称所有 Secret 安全。
- 版本化审计：Tool 调用、Revision、预算、事件与安全错误有记录；错误回显固定文案防注入（见 §5.5）。

---

## 17. 与 Pi 的关系

V2 参考 Pi（固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6，MIT，Copyright (c) 2025 Mario Zechner）并继续沿用：Message 模型、ToolCall/ToolResult、Agent Loop、事件、Provider 边界、Context 处理、Skill 按需加载思路。逐符号 Python 映射与采纳范围见 [references/PI_SOURCE_AUDIT.md](references/PI_SOURCE_AUDIT.md)；改编代码保留上游版权与来源注释。

TestMind 自己重点建设（Pi 没有或不作为参考）：Test Artifact（Node/Revision/Operation/Diff/Undo/乐观锁）、Artifact editing tools、项目与权限、按动作风险的 Approval、Test domain Skills（test-design）、Chat + MindMap + Diff 协作 UI。因此 V2 不是“Python 版 Pi”，而是**基于 Pi-like Agent Core 构建的面向测试资产协作编辑的 Test Agent**。Artifact / MindMap / Diff 是自研业务层，不硬找 Pi 一一对应。
