// P09.3B §25-31/37-38：Change Summary 由真实 Artifact Revision 事件派生（按 run_id 聚合），
// 不信任 LLM 文本；每 run 一个聚合卡片，可展开 developer details。

import { normalizeCounts } from "./artifactRealtimeModel.js";

export function aggregateByRun(events) {
  const runs = new Map();
  for (const event of events) {
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
      artifact = { artifactId, projectId: event.projectId ?? null, fromRevision: null, toRevision: null, changeCounts: normalizeCounts() };
      entry.artifacts.set(artifactId, artifact);
    } else if (event.projectId != null) {
      artifact.projectId = event.projectId;
    }
    artifact.fromRevision = artifact.fromRevision == null ? event.fromRevision : Math.min(artifact.fromRevision, event.fromRevision ?? artifact.fromRevision);
    artifact.toRevision = Math.max(artifact.toRevision ?? event.toRevision, event.toRevision);
    artifact.changeCounts = addCounts(artifact.changeCounts, event.changeCounts);
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

function addCounts(a, b) {
  const next = { ...a };
  for (const key of Object.keys(next)) next[key] += b[key] || 0;
  return next;
}

const LABELS = [
  ["added", "新增"],
  ["updated", "更新"],
  ["deleted", "删除"],
  ["moved", "移动"],
];

export function summaryLabel(counts, typeWord = "用例") {
  const parts = [];
  for (const [key, verb] of LABELS) {
    const n = counts?.[key] || 0;
    if (n > 0) parts.push(`${verb} ${n} 条${typeWord}`);
  }
  return parts.join("，") || "无变更";
}

export function summaryCard(run, artifactId) {
  const artifact = (run?.artifacts || []).find((item) => item.artifactId === artifactId) ?? run;
  const counts = artifact?.changeCounts ?? { added: 0, updated: 0, deleted: 0, moved: 0 };
  return {
    title: "Changes",
    body: summaryLabel(counts),
    revisionRange: `Revision ${artifact.fromRevision ?? "?"} → ${artifact.toRevision ?? "?"}`,
    runId: run.runId,
  };
}
