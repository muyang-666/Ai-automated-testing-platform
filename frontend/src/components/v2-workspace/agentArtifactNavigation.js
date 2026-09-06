// P09.3B §32-36：View Changes → FunctionCasePage Diff 的轻量跨页意图（不做 Router）。

let listeners = [];
let pending = null;

export const agentArtifactNavigation = {
  subscribe(listener) {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((item) => item !== listener);
    };
  },
  publish(intent) {
    if (intent == null) return;
    pending = intent;
    for (const listener of listeners.slice()) {
      try {
        listener(intent);
      } catch {
        // 订阅方异常不扩散
      }
    }
  },
  getPending() {
    return pending;
  },
  clear() {
    pending = null;
  },
};

// 由 compact Artifact Revision 事件构造 diff 意图
export function diffIntentFromArtifactEvent(event) {
  if (event?.artifactId == null || event?.fromRevision == null || event?.toRevision == null) return null;
  return {
    page: "functionCases",
    projectId: event.projectId ?? null,
    artifactId: event.artifactId,
    fromRevision: event.fromRevision,
    toRevision: event.toRevision,
  };
}
