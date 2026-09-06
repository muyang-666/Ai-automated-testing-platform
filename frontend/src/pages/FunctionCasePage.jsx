// P09.1 FunctionCasePage（Converged）：数据源 = Project Functional TestArtifact。
// 左侧 Module Tree（来自 Artifact tree），右侧 Case List（同一 tree 派生），
// 只读 Detail Drawer；不做 CRUD UI（P09.2）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Drawer, Empty, Input, Select, Space, Table, Tag, Tree, Typography } from "antd";
import { getProjectList } from "../api/project";
import { ensureProjectArtifact, getArtifact, getArtifactTree } from "../api/testArtifact";
import { collectScopeCases, buildModuleTree } from "../components/v2-workspace/caseView";
import { formatCaseNumber } from "../components/v2-workspace/caseNumber";
import { getStoredProjectId, resolveProjectId, storeProjectId } from "../utils/projectSelection";
import { isViewerOnly } from "../utils/authPermissions";

const PRIORITY_COLOR = { P0: "red", P1: "orange", P2: "gold", P3: "default" };

function textLines(items = []) {
  return items.map((item, i) => {
    if (typeof item === "string") return item;
    if (Array.isArray(item) && typeof item[0] === "string") return `${i + 1}. ${item[0]}`;
    if (item && typeof item === "object") return `${i + 1}. ${item.expected ?? ""}`;
    return String(item);
  }).filter(Boolean).join("\n");
}

function summarize(value, max = 120) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export default function FunctionCasePage() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scopeId, setScopeId] = useState(null); // null = 全部模块（root 范围）
  const [keyword, setKeyword] = useState("");
  const [priority, setPriority] = useState(undefined);
  const [selected, setSelected] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const seq = useRef(0);

  const load = useCallback(async (pid) => {
    if (pid == null) return;
    const token = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const ensured = await ensureProjectArtifact({ project_id: pid });
      if (token !== seq.current) return;
      const artifactRow = await getArtifact(ensured.data.id);
      const treeRes = await getArtifactTree(ensured.data.id);
      if (token !== seq.current) return;
      setArtifact(artifactRow.data);
      setTree(treeRes.data);
      setScopeId(null);
      setSelected(null);
    } catch (err) {
      if (token !== seq.current) return;
      setArtifact(null);
      setTree(null);
      setError(err?.response?.data?.detail || err?.message || "加载失败");
    } finally {
      if (token === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        const response = await getProjectList();
        if (disposed) return;
        const list = response.data || [];
        setProjects(list);
        const initial = resolveProjectId(list, getStoredProjectId());
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
    if (projectId == null) return;
    void load(projectId);
  }, [projectId, load]);

  const moduleTree = useMemo(() => (tree ? buildModuleTree(tree.root) : null), [tree]);

  const treeData = useMemo(() => {
    if (!moduleTree) return [];
    const mapToAntd = (node) => ({
      key: String(node.id),
      title: node.title,
      children: node.children.map(mapToAntd),
    });
    return (moduleTree.children || []).map(mapToAntd);
  }, [moduleTree]);

  const rows = useMemo(() => {
    if (!tree) return [];
    return collectScopeCases(tree.root, scopeId);
  }, [tree, scopeId]);

  const filtered = useMemo(() => rows.filter((row) => {
    if (priority && row.priority !== priority) return false;
    if (keyword) {
      const haystack = [
        row.caseNumber, row.title, row.modulePath.join("/"),
        ...row.preconditions, ...row.steps.map((s) => `${s.step_no ?? ""} ${s.action}`),
        ...row.expectedResults.map((e) => (typeof e === "string" ? e : e?.expected ?? "")),
      ].join(" ").toLowerCase();
      if (!haystack.includes(keyword.toLowerCase())) return false;
    }
    return true;
  }), [rows, keyword, priority]);

  const viewerOnly = isViewerOnly();

  const columns = [
    { title: "编号", dataIndex: "caseNumber", width: 110, fixed: "left",
      render: (value) => <Typography.Text type="secondary">{value}</Typography.Text> },
    { title: "模块", key: "module", width: 150,
      render: (_, row) => row.modulePath.join(" / ") || "—" },
    { title: "名称", dataIndex: "title", ellipsis: true, width: 200 },
    { title: "前置条件", key: "pre", width: 180,
      render: (_, row) => <span className="cell-preview">{summarize(textLines(row.preconditions)) || "—"}</span> },
    { title: "步骤", key: "steps", width: 220,
      render: (_, row) => <span className="cell-preview">{summarize(textLines(row.steps)) || "—"}</span> },
    { title: "预期结果", key: "expected", width: 220,
      render: (_, row) => <span className="cell-preview">{summarize(textLines(row.expectedResults)) || "—"}</span> },
    { title: "优先级", dataIndex: "priority", width: 90,
      render: (value) => <Tag color={PRIORITY_COLOR[value] || "default"}>{value}</Tag> },
  ];

  return (
    <Card size="small" title={null} className="case-page">
      <div className="case-page-toolbar">
        <Space wrap>
          <span>项目：</span>
          <Select
            value={projectId}
            style={{ width: 240 }}
            onChange={(value) => { setProjectId(value); storeProjectId(value); }}
            options={(projects || []).map((p) => ({ value: p.id, label: p.name }))}
          />
          <Input.Search
            allowClear placeholder="搜索编号/名称/步骤/预期…" style={{ width: 300 }}
            value={keyword} onChange={(e) => setKeyword(e.target.value)}
          />
          <Select
            allowClear placeholder="优先级" style={{ width: 120 }}
            value={priority}
            onChange={setPriority}
            options={["P0", "P1", "P2", "P3"].map((p) => ({ value: p, label: p }))}
          />
          {artifact && (
            <Typography.Text type="secondary">
              {artifact.title} · Revision {tree?.current_revision}
            </Typography.Text>
          )}
        </Space>
      </div>

      {error && <div className="case-page-error">{error}</div>}

      <div className="case-page-body">
        <aside className="case-module-panel">
          <div className="case-module-head">
            <strong>Modules</strong>
          </div>
          <button type="button"
            className={scopeId == null ? "case-module-all active" : "case-module-all"}
            onClick={() => { setScopeId(null); setSelected(null); }}>
            全部模块
          </button>
          {loading && <div className="case-loading">加载中…</div>}
          {!loading && moduleTree && (
            <Tree
              defaultExpandAll
              selectedKeys={scopeId != null ? [String(scopeId)] : []}
              treeData={treeData}
              onSelect={(keys) => {
                if (!keys.length) { setScopeId(null); return; }
                setScopeId(Number(keys[0]));
              }}
            />
          )}
          {!loading && !moduleTree && (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={viewerOnly ? "当前项目暂无 Artifact（只读用户不可创建）" : "暂无模块"} />
          )}
        </aside>
        <section className="case-list-panel">
          {!loading && !artifact && !error && (
            <Empty description="暂无用例（在新项目首次打开时自动创建 Functional Artifact）" />
          )}
          {!loading && artifact && (
            <Table
              size="small"
              rowKey="nodeId"
              columns={columns}
              dataSource={filtered}
              pagination={false}
              scroll={{ x: 1180 }}
              onRow={(row) => ({
                style: { cursor: "pointer" },
                onClick: () => { setSelected(row); setDetailsOpen(true); },
              })}
            />
          )}
          {loading && <div className="case-loading">Loading tree…</div>}
        </section>
      </div>

      <Drawer
        title={selected ? formatCaseNumber(selected.nodeId) : "Case"}
        width={560}
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
      >
        {selected && (
          <div className="case-detail">
            <h3>{selected.title}</h3>
            <div className="detail-line">模块：{selected.modulePath.join(" / ") || "—"}</div>
            <div className="detail-line">优先级：{selected.priority}</div>
            {selected.tags?.length > 0 && (
              <div className="detail-line">Tags：{selected.tags.map((t) => <Tag key={t}>{t}</Tag>)}</div>
            )}
            <div className="detail-sec"><strong>前置条件</strong></div>
            <ol>{selected.preconditions.map((p, i) => <li key={i}>{p}</li>)}</ol>
            <div className="detail-sec"><strong>步骤</strong></div>
            <ol>
              {selected.steps.map((s, i) => (
                <li key={i}>
                  {s.action || ""}{s.data ? `（${s.data}）` : ""}
                </li>
              ))}
            </ol>
            <div className="detail-sec"><strong>预期结果</strong></div>
            <ol>
              {selected.expectedResults.map((item, i) => (
                <li key={i}>{typeof item === "string" ? item : item?.expected ?? ""}</li>
              ))}
            </ol>
            {selected.sourceRefs?.length > 0 && (
              <div className="detail-sec"><strong>Source</strong></div>
            )}
            {selected.sourceRefs?.map((ref, i) => (
              <div key={i} className="detail-line">
                {ref.source_type === "requirement" || ref.source_type === "requirement_doc"
                  ? `Requirement #${ref.source_id}` : `${ref.source_type} #${ref.source_id}`}
                {ref.fragment_id ? ` · ${ref.fragment_id}` : ""}
              </div>
            ))}
          </div>
        )}
      </Drawer>
      <style>{`
        .case-page-toolbar { margin-bottom: 10px; }
        .case-page-body { display: flex; gap: 12px; align-items: flex-start; }
        .case-module-panel { width: 240px; flex: none; border: 1px solid #e6e6e7; border-radius: 8px; padding: 8px; max-height: 70vh; overflow: auto; }
        .case-module-head { margin-bottom: 6px; }
        .case-module-all { display: block; width: 100%; text-align: left; border: 0; background: transparent; padding: 4px 6px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
        .case-module-all.active { background: #eeeeef; }
        .case-module-all:hover { background: #f6f6f7; }
        .case-list-panel { flex: 1; min-width: 0; }
        .case-loading, .case-page-error { color: #70747a; padding: 12px 0; }
        .case-page-error { color: #b42318; }
        .cell-preview { white-space: pre-line; display: block; max-height: 64px; overflow: hidden; font-size: 12px; color: #444; }
        .case-detail h3 { margin: 0 0 10px; }
        .detail-line { margin: 4px 0; }
        .detail-sec { margin-top: 12px; }
      `}</style>
    </Card>
  );
}
