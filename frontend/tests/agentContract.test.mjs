import test from "node:test";
import assert from "node:assert/strict";
import { caseRunRequest, candidateRows, coverageRows, currentApproval, errorText, sessionStartErrorText } from "../src/components/test-agent/agentContract.js";

test("创建 Run 使用平铺 source 字段与 session_id", () => {
  const request = caseRunRequest(5, { input: { source_type: "requirement", source_id: 6, max_cases: 3 }, idempotency_key: "key" });
  assert.equal(request.session_id, 5); assert.equal(request.source_id, 6); assert.equal(request.max_cases, 3);
  assert.equal(request.idempotency_key, "key"); assert.equal(request.input, undefined);
});
test("candidate.case 展开且 ID 由服务器外层决定", () => {
  const [row] = candidateRows({ payload_json: { candidates: [{ candidate_id: "CASE-001", case: { name: "登录", candidate_id: "wrong" }, revision: 2 }] } });
  assert.equal(row.name, "登录"); assert.equal(row.candidate_id, "CASE-001"); assert.equal(row.revision, 2);
});
test("生成前不显示虚假已覆盖数量", () => {
  const [row] = coverageRows({ atomic_clauses: [{ clause_id: "R1" }], matrix: [], coverage_plan: [{ clause_id: "R1", dimension: "正常场景" }] });
  assert.equal(row.calculated, false); assert.deepEqual(row.dimensions, ["正常场景"]);
});
test("真实 matrix 数组按 clause_id 映射", () => {
  const [row] = coverageRows({ atomic_clauses: [{ clause_id: "R1" }], matrix: [{ clause_id: "R1", covered: true, covered_by: ["CASE-001"] }] });
  assert.equal(row.covered, true); assert.deepEqual(row.covered_by, ["CASE-001"]);
});
test("审批只使用当前 phase 的 pending 记录", () => {
  const run = { status: "waiting_approval", output_json: { workflow_state: { phase: "coverage_gate" } } };
  assert.equal(currentApproval(run, [{ id: 1, status: "pending", action_code: "confirm_case_generation_scope" }, { id: 2, status: "pending", action_code: "confirm_case_coverage_plan" }]).id, 2);
  assert.equal(currentApproval({ ...run, status: "queued" }, []), null);
});
test("422 数组转换成可读文字而非 React 对象", () => {
  assert.match(errorText({ response: { data: { detail: [{ loc: ["body", "source_id"], msg: "Field required" }] } } }), /source_id/);
});
test("会话启动 4xx 展示后端原因并引导重选来源，而非只显示发送失败", () => {
  const text = sessionStartErrorText({ response: { status: 404, data: { detail: "项目不存在或已删除，无法创建会话。" } } });
  assert.match(text, /项目不存在或已删除/);
  assert.match(text, /重新点击“交给 Agent”/);
});
test("会话启动 5xx 提示稍后重试/联系管理员", () => {
  const text = sessionStartErrorText({ response: { status: 500, data: { detail: "服务内部错误" } } });
  assert.match(text, /服务内部错误/);
  assert.match(text, /联系管理员/);
});
test("会话启动网络错误不误报来源无效", () => {
  const text = sessionStartErrorText(new Error("Network Error"));
  assert.match(text, /Network Error/);
  assert.ok(!/交给 Agent/.test(text));
});
