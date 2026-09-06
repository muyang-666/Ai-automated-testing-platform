// P09.1 Artifact 右侧栏：选择器/创建/Focus/只读 MindMap + Inspector。
import { useState } from "react";
import ArtifactMindMap from "./artifact/ArtifactMindMap";
import EmptyArtifactState from "./artifact/EmptyArtifactState";
import NodeInspector from "./artifact/NodeInspector";

const TYPE_LABEL = { test_design: "Test Design" };

export default function ArtifactPanel(props) {
  const {
    artifacts, listLoading, active, currentRevision,
    tree, treeLoading, treeError, unavailable, focusError, busy,
    collapsedIds, selectedNodeId,
    onFocus, onCreate, onRetryTree, onSelectNode, onToggleCollapse,
    artifactKey, treeNonce,
  } = props;
  const [menuOpen, setMenuOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");

  const startCreate = () => { setMenuOpen(false); setCreating(true); };
  const submitCreate = () => {
    const title = draftTitle.trim();
    if (!title || busy) return;
    setCreating(false);
    setDraftTitle("");
    void onCreate(title);
  };
  const pick = (artifact) => {
    setMenuOpen(false);
    void onFocus(artifact);
  };

  const skeleton = treeLoading && !active;

  return (
    <section className="v2w-panel" aria-label="Test Artifact 工作台">
      <header className="v2w-header">
        <div className="v2w-selector-wrap">
          <button type="button" className={`v2w-selector${menuOpen ? " is-open" : ""}`}
            onClick={() => { setMenuOpen((v) => !v); setCreating(false); }}
            disabled={busy}>
            <span className="v2w-selector-title">
              {active ? active.title : "No test artifact selected"}
            </span>
            <span className="v2w-selector-caret">▾</span>
          </button>
          {menuOpen && (
            <div className="v2w-selector-menu">
              {listLoading && <div className="v2w-selector-note">加载中…</div>}
              {(artifacts || []).map((artifact) => (
                <button type="button" key={artifact.id} className="v2w-selector-item"
                  onClick={() => pick(artifact)}>
                  <span className="v2w-selector-item-title">{artifact.title}</span>
                  <span className="v2w-selector-item-rev">Rev {artifact.current_revision}</span>
                </button>
              ))}
              {!listLoading && (!artifacts || artifacts.length === 0) && (
                <div className="v2w-selector-note">还没有 Artifact</div>
              )}
              <button type="button" className="v2w-selector-item v2w-selector-new"
                onClick={startCreate}>＋ New test artifact</button>
            </div>
          )}
        </div>

        <div className="v2w-header-meta">
          {active && (
            <span className="v2w-revision">
              {TYPE_LABEL[active.artifact_type] || active.artifact_type}
              {currentRevision != null ? ` · Revision ${currentRevision}` : ""}
            </span>
          )}
          <button type="button" className="v2w-icon-btn" title="Refresh Artifact"
            aria-label="Refresh Artifact" disabled={busy || treeLoading || !active}
            onClick={() => void onRetryTree()}>↻</button>
          <button type="button" className="v2w-icon-btn" title="新建测试资产" aria-label="新建测试资产"
            disabled={busy} onClick={startCreate}>＋</button>
        </div>
      </header>

      {creating && (
        <div className="v2w-create-row">
          <input
            autoFocus
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitCreate();
              if (event.key === "Escape") { setCreating(false); setDraftTitle(""); }
            }}
            placeholder="Artifact title"
            maxLength={200}
          />
          <button type="button" className="v2w-btn v2w-btn-primary" onClick={submitCreate}
            disabled={busy || !draftTitle.trim()}>Create</button>
          <button type="button" className="v2w-btn"
            onClick={() => { setCreating(false); setDraftTitle(""); }}>×</button>
        </div>
      )}

      {focusError && <div className="v2w-banner v2w-banner-error">{focusError}</div>}
      {treeError && (
        <div className="v2w-banner v2w-banner-error">
          Unable to load test artifact.
          <button type="button" className="v2w-retry" onClick={() => void onRetryTree()}>Retry</button>
        </div>
      )}
      {unavailable && (
        <div className="v2w-banner v2w-banner-error">
          该 Artifact 已删除或不可访问（unavailable）。可选择其他 Artifact 继续。
        </div>
      )}

      {skeleton && <div className="v2w-skeleton" aria-label="加载 Artifact 中">Loading tree…</div>}

      {!skeleton && !treeError && !unavailable && active && tree && (
        <>
          <ArtifactMindMap
            tree={tree}
            collapsedIds={collapsedIds}
            selectedNodeId={selectedNodeId}
            onSelect={onSelectNode}
            onToggleCollapse={onToggleCollapse}
            artifactKey={artifactKey}
            treeNonce={treeNonce}
          />
          <NodeInspector tree={tree} selectedNodeId={selectedNodeId} />
        </>
      )}

      {!skeleton && !treeError && !unavailable && !active && (
        <EmptyArtifactState onOpenSelector={() => { setCreating(false); setMenuOpen(true); }}
          onCreateStart={startCreate} />
      )}
    </section>
  );
}
