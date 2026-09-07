// P09.3B §25-31/37-38：Change Summary 由真实 Artifact Revision 事件派生（按 run_id 聚合），
// 不信任 LLM 文本；每 run 一个聚合卡片，可展开 developer details。

import { normalizeCounts, normalizeDomainCounts } from "./artifactRealtimeModel.js";

export function aggregateByRun(events) {
  // revision/diff compact events describe the same committed Revision. Merge
  // them by run+artifact+toRevision and keep the richer payload once.
  const unique = new Map();
  for (const event of events) {
    if (!event || event.runId == null || event.artifactId == null || event.toRevision == null) continue;
    const key = `${event.runId}:${event.artifactId}:${event.toRevision}`;
    const previous = unique.get(key);
    if (!previous) unique.set(key, event);
    else unique.set(key, {
      ...previous, ...event,
      fromRevision: previous.fromRevision ?? event.fromRevision,
      changeCounts: richerCounts(previous.changeCounts, event.changeCounts),
      domainCounts: richerCounts(previous.domainCounts, event.domainCounts),
    });
  }
  const runs = new Map();
  for (const event of unique.values()) {
    const runId = event?.runId;
    if (runId == null) continue;
    let entry = runs.get(runId);
    if (!entry) {
      entry = {
        runId,
        artifacts: new Map(),
        fromRevision: null,
        toRevision: null,
        revisionCount: 0,
        changeCounts: { added: 0, updated: 0, deleted: 0, moved: 0 },
      };
      runs.set(runId, entry);
    }
    const artifactId = event.artifactId;
    let artifact = entry.artifacts.get(artifactId);
    if (!artifact) {
      artifact = { artifactId, projectId: event.projectId ?? null, fromRevision: null,
        toRevision: null, changeCounts: normalizeCounts(), domainCounts: normalizeDomainCounts() };
      entry.artifacts.set(artifactId, artifact);
    } else if (event.projectId != null) {
      artifact.projectId = event.projectId;
    }
    artifact.fromRevision = artifact.fromRevision == null ? event.fromRevision : Math.min(artifact.fromRevision, event.fromRevision ?? artifact.fromRevision);
    artifact.toRevision = Math.max(artifact.toRevision ?? event.toRevision, event.toRevision);
    artifact.changeCounts = addCounts(artifact.changeCounts, event.changeCounts);
    artifact.domainCounts = addCounts(artifact.domainCounts, event.domainCounts);
    entry.fromRevision = entry.fromRevision == null ? event.fromRevision : Math.min(entry.fromRevision, event.fromRevision ?? entry.fromRevision);
    entry.toRevision = Math.max(entry.toRevision ?? event.toRevision, event.toRevision);
    entry.revisionCount += 1;
    entry.changeCounts = addCounts(entry.changeCounts, event.changeCounts);
  }
  return [...runs.values()].map((run) => ({
    runId: run.runId,
    fromRevision: run.fromRevision,
    toRevision: run.toRevision,
    revisionCount: run.revisionCount,
    changeCounts: run.changeCounts,
    artifacts: [...run.artifacts.values()],
  }));
}

function richerCounts(a, b) {
  const left = a || {}, right = b || {};
  return Object.fromEntries([...new Set([...Object.keys(left), ...Object.keys(right)])]
    .map((key) => [key, Math.max(left[key] || 0, right[key] || 0)]));
}

function addCounts(a, b) {
  const next = { ...a };
  const incoming = b || {};
  for (const key of Object.keys(next)) next[key] += incoming[key] || 0;
  return next;
}

const LABELS = [
  ["added", "新增"],
  ["updated", "更新"],
  ["deleted", "删除"],
  ["moved", "移动"],
];

export function summaryLabel(counts, unit = "项") {
  const parts = [];
  for (const [key, verb] of LABELS) {
    const n = counts?.[key] || 0;
    if (n > 0) parts.push(`${verb} ${n} ${unit}`);
  }
  return parts.join("，") || "无变更";
}

export function domainSummaryLabel(domainCounts, counts) {
  const parts = [];
  const labels = [["modules_added", "新增", "个模块"], ["cases_added", "新增", "条用例"],
    ["modules_deleted", "删除", "个模块"], ["cases_deleted", "删除", "条用例"],
    ["updated", "更新", "项"], ["moved", "移动", "项"]];
  for (const [key, verb, unit] of labels) if (domainCounts?.[key]) parts.push(`${verb} ${domainCounts[key]} ${unit}`);
  return parts.join("，") || summaryLabel(counts, "项");
}

export function revisionLabel(fromRevision, toRevision) {
  if (fromRevision != null && toRevision != null) return `版本 ${fromRevision} → ${toRevision}`;
  if (toRevision != null) return `版本 ${toRevision}`;
  return "";
}

export function summaryCard(run, artifactId) {
  const artifact = (run?.artifacts || []).find((item) => item.artifactId === artifactId) ?? run;
  const counts = artifact?.changeCounts ?? { added: 0, updated: 0, deleted: 0, moved: 0 };
  return {
    title: "变更",
    body: domainSummaryLabel(artifact.domainCounts, counts),
    revisionRange: revisionLabel(artifact.fromRevision, artifact.toRevision),
    runId: run.runId,
  };
}
