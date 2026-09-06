import test from "node:test";
import assert from "node:assert/strict";

import {
  applyArtifactEvent,
  artifactEventFromStream,
  initialState,
  markRefreshed,
} from "../src/components/v2-workspace/artifactRealtimeModel.js";
import {
  applyAgentRevision,
  expectedRevisionForSave,
  markDraftTouched,
  openEditorWithBase,
  shouldWarnConcurrency,
} from "../src/components/v2-workspace/editorConcurrencyModel.js";
import { aggregateByRun, summaryCard, summaryLabel } from "../src/components/v2-workspace/artifactChangeSummaryModel.js";
import {
  isLikelyPlainContinuation,
  looksLikeAssetDirective,
  planSubmitWithMismatch,
} from "../src/components/v2-workspace/artifactMismatchGuard.js";

test("事件归一：只接受 artifact revision/diff 事件，其它忽略", () => {
  assert.equal(artifactEventFromStream({ type: "conversation_text_delta", payload_json: {} }), null);
  const ev = artifactEventFromStream({ event_type: "artifact_revision_created", sequence_no: 7, payload_json: {
    artifact_id: 12, project_id: 1, from_revision: 20, to_revision: 21, run_id: 1001,
    conversation_id: 88, summary: "Added 3 test cases",
    change_counts: { added: 3, updated: 0, deleted: 0, moved: 0 } } });
  assert.equal(ev.artifactId, 12);
  assert.equal(ev.toRevision, 21);
  assert.deepEqual(ev.changeCounts, { added: 3, updated: 0, deleted: 0, moved: 0 });
});

test("按 Artifact 过滤：其它 Artifact 事件忽略", () => {
  const state = initialState({ artifactId: 12, currentRevision: 20 });
  const other = artifactEventFromStream({ type: "artifact_revision_created", payload_json: { artifact_id: 99, from_revision: 5, to_revision: 6 } });
  assert.equal(applyArtifactEvent(state, other), null);
});

test("Revision Guard：to<=当前 revision 的重复/重放忽略", () => {
  const state = initialState({ artifactId: 12, currentRevision: 20 });
  const dup = artifactEventFromStream({ type: "artifact_revision_created", payload_json: { artifact_id: 12, from_revision: 19, to_revision: 20 } });
  assert.equal(applyArtifactEvent(state, dup), null);
});

test("rapid 21/22/23 coalesce 最终=23，markRefreshed 防 stale", () => {
  let state = initialState({ artifactId: 12, currentRevision: 20 });
  for (const to of [21, 22, 23]) {
    const ev = artifactEventFromStream({ type: "artifact_revision_created", sequence_no: to, payload_json: { artifact_id: 12, from_revision: to - 1, to_revision: to, run_id: 1001, change_counts: { added: 1, updated: 0, deleted: 0, moved: 0 } } });
    const next = applyArtifactEvent(state, ev);
    assert.notEqual(next, null);
    state = next;
  }
  assert.equal(state.targetRevision, 23);
  // 慢的 21 响应不能把 target 拉低
  const stale = applyArtifactEvent(initialState({ artifactId: 12, currentRevision: 20 }), artifactEventFromStream({ type: "artifact_revision_created", sequence_no: 21, payload_json: { artifact_id: 12, from_revision: 20, to_revision: 21 } }));
  assert.equal(stale.targetRevision, 21);
  // 已刷新到 22（还差 23）→ 保持 pending；刷新到 23 → 收敛
  let after22 = markRefreshed({ ...state, currentRevision: 20 }, 22);
  assert.equal(after22.pending, true);
  const done = markRefreshed(after22, 23);
  assert.equal(done.pending, false);
  assert.equal(done.targetRevision, 23);
});

test("Editor baseRevision 保存与 realtime 不覆盖 Draft", () => {
  const editor = openEditorWithBase({ nodeId: 5, kind: "test_case", baseRevision: 20, currentRevision: 20, content: "v1" });
  const touched = markDraftTouched(editor);
  const afterAgent = applyAgentRevision(touched, 21);
  assert.equal(afterAgent.content, "v1"); // draft 保留
  assert.equal(expectedRevisionForSave(afterAgent), 20); // 保存仍用 baseRevision → 后端 409
  const warn = shouldWarnConcurrency(afterAgent, 21);
  assert.notEqual(warn, null);
  assert.match(warn.message, /Revision 20/);
});

test("Change Summary 按 run 聚合、不混 run", () => {
  const mk = (runId, artifactId, from, to, added) => ({
    runId, artifactId, fromRevision: from, toRevision: to, changeCounts: { added, updated: 0, deleted: 0, moved: 0 },
  });
  const runs = aggregateByRun([
    mk(1001, 12, 20, 21, 3),
    mk(1001, 12, 21, 22, 1),
    mk(1002, 12, 22, 23, 2),
  ]);
  const run1 = runs.find((r) => r.runId === 1001);
  assert.equal(run1.revisionCount, 2);
  assert.equal(run1.toRevision, 22);
  assert.equal(run1.fromRevision, 20);
  assert.equal(run1.changeCounts.added, 4);
  assert.equal(runs.find((r) => r.runId === 1002).changeCounts.added, 2); // 不混
  const card = summaryCard(run1, 12);
  assert.equal(card.body, "新增 4 条用例");
  assert.match(card.revisionRange, /20 → 22/);
  assert.equal(summaryLabel({ updated: 1 }), "更新 1 条用例");
});

test("Mismatch 安全：普通 continuation 允许；资产指令阻止", () => {
  assert.equal(isLikelyPlainContinuation("继续解释你刚才说的第二点"), true);
  assert.equal(isLikelyPlainContinuation("为什么这么设计？"), true);
  assert.equal(looksLikeAssetDirective("给登录模块补三个边界"), true);
  const blocked = planSubmitWithMismatch({ content: "给登录模块补三个边界", mismatch: true, messageNeedsWorkspaceContext: false });
  assert.equal(blocked.allowed, false);
  assert.equal(blocked.reason, "mismatch_asset");
  assert.match(blocked.hint, /新建对话或切回对应项目/);
  const allowed = planSubmitWithMismatch({ content: "继续解释第二点", mismatch: true, messageNeedsWorkspaceContext: false });
  assert.equal(allowed.allowed, true);
});

import { agentArtifactNavigation, diffIntentFromArtifactEvent } from "../src/components/v2-workspace/agentArtifactNavigation.js";

test("aggregate 保留 artifact.projectId（供 View Changes 校验）", () => {
  const runs = aggregateByRun([{ runId: 9, artifactId: 12, projectId: 3, fromRevision: 20, toRevision: 21, changeCounts: { added: 1, updated: 0, deleted: 0, moved: 0 } }]);
  assert.equal(runs[0].artifacts[0].projectId, 3);
});

test("View Changes 意图：由 compact 事件构造，字段缺失不产生意图", () => {
  const intent = diffIntentFromArtifactEvent({ artifactId: 12, projectId: 1, fromRevision: 20, toRevision: 23 });
  assert.deepEqual(intent, { page: "functionCases", projectId: 1, artifactId: 12, fromRevision: 20, toRevision: 23 });
  assert.equal(diffIntentFromArtifactEvent({ artifactId: 12, fromRevision: null, toRevision: 23 }), null);
});

test("navigation 桥：publish/subscribe/clear 与单次消费语义", () => {
  const seen = [];
  const unsubscribe = agentArtifactNavigation.subscribe((intent) => seen.push(intent));
  const intent = { page: "functionCases", projectId: 1, artifactId: 12, fromRevision: 20, toRevision: 23 };
  agentArtifactNavigation.publish(intent);
  assert.deepEqual(seen, [intent]);
  assert.equal(agentArtifactNavigation.getPending(), intent);
  agentArtifactNavigation.clear();
  assert.equal(agentArtifactNavigation.getPending(), null);
  unsubscribe();
  agentArtifactNavigation.publish(intent);
  assert.equal(seen.length, 1);
  agentArtifactNavigation.clear();
});
