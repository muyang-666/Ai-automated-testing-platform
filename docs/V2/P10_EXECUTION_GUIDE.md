# V2-P10 阶段执行任务书
## Context / Approval / Conflict / Recovery / E2E

## Goal

不再扩新架构，完成生产级加固与 V2 总验收。

## Context

模型输入：

```text
System
Loaded Skills
Conversation Summary
Recent Messages
Current Artifact metadata
Relevant nodes
Recent Diff
```

不要每轮塞整个 Conversation + Artifact。

更多内容由 Tool 按需读。

## transform context

Persistent history 与 model context 分开。

Context transform 不删除 DB 原始历史。

## Compaction

超预算：

- 保留近期关键消息；
- 保持 ToolCall/ToolResult 配对；
- 老历史 summary；
- summary call 计入预算；
- summary 失败有限 fallback；
- 不无限 retry。

## Approval suspend/resume

```text
ToolCall
→ approval_required
→ Run waiting_approval
→ release Worker
→ human decision
→ revalidate identity/hash/revision/permission/expiry
→ new execution ownership
→ resume
```

模型不能自批。

## Recovery matrix

逐项：

- Provider断流；
- Worker crash；
- revision conflict；
- Tool timeout；
- approval resume；
- cancel；
- SSE reconnect；
- compaction failure；
- Artifact committed but final LLM failed。

特别：

> Artifact 已成功写入时，后续聊天失败不能声称 Artifact 已回滚。

## Real model

经授权的小额测试：

- streaming；
- tools；
- cancel；
- finish reason；
- usage；
- context limit。

CI 不使用真实 Key。

## MySQL

授权测试库验证：

- migration；
- constraints；
- active slot；
- fencing；
- revision conflict；
- concurrent writes；
- MySQL rowcount；
- transaction isolation。

## Security final pass

- owner/project isolation；
- Tool permission；
- identity cannot be forged；
- Approval human-only；
- secret redaction；
- Markdown/XSS。

## Legacy decision

统计旧 case_generation 实际调用。

决定：

- AgentRunner / Workflow 是否删除；
- legacy API 是否下线；
- historical data 是否 read-only 保留；
- mode/workflow_code 是否保留。

不要为了整洁破坏历史数据读取。

## Final E2E

浏览器：

```text
create Conversation
create/open Artifact
先列测试点
局部展开
删除第二个
coverage
补缺口
Diff
Undo
refresh
continue
```

并覆盖：

```text
follow-up
cancel
reconnect
conflict
approval
worker recovery
```

## Completion

更新：

- 02_DEVELOPMENT_RECORD
- 03_ACCEPTANCE_CHECKLIST
- P10 acceptance evidence（若仓库继续此习惯）

V2 完成后才进入 V3：

- API Testing Agent
- Failure RCA
- Test Data
- Defect Assistant
- Execution/CI
