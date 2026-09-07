// P09.1 MindMap 只读视图纯函数（无 DOM/React 依赖，node:test 可测）。
//
// 核心原则：Artifact Tree = Source of Truth；MindMap nodes/edges = derived view。
// 本模块绝不产生 ArtifactOperation / Revision，也不把坐标写回后端——
// 坐标/collapse 属于 UI View State（useArtifactViewState 管理，session 内有效）。
//
// 用例平台式左到右树：Project/Root → Module → Case。

export const LAYOUT = {
  direction: "horizontal",
  nodeWidth: 220,
  nodeHeight: 76,
  levelGap: 340,
  leafGap: 14,
};

const CASE_DETAIL_SPECS = [
  { kind: "preconditions", label: "前置" },
  { kind: "steps", label: "步骤" },
  { kind: "expected", label: "预期" },
];

export function caseDetailText(node, kind) {
  const content = node?.content && typeof node.content === "object" ? node.content : {};
  if (kind === "preconditions") return (content.preconditions || []).filter(Boolean).join("\n");
  if (kind === "steps") return (content.steps || []).map((step, index) => (
    `${step?.step_no ?? index + 1}. ${step?.action || ""}`
  )).filter((line) => !/^\d+\.\s*$/.test(line)).join("\n");
  if (kind === "expected") return (content.expected_results || []).map((item) => (
    typeof item === "string" ? item : item?.expected || ""
  )).filter(Boolean).join("\n");
  return "";
}

function displayUnits(text) {
  return [...String(text || "")].reduce((sum, char) => (
    sum + (char.codePointAt(0) > 255 ? 2 : 1)
  ), 0);
}

export function caseDetailMetrics(text) {
  const lines = String(text || "").split("\n");
  const longest = Math.max(1, ...lines.map(displayUnits));
  const width = Math.min(300, Math.max(188, 34 + longest * 6));
  const contentWidth = Math.max(120, width - 24);
  const wrappedLines = lines.reduce((sum, line) => (
    sum + Math.max(1, Math.ceil((displayUnits(line) * 6) / contentWidth))
  ), 0);
  const height = Math.max(48, 18 + wrappedLines * 17);
  return { width, height };
}

export function caseNameMetrics(title) {
  // 202px 卡片扣除左右 padding、priority 与 gap 后，名称约有 132px 可用。
  // displayUnits 同时兼顾中英文宽度，卡片高度严格落在 1/2/3 行三个档位。
  const lineCount = Math.min(3, Math.max(1, Math.ceil(displayUnits(title) / 24)));
  return { lineCount, height: 34 + (lineCount - 1) * 16 };
}

// ── 通用树辅助 ──

// 深度优先前序展开（children 已按 (order_key,id) 稳定排序，这里再排一次兜底）
export function flattenTree(root) {
  const result = [];
  const walk = (node) => {
    if (!node) return;
    result.push(node);
    for (const child of [...(node.children || [])].sort(byOrder)) walk(child);
  };
  walk(root);
  return result;
}

export function byOrder(a, b) {
  return (a.order_key ?? 0) - (b.order_key ?? 0) || a.id - b.id;
}

export function totalNodeCount(root) {
  return root ? flattenTree(root).length : 0;
}

export function directChildrenOf(node) {
  return [...(node?.children || [])].sort(byOrder);
}

// id → node 全量索引（含完整 content，供 Inspector 使用；与折叠无关）
export function buildNodeIndex(root) {
  const index = new Map();
  for (const node of flattenTree(root)) index.set(node.id, node);
  return index;
}

export function selectMindMapScope(root, scopeId) {
  if (!root || scopeId == null || scopeId === root.id) return root;
  return buildNodeIndex(root).get(scopeId) || root;
}

// ── Tree → MindMap 派生（buildMindMap） ──

// 返回 { nodes, edges }；nodes 为可见节点（祖先被折叠则整棵隐藏），
// node.key = `n${id}`、edge.id = `e${parentId}-${id}`——id 稳定对应 ArtifactNode.id，
// 绝不用 Math.random/uuid（选择/布局/后续 P09.2 编辑依赖稳定 key）。
export function buildMindMap(root, collapsedIds = []) {
  const collapsed = new Set(collapsedIds);
  const nodes = [];
  const edges = [];
  if (!root) return { nodes, edges };

  // 折叠时隐藏的子孙总数 = 整棵子树大小 - 1（与内部是否另有折叠无关）
  const subtreeSize = (node) => 1 + (node.children || []).reduce(
    (sum, child) => sum + subtreeSize(child), 0);

  const walk = (node, parentId, level) => {
    const children = directChildrenOf(node);
    const isCollapsed = collapsed.has(node.id);
    const caseMetrics = node.node_type === "test_case" ? caseNameMetrics(node.title) : null;
    const renderedNode = {
      key: `n${node.id}`,
      nodeId: node.id,
      node_type: node.node_type,
      title: node.title,
      priority: node.node_type === "test_case" ? node.content?.priority ?? "P1" : null,
      order_key: node.order_key,
      parentId: parentId ?? null,
      parentKey: parentId != null ? `n${parentId}` : null,
      level,
      childrenCount: children.length,
      collapsed: isCollapsed,
      caseHeight: caseMetrics?.height ?? null,
      layoutHeight: caseMetrics?.height ?? 58,
      hiddenDescendants: isCollapsed ? subtreeSize(node) - 1 : 0,
    };
    nodes.push(renderedNode);
    if (parentId != null) {
      edges.push({ id: `e${parentId}-${node.id}`, source: `n${parentId}`,
        target: `n${node.id}`, edgeKind: "hierarchy" });
    }
    if (!isCollapsed) {
      for (const child of children) walk(child, node.id, level + 1);
    }
    if (node.node_type === "test_case") {
      const details = CASE_DETAIL_SPECS.map((spec) => {
        const text = caseDetailText(node, spec.kind);
        return { ...spec, text, metrics: caseDetailMetrics(text) };
      }).filter((detail) => detail.text.trim());
      const rowHeight = Math.max(
        LAYOUT.nodeHeight, caseMetrics?.height ?? 0,
        ...details.map((detail) => detail.metrics.height),
      );
      renderedNode.rowHeight = rowHeight;
      let parentKey = `n${node.id}`;
      details.forEach((detail, index) => {
        const spec = detail;
        const key = `d${node.id}-${spec.kind}`;
        nodes.push({
          key,
          nodeId: null,
          node_type: "case_detail",
          title: spec.label,
          detailKind: spec.kind,
          detailText: detail.text,
          detailWidth: detail.metrics.width,
          detailHeight: detail.metrics.height,
          layoutHeight: detail.metrics.height,
          rowHeight,
          ownerCaseId: node.id,
          order_key: index,
          parentId: null,
          parentKey,
          level: level + index + 1,
          childrenCount: index < CASE_DETAIL_SPECS.length - 1 ? 1 : 0,
          collapsed: false,
          hiddenDescendants: 0,
        });
        edges.push({ id: `ed${node.id}-${spec.kind}`, source: parentKey,
          target: key, edgeKind: "detail" });
        parentKey = key;
      });
    }
  };
  walk(root, null, 0);
  return { nodes, edges };
}

// ── 布局（左到右，确定性递归；collapsed 子树按单个叶子占位） ──

export function layoutMindMap(nodes) {
  // 输入为 buildMindMap 输出的可见节点（前序）。
  // 1) 先按前序确定每棵子树的叶子宽度（折叠节点宽度=1）
  const childrenByKey = new Map();
  const nodeByKey = new Map(nodes.map((node) => [node.key, node]));
  for (const node of nodes) {
    const parentKey = node.parentKey ?? (node.parentId != null ? `n${node.parentId}` : null);
    if (parentKey != null) {
      const list = childrenByKey.get(parentKey) || [];
      list.push(node);
      childrenByKey.set(parentKey, list);
    }
  }
  // 叶子从上到下分配 y，内部节点取首尾子节点中点。
  const positions = new Map();
  let cursorY = 0;
  const heightOf = (key) => nodeByKey.get(key)?.layoutHeight ?? 58;
  const assign = (key, level) => {
    const current = nodeByKey.get(key);
    const children = childrenByKey.get(key) || [];
    if (!children.length) {
      const rowHeight = current?.rowHeight ?? LAYOUT.nodeHeight;
      const centerY = cursorY + rowHeight / 2;
      positions.set(key, { x: level * LAYOUT.levelGap, y: centerY - heightOf(key) / 2 });
      cursorY += rowHeight + LAYOUT.leafGap;
      return;
    }
    for (const child of children) assign(child.key, level + 1);
    const first = positions.get(children[0].key);
    const last = positions.get(children[children.length - 1].key);
    const firstCenter = first.y + heightOf(children[0].key) / 2;
    const lastCenter = last.y + heightOf(children[children.length - 1].key) / 2;
    const centerY = (firstCenter + lastCenter) / 2;
    positions.set(key, { x: level * LAYOUT.levelGap, y: centerY - heightOf(key) / 2 });
  };
  if (nodes.length) assign(nodes[0].key, 0);
  return positions;
}

// 组合入口：tree + collapsed → { nodes, edges, positions, index }
export function buildMindMapView(root, collapsedIds = []) {
  const { nodes, edges } = buildMindMap(root, collapsedIds);
  const positions = layoutMindMap(nodes);
  const index = buildNodeIndex(root);
  return { nodes, edges, positions, index };
}

// 简化文本字段（MindMap 只显示短信息；详细字段交给 Inspector）
export function shortTitle(node) {
  const title = node?.title || "";
  return title.length > 28 ? `${title.slice(0, 27)}…` : title;
}

export function mindMapContextMenuItems(nodeType, editable = true) {
  if (!editable) return [];
  if (nodeType === "module") return [
    { key: "add_module", label: "新增模块" },
    { key: "add_case", label: "新增用例" },
    { key: "delete", label: "删除模块", danger: true },
  ];
  if (nodeType === "test_case") return [
    { key: "delete", label: "删除", danger: true },
  ];
  return [];
}
