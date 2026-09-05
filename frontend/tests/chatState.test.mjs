import { test } from "node:test";
import assert from "node:assert/strict";
import {
  canSendMessage, conversationState, mergeRenamedConversation, stopTargetRun,
} from "../src/components/v2-chat/chatState.js";

// P06 fix：A running + B queued → Stop 必须取消 A（active head），不能取消最新提交的 B。
test("Stop 目标 = snapshot.active_run.id（A running + B queued → 取消 A）", () => {
  const snapshot = {
    active_run: { id: 11, status: "running" },
    latest_run: { id: 22, status: "queued" }, // 刚提交的 follow-up，不是 Stop 目标
    queue_state: "executable",
  };
  assert.equal(stopTargetRun(snapshot), 11);
});

test("Stop 目标：无 active head（如仅排队）时返回 null，不误伤任何 run", () => {
  assert.equal(stopTargetRun({ latest_run: { id: 22, status: "queued" } }), null);
  assert.equal(stopTargetRun(null), null);
});

test("conversationState: A running + B queued → 顶部仍是 running（提交 follow-up 不改全局状态）", () => {
  const snapshot = {
    active_run: { id: 11, status: "running" },
    latest_run: { id: 22, status: "queued" },
    queue_state: "executable",
  };
  assert.equal(conversationState(snapshot), "running");
});

test("conversationState: 无 active、head 排队待 claim → queued", () => {
  assert.equal(conversationState({
    active_run: null, latest_run: { id: 22, status: "queued" }, queue_state: "executable",
  }), "queued");
});

test("conversationState: pause-guard → paused；终态失败 → failed；空闲 → idle", () => {
  assert.equal(conversationState({ queue_state: "paused", latest_run: { id: 1, status: "failed" } }), "paused");
  assert.equal(conversationState({ queue_state: "idle", latest_run: { id: 1, status: "failed" } }), "failed");
  assert.equal(conversationState({ queue_state: "idle", latest_run: { id: 1, status: "succeeded" } }), "idle");
  assert.equal(conversationState(null), "idle");
});

// P06 fix：快速连续发送不能被网络 busy 静默吞掉——发送门禁只看对话状态。
test("canSendMessage: running/queued/idle 均可发送；busy/loading 不参与门禁", () => {
  assert.equal(canSendMessage({ hasActive: true, phase: "running", modelReady: true }), true);
  assert.equal(canSendMessage({ hasActive: true, phase: "queued", modelReady: true }), true);
  assert.equal(canSendMessage({ hasActive: true, phase: "idle", modelReady: true }), true);
  // 即使上一次提交还在网络在途（busy），仍允许继续发送 follow-up
  assert.equal(canSendMessage({ hasActive: true, phase: "running", modelReady: true, busy: true }), true);
});

test("canSendMessage: paused 或模型未配置时拒绝发送", () => {
  assert.equal(canSendMessage({ hasActive: true, phase: "paused", modelReady: true }), false);
  assert.equal(canSendMessage({ hasActive: true, phase: "idle", modelReady: false }), false);
  assert.equal(canSendMessage({ hasActive: false, phase: "idle", modelReady: true }), false);
});

// P06 fix：自动命名成功后 list 与 active（header title 数据源）必须一起更新。
test("mergeRenamedConversation: 同时更新 conversations list 与 active conversation", () => {
  const conversations = [{ id: 1, title: "新对话" }, { id: 2, title: "旧话题" }];
  const active = { id: 1, title: "新对话" };
  const next = mergeRenamedConversation({ conversations, active, conversationId: 1, title: "帮我排查登录失败" });
  assert.equal(next.conversations[0].title, "帮我排查登录失败");
  assert.equal(next.active.title, "帮我排查登录失败");
  assert.equal(next.conversations[1].title, "旧话题");
});

test("mergeRenamedConversation: 重命名非激活会话时 active 不变", () => {
  const conversations = [{ id: 1, title: "新对话" }, { id: 2, title: "旧话题" }];
  const active = { id: 1, title: "新对话" };
  const next = mergeRenamedConversation({ conversations, active, conversationId: 2, title: "改名B" });
  assert.equal(next.conversations[1].title, "改名B");
  assert.equal(next.active, active);
});
