import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildMindMap, buildMindMapView, buildNodeIndex, byOrder, flattenTree, selectMindMapScope,
} from "../src/components/v2-workspace/mindMapModel.js";
import {
  focusFailureMessage, isTreeLoadStale, shouldApplyResponse,
} from "../src/components/v2-workspace/artifactWorkspaceModel.js";

function node(id, node_type, title, children = [], order_key = 1) {
  return { id, node_type, title, order_key, parent_id: null, content: null,
    source_refs: null, children };
}

function sampleTree() {
  // root → [group(功能, order=1), group(状态, order=2)]
  //   功能 → p1(正常登录)[tc1,tc2] + p2(密码错误)
  //   状态 → p3(账号锁定)
  const tc1 = node(4, "test_case", "TC001");
  const tc2 = node(5, "test_case", "TC002");
  const p1 = node(3, "module", "正常登录", [tc1, tc2]);
  const p2 = node(6, "module", "密码错误");
  const p3 = node(7, "module", "账号锁定");
  const g1 = node(2, "module", "功能", [p1, p2], 1);
  const g2 = node(8, "module", "状态", [p3], 2);
  return node(1, "root", "登录测试", [g1, g2]);
}

test("Test1: tree → 正确的 nodes/edges", () => {
  const { nodes, edges } = buildMindMap(sampleTree());
  assert.equal(nodes.length, 8);
  assert.equal(edges.length, 7);
  assert.deepEqual(nodes.map((n) => n.nodeId), [1, 2, 3, 4, 5, 6, 8, 7]);
  assert.deepEqual(edges.map((e) => e.id), ["e1-2", "e2-3", "e3-4", "e3-5", "e2-6", "e1-8", "e8-7"]);
});

test("Test2: nested ordering 稳定（与插入顺序无关，按 order_key/id）", () => {
  // 故意把 children 打乱传入：buildMindMap 必须按 (order_key,id) 稳定输出
  const p2 = node(6, "module", "密码错误");
  const p1 = node(3, "module", "正常登录");
  const g1 = node(2, "module", "功能", [p2, p1], 1); // p2(6) 先于 p1(3)
  const root = node(1, "root", "登录测试", [g1]);
  const first = buildMindMap(root);
  const second = buildMindMap(root);
  assert.deepEqual(first, second); // 确定性（无随机）
  assert.deepEqual(first.nodes.map((n) => n.nodeId), [1, 2, 3, 6]);
  // flattenTree / byOrder 同样稳定
  assert.deepEqual(flattenTree(root).map((n) => n.id), [1, 2, 3, 6]);
  assert.equal(byOrder({ order_key: 5, id: 9 }, { order_key: 5, id: 3 }) > 0, true);
});

test("collapse: 折叠子树不进 nodes/edges，但保留计数", () => {
  const { nodes, edges } = buildMindMap(sampleTree(), [3]);
  const visibleIds = nodes.map((n) => n.nodeId);
  assert.ok(!visibleIds.includes(4) && !visibleIds.includes(5)); // TC001/TC002 被折叠隐藏
  assert.ok(visibleIds.includes(3));
  const p1 = nodes.find((n) => n.nodeId === 3);
  assert.equal(p1.collapsed, true);
  assert.equal(p1.hiddenDescendants, 2);
  assert.equal(edges.some((e) => e.target === "n3" || e.source === "n3"), true);
  assert.equal(edges.length, 5);
});

test("200+ 节点：render 数据一次树请求即可构造，id 稳定且布局确定性", () => {
  // 1 root + 8 modules + 40 submodules + 160 cases = 209
  const groups = Array.from({ length: 8 }, (_, gi) => {
    const points = Array.from({ length: 5 }, (_, pi) => {
      const cases = Array.from({ length: 4 }, (_, ci) =>
        node(30_000 + gi * 1000 + pi * 40 + ci, "test_case", `C${gi}-${pi}-${ci}`));
      return node(10_000 + gi * 100 + pi, "module", `P${gi}-${pi}`, cases);
    });
    return node(100 + gi, "module", `G${gi}`, points);
  });
  const root = node(1, "root", "大库", groups);
  const view = buildMindMapView(root, []);
  assert.equal(view.nodes.length, 209);
  assert.equal(view.edges.length, 208);
  const ids = new Set(view.nodes.map((n) => n.key));
  assert.equal(ids.size, 209, "node key 必须唯一且稳定对应 ArtifactNode.id");
  const index = buildNodeIndex(root);
  assert.equal(index.size, 209);
  // 左到右：层级决定 x；y 只负责纵向铺开叶子。
  for (const n of view.nodes) {
    const pos = view.positions.get(n.key);
    assert.ok(pos && Number.isFinite(pos.x) && Number.isFinite(pos.y));
  }
  const byLevel = new Map();
  for (const n of view.nodes) byLevel.set(n.key, n.level);
  assert.equal(view.positions.get("n1").x, 0);
  assert.equal(byLevel.get("n1"), 0);
  assert.equal([...view.positions.values()].every((p) => p.y >= 0), true);
  // 确定性：重复调用布局结果一致
  const again = buildMindMapView(root, []);
  assert.deepEqual(view.positions, again.positions);
});

test("MindMap scope: root 显示全部，子模块只显示自身和子用例", () => {
  const root = sampleTree();
  assert.equal(buildMindMap(selectMindMapScope(root, null)).nodes.length, 8);
  const scoped = selectMindMapScope(root, 3);
  assert.equal(scoped.id, 3);
  assert.deepEqual(buildMindMap(scoped).nodes.map((item) => item.nodeId), [3, 4, 5]);
});

test("race/409 纯逻辑：late response 丢弃；409 保留旧视图并给可读消息", () => {
  assert.equal(shouldApplyResponse({
    requestConversationId: 1, currentConversationId: 1, requestToken: 3, currentToken: 3,
  }), true);
  assert.equal(shouldApplyResponse({
    requestConversationId: 1, currentConversationId: 2, requestToken: 3, currentToken: 3,
  }), false, "会话已切换 → 丢弃");
  assert.equal(shouldApplyResponse({
    requestConversationId: 1, currentConversationId: 1, requestToken: 3, currentToken: 4,
  }), false, "发起后又有新请求 → 丢弃旧结果");

  assert.equal(isTreeLoadStale({
    requestKey: 1, currentKey: 1, requestSeq: 2, currentSeq: 2,
  }), false);
  assert.equal(isTreeLoadStale({
    requestKey: 1, currentKey: 1, requestSeq: 1, currentSeq: 2,
  }), true, "Artifact A→B→C：A 的旧请求不得覆盖 C");

  assert.equal(focusFailureMessage({ httpStatus: 409, detail: "正在运行，不能切换" }),
    "正在运行，不能切换");
  assert.equal(focusFailureMessage({ httpStatus: 409, detail: null }),
    "Agent 正在执行，请等待本轮完成后再切换测试资产。");
  assert.equal(focusFailureMessage({ httpStatus: 500, detail: null }),
    "切换测试资产失败，请稍后重试。");
});
