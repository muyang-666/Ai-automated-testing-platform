// P09.1 Artifact View State（纯 UI 状态，session 内有效，绝不写 Artifact DB）。
//
// - collapsedNodeIds：以 Artifact 为 key 各自维护（切换 Artifact 不丢）；
// - selectedNodeId：切换 Artifact 时清空（避免旧选中冒充新树）。
import { useCallback, useMemo, useState } from "react";

export default function useArtifactViewState(artifactKey) {
  const [byArtifact, setByArtifact] = useState(() => ({}));
  const [selectedByArtifact, setSelectedByArtifact] = useState(() => ({}));

  // artifactKey = active Artifact id（null 时无视图）
  const collapsedIds = useMemo(
    () => (artifactKey != null && byArtifact[artifactKey] ? byArtifact[artifactKey] : []),
    [artifactKey, byArtifact],
  );
  // 选中按 Artifact 各自维护：切换 Artifact 自动落到新 Artifact 的选中（无则 null）
  const selectedNodeId = artifactKey != null ? (selectedByArtifact[artifactKey] ?? null) : null;

  const toggleCollapse = useCallback((nodeId) => {
    if (artifactKey == null) return;
    setByArtifact((current) => {
      const base = current[artifactKey] ? [...current[artifactKey]] : [];
      const next = base.includes(nodeId)
        ? base.filter((id) => id !== nodeId)
        : [...base, nodeId];
      return { ...current, [artifactKey]: next };
    });
  }, [artifactKey]);

  const selectNode = useCallback((nodeId) => {
    if (artifactKey == null) return;
    setSelectedByArtifact((current) => ({ ...current, [artifactKey]: nodeId }));
  }, [artifactKey]);

  return { collapsedIds, selectedNodeId, toggleCollapse, selectNode };
}
