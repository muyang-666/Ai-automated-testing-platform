// P09.2 FunctionCasePage：Module/Case 编辑 + List/MindMap + History/Diff/Undo/Restore + Conflict。
// 所有人工写操作 → /operations → Artifact Service → Revision；本页只是 View + 编排。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button, Card, Drawer, Dropdown, Empty, Input, Modal, Select, Space,
  Table, Tag, Tree, Typography,
} from "antd";
import { ReactFlowProvider } from "@xyflow/react";
import { getProjectList } from "../api/project";
import {
  applyArtifactOperations, ensureProjectArtifact, getArtifact, getArtifactDiff,
  getArtifactRevisions, getArtifactTree, listArtifacts, restoreArtifact, undoArtifact,
} from "../api/testArtifact";
import ArtifactMindMap from "../components/v2-workspace/artifact/ArtifactMindMap";
import * as caseEditorModel from "../components/v2-workspace/caseEditorModel.js";
import {
  collectScopeCases, buildModuleTree, expectedSummary, stepsSummary,
} from "../components/v2-workspace/caseView";
import { formatCaseNumber } from "../components/v2-workspace/caseNumber";
import { buildNodeIndex } from "../components/v2-workspace/mindMapModel";
import { getStoredProjectId, resolveProjectId, storeProjectId } from "../utils/projectSelection";
import { isViewerOnly } from "../utils/authPermissions";
import useFunctionalWorkspace from "../components/v2-workspace/useFunctionalWorkspace.js";
import { deriveFunctionalWorkspace } from "../components/v2-workspace/functionalWorkspaceModel.js";

const PRIORITY_COLOR = { P0: "red", P1: "orange", P2: "gold", P3: "default" };

function summarize(value, max = 120) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function flattenModules(root) {
  const out = [];
  const walk = (n, depth) => {
    if (n.node_type === "module") out.push({ id: n.id, title: n.title, depth });
    for (const c of n.children || []) walk(c, depth + 1);
  };
  walk(root, 0);
  return out;
}

function subtreeIds(root, id) {
  const index = buildNodeIndex(root);
  const ids = new Set();
  const stack = index.get(id) ? [index.get(id)] : [];
  while (stack.length) {
    const n = stack.pop();
    ids.add(n.id);
    stack.push(...(n.children || []));
  }
  return ids;
}

function subtreeCounts(root, id) {
  let modules = 0;
  let cases = 0;
  for (const nid of subtreeIds(root, id)) {
    const node = buildNodeIndex(root).get(nid);
    if (!node) continue;
    if (node.node_type === "module" && node.id !== id) modules += 1;
    if (node.node_type === "test_case") cases += 1;
  }
  return { modules, cases };
}

function actorName(actor) {
  if (actor === "user") return "You";
  if (actor === "agent") return "Agent";
  if (actor === "system") return "System";
  return actor || "—";
}

function lineLabel(line, treeIndex) {
  const type = line.node_type ?? (treeIndex?.get ? treeIndex.get(line.node_id)?.node_type : null);
  if (type === "test_case") return formatCaseNumber(line.node_id);
  return line.title || (type === "module" ? "module" : "");
}

function DiffLine({ line, treeIndex }) {
  const label = lineLabel(line, treeIndex);
  if (line.change === "added") {
    return <div className="diff-line add">+ {label || line.title}</div>;
  }
  if (line.change === "deleted") {
    return (
      <div className="diff-line del">
        - {label || line.title || `#${line.node_id}`}
        {line.descendant_count != null ? `（affected: ${line.descendant_count} nodes）` : ""}
      </div>
    );
  }
  if (line.change === "moved") {
    return (
      <div className="diff-line move">
        {label || `#${line.node_id}`}: parent/order {line.before?.parent_id ?? "—"}
        {" → "}{line.after?.parent_id ?? "—"}
      </div>
    );
  }
  if (line.change === "updated") {
    return (
      <div className="diff-line update">
        {label || `#${line.node_id}`}
        {Object.entries(line.fields || {}).map(([key, pair]) => (
          <div key={key} className="diff-fields">
            <span className="diff-fields-key">{key}</span>
            <div className="diff-remove">- {summarize(String(pair?.before ?? ""), 100)}</div>
            <div className="diff-add-text">+ {summarize(String(pair?.after ?? ""), 100)}</div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

export default function FunctionCasePage() {
  const { setWorkspace, leaveWorkspace } = useFunctionalWorkspace();
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [tree, setTree] = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scopeId, setScopeId] = useState(null);
  const [keyword, setKeyword] = useState("");
  const [priority, setPriority] = useState(undefined);
  const [viewMode, setViewMode] = useState("list");
  const [collapsed, setCollapsed] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [writeBusy, setWriteBusy] = useState(false);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [diffData, setDiffData] = useState(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [undoVisible, setUndoVisible] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState(null);

  // dialogs
  const [moduleDlg, setModuleDlg] = useState(null); // {kind, target, title}
  const [caseDlg, setCaseDlg] = useState(null); // editor payload
  const [deleteDlg, setDeleteDlg] = useState(null); // {kind:'module'|'case', node}
  const [moveDlg, setMoveDlg] = useState(null); // {kind,node}
  const [conflict, setConflict] = useState(null); // {expected,current}

  const seq = useRef(0);
  const viewerOnly = isViewerOnly();
  const writeVisible = !!artifact && !viewerOnly;

  const refreshContent = useCallback(async (aid) => {
    const [treeRes, revRes] = await Promise.all([
      getArtifactTree(aid), getArtifactRevisions(aid),
    ]);
    setTree(treeRes.data);
    setRevisions(revRes.data);
    return treeRes.data;
  }, []);

  const load = useCallback(async (pid) => {
    if (pid == null) return;
    const token = ++seq.current;
    setLoading(true);
    setError("");
    setArtifact(null);
    setTree(null);
    setRevisions([]);
    setDiffData(null);
    try {
      const listRes = await listArtifacts();
      if (token !== seq.current) return;
      const own = (listRes.data || []).find(
        (item) => item.project_id === pid && item.artifact_type === "test_design");
      let artifactRow = null;
      if (own) artifactRow = await getArtifact(own.id);
      else if (!viewerOnly) {
        const ensured = await ensureProjectArtifact({ project_id: pid });
        if (token !== seq.current) return;
        artifactRow = await getArtifact(ensured.data.id);
      }
      if (token !== seq.current) return;
      if (artifactRow) {
        setArtifact(artifactRow.data);
        await refreshContent(artifactRow.data.id);
        setScopeId(null);
        setSelectedNodeId(null);
      }
    } catch (err) {
      if (token !== seq.current) return;
      setError(err?.response?.data?.detail || err?.message || "加载失败");
    } finally {
      if (token === seq.current) setLoading(false);
    }
  }, [refreshContent, viewerOnly]);

  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        const response = await getProjectList();
        if (disposed) return;
        setProjects(response.data || []);
        const initial = resolveProjectId(response.data || [], getStoredProjectId());
        if (initial) {
          setProjectId(initial.id);
          storeProjectId(initial.id);
        }
      } catch {
        if (!disposed) setError("加载项目列表失败");
      }
    })();
    return () => { disposed = true; seq.current += 1; };
  }, []);

  useEffect(() => {
    if (projectId != null) void load(projectId);
  }, [projectId, load]);

  const index = useMemo(() => (tree ? buildNodeIndex(tree.root) : new Map()), [tree]);
  const selectedNode = useMemo(
    () => (selectedNodeId != null ? index.get(selectedNodeId) ?? null : null),
    [selectedNodeId, index]);
  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId) || null,
    [projects, projectId]);
  const workspaceValue = useMemo(() => deriveFunctionalWorkspace({
    project: selectedProject, artifact, index, scopeId, selectedNodeId, viewMode,
  }), [selectedProject, artifact, index, scopeId, selectedNodeId, viewMode]);

  useEffect(() => {
    setWorkspace(workspaceValue);
  }, [setWorkspace, workspaceValue]);

  useEffect(() => () => leaveWorkspace(), [leaveWorkspace]);
  const moduleTree = useMemo(() => (tree ? buildModuleTree(tree.root) : null), [tree]);
  const rows = useMemo(() => (tree ? collectScopeCases(tree.root, scopeId) : []), [tree, scopeId]);
  const scopedRoot = useMemo(() => {
    if (!tree) return null;
    if (scopeId == null || scopeId === tree.root?.id) return tree.root;
    return index.get(scopeId) || tree.root;
  }, [tree, scopeId, index]);

  const filtered = useMemo(() => rows.filter((row) => {
    if (priority && row.priority !== priority) return false;
    if (keyword) {
      const hay = [
        row.caseNumber, row.title, row.modulePath.join("/"),
        ...row.preconditions, ...row.steps.map((s) => `${s.step_no ?? ""} ${s.action}`),
        ...row.expectedResults.map((e) => (typeof e === "string" ? e : e?.expected ?? "")),
      ].join(" ").toLowerCase();
      if (!hay.includes(keyword.toLowerCase())) return false;
    }
    return true;
  }), [rows, keyword, priority]);

  const treeData = useMemo(() => {
    const map = (n) => ({
      key: String(n.id),
      title: n.title,
      isLeaf: !(n.children || []).length,
      children: n.children.map(map),
    });
    return (moduleTree?.children || []).map(map);
  }, [moduleTree]);

  const openCaseEditor = useCallback((mode, row, defaultModuleId) => {
    const content = row?.content && typeof row.content === "object" ? row.content : {};
    const base = {
      mode, // create|edit
      title: row?.title || "",
      moduleId: row ? index.get(row.nodeId)?.parent_id ?? null : defaultModuleId ?? scopeId,
      priority: content.priority || "P1",
      tags: (content.tags || []).join(", "),
      preconditions: [...(content.preconditions || [])],
      steps: (content.steps || []).map((s) => ({
        step_no: s.step_no ?? null, action: s.action ?? "", data: s.data ?? null,
      })),
      expected: (content.expected_results || []).map((e) => ({
        step_no: typeof e === "object" && e ? e.step_no ?? null : null,
        expected: typeof e === "string" ? e : e?.expected ?? "",
      })),
    };
    setCaseDlg({ ...base, nodeId: row?.nodeId ?? null });
  }, [scopeId, index]);

  const openRecentDiff = useCallback(async () => {
    if (!artifact || !tree) return;
    const from = Math.max(0, tree.current_revision - 1);
    try {
      const res = await getArtifactDiff(artifact.id, { from_revision: from, to_revision: tree.current_revision });
      setDiffData({ ...res.data, title: `Revision ${from} → ${tree.current_revision}` });
      setDiffOpen(true);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "加载 diff 失败");
    }
  }, [artifact, tree]);

  const openRevisionDiff = useCallback(async (revisionNo) => {
    if (!artifact) return;
    try {
      const res = await getArtifactDiff(artifact.id, {
        from_revision: Math.max(0, revisionNo - 1), to_revision: revisionNo,
      });
      setDiffData({ ...res.data, title: `Revision ${Math.max(0, revisionNo - 1)} → ${revisionNo}` });
      setDiffOpen(true);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "加载 diff 失败");
    }
  }, [artifact]);

  const runWrite = useCallback(async (operations, summary) => {
    if (!artifact || !tree) return false;
    const expected = tree.current_revision;
    setWriteBusy(true);
    try {
      await applyArtifactOperations(artifact.id, { expected_revision: expected, operations, summary });
      await refreshContent(artifact.id);
      setConflict(null);
      return true;
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 409 && detail && typeof detail === "object") {
        setConflict({ expected, current: detail.current_revision ?? null });
        return false;
      }
      setError(detail || err?.message || "保存失败");
      return false;
    } finally {
      setWriteBusy(false);
    }
  }, [artifact, tree, refreshContent]);


  const applyStepReflow = (nextSteps, expectedOverride = null) => {
    setCaseDlg((d) => {
      if (!d) return d;
      const remapped = caseEditorModel.renumberStepsAndExpected(
        nextSteps, expectedOverride ?? d.expected);
      return { ...d, steps: remapped.steps, expected: remapped.expected };
    });
  };

  const saveModule = async () => {
    if (!moduleDlg) return;
    const title = (moduleDlg.title || "").trim();
    if (!title) return;
    const ops = caseEditorModel.moduleOps({
      kind: moduleDlg.kind, parentId: moduleDlg.parentId, nodeId: moduleDlg.nodeId, title,
    });
    const ok = await runWrite(ops, moduleDlg.kind === "create" ? `新增模块 ${title}` : `重命名模块 → ${title}`);
    if (ok) setModuleDlg(null);
  };

  const saveCaseEditor = async () => {
    if (!caseDlg) return;
    const title = (caseDlg.title || "").trim();
    if (!title) return;
    try {
      const content = {
        preconditions: caseDlg.preconditions.filter((x) => x.trim()),
        steps: caseDlg.steps.map((s) => ({ step_no: s.step_no ?? null, action: s.action, data: s.data || null })),
        expected_results: caseDlg.expected.map((e) => ({
          step_no: e.step_no ?? null, expected: e.expected,
        })).filter((e) => e.expected && e.expected.trim()),
        priority: caseDlg.priority,
        tags: caseDlg.tags.split(",").map((t) => t.trim()).filter(Boolean),
      };
      const ops = caseEditorModel.editorToCaseOperations({
        create: caseDlg.mode === "create", moduleId: caseDlg.moduleId, nodeId: caseDlg.nodeId,
        title, content, sourceRefs: null,
      });
      const summary = caseDlg.mode === "create" ? `新增用例 ${title}` : `编辑用例 ${title}`;
      const ok = await runWrite(ops, summary);
      if (ok) setCaseDlg(null);
    } catch (err) {
      setError(err?.message || "表单校验失败");
    }
  };

  const doDelete = async () => {
    if (!deleteDlg) return;
    const ops = [{
      operation_type: "delete_node",
      target_node_id: deleteDlg.node.id,
    }];
    const ok = await runWrite(ops, `删除 ${deleteDlg.node.node_type === "module" ? "模块" : "用例"} ${deleteDlg.node.title}`);
    if (ok) {
      if (scopeId === deleteDlg.node.id) setScopeId(null);
      if (selectedNodeId === deleteDlg.node.id) setSelectedNodeId(null);
      setDeleteDlg(null);
    }
  };

  const doMove = async () => {
    if (!moveDlg) return;
    const ops = caseEditorModel.moduleOps({
      kind: "move", nodeId: moveDlg.node.id, newParentId: moveDlg.parentId,
    });
    const ok = await runWrite(ops, `移动 ${moveDlg.node.title}`);
    if (ok) setMoveDlg(null);
  };

  const loadLatestAfterConflict = async () => {
    if (!artifact) return;
    setConflict(null);
    await refreshContent(artifact.id);
  };

  const doUndo = async () => {
    if (!artifact) return;
    try {
      setWriteBusy(true);
      await undoArtifact(artifact.id, tree?.current_revision);
      await refreshContent(artifact.id);
      setUndoVisible(false);
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (err?.response?.status === 409 && d && typeof d === "object") {
        setConflict({ expected: d.expected_revision ?? null, current: d.current_revision ?? null });
      } else {
        setError(d || err?.message || "撤销失败");
      }
    } finally {
      setWriteBusy(false);
    }
  };

  const doRestore = async () => {
    if (!artifact || restoreTarget == null) return;
    try {
      setWriteBusy(true);
      await restoreArtifact(artifact.id, restoreTarget, tree?.current_revision);
      await refreshContent(artifact.id);
      setRestoreTarget(null);
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (err?.response?.status === 409 && d && typeof d === "object") {
        setConflict({ expected: d.expected_revision ?? null, current: d.current_revision ?? null });
      } else {
        setError(d || err?.message || "恢复失败");
      }
    } finally {
      setWriteBusy(false);
    }
  };

  const moduleMenu = (node) => ({
    items: [
      { key: "child", label: "新增子模块" },
      { key: "rename", label: "重命名" },
      { key: "move", label: "移动" },
      { key: "delete", label: "删除", danger: true },
    ],
    onClick: ({ key }) => {
      if (key === "child") setModuleDlg({ kind: "create", parentId: node.id, title: "" });
      if (key === "rename") setModuleDlg({ kind: "rename", nodeId: node.id, title: node.title });
      if (key === "move") {
        setMoveDlg({ kind: "module", node, parentId: null });
      }
      if (key === "delete") setDeleteDlg({ kind: "module", node });
    },
  });

  const moduleOptions = useMemo(() => {
    const list = moduleTree ? flattenModules(moduleTree) : [];
    return list;
  }, [moduleTree]);

  const columns = [
    { title: "编号", dataIndex: "caseNumber", width: 120, fixed: "left",
      render: (v) => <Typography.Text type="secondary">{v}</Typography.Text> },
    { title: "模块", key: "module", width: 160, render: (_, r) => r.modulePath.join(" / ") || "—" },
    { title: "名称", dataIndex: "title", ellipsis: true, width: 200 },
    { title: "前置条件", key: "pre", width: 170,
      render: (_, r) => <span className="cell-preview">{summarize(r.preconditions.join("；")) || "—"}</span> },
    { title: "步骤", key: "steps", width: 210,
      render: (_, r) => <span className="cell-preview">{summarize(stepsSummary(r.steps)) || "—"}</span> },
    { title: "预期", key: "expected", width: 210,
      render: (_, r) => <span className="cell-preview">{summarize(expectedSummary(r.expectedResults)) || "—"}</span> },
    { title: "优先级", dataIndex: "priority", width: 90,
      render: (v) => <Tag color={PRIORITY_COLOR[v] || "default"}>{v}</Tag> },
  ];

  const moduleItem = (node) => {
    const content = (
      <span>
        {node.title}
        {node.id === scopeId ? " ✓" : ""}
      </span>
    );
    if (!writeVisible) {
      return <span className="module-row" onClick={() => { setScopeId(node.id); setSelectedNodeId(node.id); }}>{content}</span>;
    }
    return (
      <Dropdown trigger={["contextMenu", "hover"]} menu={moduleMenu(node)}>
        <span className="module-row" onClick={(e) => { e.stopPropagation(); setScopeId(node.id); setSelectedNodeId(node.id); }}>
          {content}
        </span>
      </Dropdown>
    );
  };

  const titleRender = (nodeData) => {
    const node = index.get(Number(nodeData.key));
    return node ? moduleItem(node) : nodeData.title;
  };

  return (
    <Card size="small" title={null} className="case-page">
      <div className="case-page-toolbar">
        <Space wrap>
          <span>项目：</span>
          <Select style={{ width: 220 }} value={projectId}
            onChange={(v) => {
              // Clear Artifact/selection in the same interaction. Until B loads,
              // Chat must never mistake the previous Project A Artifact for B.
              setArtifact(null); setTree(null); setScopeId(null); setSelectedNodeId(null);
              setProjectId(v); storeProjectId(v);
            }}
            options={projects.map((p) => ({ value: p.id, label: p.name }))} />
          <Input.Search allowClear placeholder="搜索…" style={{ width: 260 }}
            value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          <Select allowClear placeholder="优先级" style={{ width: 110 }} value={priority}
            onChange={setPriority}
            options={["P0", "P1", "P2", "P3"].map((v) => ({ value: v, label: v }))} />
          <Button.Group>
            <Button type={viewMode === "list" ? "primary" : "default"} onClick={() => setViewMode("list")}>列表</Button>
            <Button type={viewMode === "mindmap" ? "primary" : "default"} onClick={() => setViewMode("mindmap")}>脑图</Button>
          </Button.Group>
          {artifact && (
            <>
              <Typography.Text type="secondary">
                {artifact.title} · Revision {tree?.current_revision}
              </Typography.Text>
              {writeVisible && (
                <Button size="small" onClick={async () => {
                  const latest = await getArtifactTree(artifact.id).then((r) => r.data);
                  setTree(latest);
                  const revRes = await getArtifactRevisions(artifact.id);
                  setRevisions(revRes.data);
                  setError("");
                }}>刷新</Button>
              )}
              <Button size="small" onClick={openRecentDiff}>查看最近变更</Button>
              <Button size="small" onClick={() => setHistoryOpen(true)}>历史</Button>
              {writeVisible && tree && tree.current_revision > 1 && (
                <Button size="small" danger onClick={() => setUndoVisible(true)}>Undo latest</Button>
              )}
            </>
          )}
        </Space>
      </div>
      {error && <div className="case-page-error">{error}</div>}

      <div className="case-page-body">
        <aside className="case-module-panel">
          <div className="case-module-head">
            <strong>Modules</strong>
            {writeVisible && (
              <Button size="small" type="text" onClick={() => {
                setModuleDlg({ kind: "create", parentId: tree?.root?.id ?? null, title: "" });
              }}>＋ 新增模块</Button>
            )}
          </div>
          <button type="button" className={scopeId == null ? "case-module-all active" : "case-module-all"}
            onClick={() => { setScopeId(null); setSelectedNodeId(null); }}>
            全部模块
          </button>
          {loading && <div className="case-loading">加载中…</div>}
          {!loading && tree && (
            <Tree
              defaultExpandAll blockNode
              selectedKeys={scopeId != null ? [String(scopeId)] : []}
              treeData={treeData}
              titleRender={titleRender}
              onSelect={(keys) => {
                if (!keys.length) { setScopeId(null); setSelectedNodeId(null); return; }
                const id = Number(keys[0]);
                setScopeId(id);
                setSelectedNodeId(id);
              }}
            />
          )}
          {!loading && !tree && (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={viewerOnly ? "当前项目暂无 Artifact（只读）" : "暂无模块"} />
          )}
        </aside>

        <section className="case-list-panel">
          {viewMode === "list" ? (
            <>
              {writeVisible && (
                <div className="case-toolbar-actions">
                  <Button size="small" type="primary"
                    onClick={() => openCaseEditor("create", null, scopeId)}>＋ 新增用例</Button>
                </div>
              )}
              {!loading && artifact && (
                <Table size="small" rowKey="nodeId" columns={columns} dataSource={filtered}
                  pagination={false} scroll={{ x: 1160 }}
                  onRow={(row) => ({
                    style: { cursor: "pointer" },
                    onClick: () => {
                      setSelectedNodeId(row.nodeId);
                      if (writeVisible) openCaseEditor("edit", row);
                    },
                  })} />
              )}
              {!loading && !artifact && (
                <Empty description={viewerOnly ? "只读：当前项目没有 Artifact" : "暂无用例"} />
              )}
            </>
          ) : (
            <div className="mindmap-host">
              {scopedRoot ? (
                <ReactFlowProvider>
                  <ArtifactMindMap
                    tree={{ root: scopedRoot }}
                    collapsedIds={collapsed}
                    selectedNodeId={selectedNode?.id ?? null}
                    onSelect={(id) => {
                      const node = index.get(id);
                      if (!node) return;
                      setSelectedNodeId(id);
                      if (node.node_type === "module") setScopeId(id);
                    }}
                    onToggleCollapse={(id) => setCollapsed((prev) => (
                      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
                    ))}
                    artifactKey={artifact?.id}
                    treeNonce={tree?.current_revision}
                  />
                </ReactFlowProvider>
              ) : (
                <Empty description="暂无内容" />
              )}
              {selectedNode && (
                <div className="mindmap-inspector">
                  <Typography.Text strong>
                    {selectedNode.node_type === "test_case" ? formatCaseNumber(selectedNode.id) : selectedNode.title}
                  </Typography.Text>
                  <Typography.Text type="secondary"> · {selectedNode.node_type}</Typography.Text>
                  {writeVisible && (
                    <Space size={4} style={{ float: "right" }}>
                      <Button size="small"
                        onClick={() => selectedNode.node_type === "module"
                          ? setModuleDlg({ kind: "rename", nodeId: selectedNode.id, title: selectedNode.title })
                          : openCaseEditor("edit", selectedNode)}>编辑</Button>
                      {selectedNode.node_type === "module"
                        ? <Button size="small"
                            onClick={() => setDeleteDlg({ kind: "module", node: selectedNode })} danger>删除</Button>
                        : <Button size="small"
                            onClick={() => setDeleteDlg({ kind: "case", node: selectedNode })} danger>删除</Button>}
                    </Space>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Module dialogs */}
      <Modal open={!!moduleDlg} title={moduleDlg?.kind === "create" ? "新增模块" : "重命名模块"}
        onOk={saveModule} onCancel={() => setModuleDlg(null)} okButtonProps={{ loading: writeBusy }}
        destroyOnClose>
        <Input placeholder="模块名称" value={moduleDlg?.title || ""} maxLength={100}
          onChange={(e) => setModuleDlg((d) => ({ ...d, title: e.target.value }))}
          onPressEnter={saveModule} />
      </Modal>

      {/* Move dialog (module or case) */}
      <Modal open={!!moveDlg} title="移动"
        onOk={doMove} onCancel={() => setMoveDlg(null)} okButtonProps={{ loading: writeBusy }}
        destroyOnClose>
        <Select
          style={{ width: "100%" }} placeholder="选择目标模块"
          value={moveDlg?.parentId ?? undefined}
          onChange={(v) => setMoveDlg((d) => ({ ...d, parentId: v }))}
          options={[
            ...(moveDlg?.kind === "module" && tree?.root
              ? [{ value: tree.root.id, label: "项目根（一级模块）" }] : []),
            ...moduleOptions
              .filter((m) => !subtreeIds(tree?.root, moveDlg?.node?.id).has(m.id))
              .map((m) => ({ value: m.id, label: `${"　".repeat(Math.min(m.depth, 6))}${m.title}` })),
          ]}
        />
        <Typography.Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12 }}>
          后端会校验 parent 类型/环/Revision。
        </Typography.Paragraph>
      </Modal>

      {/* Delete confirm */}
      <Modal open={!!deleteDlg}
        title={`删除「${deleteDlg?.node?.title || ""}」？`}
        onOk={doDelete} onCancel={() => setDeleteDlg(null)} okText="删除" okButtonProps={{ danger: true, loading: writeBusy }}
        destroyOnClose>
        {deleteDlg?.kind === "module" && (() => {
          const counts = deleteDlg?.node ? subtreeCounts(tree?.root, deleteDlg.node.id) : null;
          return <div>{counts ? `${counts.modules} 个子模块，${counts.cases} 条用例` : ""}，删除后可在 Revision 历史中恢复。</div>;
        })()}
        {deleteDlg?.kind === "case" && <div>删除用例「{deleteDlg?.node?.title}」。可稍后 Undo 恢复。</div>}
      </Modal>

      {/* Case editor */}
      <Modal open={!!caseDlg} width={860}
        title={caseDlg?.mode === "create" ? "新增用例" : "编辑用例"}
        onOk={saveCaseEditor} onCancel={() => setCaseDlg(null)}
        okText={caseDlg?.mode === "create" ? "创建" : "保存"} okButtonProps={{ loading: writeBusy }}
        destroyOnClose>
        {caseDlg && (
          <div className="case-editor">
            <div className="editor-grid">
              <label>名称</label>
              <Input value={caseDlg.title} onChange={(e) => setCaseDlg({ ...caseDlg, title: e.target.value })} />
              <label>所属模块</label>
              <Select value={caseDlg.moduleId ?? undefined} style={{ width: "100%" }}
                onChange={(v) => setCaseDlg({ ...caseDlg, moduleId: v })}
                options={moduleOptions.map((m) => ({ value: m.id, label: m.title }))}
                placeholder="请选择模块（空则进入默认模块）" />
              <label>优先级</label>
              <Select value={caseDlg.priority} style={{ width: 120 }}
                onChange={(v) => setCaseDlg({ ...caseDlg, priority: v })}
                options={["P0", "P1", "P2", "P3"].map((v) => ({ value: v, label: v }))} />
              <label>Tags</label>
              <Input value={caseDlg.tags} placeholder="逗号分隔"
                onChange={(e) => setCaseDlg({ ...caseDlg, tags: e.target.value })} />
            </div>

            <div className="editor-sec">
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <strong>前置条件</strong>
                <Button size="small" onClick={() => setCaseDlg({
                  ...caseDlg, preconditions: [...caseDlg.preconditions, ""],
                })}>＋ 前置条件</Button>
              </Space>
              {caseDlg.preconditions.map((item, i) => (
                <div key={i} className="editor-row">
                  <Input value={item} placeholder={`前置 ${i + 1}`}
                    onChange={(e) => {
                      const preconditions = [...caseDlg.preconditions];
                      preconditions[i] = e.target.value;
                      setCaseDlg({ ...caseDlg, preconditions });
                    }} />
                  <Button size="small" type="text" danger
                    onClick={() => setCaseDlg({
                      ...caseDlg, preconditions: caseDlg.preconditions.filter((_, j) => j !== i),
                    })}>✕</Button>
                </div>
              ))}
            </div>

            <div className="editor-sec">
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <strong>步骤</strong>
                <Button size="small" onClick={() => applyStepReflow([
                  ...caseDlg.steps, { step_no: null, action: "", data: null },
                ])}>＋ 步骤</Button>
              </Space>
              {caseDlg.steps.map((step, i) => (
                <div key={i} className="editor-row steps-row">
                  <span className="step-no">{step.step_no ?? i + 1}</span>
                  <Input value={step.action} placeholder="Action"
                    onChange={(e) => {
                      const steps = [...caseDlg.steps];
                      steps[i] = { ...steps[i], action: e.target.value };
                      setCaseDlg({ ...caseDlg, steps });
                    }} />
                  <Input value={step.data ?? ""} placeholder="Data"
                    onChange={(e) => {
                      const steps = [...caseDlg.steps];
                      steps[i] = { ...steps[i], data: e.target.value || null };
                      setCaseDlg({ ...caseDlg, steps });
                    }} />
                  <Space size={0}>
                    <Button size="small" type="text" disabled={i === 0}
                      onClick={() => {
                        const steps = [...caseDlg.steps];
                        [steps[i - 1], steps[i]] = [steps[i], steps[i - 1]];
                        applyStepReflow(steps);
                      }}>↑</Button>
                    <Button size="small" type="text" disabled={i === caseDlg.steps.length - 1}
                      onClick={() => {
                        const steps = [...caseDlg.steps];
                        [steps[i + 1], steps[i]] = [steps[i], steps[i + 1]];
                        applyStepReflow(steps);
                      }}>↓</Button>
                    <Button size="small" type="text" danger
                      onClick={() => {
                        const removedNo = caseDlg.steps[i]?.step_no ?? null;
                        const nextSteps = caseDlg.steps.filter((_, j) => j !== i);
                        const clearedExpected = caseDlg.expected.map((e) =>
                          e.step_no === removedNo ? { ...e, step_no: null } : e);
                        applyStepReflow(nextSteps, clearedExpected);
                      }}>✕</Button>
                  </Space>
                </div>
              ))}
            </div>

            <div className="editor-sec">
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <strong>预期结果</strong>
                <Button size="small" onClick={() => setCaseDlg({
                  ...caseDlg, expected: [...caseDlg.expected, { step_no: null, expected: "" }],
                })}>＋ 预期</Button>
              </Space>
              {caseDlg.expected.map((item, i) => (
                <div key={i} className="editor-row">
                  <Select value={item.step_no ?? null} style={{ width: 120 }}
                    onChange={(v) => {
                      const expected = [...caseDlg.expected];
                      expected[i] = { ...expected[i], step_no: v };
                      setCaseDlg({ ...caseDlg, expected });
                    }}
                    options={[
                      { value: null, label: "整体" },
                      ...caseDlg.steps.map((s, j) => ({
                        value: s.step_no ?? j + 1, label: `步骤 ${s.step_no ?? j + 1}`,
                      })),
                    ]} />
                  <Input value={item.expected} placeholder="预期内容"
                    onChange={(e) => {
                      const expected = [...caseDlg.expected];
                      expected[i] = { ...expected[i], expected: e.target.value };
                      setCaseDlg({ ...caseDlg, expected });
                    }} />
                  <Button size="small" type="text" danger
                    onClick={() => setCaseDlg({
                      ...caseDlg, expected: caseDlg.expected.filter((_, j) => j !== i),
                    })}>✕</Button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>

      {/* Conflict */}
      <Modal open={!!conflict} title="测试资产已被其他修改更新" onCancel={() => setConflict(null)}
        footer={[
          <Button key="close" onClick={() => setConflict(null)}>保留草稿</Button>,
          <Button key="latest" type="primary" onClick={loadLatestAfterConflict}>加载最新版本</Button>,
        ]}>
        <div>你的版本：{conflict?.expected ?? "—"}</div>
        <div>当前版本：{conflict?.current ?? "—"}</div>
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          草稿不会自动清空；加载最新版本后可重新确认保存。
        </Typography.Paragraph>
      </Modal>

      {/* Undo confirm */}
      <Modal open={undoVisible} title="撤销最近一次修改？"
        onOk={doUndo} onCancel={() => setUndoVisible(false)} okText="撤销" okButtonProps={{ danger: true }}
        destroyOnClose>
        {revisions.length > 0 && (
          <div>
            最近：Revision {revisions[revisions.length - 1].revision_no} — {revisions[revisions.length - 1].summary || "（无摘要）"}
          </div>
        )}
        <div style={{ marginTop: 6 }}>撤销会创建新 Revision，不删除历史。</div>
      </Modal>

      {/* History Drawer */}
      <Drawer title="Revision History" width={520} open={historyOpen} onClose={() => setHistoryOpen(false)}>
        <Space direction="vertical" style={{ width: "100%" }}>
          {[...revisions].reverse().map((rev) => (
            <div key={rev.revision_no} className="history-item">
              <div className="history-head">
                <Typography.Text strong>Revision {rev.revision_no}</Typography.Text>
                <Typography.Text type="secondary">
                  {actorName(rev.actor_type)} · {rev.summary || "—"}
                </Typography.Text>
              </div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {new Date(rev.created_at).toLocaleString()}
              </Typography.Text>
              <div>
                <Button size="small" onClick={() => openRevisionDiff(rev.revision_no)}>Diff</Button>
                {writeVisible && rev.revision_no < tree?.current_revision && (
                  <Button size="small" style={{ marginLeft: 6 }}
                    onClick={() => { setRestoreTarget(rev.revision_no); setHistoryOpen(false); }}>
                    Restore
                  </Button>
                )}
              </div>
            </div>
          ))}
        </Space>
      </Drawer>

      {/* Restore confirm */}
      <Modal open={restoreTarget != null}
        title="恢复到此版本？"
        okText="恢复" okButtonProps={{ danger: true, loading: writeBusy }}
        onOk={doRestore} onCancel={() => setRestoreTarget(null)}>
        恢复不会删除后续历史：将创建新 Revision（当前 {tree?.current_revision} → {tree?.current_revision + 1}）。
      </Modal>

      {/* Diff viewer */}
      <Drawer title={diffData?.title || "Diff"} width={640} open={diffOpen} onClose={() => setDiffOpen(false)}>
        {diffData?.changes?.map((line, i) => <DiffLine key={i} line={line} treeIndex={index} />)}
        {diffData && !diffData.changes?.length && <Empty description="无变更" />}
      </Drawer>

      <style>{`
        .case-page-toolbar { margin-bottom: 10px; }
        .case-page-body { display: flex; gap: 12px; align-items: flex-start; }
        .case-module-panel { width: 250px; flex: none; border: 1px solid #e6e6e7; border-radius: 8px; padding: 8px; max-height: 74vh; overflow: auto; }
        .case-module-head { display:flex; align-items:center; justify-content:space-between; margin-bottom: 6px; }
        .case-module-all { display:block; width:100%; text-align:left; border:0; background:transparent; padding:4px 6px; border-radius:6px; cursor:pointer; margin-bottom:4px; }
        .case-module-all.active, .module-row:hover { background: #eeeeef; }
        .module-row { display:block; padding: 2px 4px; border-radius: 4px; cursor:pointer; }
        .case-list-panel { flex: 1; min-width: 0; }
        .case-toolbar-actions { margin-bottom: 6px; text-align: right; }
        .cell-preview { white-space: pre-line; display:block; max-height: 60px; overflow:hidden; font-size:12px; color:#444; }
        .case-page-error { color:#b42318; padding: 4px 0; }
        .mindmap-host { border: 1px solid #e6e6e7; border-radius: 8px; min-height: 560px; position: relative; overflow: hidden; }
        .mindmap-host .react-flow { height: 520px; }
        .mindmap-inspector { position:absolute; left:10px; bottom:8px; right:10px; background:rgba(255,255,255,.95); border:1px solid #e6e6e7; border-radius:8px; padding:8px 12px; }
        .history-item { border:1px solid #e6e6e7; border-radius:8px; padding:8px 10px; width:100%; }
        .history-head { display:flex; justify-content:space-between; gap:8px; }
        .diff-line { font-size:12.5px; margin: 4px 0; }
        .diff-line.add { color:#1a7f37; }
        .diff-line.del { color:#b42318; }
        .diff-fields { margin-left: 12px; }
        .diff-add-text { color:#1a7f37; }
        .diff-remove { color:#b42318; text-decoration: line-through; }
        .case-editor .editor-grid { display:grid; grid-template-columns: 84px 1fr 84px 200px; gap:6px 10px; align-items:center; }
        .case-editor .editor-sec { margin-top: 12px; border-top:1px dashed #e6e6e7; padding-top:8px; }
        .editor-row { display:flex; align-items:center; gap:6px; margin: 4px 0; }
        .steps-row .step-no { width: 26px; color:#8c959f; font-size:12px; text-align:right; }
      `}</style>
    </Card>
  );
}
