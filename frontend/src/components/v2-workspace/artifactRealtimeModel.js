// P09.3B：Artifact Revision realtime 状态合并（纯函数，供 FunctionCasePage 消费）。
// SSE 只携带 compact 元数据（artifact_id/project_id/from_revision/to_revision/run_id/
// conversation_id/summary/change_counts），完整 Diff 走后端 GET diff。

export const ARTIFACT_EVENT_TYPES = new Set(["artifact_revision_created", "artifact_diff_created"]);

export function artifactEventFromStream(rawEvent) {
  // rawEvent: Conversation SSE 事件对象（含 event_type + payload_json），或已完成归一对象
  const type = rawEvent?.event_type ?? rawEvent?.type;
  if (!ARTIFACT_EVENT_TYPES.has(type)) return null;
  const payload = rawEvent?.payload_json ?? rawEvent?.payload ?? rawEvent;
  const artifactId = payload?.artifact_id;
  if (typeof artifactId !== "number") return null;
  const to = payload?.to_revision ?? payload?.revision;
  if (typeof to !== "number") return null;
  return {
    artifactId,
    projectId: typeof payload?.project_id === "number" ? payload.project_id : null,
    fromRevision: payload?.from_revision ?? (to > 0 ? to - 1 : null),
    toRevision: to,
    runId: payload?.run_id ?? null,
    conversationId: payload?.conversation_id ?? null,
    sequenceNo: Number(rawEvent?.sequence_no ?? rawEvent?.sequenceNo ?? 0) || 0,
    summary: payload?.summary ?? "",
    changeCounts: normalizeCounts(payload?.change_counts, payload?.changes),
    domainCounts: normalizeDomainCounts(payload?.domain_change_counts),
  };
}

export function normalizeCounts(value, changes = null) {
  const base = { added: 0, updated: 0, deleted: 0, moved: 0 };
  if (value && typeof value === "object") {
    for (const key of Object.keys(base)) {
      const n = Number(value[key]);
      if (Number.isFinite(n) && n > 0) base[key] += Math.floor(n);
    }
  }
  if (!Object.values(base).some(Boolean) && Array.isArray(changes)) {
    for (const change of changes) if (change?.change in base) base[change.change] += 1;
  }
  return base;
}

export function normalizeDomainCounts(value) {
  const base = { modules_added: 0, cases_added: 0, modules_deleted: 0,
    cases_deleted: 0, updated: 0, moved: 0 };
  if (!value || typeof value !== "object") return base;
  for (const key of Object.keys(base)) {
    const n = Number(value[key]);
    if (Number.isFinite(n) && n > 0) base[key] = Math.floor(n);
  }
  return base;
}

export function initialState({ artifactId, currentRevision }) {
  return {
    artifactId: Number(artifactId),
    currentRevision: Number(currentRevision) || 0,
    targetRevision: Number(currentRevision) || 0,
    fromRevision: null,
    toRevision: null,
    runId: null,
    conversationId: null,
    sequenceNo: 0,
    changeCounts: { added: 0, updated: 0, deleted: 0, moved: 0 },
    pending: false,
  };
}

// 返回新的 state；不相关/重复/乱序事件返回 null（无需刷新）。
export function applyArtifactEvent(state, event) {
  if (event.artifactId !== state.artifactId) return null; // §9 其它 Artifact 忽略
  if (event.toRevision <= state.currentRevision) return null; // §10 duplicate/replay
  if (event.toRevision <= state.targetRevision) return null; // §11 already observed
  if (event.sequenceNo && event.sequenceNo <= state.sequenceNo) return null; // 乱序回放
  const counts = { ...state.changeCounts };
  for (const key of Object.keys(counts)) counts[key] += event.changeCounts[key];
  const from = state.fromRevision == null ? event.fromRevision : Math.min(state.fromRevision, event.fromRevision ?? Infinity);
  return {
    ...state,
    targetRevision: Math.max(state.targetRevision, event.toRevision),
    fromRevision: from === Infinity ? null : from,
    toRevision: Math.max(state.toRevision ?? event.toRevision, event.toRevision),
    runId: event.runId ?? state.runId,
    conversationId: event.conversationId ?? state.conversationId,
    sequenceNo: Math.max(state.sequenceNo, event.sequenceNo),
    changeCounts: counts,
    pending: true,
  };
}

export function markRefreshed(state, loadedRevision) {
  const revision = Number(loadedRevision) || state.currentRevision;
  if (revision < state.targetRevision) {
    // §12 bounded retry：刷新仍未追到最新观察值，保持 pending 由调用方再次刷新
    return { ...state, currentRevision: revision, pending: true };
  }
  return {
    ...state,
    currentRevision: revision,
    targetRevision: revision,
    pending: false,
    fromRevision: null,
    toRevision: null,
    changeCounts: { added: 0, updated: 0, deleted: 0, moved: 0 },
  };
}
