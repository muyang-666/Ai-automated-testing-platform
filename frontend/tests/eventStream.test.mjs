import test from "node:test";
import assert from "node:assert/strict";
import { subscribeEventStream } from "../src/components/v2-chat/eventStream.js";

const encoder = new TextEncoder();
const frame = (seq, text = "你好") => `data: ${JSON.stringify({
  sequence_no: seq, event_type: "conversation_text_delta", payload: { message_id: "m1", text },
})}\n\n`;
function response(text = "") { return new Response(text, { headers: { "Content-Type": "text/event-stream" } }); }
async function until(predicate) {
  const deadline = Date.now() + 1500;
  while (!predicate() && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.ok(predicate(), "stream did not recover within test deadline");
}

test("超过五次正常空闲超时后，仍能实时收到回答", async (t) => {
  let calls = 0;
  const events = [];
  const stop = subscribeEventStream({
    url: "http://localhost/events", renewalDelayMs: 0,
    fetchImpl: async () => response(++calls === 8 ? frame(1) : ": keep-alive\n\n"),
    onEvent: (event) => events.push(event),
  });
  t.after(stop);
  await until(() => events.length === 1);
  assert.ok(calls >= 8);
  assert.equal(events[0].payload.text, "你好");
});

test("建连失败和读取中断均重连，并带最后已接收的事件游标去重", async (t) => {
  const urls = [], events = [], errors = [];
  let stop;
  stop = subscribeEventStream({
    url: "http://localhost/events", retryDelayMs: 0, renewalDelayMs: 0,
    fetchImpl: async (url) => {
      urls.push(url);
      if (urls.length === 1) throw new TypeError("network unavailable");
      if (urls.length === 2) {
        let first = true;
        return new Response(new ReadableStream({ pull(controller) {
          if (first) { first = false; controller.enqueue(encoder.encode(frame(10))); }
          else controller.error(new TypeError("connection reset"));
        } }));
      }
      return response(frame(10) + frame(11, "后续"));
    },
    onEvent: (event) => { events.push(event); if (event.sequence_no === 11) stop(); },
    onError: (error) => errors.push(error),
  });
  t.after(stop);
  await until(() => events.length === 2);
  assert.deepEqual(events.map((event) => event.sequence_no), [10, 11]);
  assert.equal(new URL(urls[2]).searchParams.get("after_sequence"), "10");
  assert.equal(errors.length, 2);
});

test("首段文字在连接结束之前即交给界面，支持 UTF8 与 CRLF 跨包", async (t) => {
  let streamController;
  const events = [];
  const bytes = encoder.encode(frame(1).replaceAll("\n", "\r\n"));
  const stop = subscribeEventStream({
    url: "http://localhost/events",
    fetchImpl: async () => new Response(new ReadableStream({ start(controller) {
      streamController = controller;
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      // Deliberately leave the stream open, as a slow model would.
    } })),
    onEvent: (event) => events.push(event),
  });
  t.after(stop);
  await until(() => events.length === 1);
  assert.equal(events[0].payload.text, "你好");
  streamController.close();
});

test("取消订阅会停止待重连定时器，不会复活旧会话连接", async () => {
  let calls = 0;
  const stop = subscribeEventStream({
    url: "http://localhost/events", retryDelayMs: 20,
    fetchImpl: async () => { ++calls; throw new TypeError("offline"); },
  });
  await until(() => calls === 1);
  stop();
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.equal(calls, 1);
});

test("401 退出登录且不无限重连", async () => {
  let calls = 0, unauthorized = 0;
  const stop = subscribeEventStream({
    url: "http://localhost/events", retryDelayMs: 0,
    fetchImpl: async () => { ++calls; return new Response("", { status: 401 }); },
    onUnauthorized: () => { ++unauthorized; },
  });
  await until(() => unauthorized === 1);
  stop();
  assert.equal(calls, 1);
});

test("切换会话时取消，当前数据包里的后续事件也不能污染新会话", async () => {
  const events = [];
  let stop;
  stop = subscribeEventStream({
    url: "http://localhost/events", renewalDelayMs: 0,
    fetchImpl: async () => response(frame(1) + frame(2)),
    onEvent: (event) => { events.push(event); stop(); },
  });
  await until(() => events.length > 0);
  assert.deepEqual(events.map((event) => event.sequence_no), [1]);
});
