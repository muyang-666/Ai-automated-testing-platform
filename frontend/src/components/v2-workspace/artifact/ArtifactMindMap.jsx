// P09 MindMap（React Flow）。Artifact Tree = Source of Truth；节点/布局仍是纯派生视图，
// 编辑动作只向 FunctionCasePage 发出意图，实际写入继续复用既有 Operation/Revision 链路。
import { useEffect, useMemo, useState } from "react";
import { Dropdown } from "antd";
import {
  Background, Controls, Handle, Position, ReactFlow, useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "../v2Workspace.css";
import {
  buildMindMapView, mindMapContextMenuItems, shortTitle,
} from "../mindMapModel";

function MindMapNodeView({ data, selected }) {
  const { node_type: type, title, hiddenDescendants, collapsed } = data;
  if (type === "case_detail") {
    return (
      <div className={`v2w-node v2w-node-case-detail is-${data.detailKind}`}
        style={{ width: data.detailWidth, minHeight: data.detailHeight }}>
        <Handle type="target" position={Position.Left}
          className="v2w-node-handle v2w-node-detail-target" />
        <div className="v2w-node-detail-label">{title}</div>
        <div className="v2w-node-detail-text" title={data.detailText}>{data.detailText}</div>
        {data.detailKind !== "expected" ? (
          <Handle type="source" position={Position.Right} className="v2w-node-handle" />
        ) : null}
      </div>
    );
  }
  const node = (
    <div className={`v2w-node v2w-node-${type}${selected ? " is-selected" : ""}`}
      data-selected={selected || undefined}
      style={type === "test_case" ? { minHeight: data.caseHeight } : undefined}>
      <Handle type="target" position={Position.Left} className="v2w-node-handle" />
      {type === "test_case" ? (
        <div className="v2w-node-case-main">
          <div className="v2w-node-title" title={title}>{title}</div>
          <span className={`v2w-node-priority is-${String(data.priority || "P1").toLowerCase()}`}>
            {data.priority || "P1"}
          </span>
        </div>
      ) : (
        <>
          <div className="v2w-node-title" title={title}>{shortTitle({ title })}</div>
          <div className="v2w-node-meta">
            <span>{type === "root" ? "项目" : "模块"}
              {collapsed && hiddenDescendants > 0 ? ` · +${hiddenDescendants}` : ""}</span>
            {type === "module" && data.hasChildren ? (
              <button type="button" className="v2w-node-collapse"
                aria-label={collapsed ? `展开${title}` : `折叠${title}`}
                onClick={(event) => { event.stopPropagation(); data.onToggleCollapse?.(); }}
                onDoubleClick={(event) => event.stopPropagation()}>
                {collapsed ? "展开" : "折叠"}
              </button>
            ) : null}
          </div>
        </>
      )}
      <Handle type="source" position={Position.Right} className="v2w-node-handle" />
    </div>
  );
  if (!data.menuItems?.length) return node;
  return (
    <Dropdown trigger={["contextMenu"]} open={data.menuOpen}
      onOpenChange={data.onMenuOpenChange}
      menu={{ items: data.menuItems, onClick: ({ key }) => data.onMenuAction?.(key) }}>
      {node}
    </Dropdown>
  );
}

const NODE_TYPES = { artifact: MindMapNodeView };

// 视图稳定：node key = `n${ArtifactNode.id}`、edge key = `e{parent}-{child}`，
// 每次 render 不做随机生成；positions 由确定性布局函数计算。
export default function ArtifactMindMap({
  tree, collapsedIds, selectedNodeId, onSelect, onToggleCollapse, onEditCase,
  onRenameNode, onCreateModule, onCreateCase, onDeleteNode, editable = false,
  artifactKey, treeNonce,
}) {
  const { fitView } = useReactFlow();
  const [openMenuNodeId, setOpenMenuNodeId] = useState(null);
  const root = tree?.root ?? null;
  const view = useMemo(
    () => buildMindMapView(root, collapsedIds),
    [root, collapsedIds],
  );

  const flowNodes = useMemo(() => view.nodes.map((node) => {
    const menuItems = mindMapContextMenuItems(node.node_type, editable);
    return {
      id: node.key,
      type: "artifact",
      position: view.positions.get(node.key) || { x: 0, y: 0 },
      data: {
        nodeId: node.nodeId,
        node_type: node.node_type,
        title: node.title,
        priority: node.priority,
        caseHeight: node.caseHeight,
        detailKind: node.detailKind,
        detailText: node.detailText,
        detailWidth: node.detailWidth,
        detailHeight: node.detailHeight,
        collapsed: node.collapsed,
        hiddenDescendants: node.hiddenDescendants,
        hasChildren: node.childrenCount > 0,
        menuItems,
        menuOpen: openMenuNodeId === node.nodeId,
        onMenuOpenChange: (open) => setOpenMenuNodeId((current) => (
          open ? node.nodeId : current === node.nodeId ? null : current
        )),
        onMenuAction: (key) => {
          setOpenMenuNodeId(null);
          if (key === "add_module") onCreateModule?.(node.nodeId);
          if (key === "add_case") onCreateCase?.(node.nodeId);
          if (key === "delete") onDeleteNode?.(node.nodeId);
        },
        onToggleCollapse: () => onToggleCollapse?.(node.nodeId),
      },
      selected: node.nodeId === selectedNodeId,
      selectable: node.node_type !== "case_detail",
      draggable: node.node_type !== "case_detail",
    };
  }), [
    editable, onCreateCase, onCreateModule, onDeleteNode, onToggleCollapse,
    openMenuNodeId, selectedNodeId, view,
  ]);
  const flowEdges = useMemo(() => view.edges.map((edge) => ({
    id: edge.id, source: edge.source, target: edge.target,
    type: edge.edgeKind === "detail" ? "straight" : "smoothstep",
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
        onPaneClick={() => setOpenMenuNodeId(null)}
        onNodeClick={(_, node) => {
          if (node.data.node_type === "case_detail") return;
          setOpenMenuNodeId(null);
          onSelect?.(node.data.nodeId);
          if (node.data.node_type === "test_case") onEditCase?.(node.data.nodeId);
        }}
        onNodeDoubleClick={(event, node) => {
          if (node.data.node_type === "case_detail") return;
          event.preventDefault();
          event.stopPropagation();
          setOpenMenuNodeId(null);
          onSelect?.(node.data.nodeId);
          onRenameNode?.(node.data.nodeId);
        }}
      >
        <Background gap={22} color="#eceff1" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
