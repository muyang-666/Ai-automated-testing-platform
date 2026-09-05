// 滚动跟随策略（纯函数，便于测试）。
export function isNearBottom(scrollTop, clientHeight, scrollHeight, threshold = 80) {
  if (!scrollHeight) return true;
  return scrollTop + clientHeight >= scrollHeight - threshold;
}

// eventKind: "open" | "own"（自己发送） | "stream"（新内容） | "refresh"
export function shouldAutoScroll({ eventKind, isNearBottomNow, hasUserScrolledUp }) {
  if (eventKind === "open" || eventKind === "own" || eventKind === "refresh") return true;
  if (eventKind === "stream") return isNearBottomNow && !hasUserScrolledUp;
  return false;
}
