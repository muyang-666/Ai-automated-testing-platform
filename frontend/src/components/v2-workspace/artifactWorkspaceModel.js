// P09.1 Artifact Workspace 轻量纯逻辑（可测）。
// 竞态/409 语义抽成纯函数，hooks 与测试共用同一实现，避免行为漂移。

// Conversation/Artifact 快速切换的 late-response 裁决：
// 只有"请求时的会话/序号仍是当前"的结果才允许落地。
export function shouldApplyResponse({ requestConversationId, currentConversationId,
  requestToken, currentToken }) {
  return requestConversationId === currentConversationId && requestToken === currentToken;
}

// Focus 失败反馈：409（含 conversation_conflict）→ 保留旧 Artifact/MindMap 并给出可读消息。
export function focusFailureMessage({ httpStatus, detail }) {
  if (httpStatus === 409) {
    if (detail && typeof detail === "string") return detail;
    return "Agent 正在执行，请等待本轮完成后再切换测试资产。";
  }
  if (httpStatus === 404) return "该 Artifact 已不可访问或已删除。";
  if (detail && typeof detail === "string") return detail;
  return "切换测试资产失败，请稍后重试。";
}

// 树加载结果在哪种情形应被丢弃（不覆盖当前视图）。
export function isTreeLoadStale({ requestKey, currentKey, requestSeq, currentSeq }) {
  return requestKey !== currentKey || requestSeq !== currentSeq;
}
