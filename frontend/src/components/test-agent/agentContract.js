export const ACTIVE_STATUSES = new Set(["queued", "running"]);
export const GATE_ACTIONS = {
  scope_gate: "confirm_case_generation_scope",
  coverage_gate: "confirm_case_coverage_plan",
  save_gate: "save_generated_case_candidates",
};

export function caseRunRequest(sessionId, data) {
  const input = data.input || data;
  return {
    session_id: sessionId,
    source_type: input.source_type,
    source_id: input.source_id,
    case_types: input.case_types,
    max_cases: input.max_cases,
    user_goal: input.user_goal,
    idempotency_key: data.idempotency_key,
  };
}

export function listData(response, key) {
  const data = response?.data ?? response;
  return Array.isArray(data) ? data : data?.[key] || data?.items || [];
}

export function currentApproval(run, approvals) {
  if (run?.status !== "waiting_approval") return null;
  const action = GATE_ACTIONS[run.output_json?.workflow_state?.phase];
  return approvals.find((item) => item.status === "pending" && item.action_code === action) || null;
}

export function candidateRows(artifact) {
  return (artifact?.payload_json?.candidates || []).map((item) => ({
    ...item.case,
    candidate_id: item.candidate_id,
    revision: item.revision,
    covered_clause_ids: item.covered_clause_ids || [],
    dry_run_ok: item.dry_run_ok,
  }));
}

export function coverageRows(payload) {
  const matrix = Array.isArray(payload.matrix) ? payload.matrix : [];
  const calculated = matrix.length > 0;
  return (payload.atomic_clauses || []).map((clause) => {
    const result = matrix.find((row) => row.clause_id === clause.clause_id);
    return {
      ...clause,
      calculated,
      covered: result?.covered ?? false,
      covered_by: result?.covered_by || [],
      dimensions: (payload.coverage_plan || []).filter((row) => row.clause_id === clause.clause_id).map((row) => row.dimension),
    };
  });
}

export function errorText(error, fallback = "请求失败，请稍后重试") {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => `${(item.loc || []).slice(1).join(".")}：${item.msg}`).join("；");
  if (typeof detail === "string") return detail;
  return error?.message || fallback;
}

// 会话/来源启动失败时的可操作提示。4xx 意味着所选项目或来源本身不可用，
// 引导用户回到来源页面重新“交给 Agent”，而不是只显示一句“发送失败”。
export function sessionStartErrorText(error) {
  const status = error?.response?.status;
  if (status >= 400 && status < 500) {
    return `${errorText(error, "会话创建被拒绝")}。项目或来源可能已失效、被删除或无权访问，请回到需求/接口文档页面重新点击“交给 Agent”选择有效来源后重试。`;
  }
  if (status >= 500) {
    return `${errorText(error, "服务处理失败")}。请稍后重试；若持续失败，请联系管理员检查项目数据。`;
  }
  return errorText(error);
}
