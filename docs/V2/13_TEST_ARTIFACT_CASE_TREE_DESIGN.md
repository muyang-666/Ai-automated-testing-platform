# Test Artifact / Case Tree 数据模型设计

> 目标：把测试用例从“一次 LLM 输出”升级成可持续编辑、可 Diff、可版本化、可恢复的长期业务资产。

## 1. 核心原则

### 1.1 Artifact 是业务对象，不是聊天消息

错误：

```text
AssistantMessage.content = 整棵测试用例 JSON
```

正确：

```text
Conversation
  ↕
Agent
  ↕
Tools
  ↕
TestArtifact
```

聊天解释修改，Artifact 保存修改。

---

### 1.2 Artifact 与 View 解耦

```text
                TestArtifact
                     │
        ┌────────────┼────────────┐
        ↓            ↓            ↓
     MindMap       Table        JSON/API
```

前端可以用 React Flow、X6、MindElixir 等任意视图实现，但数据库不存某个 UI 库的坐标/组件结构作为业务真相。

视图坐标如有需要，应放独立 `view_state`。

---

## 2. 领域对象

## 2.1 TestArtifact

建议字段：

```text
id
project_id
owner_user_id
title
artifact_type
status
current_revision
root_node_id
schema_version
created_at
updated_at
```

首期：

```text
artifact_type = test_design
```

以后可扩：

```text
api_test_design
test_plan
rca_report
```

---

## 2.2 ArtifactNode

所有测试点/用例统一成树节点。

```text
id
artifact_id
parent_id
node_type
order_key
title
content_json
source_refs_json
created_revision
deleted_revision?
created_by
created_at
updated_at
```

### node_type

首期仅支持：

```text
root
group
test_point
test_case
```

示例：

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

---

## 3. TestCase content_json

`test_case` 节点不要把所有字段摊平成表结构。

首期建议：

```json
{
  "preconditions": [
    "账号存在且未锁定"
  ],
  "steps": [
    {
      "action": "输入正确账号",
      "data": "user@example.com"
    },
    {
      "action": "连续输入错误密码 5 次"
    }
  ],
  "expected_results": [
    "第 5 次失败后账号进入锁定状态",
    "锁定时间为 30 分钟"
  ],
  "priority": "P1",
  "tags": ["边界", "状态转换"]
}
```

不同类型节点允许不同 schema。

---

## 4. SourceRef

测试设计必须能够回到来源。

```json
{
  "source_type": "requirement",
  "source_id": "REQ-123",
  "fragment_id": "clause-7",
  "snapshot_hash": "..."
}
```

一个节点可关联多个来源。

意义：

- Agent 能解释“为什么有这条用例”；
- 需求变化后可分析受影响节点；
- Coverage 不需要只靠文本相似度；
- 后续可以做 Requirement → TestCase Traceability。

---

# 5. Revision 模型

## 5.1 为什么不能只 update 当前 JSON

如果只存：

```text
artifact.payload_json = latest tree
```

会失去：

- 谁改了什么；
- Agent 是否误删；
- Undo；
- Diff；
- 冲突判断；
- 按 Revision 构建 Context；
- AI 和人工协作的可靠性。

---

## 5.2 ArtifactRevision

建议：

```text
id
artifact_id
revision_no
base_revision
actor_type        # user / agent / system
actor_user_id
conversation_id
run_id
summary
created_at
```

Revision 代表一次逻辑提交。

类比 Git：

```text
Artifact ≈ repository/document
Revision ≈ commit
Operation ≈ patch
```

但首期不需要实现 Git DAG，线性 revision 即可。

---

# 6. ArtifactOperation

建议每次 Revision 包含一组 operation。

```text
id
revision_id
op_index
operation_type
target_node_id
payload_json
before_json
after_json
```

支持：

```text
add_node
update_node
delete_node
move_node
restore
```

### add_node

```json
{
  "operation_type": "add_node",
  "parent_id": "TP_LOCK",
  "node": {
    "node_type": "test_case",
    "title": "29分59秒仍保持锁定"
  }
}
```

### update_node

```json
{
  "operation_type": "update_node",
  "target_node_id": "TC023",
  "patch": {
    "title": "30分钟整允许重新登录"
  }
}
```

### move_node

```json
{
  "operation_type": "move_node",
  "target_node_id": "TC023",
  "new_parent_id": "TP_TIME_BOUNDARY",
  "new_order_key": "3"
}
```

---

# 7. Diff

Diff 是 Revision 的派生结果。

```json
{
  "artifact_id": 12,
  "from_revision": 17,
  "to_revision": 18,
  "changes": [
    {
      "change": "add",
      "node_id": "TC021",
      "parent_id": "TP_LOCK"
    },
    {
      "change": "update",
      "node_id": "TC012",
      "fields": {
        "expected_results": {
          "before": ["锁定后无法登录"],
          "after": ["锁定期间正确密码仍无法登录"]
        }
      }
    }
  ]
}
```

Diff 既供 UI 使用，也供 Agent 最近上下文使用。

---

# 8. Optimistic Concurrency

任何写工具必须携带：

```text
expected_revision
```

例：

```text
Agent 读取 revision=17
        ↓
用户手工修改
        ↓
current revision=18
        ↓
Agent 尝试以 expected_revision=17 更新
        ↓
409 revision_conflict
```

ToolResult 应返回：

```json
{
  "error": "revision_conflict",
  "expected_revision": 17,
  "current_revision": 18
}
```

模型随后可以重新读取相关节点，而不是覆盖用户修改。

---

# 9. Undo

首期不实现任意复杂分支。

支持：

```text
undo latest revision
restore to revision N
```

推荐通过“生成一个反向 Revision”实现，而不是物理删除历史：

```text
17
↓
18 AI add
↓
19 user update
↓
20 revert revision 19
```

这样审计历史不会消失。

---

# 10. 与现有 AgentArtifact 的关系

当前 `AgentArtifact` 更接近：

> 某次 Agent Run 产生的一份结构化产物快照。

新的 TestArtifact 更接近：

> 用户长期维护的业务工作对象。

建议不要强行让一个表承担两个语义。

推荐：

```text
AgentArtifact
= execution output / evidence / temporary generated result

TestArtifact
= long-lived editable domain object
```

如果未来确认旧 `AgentArtifact` 无需保留，可迁移后再合并；P07 不应为了复用表名牺牲语义清晰度。

---

# 11. 推荐 API

```text
POST /test-artifacts
GET  /test-artifacts/{id}
GET  /test-artifacts/{id}/tree
GET  /test-artifacts/{id}/nodes/{node_id}
GET  /test-artifacts/{id}/revisions
GET  /test-artifacts/{id}/diff?from=&to=

POST /test-artifacts/{id}/operations
POST /test-artifacts/{id}/undo
```

Agent Tool 和人工 UI 最终应调用同一个 Application Service。

不要出现：

```text
AI 写入逻辑一套
前端人工编辑另一套
```

---

# 12. P07 最小验收数据

构造 Artifact：

```text
Login
├─ Happy Path
├─ Password Error
└─ Locking
```

执行：

1. add `第五次失败锁定`
2. add `29分59秒`
3. add `30分钟`
4. update `30分钟` expected result
5. move node
6. delete one node
7. undo
8. stale revision write

逐项验证：

- Tree；
- Revision；
- Diff；
- Audit；
- rollback/revert；
- permissions；
- concurrent update。
