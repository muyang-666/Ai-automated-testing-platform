// Turn 归组纯函数（P06 Frontend UX Hardening 核心，P06 fix 轮加固工具归属）。
//
// 数据库 Message sequence 是物理落库顺序；Follow-up 场景下 B.user 可能先于
// A.assistant 落库（sequence 交错）。UI 层一律按"所属 Turn"归组，而不是按
// 物理 sequence 平铺，也不是"遇到下一个 user 就截断上一轮"。
//
// 归组依据优先级：
//   1) 主：message.run_id / 事件 run_id（后端已提供）→ 该 Run 的 user message；
//   2) 兜底：缺少 run_id 的旧行 → 归属最近一条 sequence 更小的 user message
//      （仅在数据缺失时使用，不参与测试主路径）。
//
// 输入约定（与 conversationApi 返回一致）：
//   message: {id, message_id, role, sequence_no, run_id, content, stop_reason?, error_code?}
//   event:   {sequence_no, event_type, run_id, payload:{tool_call_id, tool_name, ...}}
export function extractText(content) {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if (typeof block === "string") return block;
        if (block?.type === "text") return block.text || "";
        if (block?.type === "toolCall") return `🔧 ${block.name}`;
        return "";
      })
      .join("");
  }
  return "";
}

// 每条消息的 owner sequence：其所属 Run 的 user message 序号。
export function ownerSequenceOf(message, userSeqByRunId) {
  if (message.role === "user") return message.sequence_no;
  const owner = userSeqByRunId.get(message.run_id);
  return owner ?? null; // 由调用方决定兜底
}

// messages/events → 结构化 Turns。纯函数，无 DOM/React 依赖。
export function buildConversationTurns({
  messages = [],
  events = [],
  overrides = {},
}) {
  const overridesMap = overrides.runs || {};
  const userMessages = messages.filter((m) => m.role === "user");
  const userSeqByRunId = new Map(
    userMessages.filter((m) => m.run_id != null).map((m) => [m.run_id, m.sequence_no]),
  );

  // 事件 → 工具活动。合并键 = (run_id, tool_call_id)：不同 Run 复用同一
  // tool_call_id 时互不污染（否则 A 的 started 会被 B 的 finished 覆盖终态）。
  // 排序键 = 事件 sequence_no（同 Turn 内按调用先后，而非 callId 字典序）。
  const toolByKey = new Map();
  const terminalStatusByRunId = new Map();
  for (const event of events) {
    if (["conversation_tool_started", "conversation_tool_finished"].includes(event.event_type)) {
      const callId = event.payload?.tool_call_id;
      if (!callId) continue;
      const runId = event.run_id ?? null;
      const key = `${runId ?? ""}::${callId}`;
      const existing = toolByKey.get(key) || {
        toolCallId: callId,
        runId,
        toolName: event.payload?.tool_name || "",
        status: "running",
        errorCode: null,
        seq: event.sequence_no ?? 0,
      };
      if (!existing.toolName && event.payload?.tool_name) existing.toolName = event.payload.tool_name;
      if (existing.runId == null && runId != null) existing.runId = runId;
      existing.seq = Math.min(existing.seq, event.sequence_no ?? existing.seq);
      if (event.event_type === "conversation_tool_finished") {
        existing.status = event.payload?.is_error ? "error" : "success";
        existing.errorCode = event.payload?.error_code ?? null;
      }
      toolByKey.set(key, existing);
    } else if (["run_succeeded", "run_failed", "run_cancelled", "run_interrupted"].includes(event.event_type)) {
      if (event.run_id != null) terminalStatusByRunId.set(event.run_id, event.event_type.replace("run_", ""));
    }
  }
  const toolActivities = [...toolByKey.values()]
    .sort((a, b) => (a.seq - b.seq) || (a.toolCallId < b.toolCallId ? -1 : 1));

  // 兜底：无 run_id 的非 user 消息归属最近的 user。
  const ownerByMessageId = new Map();
  let lastUserSeq = null;
  for (const message of messages) {
    const owner = ownerSequenceOf(message, userSeqByRunId);
    if (message.role === "user") {
      lastUserSeq = message.sequence_no;
      ownerByMessageId.set(message.id ?? message.message_id ?? message.sequence_no, message.sequence_no);
    } else if (owner != null) {
      ownerByMessageId.set(message.id ?? message.message_id ?? message.sequence_no, owner);
    } else if (lastUserSeq != null && lastUserSeq < message.sequence_no) {
      ownerByMessageId.set(message.id ?? message.message_id ?? message.sequence_no, lastUserSeq);
    }
  }

  const turnsByOwner = new Map();
  for (const message of messages) {
    const key = ownerByMessageId.get(message.id ?? message.message_id ?? message.sequence_no);
    if (key == null) continue; // 数据异常，跳过而非错误归组
    let turn = turnsByOwner.get(key);
    if (!turn) {
      turn = {
        ownerSequence: key,
        runId: message.run_id ?? null,
        userMessage: null,
        userSequence: null,
        userText: "",
        messages: [],
        assistantTexts: [],
        assistantMessage: null,
        toolActivities: [],
        status: null, // running/succeeded/failed/cancelled/interrupted/queued
        errorCode: null,
        streamingText: "",
        queued: false,
      };
      turnsByOwner.set(key, turn);
    }
    turn.messages.push(message);
    if (message.role === "user") {
      turn.userMessage = message;
      turn.userSequence = message.sequence_no;
      turn.runId = message.run_id ?? turn.runId;
      turn.userText = extractText(message.content);
    } else if (message.role === "assistant") {
      turn.assistantMessages = turn.assistantMessages || [];
      turn.assistantMessages.push(message);
      if (message.stop_reason !== "toolUse") turn.assistantTexts.push(extractText(message.content));
      if (message.stop_reason !== "toolUse") turn.assistantMessage = message;
      if (message.error_code) turn.errorCode = message.error_code;
    }
  }

  // 工具活动归属 Turn：只接受两种可信来源 —— DB 事件 run_id，或调用方在事件
  // 到达时解析好的 overrides.toolOwners（callId -> ownerSequence）。
  // 禁止“兜底挂到最新 Turn”：旧数据缺失归属时会错误迁移到每个新回答之后。
  const turns = [...turnsByOwner.values()].sort((a, b) => a.ownerSequence - b.ownerSequence);
  const toolRunToTurn = new Map();
  const toolOwnerToTurn = new Map();
  for (const turn of turns) {
    if (turn.runId != null) toolRunToTurn.set(turn.runId, turn);
    toolOwnerToTurn.set(turn.ownerSequence, turn);
  }
  const explicitOwners = overrides.toolOwners || new Map();
  for (const activity of toolActivities) {
    const byRun = activity.runId != null ? toolRunToTurn.get(activity.runId) : undefined;
    const byOwner = explicitOwners.get(activity.toolCallId);
    const target = byRun || (byOwner != null && toolOwnerToTurn.get(byOwner));
    if (target) {
      target.toolActivities.push(activity);
      activity.turnOwnerSequence = target.ownerSequence;
    }
  }

  // 状态：events 终态 > overrides(active run 状态) > 无回复=queued(等待 head)
  const activeRunId = overrides.activeRunId ?? null;
  for (const turn of turns) {
    if (turn.runId != null) {
      const terminal = terminalStatusByRunId.get(turn.runId);
      if (terminal) {
        turn.status = terminal;
      } else if (overridesMap[turn.runId]) {
        turn.status = overridesMap[turn.runId].status;
        turn.errorCode = overridesMap[turn.runId].errorCode || null;
      } else if (turn.runId === activeRunId) {
        // 活跃 head（已 claim / 执行中）：一律 running —— 流式文本在途时
        // 落库 assistant 消息可能尚未写入，不能因此标成 queued。
        turn.status = "running";
      }
    }
    // 尚无任何 Run 信息的纯 user turn：提交后未执行 → queued（follow-up 或等待 claim）
    if (turn.status == null && !turn.assistantMessages?.length) {
      turn.status = "queued";
    }
    if (overrides.streaming && turn.runId != null && overrides.streaming.runId === turn.runId) {
      turn.streamingText = overrides.streaming.text;
    }
  }
  return turns;
}

export function statusLabel(status) {
  return {
    idle: "空闲", queued: "排队中", running: "回答中", succeeded: "已完成",
    failed: "失败", interrupted: "已中断", cancelled: "已取消", paused: "已暂停",
  }[status] || "";
}
