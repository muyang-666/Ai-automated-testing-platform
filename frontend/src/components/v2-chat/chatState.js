// Conversation 级状态纯函数（P06 fix：Stop 目标 / 顶部状态 / 发送门禁 / 重命名同步）。
//
// 与后端 conversation snapshot 字段对齐：{ active_run, latest_run, queue_state }。
// active_run  = 正在执行的 head（Stop 的唯一目标）；
// latest_run  = 最近一次提交的 run（可能只是 queued follow-up，不能当 Stop 目标）；
// queue_state = idle / executable / paused（后端 pause-guard 语义）。

// 顶部“Conversation 当前状态”，只由 snapshot 派生，绝不因“提交了一个 follow-up”而改。
// A running + B queued → active_run.status = running → 顶部仍是 Running；
// B 自己是 queued 由 turnModel（run 尚无终态且不是 active head）负责。
export function conversationState(snapshot) {
  if (!snapshot) return "idle";
  const activeStatus = snapshot.active_run?.status;
  if (activeStatus && activeStatus !== "succeeded") return activeStatus;
  if (snapshot.queue_state === "executable") return "queued"; // head 已排队、worker 未 claim
  if (snapshot.queue_state === "paused") return "paused";     // 上一轮失败/中断 pause-guard
  const latest = snapshot.latest_run?.status;
  if (latest && latest !== "succeeded") return latest;        // 终态消息（failed/interrupted/cancelled）
  return "idle";
}

// Stop 目标 = 正在执行的 active head。已提交但排队的 follow-up（active_run 之外）
// 不是可取消对象——取消它只会放跑真正在跑的那一轮。
export function stopTargetRun(snapshot) {
  return snapshot?.active_run?.id ?? null;
}

// 发送门禁：只由“对话状态/配置”决定；网络请求在途（submitPending/loading/busy）
// 一律不参与——Running 时永远允许继续发送 follow-up，禁止静默吞消息。
export function canSendMessage({ hasActive, phase, modelReady }) {
  return Boolean(hasActive) && phase !== "paused" && modelReady !== false;
}

// 自动命名/手动重命名成功后，同时更新 conversations list 与 active conversation，
// 保证 sidebar 与顶部 header title 一致。
export function mergeRenamedConversation({ conversations, active, conversationId, title }) {
  return {
    conversations: conversations.map((c) => (c.id === conversationId ? { ...c, title } : c)),
    active: active && active.id === conversationId ? { ...active, title } : active,
  };
}
