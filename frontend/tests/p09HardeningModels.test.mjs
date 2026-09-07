import test from "node:test";
import assert from "node:assert/strict";
import { nextModuleMenu } from "../src/components/v2-workspace/moduleMenuModel.js";
import { paginateCases } from "../src/components/v2-workspace/casePaginationModel.js";
import { aggregateByRun, domainSummaryLabel, revisionLabel } from "../src/components/v2-workspace/artifactChangeSummaryModel.js";
import { toolDisplayName } from "../src/components/v2-chat/toolActivityModel.js";

test("父子孙 Module 菜单始终只有最后一个，空白和 Escape 关闭", () => {
  let open = nextModuleMenu(null, { type: "open", nodeId: 1 });
  open = nextModuleMenu(open, { type: "open", nodeId: 2 });
  assert.equal(open, 2);
  open = nextModuleMenu(open, { type: "open", nodeId: 3 });
  assert.equal(open, 3);
  assert.equal(nextModuleMenu(open, { type: "close" }), null);
  assert.equal(nextModuleMenu(3, { type: "escape" }), null);
});

test("45 条分页为 20/20/5，过滤和删除后 clamp", () => {
  const items = Array.from({ length: 45 }, (_, id) => ({ id }));
  assert.equal(paginateCases(items, 1, 20).items.length, 20);
  assert.equal(paginateCases(items, 2, 20).items.length, 20);
  assert.equal(paginateCases(items, 3, 20).items.length, 5);
  const filtered = items.filter((item) => item.id < 6);
  assert.deepEqual(paginateCases(filtered, 3, 20), {
    items: filtered, total: 6, page: 1, pageSize: 20, pageCount: 1,
  });
  assert.equal(paginateCases(items.slice(0, 39), 3, 20).page, 2);
});

test("Change Summary 合并 revision/diff，恢复范围且不双计数", () => {
  const base = { runId: 7, artifactId: 9, projectId: 1, fromRevision: 10,
    toRevision: 11, changeCounts: { added: 3, updated: 0, deleted: 0, moved: 0 },
    domainCounts: { modules_added: 1, cases_added: 2 } };
  const [run] = aggregateByRun([base, { ...base }]);
  assert.equal(run.revisionCount, 1);
  assert.equal(run.changeCounts.added, 3);
  assert.equal(domainSummaryLabel(run.artifacts[0].domainCounts, run.changeCounts),
    "新增 1 个模块，新增 2 条用例");
  assert.equal(revisionLabel(run.fromRevision, run.toRevision), "版本 10 → 11");
  assert.equal(revisionLabel(null, 11), "版本 11");
  assert.doesNotMatch(revisionLabel(null, 11), /\?/);
});

test("内部工具名映射为产品文案", () => {
  assert.equal(toolDisplayName("batch_apply_artifact_operations"), "批量修改测试资产");
  assert.equal(toolDisplayName("read_artifact_outline"), "读取测试结构");
  assert.equal(toolDisplayName("unknown_internal_tool"), "使用工具");
});
