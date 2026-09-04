# V2-P06 阶段执行任务书
## Conversation API + SSE + 基础持续聊天工作台

> 执行补充，不是 Source of Truth。规范仍以 01/04/05 为准。

## Goal

浏览器第一次真正使用新的 Conversation Agent：

```text
Browser
→ Conversation API
→ Worker
→ ConversationRunner
→ AgentLoop
→ SSE / DB
→ UI
```

完成：

- 多轮聊天；
- streaming；
- Tool activity；
- follow-up 队列；
- Cancel；
- Refresh restore；
- Error 后继续；
- Session list；
- 无项目聊天。

P06 不做 TestArtifact / MindMap。

## Backend API

建议：

```text
POST /agent/conversations
GET  /agent/conversations
GET  /agent/conversations/{id}
GET  /agent/conversations/{id}/messages
POST /agent/conversations/{id}/turns
GET  /agent/conversations/{id}/events
POST /agent/conversation-runs/{id}/cancel
```

Turn 单请求完成：

```text
保存 UserMessage + Run + idempotency
```

前端禁止再：

```text
appendMessage
→ createCaseGenerationRun
```

## Turn request

```json
{
  "content": "你好",
  "client_request_id": "uuid",
  "queue_mode": "follow_up"
}
```

返回 202 + run/message/queue state。

## SSE

要求：

- Bearer auth；
- owner isolation；
- sequence cursor / Last-Event-ID；
- reconnect；
- duplicate protection；
- snapshot recovery；
- 不传隐藏 CoT。

事件：

```text
run_status
assistant_delta
tool_started
tool_finished
assistant_committed
queue_state
terminal
```

DB Message/Run 仍是最终 Source of Truth。

## AgentLoop event sink

把 P03 events 接到持久化/广播边界。

注意：

- text delta 不必每 token 落 DB；
- Tool lifecycle / MessageEnd / terminal 可恢复；
- SSE 故障不能回滚已提交 Message。

## Provider config

收敛为明确 `agent_chat` scene 或现有统一 scene。

- secret 不进前端；
- 无配置明确失败；
- Run 保存非敏感 provider/model snapshot；
- CI 使用 Fake Provider；
- 真实模型留 P10。

## Tool whitelist

P06 conversation 只暴露安全通用工具。

不要把 legacy 全部工具直接暴露。

## Frontend

首期：

```text
Session list | Chat
             | Message
             | Tool activity
             | Queue status
             | Stop
             | Input
```

状态至少：

```text
idle / queued / running / failed / interrupted / cancelled
```

## Refresh

刷新后：

1. GET conversation；
2. GET messages；
3. 获取 active/queued snapshot；
4. SSE 从 cursor 重连；
5. 去重。

## Acceptance

真实 HTTP + Worker + Fake Provider：

```text
记住数字17
→ 好

加5
→ calculator
→ 22

刷新

最开始的数字？
→ 17
```

另测：

- 慢模型时 follow-up；
- cancel；
- SSE reconnect；
- provider failure 后下一 Turn；
- cross-user access denied。

## Tests

Backend API + SSE + worker E2E。

Frontend Playwright：

- create/open；
- 3 turns；
- stream；
- refresh；
- cancel；
- follow-up queued。

## Stop boundary

不做：

- TestArtifact；
- Revision/Diff；
- MindMap；
- Artifact Tools；
- Test Design Skill；
- compaction；
- 完整 Action-Risk Approval。

P06 完成后建议实际在浏览器连续聊天 10+ Turn 再进入 P07。
