import { test } from "node:test";
import assert from "node:assert/strict";
import {
  editorToCaseOperations, moduleOps, moduleParentCandidates, normalizeEditorSteps, scopedRoot,
} from "../src/components/v2-workspace/caseEditorModel.js";

function node(id, node_type, title, children = []) {
  return { id, node_type, title, children, order_key: id };
}

const sampleRoot = node(1, "root", "功能", [
  node(10, "module", "登录", [
    node(100, "test_case", "TC1"),
    node(11, "module", "账号锁定"),
  ]),
  node(20, "module", "支付"),
]);

test("normalizeEditorSteps: 自动补号且唯一", () => {
  const steps = normalizeEditorSteps([{ action: "a" }, { action: "b" }, { step_no: 1, action: "c" }]);
  assert.deepEqual(steps.map((s) => s.step_no), [2, 3, 1]);
  assert.throws(() => normalizeEditorSteps([{ step_no: 2, action: "x" }, { step_no: 2, action: "y" }]),
    /step_no/);
});

test("editorToCaseOperations: create 用 parent module；update 只 patch title/content", () => {
  const create = editorToCaseOperations({
    create: true, moduleId: 10, nodeId: null, title: "新TC", sourceRefs: null,
    content: { preconditions: ["已登录"], priority: "P1", tags: [],
      steps: [{ action: "打开" }], expected_results: [] },
  });
  assert.equal(create.length, 1);
  assert.equal(create[0].operation_type, "add_node");
  assert.equal(create[0].parent_id, 10);
  assert.deepEqual(create[0].content.steps, [{ step_no: 1, action: "打开", data: null }]);
  const update = editorToCaseOperations({
    create: false, moduleId: 10, nodeId: 55, title: "改名", sourceRefs: null,
    content: { preconditions: [], priority: "P2", tags: [],
      steps: [], expected_results: [] },
  });
  assert.equal(update[0].operation_type, "update_node");
  assert.equal(update[0].target_node_id, 55);
  assert.deepEqual(update[0].patch.title, "改名");
});

test("moduleOps: create/rename/move/delete", () => {
  assert.equal(moduleOps({ kind: "create", parentId: 1, title: "M" })[0].parent_id, 1);
  assert.deepEqual(moduleOps({ kind: "rename", nodeId: 10, title: "新名" })[0].patch, { title: "新名" });
  assert.equal(moduleOps({ kind: "move", nodeId: 20, newParentId: 11 })[0].new_parent_id, 11);
  assert.equal(moduleOps({ kind: "delete", nodeId: 20 })[0].target_node_id, 20);
});

test("moduleParentCandidates: 排除自身子树", () => {
  const candidates = moduleParentCandidates(sampleRoot, 10);
  const ids = candidates.map((c) => c.id);
  assert.ok(ids.includes(20));
  assert.ok(!ids.includes(10) && !ids.includes(11));
});

test("scopedRoot: root/scope 切换保持同一视图源", () => {
  assert.equal(scopedRoot(sampleRoot, null), sampleRoot);
  assert.equal(scopedRoot(sampleRoot, 10).title, "登录");
  assert.equal(scopedRoot(sampleRoot, 99).title, "功能");
});
