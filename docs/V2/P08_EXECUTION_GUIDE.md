# V2-P08 阶段执行任务书
## Artifact Tools + Test Design Skill

## Goal

AgentLoop 第一次真正编辑 TestArtifact：

```text
LLM
→ ToolCall
→ Artifact Tool
→ Artifact Application Service
→ Revision/Diff
→ ToolResult
→ LLM
```

模型决定顺序，不用 Workflow phase。

## Tools

Read：

```text
get_current_artifact
read_artifact_outline
read_artifact_nodes
search_artifact
get_artifact_diff
read_requirement
```

Write：

```text
add_artifact_node
update_artifact_node
delete_artifact_node
move_artifact_node
batch_apply_artifact_operations
```

Quality：

```text
validate_test_artifact
find_duplicate_cases
analyze_test_coverage
```

Quality 默认 read-only。

## Identity

Tool 从 RuntimeContext 获取：

```text
user
conversation
project
focused artifact
run
permissions
```

模型不能伪造 owner/user/project。

## Editing principles

Skill：

```text
Read before write
Minimal edit
Respect user structure
No mandatory generation path
```

禁止：

```text
任何测试任务都固定
测试点→用例→查重→coverage
```

## Revision

写 Tool 携带 expected_revision。

冲突：

```text
ToolResult(revision_conflict)
→ model re-read
→ finite retry / ask user
```

不能内部无限重试。

## Test Design Skill

新增：

```text
skills/test-design/SKILL.md
```

包含测试设计方法和行为指导，不包含 phase 状态机。

## Approval groundwork

小 add/update 可 allow。

大范围 delete：

```text
approval_required + impact
```

完整 suspend/resume 可在 P10。

## 8 类 Agent tests

1. 空 Artifact 增测试点；
2. 局部展开；
3. 单用例修改；
4. “第二个不要”；
5. move；
6. 查重不修改；
7. coverage 后按要求补；
8. 直接补用例，不强制测试点。

Tool 自身先 deterministic tests，再 Fake Provider。

## Stop boundary

不做 MindMap UI、多 Agent、API 执行、RCA、Test Data。
