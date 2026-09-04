# V2-P09 阶段执行任务书
## Chat + MindMap + Diff 协作工作台

## Goal

实现：

> 一边聊天，一边看到 Agent 对同一 TestArtifact 的实际修改；人工编辑后 Agent 下一轮基于最新 Revision 继续。

## Layout

```text
Chat                  MindMap
Messages              Tree
Tool activity         Node inspector
Diff cards

Revision / History / Undo
```

## One source

Chat解释、Diff、MindMap 三者都来自同一 Artifact Revision。

不要维护三份独立业务状态。

## MindMap adapter

Artifact Tree → UI nodes。

树结构移动：

```text
move_node
```

画布位置：

```text
view_state
```

不要混。

## Node Inspector

详细编辑：

- title；
- priority；
- tags；
- preconditions；
- steps；
- expected；
- source refs。

人工编辑仍走 Artifact Operation + Revision。

## AI edit

完整 ToolCall 成功后一次 commit Revision。

不要 token-level 半成品节点写库。

## Conflict

两个浏览器：

```text
A revision20 → writes21
B expected20 → 409
```

前端刷新最新版本，不静默覆盖。

## History / Undo

Revision history 显示 actor + summary。

Undo = 新反向 Revision。

## Artifact focus

Conversation 有当前 Artifact。

running Turn 期间不得静默切换 focus。

## Approval UX

大范围删除显示：

```text
target
affected nodes
impact
approve/reject
```

不显示 Workflow gate。

## E2E

```text
先列测试点
→ 脑图出现

锁定分支展开
→ 局部改变

第二个不要
→ 正确删除

人工改 TC003
→ AI 基于最新版继续

Diff
History
Undo
```

至少验证 200+ nodes 基本可用。

## Stop boundary

不做 CRDT、Git branches、复杂自动 merge、全功能 XMind。
