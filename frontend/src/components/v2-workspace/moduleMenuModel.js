export function nextModuleMenu(openNodeId, action) {
  if (action.type === "open") return action.nodeId;
  if (action.type === "close" || action.type === "select" || action.type === "escape") return null;
  return openNodeId;
}
