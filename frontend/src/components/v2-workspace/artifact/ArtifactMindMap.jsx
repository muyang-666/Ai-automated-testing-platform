// P09.1 只读 MindMap（React Flow）。Artifact Tree = Source of Truth，
// 本组件只消费 buildMindMapView 派生的 nodes/edges/positions；无任何写回。
import { useEffect, useMemo } from "react";
import {
  Background, Controls, Handle, Position, ReactFlow, useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "../v2Workspace.css";
import { buildMindMapView, shortTitle } from "../mindMapModel";
import { formatCaseNumber } from "../caseNumber";

function MindMapNodeView({ data, selected }) {
  const { node_type: type, title, hiddenDescendants, collapsed } = data;
  return (
    <div className={`v2w-node v2w-node-${type}${selected ? " is-selected" : ""}`}
      data-selected={selected || undefined}>
      <Handle type="target" position={Position.Left} className="v2w-node-handle" />
      <div className="v2w-node-title" title={title}>{shortTitle({ title })}</div>
      <div className="v2w-node-meta">
        {type === "test_case" ? formatCaseNumber(data.nodeId) : type === "root" ? "项目" : "模块"}
        {collapsed && hiddenDescendants > 0 ? ` · +${hiddenDescendants}` : ""}
      </div>
      <Handle type="source" position={Position.Right} className="v2w-node-handle" />
    </div>
  );
}

const NODE_TYPES = { artifact: MindMapNodeView };

// 视图稳定：node key = `n${ArtifactNode.id}`、edge key = `e{parent}-{child}`，
// 每次 render 不做随机生成；positions 由确定性布局函数计算。
export default function ArtifactMindMap({
  tree, collapsedIds, selectedNodeId, onSelect, onToggleCollapse, artifactKey, treeNonce,
}) {
  const { fitView } = useReactFlow();
  const root = tree?.root ?? null;
  const view = useMemo(
    () => buildMindMapView(root, collapsedIds),
    [root, collapsedIds],
  );

  const flowNodes = useMemo(() => view.nodes.map((node) => ({
    id: node.key,
    type: "artifact",
    position: view.positions.get(node.key) || { x: 0, y: 0 },
    data: {
      nodeId: node.nodeId,
      node_type: node.node_type,
      title: node.title,
      collapsed: node.collapsed,
      hiddenDescendants: node.hiddenDescendants,
    },
    selected: node.nodeId === selectedNodeId,
  })), [view, selectedNodeId]);
  const flowEdges = useMemo(() => view.edges.map((edge) => ({
    id: edge.id, source: edge.source, target: edge.target, type: "smoothstep",
  })), [view]);

  // fit view：仅首次打开/切换 Artifact/创建新 Artifact/手动刷新后（treeNonce 变化）。
  // 不做 Chat streaming 时的自动 fit。
  const hasNodes = flowNodes.length > 0;
  useEffect(() => {
    if (!hasNodes || artifactKey == null) return;
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.18, duration: 260, maxZoom: 1 });
    }, 30);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactKey, treeNonce, hasNodes]);

  if (!hasNodes) {
    return <div className="v2w-mindmap-empty">当前项目暂无测试模块</div>;
  }

  return (
    <div className="v2w-mindmap">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={NODE_TYPES}
        nodesConnectable={false}
        elementsSelectable
        fitView={false}
        minZoom={0.15}
        maxZoom={2.2}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onSelect(node.data.nodeId)}
        onNodeDoubleClick={(_, node) => onToggleCollapse(node.data.nodeId)}
      >
        <Background gap={22} color="#eceff1" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
