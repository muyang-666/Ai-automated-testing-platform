// P09.1 只读 Node Inspector（无编辑）。
// 数据来自 tree（整树一次拉取，内含完整 content/source_refs）；选中节点不存在时显示空提示。
import { useMemo } from "react";
import { buildNodeIndex, directChildrenOf } from "../mindMapModel";

function SourceRefList({ refs }) {
  if (!refs?.length) return null;
  return (
    <div className="v2w-insp-field">
      <span className="v2w-insp-label">Source</span>
      <ul className="v2w-insp-refs">
        {refs.map((ref, i) => (
          <li key={`${ref.source_type}-${ref.source_id}-${i}`}>
            {ref.source_type === "requirement" || ref.source_type === "requirement_doc"
              ? `Requirement #${ref.source_id}`
              : `${ref.source_type} #${ref.source_id}`}
            {ref.fragment_id ? ` · ${ref.fragment_id}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StepRow({ step, index }) {
  const parts = [`${index + 1}. ${step.action || ""}`];
  if (step.data != null && step.data !== "") parts.push(`（${step.data}）`);
  return <li>{parts.join(" ")}</li>;
}

export default function NodeInspector({ tree, selectedNodeId }) {
  const index = useMemo(() => (tree ? buildNodeIndex(tree.root) : new Map()), [tree]);
  const node = selectedNodeId != null ? index.get(selectedNodeId) : undefined;

  if (!node) {
    return (
      <div className="v2w-inspector v2w-inspector-empty">
        点击脑图节点查看详情
      </div>
    );
  }

  const parent = node.parent_id != null ? index.get(node.parent_id) : null;
  const content = node.content && typeof node.content === "object" ? node.content : {};
  const refs = node.source_refs || null;
  const childrenCount = directChildrenOf(node).length;

  return (
    <div className="v2w-inspector">
      <div className="v2w-insp-title">{node.title}</div>
      <div className="v2w-insp-sub">{node.node_type}</div>

      <div className="v2w-insp-field">
        <span className="v2w-insp-label">Type</span>
        <span className="v2w-insp-value">{node.node_type}</span>
      </div>
      <div className="v2w-insp-field">
        <span className="v2w-insp-label">Parent</span>
        <span className="v2w-insp-value">{parent ? parent.title : "—"}</span>
      </div>

      {(node.node_type === "module" || node.node_type === "root") && (
        <div className="v2w-insp-field">
          <span className="v2w-insp-label">Children</span>
          <span className="v2w-insp-value">{childrenCount}</span>
        </div>
      )}

      {node.node_type === "test_case" && (
        <>
          <div className="v2w-insp-field">
            <span className="v2w-insp-label">Priority</span>
            <span className="v2w-insp-value">{content.priority ?? "P1"}</span>
          </div>
          <div className="v2w-insp-field">
            <span className="v2w-insp-label">Tags</span>
            <span className="v2w-insp-value">
              {(content.tags || []).join(", ") || "—"}
            </span>
          </div>
          {content.preconditions?.length > 0 && (
            <div className="v2w-insp-field">
              <span className="v2w-insp-label">Preconditions</span>
              <ul className="v2w-insp-list">
                {content.preconditions.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}
          {(content.steps || []).length > 0 && (
            <div className="v2w-insp-field">
              <span className="v2w-insp-label">Steps</span>
              <ul className="v2w-insp-list">
                {content.steps.map((step, i) => <StepRow key={i} step={step} index={i} />)}
              </ul>
            </div>
          )}
          {(content.expected_results || []).length > 0 && (
            <div className="v2w-insp-field">
              <span className="v2w-insp-label">Expected</span>
              <ul className="v2w-insp-list">
                {content.expected_results.map((item, i) => (
                  <li key={i}>
                    {typeof item === "string" ? item : item?.expected ?? ""}
                    {item && typeof item === "object" && item.step_no
                      ? `（步骤 ${item.step_no}）` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <SourceRefList refs={refs} />
    </div>
  );
}
