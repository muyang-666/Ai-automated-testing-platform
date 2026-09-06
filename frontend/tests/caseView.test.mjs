import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildModuleTree, collectScopeCases, expectedSummary, stepsSummary,
} from "../src/components/v2-workspace/caseView.js";
import { formatCaseNumber } from "../src/components/v2-workspace/caseNumber.js";

function node(id, node_type, title, children = []) {
  return { id, node_type, title, order_key: id, parent_id: null, content: null,
    source_refs: null, children };
}

function sample() {
  const tc1 = node(11, "test_case", "TC-A", []);
  tc1.content = { priority: "P0", tags: ["正常"],
    preconditions: ["已注册"],
    steps: [{ step_no: 1, action: "打开页" }],
    expected_results: [{ step_no: 1, expected: "成功" }] };
  tc1.source_refs = [{ source_type: "requirement", source_id: "1" }];
  const tc2 = node(12, "test_case", "TC-B", []);
  tc2.content = { priority: "P2", tags: [], preconditions: [],
    steps: [{ step_no: 1, action: "操作" }], expected_results: [] };
  const m2 = node(5, "module", "子模块", [tc2]);
  const m1 = node(3, "module", "登录", [tc1, m2]);
  const root = node(1, "root", "功能", [m1]);
  return root;
}

test("Module Tree：只含 module，不含 test_case；嵌套稳定", () => {
  const tree = buildModuleTree(sample());
  assert.equal(tree.id, 1);
  assert.deepEqual(tree.children.map((m) => m.title), ["登录"]);
  assert.deepEqual(tree.children[0].children.map((m) => m.title), ["子模块"]);
  assert.equal(tree.children[0].children[0].children.length, 0);
});

test("collectScopeCases：scope=全部 得到全部用例；scope=module 得到其子树用例", () => {
  const all = collectScopeCases(sample(), null);
  assert.equal(all.length, 2);
  const login = collectScopeCases(sample(), 3);
  assert.equal(login.length, 2);
  assert.deepEqual(login.map((r) => r.title).sort(), ["TC-A", "TC-B"]);
  const child = collectScopeCases(sample(), 5);
  assert.equal(child.length, 1);
  assert.equal(child[0].title, "TC-B");
});

test("Case 行字段与 modulePath/编号派生", () => {
  const [row] = collectScopeCases(sample(), 3).filter((r) => r.nodeId === 11);
  assert.deepEqual(row.modulePath, ["登录"]);
  assert.equal(row.priority, "P0");
  assert.equal(formatCaseNumber(11), "TC-000011");
  assert.equal(row.caseNumber, "TC-000011");
  assert.equal(row.sourceRefs[0].source_id, "1");
});

test("摘要函数：steps/expected 结构化输出", () => {
  assert.equal(stepsSummary([{ step_no: 1, action: "打开页" }, { action: "点登录" }]),
    "1. 打开页\n2. 点登录");
  assert.equal(expectedSummary([{ step_no: 1, expected: "成功" }, "整体"]), "成功\n整体");
});
