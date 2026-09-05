import test from "node:test";
import assert from "node:assert/strict";
import { runErrorMessage, messageFailure } from "../src/components/v2-chat/conversationErrors.js";

test("余额不足提示账户操作，而不是稍后重试", () => {
  assert.match(runErrorMessage("insufficient_balance"), /余额不足/);
  assert.doesNotMatch(runErrorMessage("insufficient_balance"), /稍后/);
});
test("旧失败消息和新失败消息均有可读说明，成功回复不显示错误", () => {
  assert.match(messageFailure({ role: "assistant", stop_reason: "error", error_code: "http_error", content: [] }), /余额/);
  assert.match(messageFailure({ role: "assistant", stop_reason: "error", error_code: "insufficient_balance", content: [] }), /余额不足/);
  assert.equal(messageFailure({ role: "assistant", stop_reason: "stop", content: [{text:"17"}] }), null);
  assert.equal(messageFailure({ role: "user", stop_reason: "error" }), null);
});
