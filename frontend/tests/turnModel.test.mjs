import { test } from "node:test";
import assert from "node:assert/strict";
import { buildConversationTurns } from "../src/components/v2-chat/turnModel.js";
import { isNearBottom, shouldAutoScroll } from "../src/components/v2-chat/scrollPolicy.js";

const user = (id, runId, seq, text) => ({
  id, message_id: `m-${id}`, role: "user", sequence_no: seq, run_id: runId,
  content: [{ type: "text", text }],
});
const assistant = (id, runId, seq, text, stopReason = "stop") => ({
  id, message_id: `m-${id}`, role: "assistant", sequence_no: seq, run_id: runId,
  content: [{ type: "text", text }], stop_reason: stopReason,
});
const toolEvent = (seq, runId, type, callId, toolName = "calculator", extra = {}) => ({
  sequence_no: seq, event_type: type, run_id: runId,
  payload: { tool_call_id: callId, tool_name: toolName, ...extra },
});

test("Bug1: follow-up 物理 sequence 交错时按 Turn 归组 (A user, B user, A assistant, B assistant)", () => {
  const messages = [
    user("a", 1, 1, "A"),      // seq1
    user("b", 2, 2, "B"),      // seq2（A 回答前已落库）
    assistant("a1", 1, 3, "Answer A"), // seq3 晚于 B.user
    assistant("b1", 2, 4, "Answer B"), // seq4
  ];
  const turns = buildConversationTurns({ messages });
  assert.equal(turns.length, 2);
  assert.equal(turns[0].userText, "A");
  assert.deepEqual(turns[0].assistantTexts, ["Answer A"]);
  assert.equal(turns[1].userText, "B");
  assert.deepEqual(turns[1].assistantTexts, ["Answer B"]);
  assert.equal(turns[0].ownerSequence, 1);
  assert.equal(turns[1].ownerSequence, 2);
});

test("Bug2: tool 事件按 run_id 归到产生它的 Turn", () => {
  const messages = [
    user("a", 1, 1, "A"), assistant("a1", 1, 2, "答 A"),
    user("b", 2, 3, "B"), assistant("b1", 2, 4, "答 B"),
  ];
  const events = [
    toolEvent(10, 1, "conversation_tool_started", "tc-1"),
    toolEvent(11, 1, "conversation_tool_finished", "tc-1", "calculator", { is_error: false }),
  ];
  const turns = buildConversationTurns({ messages, events });
  assert.equal(turns[0].toolActivities.length, 1);
  assert.equal(turns[0].toolActivities[0].status, "success");
  assert.equal(turns[1].toolActivities.length, 0); // B 不显示 A 的工具
});

test("started/finished 合并为单个 ToolActivity", () => {
  const events = [
    toolEvent(1, 7, "conversation_tool_started", "tc-x"),
    toolEvent(2, 7, "conversation_tool_finished", "tc-x", "calculator", { is_error: false }),
  ];
  const messages = [user("a", 7, 1, "A"), assistant("a1", 7, 2, "ok")];
  const turns = buildConversationTurns({ messages, events });
  assert.equal(turns[0].toolActivities.length, 1);
  assert.equal(turns[0].toolActivities[0].status, "success");
});

test("follow-up queued: 尚无回复的后续 user turn 标记 queued", () => {
  const messages = [
    user("a", 1, 1, "A"), assistant("a1", 1, 2, "答 A"),
    user("b", 2, 3, "B"), // 已入队未执行
  ];
  const turns = buildConversationTurns({ messages, overrides: { activeRunId: 1 } });
  assert.equal(turns[1].status, "queued");
});

test("终态事件驱动 turn.status（failed/interrupted 等）", () => {
  const messages = [user("a", 1, 1, "A")];
  const events = [
    toolEvent(1, 1, "run_failed", "tc-none", "x", {}),
  ];
  const turns = buildConversationTurns({ messages, events: [{ sequence_no: 1, event_type: "run_failed", run_id: 1, payload: {} }] });
  assert.equal(turns[0].status, "failed");
  assert.equal(turns.length, 1);
  void events;
});

test("Bug7: (run_id, tool_call_id) 合并键 —— 两 Run 复用同一 callId 不串 Turn，且按 sequence 排序", () => {
  const messages = [
    user("a", 1, 1, "A"), assistant("a1", 1, 2, "答 A"),
    user("b", 2, 3, "B"), assistant("b1", 2, 4, "答 B"),
  ];
  const events = [
    toolEvent(10, 1, "conversation_tool_started", "tc-same"),
    toolEvent(11, 1, "conversation_tool_finished", "tc-same", "calculator", { is_error: false }),
    toolEvent(20, 2, "conversation_tool_started", "tc-same"), // 另一 Run 复用同一 callId
    toolEvent(21, 2, "conversation_tool_finished", "tc-same", "calculator", { is_error: true, error_code: "boom" }),
  ];
  const turns = buildConversationTurns({ messages, events });
  assert.equal(turns.length, 2);
  assert.equal(turns[0].toolActivities.length, 1, "A 只见自己的工具活动");
  assert.equal(turns[0].toolActivities[0].status, "success");
  assert.equal(turns[0].toolActivities[0].seq, 10);
  assert.equal(turns[1].toolActivities.length, 1, "B 的工具不被 A 的 started/finished 污染");
  assert.equal(turns[1].toolActivities[0].status, "error");
  assert.equal(turns[1].toolActivities[0].errorCode, "boom");
  assert.equal(turns[1].toolActivities[0].seq, 20);
});

test("同一 Turn 内多 Tool 按事件 sequence_no 排序（而非 callId 字典序）", () => {
  const messages = [user("a", 1, 1, "A"), assistant("a1", 1, 2, "答 A")];
  const events = [
    toolEvent(30, 1, "conversation_tool_started", "tc-zebra"),
    toolEvent(31, 1, "conversation_tool_finished", "tc-zebra", "calculator", { is_error: false }),
    toolEvent(20, 1, "conversation_tool_started", "tc-alpha"),
    toolEvent(21, 1, "conversation_tool_finished", "tc-alpha", "calculator", { is_error: false }),
  ];
  const [turn] = buildConversationTurns({ messages, events });
  assert.equal(turn.toolActivities.length, 2);
  assert.equal(turn.toolActivities[0].toolCallId, "tc-alpha"); // seq 20 先发生
  assert.equal(turn.toolActivities[1].toolCallId, "tc-zebra");
});

test("活跃 head 尚无落库回复（流式文本在途）时 turn 为 running，不误标 queued", () => {
  const messages = [user("a", 1, 1, "A")]; // assistant 消息尚未 commit
  const turns = buildConversationTurns({
    messages,
    overrides: { activeRunId: 1, streaming: { runId: 1, text: "正在流式…" } },
  });
  assert.equal(turns[0].status, "running");
  assert.equal(turns[0].streamingText, "正在流式…");
});

test("scrollPolicy: 打开/自己发送/刷新强制到底；流式仅在近底部时跟随", () => {
  assert.equal(shouldAutoScroll({ eventKind: "open", isNearBottomNow: false }), true);
  assert.equal(shouldAutoScroll({ eventKind: "own", isNearBottomNow: false }), true);
  assert.equal(shouldAutoScroll({ eventKind: "refresh", isNearBottomNow: false }), true);
  assert.equal(shouldAutoScroll({ eventKind: "stream", isNearBottomNow: true }), true);
  assert.equal(shouldAutoScroll({ eventKind: "stream", isNearBottomNow: false }), false);
  assert.equal(isNearBottom(1000, 100, 1100, 80), true);
  assert.equal(isNearBottom(700, 100, 1100, 80), false);
});
