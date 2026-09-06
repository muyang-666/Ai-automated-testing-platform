import test from "node:test";
import assert from "node:assert/strict";
import {
  EMPTY_FUNCTIONAL_WORKSPACE, deriveFunctionalWorkspace,
  functionalWorkspaceReducer, workspaceTurnPayload,
} from "../src/components/v2-workspace/functionalWorkspaceModel.js";
import { buildContextIndicator, planWorkspaceSubmission } from "../src/components/v2-chat/chatContextModel.js";

const nodes = new Map([
  [1, { id: 1, node_type: "root", title: "商城", parent_id: null }],
  [10, { id: 10, node_type: "module", title: "登录", parent_id: 1 }],
  [11, { id: 11, node_type: "module", title: "账号锁定", parent_id: 10 }],
  [100, { id: 100, node_type: "test_case", title: "第五次失败锁定", parent_id: 11 }],
]);
const base = { project: { id: 7, name: "商城" }, artifact: { id: 9, title: "商城功能用例" },
  index: nodes, scopeId: null, selectedNodeId: null, viewMode: "list" };

test("FunctionCasePage 选择 Module 发布稳定 ID 和完整路径", () => {
  const value = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 11 });
  assert.equal(value.selectedModuleId, 11);
  assert.equal(value.selectedCaseId, null);
  assert.deepEqual(value.modulePath, ["登录", "账号锁定"]);
});

test("选择 Case 同时保存直接父 Module 和 Case ID", () => {
  const value = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 100,
                                            viewMode: "mindmap" });
  assert.equal(value.selectedModuleId, 11);
  assert.equal(value.selectedCaseId, 100);
  assert.equal(value.caseLabel, "TC-000100");
  assert.equal(value.viewMode, "mindmap");
});

test("离开 FunctionCasePage 清空页面 selection，但这是前端状态动作", () => {
  const value = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 100 });
  assert.deepEqual(functionalWorkspaceReducer(value, { type: "leave" }), EMPTY_FUNCTIONAL_WORKSPACE);
});

test("Context Indicator 使用 Conversation focus authority 并显示友好路径", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 100 });
  const context = buildContextIndicator({ workspace, snapshot: { focused_artifact: {
    id: 9, project_id: 7, project_name: "商城", title: "商城功能用例" } } });
  assert.equal(context.mismatch, false);
  assert.match(context.label, /商城 · 功能用例 · 登录 · 账号锁定 · TC-000100/);
});

test("页面与 Conversation Artifact 不同时显示真实 AI Context", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 11 });
  const context = buildContextIndicator({ workspace, snapshot: { focused_artifact: {
    id: 99, project_id: 8, project_name: "支付后台", title: "支付功能用例" } } });
  assert.equal(context.mismatch, true);
  assert.match(context.label, /支付后台/);
  assert.match(context.warning, /当前页面是「商城」/);
});

test("功能用例页新 Conversation 计划先 focus 当前 Artifact 再提交", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 11 });
  const plan = planWorkspaceSubmission({ isUnsaved: true, focusedArtifactId: null,
                                        phase: "idle", workspace });
  assert.equal(plan.action, "focus-then-submit");
  assert.equal(plan.workspaceContext.selected_module_id, 11);
});

test("busy 或已绑定其他 Artifact 都不会 silent refocus", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 11 });
  assert.equal(planWorkspaceSubmission({ isUnsaved: false, snapshotReady: true,
    focusedArtifactId: null, phase: "running", workspace, message: "这里补一条" }).action, "busy");
  assert.equal(planWorkspaceSubmission({ isUnsaved: false, snapshotReady: true,
    focusedArtifactId: 99, phase: "idle", workspace, message: "这个模块补边界" }).action, "mismatch");
  assert.equal(planWorkspaceSubmission({ isUnsaved: false, snapshotReady: true,
    focusedArtifactId: 99, phase: "running", workspace, message: "继续解释刚才的回答" }).action,
  "submit");
  // P09.3B §2.3/§60：功能用例页无 Artifact（加载中/空/无权限）时普通聊天照常允许，
  // 只有引用“这里/这个模块”或资产型指令时明确提示“无可用功能测试资产”。
  assert.equal(planWorkspaceSubmission({ isUnsaved: false, snapshotReady: true,
    focusedArtifactId: 9, phase: "idle",
    workspace: { ...workspace, artifactId: null }, message: "为什么这么设计？" }).action,
  "submit");
  assert.equal(planWorkspaceSubmission({ isUnsaved: false, snapshotReady: true,
    focusedArtifactId: 9, phase: "idle",
    workspace: { ...workspace, artifactId: null }, message: "这里补一条边界" }).action,
  "no-artifact");
});

test("Turn payload 只包含 selection/view，不重复 project/artifact", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 100,
                                                viewMode: "mindmap" });
  assert.deepEqual(workspaceTurnPayload(workspace), {
    selected_module_id: 11, selected_case_id: 100, current_view: "mindmap",
  });
  assert.equal("project_id" in workspaceTurnPayload(workspace), false);
  assert.equal("artifact_id" in workspaceTurnPayload(workspace), false);
});

test("后端拒绝 stale/deleted selection 后清除 ID 并保留可读错误", () => {
  const workspace = deriveFunctionalWorkspace({ ...base, scopeId: 11, selectedNodeId: 100 });
  const cleared = functionalWorkspaceReducer(workspace, {
    type: "clear-selection", message: "之前选择的模块或用例已失效，请重新选择。",
  });
  assert.equal(cleared.selectedModuleId, null);
  assert.equal(cleared.selectedCaseId, null);
  assert.match(cleared.selectionError, /重新选择/);
});
