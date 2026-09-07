// P09.1 MindMap 只读视图纯函数（无 DOM/React 依赖，node:test 可测）。
//
// 核心原则：Artifact Tree = Source of Truth；MindMap nodes/edges = derived view。
// 本模块绝不产生 ArtifactOperation / Revision，也不把坐标写回后端——
// 坐标/collapse 属于 UI View State（useArtifactViewState 管理，session 内有效）。
//
// 用例平台式左到右树：Project/Root → Module → Case。

export const LAYOUT = {
  direction: "horizontal",
  nodeWidth: 184,
  nodeHeight: 58,
  levelGap: 236,
  leafGap: 18,
};

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
    nodes.push({
      key: `n${node.id}`,
      nodeId: node.id,
      node_type: node.node_type,
      title: node.title,
      order_key: node.order_key,
      parentId: parentId ?? null,
      level,
      childrenCount: children.length,
      collapsed: isCollapsed,
      hiddenDescendants: isCollapsed ? subtreeSize(node) - 1 : 0,
    });
    if (parentId != null) {
      edges.push({ id: `e${parentId}-${node.id}`, source: `n${parentId}`, target: `n${node.id}` });
    }
    if (!isCollapsed) {
      for (const child of children) walk(child, node.id, level + 1);
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
  for (const node of nodes) {
    if (node.parentId != null) {
      const list = childrenByKey.get(`n${node.parentId}`) || [];
      list.push(node);
      childrenByKey.set(`n${node.parentId}`, list);
    }
  }
  // 叶子从上到下分配 y，内部节点取首尾子节点中点。
  const positions = new Map();
  let cursor = 0;
  const assign = (key, level) => {
    const children = childrenByKey.get(key) || [];
    const unit = LAYOUT.nodeHeight + LAYOUT.leafGap;
    if (!children.length) {
      positions.set(key, { x: level * LAYOUT.levelGap, y: cursor * unit });
      cursor += 1;
      return;
    }
    for (const child of children) assign(child.key, level + 1);
    const first = positions.get(children[0].key);
    const last = positions.get(children[children.length - 1].key);
    positions.set(key, { x: level * LAYOUT.levelGap, y: (first.y + last.y) / 2 });
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
