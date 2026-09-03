import { Button, Checkbox, Empty, Tag } from "antd";
import { useMemo, useState } from "react";
import { candidateRows, coverageRows } from "./agentContract";

const TYPE_LABELS = {
  coverage_matrix: "覆盖矩阵",
  coverage_plan: "覆盖计划",
  test_case_set: "候选用例",
  scope_summary: "生成范围",
};

function artifactPayload(artifact) {
  return artifact?.payload_json || artifact?.payload || {};
}

function getCandidateName(candidate) {
  return candidate.case_name || candidate.name || candidate.title || candidate.candidate_id || "未命名用例";
}

function getCandidateSteps(candidate) {
  const steps = candidate.steps_json || candidate.steps;
  return Array.isArray(steps) ? steps.join("；") : "";
}

function CoverageView({ payload }) {
  const clauses = payload.atomic_clauses || payload.clauses || [];
  const rows = coverageRows(payload);
  const calculated = rows.some((row) => row.calculated);
  const missing = rows.filter((row) => row.calculated && !row.covered);

  return (
    <div className="test-agent-artifact-content">
      <div className="test-agent-metrics">
        <div><strong>{clauses.length}</strong><span>需求条款</span></div>
        <div><strong>{calculated ? rows.filter((row) => row.covered).length : "—"}</strong><span>已覆盖</span></div>
        <div><strong>{calculated ? missing.length : "—"}</strong><span>{calculated ? "待补充" : "尚未生成"}</span></div>
      </div>
      {(payload.assumptions || []).length > 0 && <div className="test-agent-warning"><strong>待确认假设</strong><ul>{payload.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {clauses.length > 0 ? (
        <div className="test-agent-clause-list">
          {rows.map((clause, index) => {
            const clauseId = clause.clause_id || clause.id || `C-${index + 1}`;
            return (
              <article key={clauseId}>
                <div><Tag>{clauseId}</Tag><strong>{clause.text || clause.description}</strong></div>
                <p>计划：{clause.dimensions.join(" · ") || "未指定维度"}</p>
                <p>{clause.calculated ? (clause.covered ? `已覆盖：${clause.covered_by.join("、")}` : "尚未覆盖") : "等待生成候选后计算实际覆盖"}</p>
              </article>
            );
          })}
        </div>
      ) : (
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      )}
    </div>
  );
}

function CandidateView({ payload, selectedIds, onSelectionChange, onSave, saving, canSave }) {
  const candidates = candidateRows({ payload_json: payload });

  const toggle = (candidateId, checked) => {
    const next = checked
      ? [...new Set([...selectedIds, candidateId])]
      : selectedIds.filter((id) => id !== candidateId);
    onSelectionChange(next);
  };

  const toggleAll = (checked) => {
    onSelectionChange(checked ? candidates.map((item) => item.candidate_id).filter(Boolean) : []);
  };

  return (
    <div className="test-agent-artifact-content">
      <div className="test-agent-candidate-toolbar">
        <Checkbox
          disabled={!canSave || saving}
          checked={candidates.length > 0 && selectedIds.length === candidates.length}
          indeterminate={selectedIds.length > 0 && selectedIds.length < candidates.length}
          onChange={(event) => toggleAll(event.target.checked)}
        >
          全选 {candidates.length} 条
        </Checkbox>
        <Button type="primary" size="small" loading={saving} disabled={!canSave || selectedIds.length === 0} onClick={onSave}>
          保存选中 ({selectedIds.length})
        </Button>
      </div>
      <div className="test-agent-candidate-list">
        {candidates.map((candidate, index) => {
          const candidateId = candidate.candidate_id || `candidate-${index}`;
          return (
            <article key={candidateId} className={selectedIds.includes(candidateId) ? "is-selected" : ""}>
              <Checkbox aria-label={`选择 ${getCandidateName(candidate)}`} disabled={!canSave || saving} checked={selectedIds.includes(candidateId)} onChange={(event) => toggle(candidateId, event.target.checked)} />
              <div>
                <div className="test-agent-candidate-title">
                  <strong>{getCandidateName(candidate)}</strong>
                  <Tag>{candidate.priority || "P1"}</Tag>
                  <Tag>{candidate.case_type || "其他"}</Tag>
                </div>
                {(candidate.method || candidate.url) && <p>{[candidate.method, candidate.url].filter(Boolean).join(" · ")}</p>}
                {getCandidateSteps(candidate) && <p>{getCandidateSteps(candidate)}</p>}
                {candidate.expected_result && <p><b>预期：</b>{typeof candidate.expected_result === "string" ? candidate.expected_result : JSON.stringify(candidate.expected_result)}</p>}
                <p>覆盖条款：{candidate.covered_clause_ids.join("、") || "未关联"}</p>
                {typeof candidate.dry_run_ok === "boolean" && <p>代码生成检查：{candidate.dry_run_ok ? "通过（未执行测试）" : "未通过"}</p>}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export default function AgentArtifactPanel({ artifacts, approval, selectedIds, onSelectionChange, onSave, saving }) {
  const sorted = useMemo(
    () => [...artifacts].sort((a, b) => (b.version || 0) - (a.version || 0) || (b.id || 0) - (a.id || 0)),
    [artifacts],
  );
  const [selectedArtifactId, setSelectedArtifactId] = useState(null);
  const selected = sorted.find((item) => item.id === selectedArtifactId) || sorted.find((item) => item.id === approval?.artifact_id) || sorted[0];
  const payload = artifactPayload(selected);
  const canSave = approval?.action_code === "save_generated_case_candidates" && approval?.status === "pending" && selected?.id === approval.artifact_id && selected?.status !== "saved";

  return (
    <aside className="test-agent-artifacts">
      <div className="test-agent-artifacts-head">
        <div><span>WORKSPACE</span><strong>Agent 产物</strong></div>
        {selected && <Tag>{TYPE_LABELS[selected.artifact_type] || selected.artifact_type}</Tag>}
      </div>

      {sorted.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Agent 产物会显示在这里" />
      ) : (
        <>
          <div className="test-agent-artifact-tabs">
            {sorted.map((artifact) => (
              <button
                type="button"
                className={(artifact.id || artifact.artifact_id) === (selected?.id || selected?.artifact_id) ? "is-active" : ""}
                key={artifact.id || artifact.artifact_id}
                onClick={() => setSelectedArtifactId(artifact.id || artifact.artifact_id)}
              >
                {TYPE_LABELS[artifact.artifact_type] || artifact.artifact_type}
                <small>v{artifact.version || 1}</small>
              </button>
            ))}
          </div>

          {(payload.warnings || []).length > 0 && <div role="status" className="test-agent-warning">{payload.warnings.join("；")}</div>}
          {selected?.status === "saved" && <div role="status" className="test-agent-saved">已保存到正式用例管理</div>}

          {selected?.artifact_type === "test_case_set" ? (
            <CandidateView
              payload={payload}
              selectedIds={selectedIds}
              onSelectionChange={onSelectionChange}
              onSave={() => onSave?.(selected)}
              saving={saving}
              canSave={canSave}
            />
          ) : selected?.artifact_type === "coverage_matrix" || selected?.artifact_type === "coverage_plan" ? (
            <CoverageView payload={payload} />
          ) : (
            <div className="test-agent-artifact-content"><pre>{JSON.stringify(payload, null, 2)}</pre></div>
          )}
        </>
      )}
    </aside>
  );
}
