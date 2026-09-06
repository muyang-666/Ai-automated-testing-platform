// P09.1 功能用例页纯视图模型（无 React/DOM 依赖）：
// Module Tree 与 Case List 都从同一份 Artifact tree 派生（无第二份数据源）。
import { byOrder, buildNodeIndex } from "./mindMapModel.js";
import { formatCaseNumber } from "./caseNumber.js";

// Module Tree：只含 root/module 容器，test_case 不出现在左侧树。
// 返回 { id, title, children } 嵌套；树包含 root 自身（title 用于"全部模块"）。
export function buildModuleTree(root) {
  const modules = (node) => {
    const children = (node?.children || []).filter((c) => c.node_type === "module").sort(byOrder);
    return {
      id: node.id,
      node_type: node.node_type,
      title: node.title,
      children: children.map(modules),
    };
  };
  return root ? modules(root) : null;
}

// Case List 行（含 scope）：scopeNodeId=module 时只取该 module subtree 的 cases。
// modulePath 为祖先 module 标题链（含父 module）。
export function collectScopeCases(root, scopeNodeId = null) {
  const rows = [];
  if (!root) return rows;
  const scopeRoot = scopeNodeId != null ? buildNodeIndex(root).get(scopeNodeId) || root : root;
  const collect = (node, modulePath) => {
    if (node.node_type === "test_case") {
      rows.push({
        nodeId: node.id,
        title: node.title,
        moduleId: modulePath[modulePath.length - 1]?.id ?? null,
        modulePath: modulePath.map((m) => m.title),
        caseNumber: formatCaseNumber(node.id),
        priority: node.content?.priority ?? "P1",
        tags: node.content?.tags ?? [],
        preconditions: node.content?.preconditions ?? [],
        steps: node.content?.steps ?? [],
        expectedResults: node.content?.expected_results ?? [],
        sourceRefs: node.source_refs ?? [],
      });
    }
    for (const child of (node.children || []).sort(byOrder)) {
      if (child.node_type === "module") collect(child, [...modulePath, child]);
      else collect(child, modulePath);
    }
  };
  if (scopeNodeId == null || scopeNodeId === root.id) {
    collect(root, []);
  } else {
    // 从 scope module 开始（其子 module 也在范围内；不含 scope 本身作为 case）
    collect(scopeRoot, scopeRoot.node_type === "module" ? [scopeRoot] : []);
  }
  return rows;
}

// 文本摘要（表格列只放摘要）
export function stepsSummary(steps = []) {
  return steps.map((s, i) => `${s.step_no ?? i + 1}. ${s.action || ""}`).join("\n");
}

export function expectedSummary(items = []) {
  const texts = items.map((item) => (typeof item === "string" ? item : item?.expected ?? ""));
  return texts.join("\n");
}
