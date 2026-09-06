// P09.1 Workspace 容器：Conversation ↔ Focused Artifact ↔ Artifact Tree 同窗。
// 数据状态在 useArtifactWorkspace，纯 UI 视图状态在 useArtifactViewState。
import { useCallback } from "react";
import ArtifactPanel from "./ArtifactPanel";
import useArtifactWorkspace from "./hooks/useArtifactWorkspace";
import useArtifactViewState from "./hooks/useArtifactViewState";

export default function ArtifactWorkspace({
  conversationId, focusedArtifactId, conversationProjectId, onConversationRefresh,
}) {
  const store = useArtifactWorkspace({
    conversationId,
    focusedArtifactId,
    conversationProjectId,
    onConversationRefresh,
  });
  const artifactKey = store.active?.id ?? null;
  const view = useArtifactViewState(artifactKey);

  const retryTree = useCallback(() => {
    // tree 加载失败重试；active 丢失（404）时回到 focused 加载入口
    if (store.active) return store.reloadActive();
    if (focusedArtifactId != null) return store.focusArtifact({ id: focusedArtifactId });
    return Promise.resolve(false);
  }, [store, focusedArtifactId]);

  return (
    <ArtifactPanel
      artifacts={store.artifacts}
      listLoading={store.listLoading}
      active={store.active}
      currentRevision={store.currentRevision}
      tree={store.tree}
      treeLoading={store.treeLoading}
      treeError={store.treeError}
      unavailable={store.unavailable}
      focusError={store.focusError}
      busy={store.busy}
      artifactKey={artifactKey}
      treeNonce={store.treeNonce}
      collapsedIds={view.collapsedIds}
      selectedNodeId={view.selectedNodeId}
      onFocus={store.focusArtifact}
      onCreate={store.createArtifact}
      onRetryTree={retryTree}
      onSelectNode={view.selectNode}
      onToggleCollapse={view.toggleCollapse}
    />
  );
}
