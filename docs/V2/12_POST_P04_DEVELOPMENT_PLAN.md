# V2-P05～P10 新开发路线：Conversational Test Artifact Agent

> 前置状态：V2-P01～P04 已完成。  
> 本计划替代原 P05～P10 中“V2 只做通用聊天，测试 Artifact 全部后移 V3”的边界。  
> 原 P01～P04 不推倒重做，以现有 Message / Provider / Agent Loop / Persistence 为基础继续。

## 1. V2 新交付目标

P10 完成后，用户应能在浏览器中完成以下真实闭环：

```text
创建/打开一个 Test Artifact
        ↓
和 Agent 持续聊天
        ↓
“先帮我分析需求，列测试点”
        ↓
Agent 动态调用 Tool 修改 Artifact
        ↓
脑图实时出现测试点
        ↓
“锁定这里补一下边界”
        ↓
Agent 读取相关节点和需求
        ↓
只修改相关分支
        ↓
UI 展示 Diff
        ↓
“第二个不要”
        ↓
Agent 根据上下文删除对应节点
        ↓
Revision +1，可撤销
```

不允许实现成：

```text
每次输入
→ case_generation workflow
→ 固定 generate
→ fixed validate
→ fixed save
```

---

# 2. 新里程碑

| 阶段 | 主题 | 关键交付 |
|---|---|---|
| P05 | Conversation Runtime 收敛 | Worker、租约、取消、队列；新 Agent 不再走测试 Workflow |
| P06 | Conversation API + Streaming Shell | 真正持续聊天、刷新恢复、SSE |
| P07 | Test Artifact Core | Case Tree、Revision、Operation、Diff、Undo 基础 |
| P08 | Artifact Tools + Test Design Skill | Agent 可动态 read/add/edit/delete/move/validate Artifact |
| P09 | Chat + MindMap + Diff Workspace | 用户与 Agent 围绕同一 Artifact 协作编辑 |
| P10 | Context / Safety / Recovery / E2E | 长会话、冲突、审批、恢复、真实闭环验收 |

---

# 3. V2-P05 — Conversation Runtime 收敛与 Workflow 退役

## 目标

完成 P04 的持久化执行桥接，使新 Conversation Agent 只有一条明确运行链：

```text
ConversationTurn
→ Worker
→ ConversationRunner
→ Agent Loop
```

旧固定测试 Workflow 不再作为新架构执行路径。

## 实施内容

### 3.1 Worker

保留并完成：

- queued Run 抢占；
- lease；
- heartbeat；
- fencing token；
- cancellation；
- interrupted；
- 同会话一个 active Turn；
- follow-up queue。

### 3.2 Runner

新增/固化：

```text
ConversationRunner
```

职责仅为：

1. 从 Repository 重建会话 Context；
2. 构造 RuntimeContext；
3. 调用 `run_agent_loop()`；
4. 持久化最终 Message / Event / Run status；
5. 不自己决定测试业务步骤。

### 3.3 Workflow 处理

新代码禁止：

```python
if workflow_code == "case_generation":
    ...
```

进入新的 Conversation Agent 路径。

旧 `case_generation` 有两种处理方式：

- 若 V1 当前仍依赖：迁移到 legacy/compat 区域，只服务旧入口；
- 若确认无调用方：删除。

不允许：

- 为了兼容继续把它挂在新 Worker 的主分发路径；
- 新 Artifact Tool 内反向调用整个 Workflow。

## 推荐目录

```text
backend/app/agents/
  conversation/
    runner.py
    loop.py
    context.py
    tool_executor.py
  legacy/
    case_generation/     # 仅临时兼容；P10 前决定是否删除
```

## 验收

- Fake Provider 可以通过 Worker 完成 3 个连续 Turn；
- 长模型调用 heartbeat 不丢 lease；
- cancel 能终止当前 Turn；
- Follow-up 顺序稳定；
- 新对话不引用 case_generation Workflow；
- Workflow 删除/隔离后 P01～P04 回归通过。

---

# 4. V2-P06 — Conversation API、SSE 与基础工作台

## 目标

让浏览器真正成为一个持续会话 Agent，而不是“生成任务 UI”。

## API 建议

```text
POST /agent/conversations
POST /agent/conversations/{id}/turns
GET  /agent/conversations/{id}
GET  /agent/conversations/{id}/messages
GET  /agent/conversations/{id}/events
POST /agent/conversation-runs/{id}/cancel
```

增加：

```text
POST /agent/conversations/{id}/artifacts/{artifact_id}/focus
```

用于设置当前工作 Artifact，首期也可以先放到 P07。

## UI 首期

```text
┌──────────────────────────────┐
│ Conversation                 │
│                              │
│ User                         │
│ Assistant                    │
│ Tool activity                │
│                              │
│                [Stop]        │
│ [input....................]  │
└──────────────────────────────┘
```

P06 暂时不要求完整脑图，只要求：

- 多轮；
- Streaming；
- Tool activity 独立展示；
- Refresh restore；
- Error 后继续聊；
- Session list；
- Cancel。

## 验收

至少完成：

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

---

# 5. V2-P07 — Test Artifact Core

## 目标

建立新的长期业务对象：

```text
TestArtifact
```

它替代“一次 Run 生成一个完整用例 JSON”的产品中心地位。

## 核心数据

```text
TestArtifact
├─ artifact_id
├─ project_id
├─ owner_id
├─ title
├─ artifact_type=test_design
├─ current_revision
├─ root_node_id
└─ status
```

```text
ArtifactNode
├─ node_id
├─ parent_id
├─ node_type
├─ order_key
├─ title
├─ content
├─ metadata
└─ source_refs
```

Node 类型首期：

```text
root
group
test_point
test_case
```

## Revision

每一次逻辑修改形成 Revision：

```text
Revision 17
  ↓
ArtifactOperation
  ↓
Revision 18
```

至少支持：

```text
add_node
update_node
delete_node
move_node
restore_revision
```

## Diff

服务端可以根据 operation 直接形成结构化 Diff：

```json
{
  "from_revision": 17,
  "to_revision": 18,
  "changes": [
    {
      "type": "update",
      "node_id": "TC023",
      "fields": {
        "expected_result": {
          "before": "无法登录",
          "after": "锁定期间即使密码正确也无法登录"
        }
      }
    }
  ]
}
```

## 并发

所有写操作要求：

```text
expected_revision
```

版本不匹配返回 conflict，不允许静默覆盖用户刚刚的人工修改。

## 重要边界

脑图不是底层存储格式。

正确关系：

```text
TestArtifact
   ├─ MindMap View
   ├─ Table View
   └─ JSON/API View
```

## 验收

- 创建空 Artifact；
- 添加 20 个节点；
- 修改单节点；
- 移动分支；
- 删除节点；
- Revision 连续；
- Diff 正确；
- Undo 到上一 Revision；
- stale revision 写入被拒；
- 不需要 LLM 也能完整测试 Artifact Domain。

---

# 6. V2-P08 — Artifact Tools 与 Test Design Skill

## 目标

Agent 第一次真正具备“像 Coding Agent 改代码一样改测试资产”的能力。

## 首期 Tools

### Read

```text
get_current_artifact
read_artifact_outline
read_artifact_nodes
search_artifact
get_artifact_diff
read_requirement
```

### Write

```text
add_artifact_node
update_artifact_node
delete_artifact_node
move_artifact_node
batch_apply_artifact_operations
```

### Quality

```text
validate_test_artifact
find_duplicate_cases
analyze_test_coverage
```

注意：

> Quality Tool 是能力，不是固定流程。

Agent 可以：

```text
用户：看看有没有重复
→ find_duplicate_cases
```

但用户仅要求：

```text
把 TC023 的预期改一下
```

则 Agent 不需要强制跑 coverage。

## Tool Contract

所有写 Tool 必须：

- 从 RuntimeContext 获取 user/project/artifact；
- 不接受模型伪造 owner；
- 使用 `expected_revision`；
- 返回 applied revision；
- 返回 machine-readable diff summary；
- 写入 audit；
- 遵守 Tool Policy。

## Test Design Skill

新增：

```text
skills/test-design/SKILL.md
```

它描述：

- 测试设计方法；
- 如何从需求提炼测试点；
- 边界/异常/状态转换等检查维度；
- 优先增量编辑；
- 修改前先 read；
- 不擅自删除大量人工用例；
- 不为了“格式统一”重写整棵树；
- 不把所有任务固定成“先测试点后测试用例”。

## Agent 示例

```text
User:
先列登录模块测试点，暂时不要展开详细用例

LLM
→ read_requirement
→ get_current_artifact
→ add_artifact_node × N
→ final
```

下一轮：

```text
User:
锁定这个节点展开成详细用例

LLM
→ read_artifact_nodes(lock-node)
→ read_requirement(lock clauses)
→ add_artifact_node × N
→ final
```

路径由模型根据用户意图决定。

## 验收

至少覆盖 8 类对话：

1. 从空 Artifact 增加测试点；
2. 只展开指定分支；
3. 修改单条用例；
4. 删除“第二个”；
5. 移动节点；
6. 查重但不修改；
7. Coverage 后按用户要求补缺口；
8. 用户要求直接补用例，不强制先生成测试点。

---

# 7. V2-P09 — Chat + MindMap + Diff 协作工作台

## 目标

实现 TestMind 最核心的产品体验：

> 一边对话，一边看到 AI 对测试资产的实际修改。

## 页面结构

```text
┌────────────────────────────────────────────────────────┐
│ TestMind Workspace                                     │
├──────────────────────┬─────────────────────────────────┤
│ Chat                 │ MindMap                         │
│                      │                                 │
│ User / Assistant     │ 登录                            │
│ Tool activity        │ ├─ 正常                         │
│ Diff cards           │ ├─ 异常                         │
│                      │ └─ 锁定                         │
│                      │    ├─ TP ...                    │
│ [input]              │    └─ TC ...                    │
├──────────────────────┴─────────────────────────────────┤
│ Revision 18 | Diff | History | Undo                    │
└────────────────────────────────────────────────────────┘
```

## 核心交互

### Agent 修改后

聊天区显示：

```text
我补充了锁定时间的 3 个边界场景。
```

同时 Diff：

```text
+ TC021 29分59秒
+ TC022 30分钟
+ TC023 30分01秒
```

脑图实时增加三个节点。

### 人工修改

用户直接在脑图中编辑：

```text
TC022 title
```

也产生：

```text
ArtifactOperation
→ Revision 19
```

Agent 下一轮读取的就是 Revision 19。

AI 修改和人工修改必须走同一 Artifact Domain。

## Undo

支持：

```text
撤销上一修改
```

不是通过 LLM 猜测如何恢复，而由版本系统执行。

## Diff 视图

至少支持：

```text
added
updated
deleted
moved
```

## 大范围操作

例如：

```text
删除“支付”整个分支 43 条用例
```

UI 显示 impact preview，并可进入 Approval。

## 验收

- Chat 和脑图同 Artifact；
- AI 添加节点无需刷新出现；
- 人工修改后 AI 下一轮看到最新版本；
- Diff 与 Revision 一致；
- Undo 后 UI 和 DB 一致；
- 两个浏览器同时编辑产生 revision conflict 而非静默覆盖；
- 200+ 节点基本交互可用。

---

# 8. V2-P10 — Context、Approval、Recovery 与完整验收

## 目标

把前面能力加固成可以长期工作的 Agent，而不是 Demo。

## Context

模型输入不应每轮塞整个 Artifact。

采用：

```text
System
+ Loaded Skills
+ Conversation Summary
+ Recent Messages
+ Current Artifact metadata
+ Relevant Artifact nodes
+ Recent Diff
```

需要更多内容时由 Agent 调：

```text
read_artifact_nodes
search_artifact
```

这与 Coding Agent 不会每轮把整个仓库塞进 Prompt 是同一思想。

## Context Compaction

保留：

- 原始消息；
- Artifact Revision；
- ToolCall / ToolResult；
- 最近关键 Diff。

摘要只用于模型工作上下文，不删除原历史。

## Approval

从“固定 Workflow Gate”改为“Action Risk”。

示例：

| 动作 | 默认策略 |
|---|---|
| read | allow |
| add 1～5 nodes | allow |
| update 1 node | allow |
| delete 1 node | allow / configurable |
| batch delete 30 nodes | approval |
| overwrite artifact | approval |
| export / write to formal project | approval |

审批属于 Tool execution，不属于流程 phase。

## Recovery

验证：

- Provider 断流；
- Worker 崩溃；
- Revision 冲突；
- Tool timeout；
- Approval 后恢复；
- Cancel；
- SSE 重连；
- Context summary 失败；
- Artifact 写入成功但 final response 失败。

任何情况下都不得把“聊天失败”错误解释成“已经完成的 Artifact 写入被回滚”。

## 最终 E2E 验收故事

必须真实跑通：

```text
1. 创建 Conversation
2. 创建 Test Artifact
3. User: 根据这段登录需求先列测试点
4. Agent 动态读取需求并添加节点
5. MindMap 展示修改
6. User: 锁定部分展开详细用例
7. Agent 局部读取并修改
8. User: 第二个不要
9. Agent 正确删除对应节点
10. User: 检查一下还有哪些边界没覆盖
11. Agent 调 coverage/read tools
12. 用户同意后补充
13. 查看 Diff
14. Undo 一次
15. Refresh
16. Conversation + Artifact + Revision 全部恢复
```

满足这一故事才算 V2 完成。

---

# 9. V3 新定位

如果 V2 完成上述闭环，V3 不再是“第一次接入用例生成”。

V3 应转向更高级的测试能力扩展，例如：

```text
V3.1 API Testing Agent
V3.2 Failure RCA Agent
V3.3 Test Data Agent
V3.4 Defect Assistant
V3.5 Execution / CI Integration
```

这些能力继续复用同一个 Conversation + Tool + Artifact 模型，而不是各自建立新 Workflow Runtime。
