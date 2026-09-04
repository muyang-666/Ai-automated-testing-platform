# Conversational Agent × Artifact Tool Protocol

> 目标：定义 Agent 如何像 Coding Agent 使用文件工具一样，安全地读取和修改测试 Artifact。

# 1. 设计原则

LLM 不直接拥有数据库写权限。

LLM 只能提出：

```text
ToolCall
```

系统负责：

```text
Tool exists?
→ Arguments valid?
→ Identity / project permission?
→ Artifact permission?
→ Revision valid?
→ Policy?
→ Approval?
→ Budget / deadline / cancel?
→ Execute
→ ToolResult
```

所以：

> ToolCall 是动作提案，不是执行授权。

---

# 2. 为什么必须是增量 Tool

禁止把主要写入方式设计成：

```text
replace_entire_artifact(tree_json)
```

原因：

- 误删无关节点；
- token 大；
- diff 困难；
- undo 困难；
- 人工编辑并发冲突；
- 审批粒度太粗；
- Agent 很难表达“只改这一个”。

默认使用原子/小批量编辑。

---

# 3. Tool 分类

## 3.1 Read Tools

### get_current_artifact

返回当前工作 Artifact metadata。

### read_artifact_outline

只返回树的轻量 outline：

```text
node_id
type
title
children count
```

避免每轮加载全部用例详情。

### read_artifact_nodes

按 node_id 读取完整内容。

### search_artifact

按：

```text
keyword
node_type
tag
source_ref
```

搜索。

### get_recent_artifact_diff

供模型理解“刚刚改了什么”。

---

# 4. Write Tools

## add_artifact_node

输入：

```json
{
  "artifact_id": 12,
  "expected_revision": 17,
  "parent_id": "TP_LOCK",
  "node": {
    "node_type": "test_case",
    "title": "29分59秒时账号仍锁定",
    "content": {}
  }
}
```

输出：

```json
{
  "ok": true,
  "revision": 18,
  "node_id": "TC021",
  "diff": {
    "change": "add",
    "node_id": "TC021"
  }
}
```

---

## update_artifact_node

只能 patch 指定字段。

禁止模型传：

```text
owner_user_id
project_id
created_by
current_revision
```

这些由服务端控制。

---

## delete_artifact_node

需要明确返回影响范围：

```json
{
  "target_node_id": "TP_PAY",
  "descendant_count": 43
}
```

Policy 可据此决定 Approval。

---

## move_artifact_node

负责：

- 循环引用检查；
- parent type 检查；
- order；
- revision。

---

## batch_apply_artifact_operations

用于同一个 Agent 意图的一批小修改。

例如：

```text
一次补充 3 个边界场景
```

可以一个 Revision 包含 3 个 add。

必须有：

```text
max_operations
max_nodes_affected
transaction
```

全部成功才 commit。

---

# 5. Quality Tools

Quality Tool 不修改 Artifact，除非名称和合同明确表示会修改。

推荐：

```text
validate_test_artifact       # read-only
find_duplicate_cases         # read-only
analyze_test_coverage        # read-only
```

它们返回诊断：

```json
{
  "gaps": [
    {
      "type": "boundary",
      "description": "缺少锁定时间结束瞬间"
    }
  ]
}
```

之后由 Agent 决定：

```text
解释给用户
```

或者用户允许时调用写 Tool 补充。

不要做：

```text
coverage_tool 自动偷偷新增用例
```

---

# 6. RuntimeContext

身份信息永远由 Runtime 注入：

```text
user_id
conversation_id
project_id
artifact_id
run_id
permissions
tool_policy
deadline
cancel_token
```

模型不可传入并覆盖：

```text
user_id=1
project_id=2
```

---

# 7. ToolResult 设计

ToolResult 要同时服务：

- LLM；
- UI；
- audit。

推荐：

```json
{
  "status": "ok",
  "summary": "Added 3 test cases under account locking",
  "data": {
    "revision": 22,
    "affected_node_ids": ["TC021", "TC022", "TC023"]
  },
  "diff_ref": "diff:21..22"
}
```

错误：

```json
{
  "status": "error",
  "error_code": "revision_conflict",
  "message": "Artifact changed after it was read.",
  "data": {
    "expected_revision": 21,
    "current_revision": 22
  },
  "retryable": true
}
```

模型根据错误决定是否：

```text
re-read
→ retry
```

而不是 Runtime 自动无限重放。

---

# 8. Agent 行为规则

Test Design Skill 建议包含以下硬性行为指导：

## 8.1 Read before write

如果要修改已有节点：

```text
先读取相关节点
```

除非上一 ToolResult 已提供完整最新内容。

---

## 8.2 Minimal edit

用户说：

```text
把 TC003 预期改一下
```

禁止：

```text
重写整个登录模块
```

---

## 8.3 Respect user structure

除非用户要求重构，不擅自：

- 改节点分类；
- 大量重命名；
- 重新排序整棵树。

---

## 8.4 No mandatory generation path

禁止 Skill 写：

```text
任何测试设计任务都必须：
1. 先生成测试点
2. 再生成测试用例
3. 再查重
```

可以写：

```text
当需求范围较大且尚无结构时，可以先提炼测试点；
若用户明确要求直接补用例，应按用户目标工作。
```

---

# 9. 示例完整 Agent Loop

## 场景 A：先测试点

```text
User:
先帮我列支付退款的测试点，不需要详细步骤

ModelTurn 1
→ read_requirement(refund)

ToolResult
→ clauses

ModelTurn 2
→ get_current_artifact

ToolResult
→ revision 8

ModelTurn 3
→ batch_apply_artifact_operations(
    add test_point × 7
  )

ToolResult
→ revision 9 + diff

ModelTurn 4
→ 回复：已增加 7 个测试点
```

没有固定 Workflow。

---

## 场景 B：继续展开局部

```text
User:
把“重复退款”展开一下

Model
→ read_artifact_nodes(TP_REPEAT_REFUND)
→ add test_case × 4
→ final
```

---

## 场景 C：“第二个不要”

上下文中上一轮新增：

```text
TC021
TC022
TC023
```

模型可以结合 Message + recent diff 判断：

```text
第二个 = TC022
```

然后：

```text
delete_artifact_node(TC022)
```

如果歧义较大，应追问，而不是猜。

---

# 10. Approval 从 Phase 改成 Action Risk

策略示例：

```python
if operation == "read":
    allow

elif affected_nodes <= 5 and operation in {"add", "update"}:
    allow

elif operation == "delete" and affected_nodes >= 10:
    require_approval

elif operation == "replace_artifact":
    require_approval
```

Approval 请求中保存：

```text
tool_call_id
arguments_hash
artifact_revision
affected_nodes
expires_at
```

用户批准后必须重新校验：

- revision；
- 权限；
- 参数 hash；
- lease；
- cancel。

---

# 11. Event 建议

Agent 执行期间可产生：

```text
tool_call_started
tool_call_finished
artifact_revision_created
artifact_diff_created
approval_requested
approval_resolved
revision_conflict
```

但事件不等于模型 Message。

前端可展示：

```text
正在读取当前用例…
已新增 3 个节点
Revision 22
```

不要展示隐藏 CoT。

---

# 12. 测试策略

所有 Tool 都应有纯确定性测试：

- schema invalid；
- unknown node；
- cross-project；
- stale revision；
- permission denied；
- cancel；
- approval；
- batch rollback；
- diff；
- malicious model arguments。

然后再测试 Agent + Fake Provider 是否能正确选择 Tool。

不要只通过“LLM 最终回答看起来对”来验收。
