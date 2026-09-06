// P09.3B §6-8：极薄的 Artifact Revision 事件桥。
// 只传播 artifact_revision_created / artifact_diff_created 的 compact 归一对象；
// 其它 Conversation SSE 事件不进入全 App React State，避免逐 token 重渲染。

let listeners = [];
let lastEvent = null;

export const agentArtifactEventBus = {
  subscribe(listener) {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((item) => item !== listener);
    };
  },
  publish(event) {
    if (event == null) return;
    lastEvent = event;
    for (const listener of listeners.slice()) {
      try {
        listener(event);
      } catch {
        // 订阅方异常不得破坏其它订阅者
      }
    }
  },
  getLastEvent() {
    return lastEvent;
  },
};
