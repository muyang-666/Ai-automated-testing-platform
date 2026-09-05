import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as conversationApi from "./conversationApi";
import { runErrorMessage } from "./conversationErrors.js";
import { buildConversationTurns, extractText } from "./turnModel.js";

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random()}`);
const STATE_LABELS = {
  idle: "空闲",
  queued: "排队中",
  running: "AI 正在回答",
  paused: "上一轮失败/中断，后续消息已暂停",
  failed: "失败",
  interrupted: "已中断",
  cancelled: "已取消",
};

// 内容块渲染辅助：assistant 结构化 content → 文本
export function blocksToText(content) {
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

export default function useConversationChat(userId) {
  const [conversations, setConversations] = useState([]);
  const [active, setActive] = useState(null); // {id,title,...}
  const [snapshot, setSnapshot] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activity, setActivity] = useState([]); // 兼容旧渲染（turns 为正式结构）
  const [allEvents, setAllEvents] = useState([]); // 原始事件（run_id 齐全），供 Turn 归组
  const [toolOwners, setToolOwners] = useState(() => new Map()); // toolCallId -> owner user seq
  const messagesRef = useRef([]);
  const allEventsRef = useRef([]);
  const toolOwnersRef = useRef(new Map());
  const [streaming, setStreaming] = useState("");
  const [phase, setPhase] = useState("idle"); // idle/queued/running/paused/failed/interrupted/cancelled
  const [error, setError] = useState("");
  const [runError, setRunError] = useState("");
  const [busy, setBusy] = useState(false);
  const [capabilities, setCapabilities] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const lastEventSequence = useRef(0);
  const stopStream = useRef(null);
  const runRef = useRef(null);
  const activeId = useRef(null);
  const generation = useRef(0);
  const refreshSequence = useRef(0);
  const refreshTimer = useRef(null);
  const committedIds = useRef(new Set());
  const pendingText = useRef(new Map());

  const resolveOwnerForRun = (runId, msgs) => {
    if (runId != null) {
      for (const m of msgs) if (m.role === "user" && m.run_id === runId) return m.sequence_no;
    }
    if (!msgs.length) return null;
    return msgs[msgs.length - 1].sequence_no; // 活跃 head 用户消息（当前 streaming/工具所属轮次）
  };

  const backfillToolOwners = useCallback((msgs) => {
    let changed = false;
    for (const event of allEventsRef.current) {
      if (!["conversation_tool_started", "conversation_tool_finished"].includes(event.event_type)) continue;
      const callId = event.payload?.tool_call_id;
      if (!callId || toolOwnersRef.current.has(callId)) continue;
      if (event.run_id == null) continue; // 无 run_id 的历史事件只允许“当前轮次”解析，刷新时不做迁移
      toolOwnersRef.current.set(callId, resolveOwnerForRun(event.run_id, msgs));
      changed = true;
    }
    if (changed) setToolOwners(new Map(toolOwnersRef.current));
  }, []);

  const refresh = useCallback(async (conversationId) => {
    if (activeId.current !== conversationId) return null;
    const scope = generation.current;
    const sequence = ++refreshSequence.current;
    const [snapRes, msgRes] = await Promise.all([
      conversationApi.getConversation(conversationId),
      conversationApi.getMessages(conversationId),
    ]);
    const snap = snapRes.data;
    const msgs = msgRes.data;
    if (scope !== generation.current || activeId.current !== conversationId
      || sequence !== refreshSequence.current) return null;
    setSnapshot(snap);
    setMessages(msgs);
    committedIds.current = new Set(msgs.map((message) => message.message_id));
    messagesRef.current = msgs;
    backfillToolOwners(msgs);
    for (const id of committedIds.current) pendingText.current.delete(id);
    setStreaming([...pendingText.current.values()].join("\n\n"));
    const latestStatus = snap.latest_run?.status;
    const nextPhase = snap.active_run?.status
      || (snap.queue_state === "paused" ? "paused"
        : ["failed", "interrupted", "cancelled"].includes(latestStatus) ? latestStatus : "idle");
    setPhase(nextPhase);
    if (["failed", "interrupted"].includes(nextPhase)) {
      setRunError(runErrorMessage(snap.latest_run?.error_code));
    } else if (nextPhase !== "cancelled") {
      setRunError("");
    }
    runRef.current = snap.active_run?.id || null;
    return { snap, msgs };
  }, [backfillToolOwners]);

  const stopAll = useCallback(() => {
    ++generation.current; // Invalidate in-flight snapshots and old stream callbacks.
    stopStream.current?.();
    stopStream.current = null;
    clearTimeout(refreshTimer.current);
    refreshTimer.current = null;
  }, []);

  const connectEvents = useCallback((conversationId) => {
    stopStream.current?.();
    const scope = generation.current;
    const isCurrent = () => scope === generation.current && activeId.current === conversationId;
    const scheduleRefresh = () => {
      if (refreshTimer.current) return;
      // Several messages and the terminal event arrive together. Fetch one
      // snapshot instead of issuing two full-history requests per event.
      refreshTimer.current = setTimeout(() => {
        refreshTimer.current = null;
        if (isCurrent()) void refresh(conversationId).catch(() => {
          if (isCurrent()) setConnectionError("正在恢复对话连接…");
        });
      }, 50);
    };
    stopStream.current = conversationApi.streamConversationEvents({
      conversationId,
      afterSequence: lastEventSequence.current,
      onEvent: (event) => {
        if (!isCurrent() || event.sequence_no <= lastEventSequence.current) return;
        lastEventSequence.current = event.sequence_no;
        setConnectionError("");
        const nextEvents = [...allEventsRef.current.slice(-499), {
          sequence_no: event.sequence_no, event_type: event.event_type,
          run_id: event.run_id ?? null, payload: event.payload || {},
        }];
        allEventsRef.current = nextEvents;
        setAllEvents(nextEvents);
        if (["conversation_tool_started", "conversation_tool_finished"].includes(event.event_type)) {
          const callId = event.payload?.tool_call_id;
          if (callId && !toolOwnersRef.current.has(callId)) {
            toolOwnersRef.current.set(callId, resolveOwnerForRun(event.run_id, messagesRef.current));
            setToolOwners(new Map(toolOwnersRef.current));
          }
        }
        if (event.event_type === "conversation_text_delta") {
          const id = event.payload?.message_id;
          if (!committedIds.current.has(id)) {
            pendingText.current.set(id, (pendingText.current.get(id) || "") + (event.payload?.text || ""));
            setStreaming([...pendingText.current.values()].join("\n\n"));
          }
        } else if (event.event_type === "conversation_tool_started") {
          setActivity((prev) => [...prev.slice(-49), { id: event.sequence_no, text: `✓ 调用工具 ${event.payload?.tool_name || ""}` }]);
        } else if (event.event_type === "conversation_tool_finished") {
          setActivity((prev) => [...prev.slice(-49), { id: event.sequence_no, text: `✓ 工具 ${event.payload?.tool_name || ""} 完成` }]);
        } else if (["run_started", "run_resumed"].includes(event.event_type)) {
          setPhase("running");
          setRunError("");
        } else if (event.event_type === "run_succeeded") {
          setPhase("idle");
          scheduleRefresh(); // Keep visible text until the committed message loads.
        } else if (event.event_type === "run_failed") {
          setPhase("failed");
          setRunError(runErrorMessage(event.payload?.error_code));
          scheduleRefresh();
        } else if (event.event_type === "run_cancelled") {
          setPhase("cancelled");
          scheduleRefresh();
        } else if (event.event_type === "run_interrupted") {
          setPhase("interrupted");
          setRunError("Agent Worker 已中断，本轮没有生成回答，请重新发送。");
          scheduleRefresh();
        } else if (event.event_type === "conversation_message_committed") {
          scheduleRefresh();
        }
      },
      onOpen: () => { if (isCurrent()) setConnectionError(""); },
      onError: () => { if (isCurrent()) setConnectionError("回复连接暂时中断，正在自动恢复…"); },
    });
  }, [refresh]);

  const openConversation = useCallback(async (conversation) => {
    stopAll();
    activeId.current = conversation.id;
    const scope = generation.current;
    lastEventSequence.current = 0;
    committedIds.current = new Set();
    pendingText.current = new Map();
    messagesRef.current = [];
    allEventsRef.current = [];
    toolOwnersRef.current = new Map();
    setToolOwners(new Map());
    setActive(conversation);
    setError("");
    setRunError("");
    setStreaming("");
    setMessages([]);
    setActivity([]);
    setAllEvents([]);
    setConnectionError("");
    setSnapshot(null);
    setPhase("idle");
    runRef.current = null;
    // Establish the subscription before slow snapshot requests. It survives
    // idle time and reconstructs in-flight text; committed IDs suppress replay.
    connectEvents(conversation.id);
    try { await refresh(conversation.id); } catch (err) {
      if (scope === generation.current) setError(String(err?.message || "对话加载失败"));
    }
  }, [refresh, connectEvents, stopAll]);

  const newConversation = useCallback(async () => {
    setBusy(true);
    try {
      const created = await conversationApi.createConversation({ title: "新对话", project_id: null });
      const list = await conversationApi.listConversations();
      setConversations(list.data);
      await openConversation(created.data);
    } catch (err) {
      setError(String(err?.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
    }
  }, [openConversation]);



  const setTitle = useCallback(async (conversationId, rawTitle) => {
    const title = String(rawTitle || "").replace(/\s+/g, " ").trim();
    if (!title || title.length > 200) return;
    try {
      const renamed = await conversationApi.renameConversation(conversationId, { title });
      setConversations((prev) => prev.map((c) => (c.id === conversationId ? renamed.data : c)));
      setActive((prev) => (prev && prev.id === conversationId ? { ...prev, title: renamed.data.title } : prev));
    } catch { /* 重命名失败不打断对话 */ }
  }, []);

  const cancel = useCallback(async () => {
    if (!runRef.current) return;
    try {
      await conversationApi.cancelConversationRun(runRef.current);
      setPhase("cancelled");
    } catch (err) {
      setError(String(err?.response?.data?.detail || err.message));
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        const [caps, list] = await Promise.all([
          conversationApi.getConversationCapabilities(), conversationApi.listConversations(),
        ]);
        if (disposed) return;
        setCapabilities(caps.data);
        setConversations(list.data);
        if (list.data.length) await openConversation(list.data[0]);
      } catch (err) {
        if (!disposed) setError(String(err?.message || "对话加载失败"));
      }
    })();
    return () => { disposed = true; activeId.current = null; stopAll(); };
  }, [userId, openConversation, stopAll]);

  useEffect(() => {
    if (!active || (!["queued", "running"].includes(phase) && !connectionError)) return undefined;
    let disposed = false;
    let timer;
    const poll = async () => {
      try { await refresh(active.id); } catch { /* stream handles reconnection notice */ }
      if (!disposed) timer = setTimeout(poll, 2000);
    };
    timer = setTimeout(poll, 2000);
    return () => { disposed = true; clearTimeout(timer); };
  }, [active, phase, connectionError, refresh]);

  const turns = useMemo(
    () => buildConversationTurns({
      messages,
      events: allEvents,
      overrides: {
        activeRunId: snapshot?.active_run?.id ?? null,
        streaming: streaming ? { runId: snapshot?.active_run?.id ?? null, text: streaming } : null,
        toolOwners,
      },
    }),
    [messages, allEvents, streaming, snapshot, toolOwners],
  );

  const renameIfNeeded = useCallback(async (conversationId, fallbackTitle) => {
    if (!fallbackTitle) return;
    const title = fallbackTitle.replace(/\s+/g, " ").trim().slice(0, 24);
    try {
      await conversationApi.renameConversation(conversationId, { title });
      const list = await conversationApi.listConversations();
      setConversations(list.data);
    } catch { /* 自动命名失败不阻断聊天 */ }
  }, []);

  const send = useCallback(async (text) => {
    if (!active || !text.trim()) return;
    if (capabilities?.model_ready === false) {
      setRunError(runErrorMessage("configuration_not_ready"));
      return;
    }
    setError("");
    setRunError("");
    setBusy(true);
    const scope = generation.current;
    try {
      const res = await conversationApi.submitTurn(active.id, {
        content: text.trim(),
        client_request_id: uid(),
        queue_mode: "follow_up",
      });
      if (scope !== generation.current) return;
      const submission = res.data;
      runRef.current = submission.run_id;
      if (submission.queue_state === "executable") setPhase("queued");
      else if (submission.queue_state === "paused") setPhase("paused");
      else setPhase("queued");
      const result = await refresh(active.id);
      const firstUser = result?.msgs?.find((m) => m.role === "user");
      if (active.title === "新对话" && result?.msgs && result.msgs.filter((m) => m.role === "user").length === 1) {
        void renameIfNeeded(active.id, firstUser ? extractText(firstUser.content) : text);
      }
    } catch (err) {
      if (scope === generation.current) setError(String(err?.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
    }
  }, [active, capabilities?.model_ready, refresh, renameIfNeeded]);

  return {
    turns,
    conversations, active, snapshot, messages, activity, allEvents, streaming, phase,
    error: error || connectionError, runError, busy, capabilities,
    newConversation, openConversation, send, cancel, setTitle, refresh, STATE_LABELS, renameIfNeeded,
  };
}
