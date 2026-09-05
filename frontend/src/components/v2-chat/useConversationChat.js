import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as conversationApi from "./conversationApi";
import { runErrorMessage } from "./conversationErrors.js";
import {
  canSendMessage, conversationState, createUnsavedConversation, isUnsavedConversation,
  mergeConversationSummaries, renameActiveConversation, renameConversationSummaries,
  shouldAdoptInitialConversation, stopTargetRun, UNSAVED_CONVERSATION_ID,
} from "./chatState.js";
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
  const [busy, setBusy] = useState(false); // 仅锁住“草稿首次落库”，不拦截已存在会话的 follow-up
  const [capabilities, setCapabilities] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const lastEventSequence = useRef(0);
  const stopStream = useRef(null);
  const activeId = useRef(null);
  const generation = useRef(0);
  const refreshSequence = useRef(0);
  const refreshTimer = useRef(null);
  const committedIds = useRef(new Set());
  const pendingText = useRef(new Map());
  const draftCreation = useRef(null);

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
    // 顶部状态一律由 snapshot 派生：A running + B queued 时仍是 running，
    // 提交 follow-up 不再直接改全局 phase。
    const nextPhase = conversationState(snap);
    setPhase(nextPhase);
    if (nextPhase === "failed" || nextPhase === "interrupted") {
      setRunError(runErrorMessage(snap.latest_run?.error_code));
    } else {
      setRunError("");
    }
    return { snap, msgs };
  }, [backfillToolOwners]);

  const stopAll = useCallback(() => {
    ++generation.current; // Invalidate in-flight snapshots and old stream callbacks.
    stopStream.current?.();
    stopStream.current = null;
    clearTimeout(refreshTimer.current);
    refreshTimer.current = null;
  }, []);

  const openUnsavedConversation = useCallback(() => {
    if (draftCreation.current) return;
    stopAll();
    activeId.current = null;
    lastEventSequence.current = 0;
    committedIds.current = new Set();
    pendingText.current = new Map();
    messagesRef.current = [];
    allEventsRef.current = [];
    toolOwnersRef.current = new Map();
    setToolOwners(new Map());
    setActive(createUnsavedConversation());
    setError("");
    setRunError("");
    setStreaming("");
    setMessages([]);
    setActivity([]);
    setAllEvents([]);
    setConnectionError("");
    setSnapshot(null);
    setPhase("idle");
  }, [stopAll]);

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
          scheduleRefresh(); // 顶部状态交给 snapshot 派生（worker 可能立刻提升下一个 run）
        } else if (event.event_type === "run_failed") {
          setRunError(runErrorMessage(event.payload?.error_code));
          scheduleRefresh();
        } else if (event.event_type === "run_cancelled") {
          scheduleRefresh();
        } else if (event.event_type === "run_interrupted") {
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
    // Establish the subscription before slow snapshot requests. It survives
    // idle time and reconstructs in-flight text; committed IDs suppress replay.
    connectEvents(conversation.id);
    try { await refresh(conversation.id); } catch (err) {
      if (scope === generation.current) setError(String(err?.message || "对话加载失败"));
    }
  }, [refresh, connectEvents, stopAll]);

  // “新对话”只是本地草稿；首次真正发送时才创建服务端 Conversation。
  const newConversation = useCallback(() => {
    openUnsavedConversation();
  }, [openUnsavedConversation]);

  const persistUnsavedConversation = useCallback(() => {
    if (draftCreation.current) return draftCreation.current;
    const scope = generation.current;
    setBusy(true);
    const pending = conversationApi.createConversation({ title: "新对话", project_id: null })
      .then((created) => {
        if (scope !== generation.current) return null;
        const conversation = created.data;
        activeId.current = conversation.id;
        setActive(conversation);
        setConversations((current) => [
          conversation,
          ...current.filter((item) => item.id !== conversation.id),
        ]);
        connectEvents(conversation.id);
        return conversation;
      })
      .finally(() => {
        if (draftCreation.current === pending) draftCreation.current = null;
        setBusy(false);
      });
    draftCreation.current = pending;
    return pending;
  }, [connectEvents]);

  // 重命名可能晚于“本地草稿 → 持久化会话”的状态切换完成。
  // 必须用 functional update 读取最新状态，禁止闭包里的旧 active 把会话回滚成草稿。
  const applyRenameTitle = useCallback((conversationId, title) => {
    setConversations((current) => renameConversationSummaries(current, conversationId, title));
    setActive((current) => renameActiveConversation(current, conversationId, title));
  }, []);

  const setTitle = useCallback(async (conversationId, rawTitle) => {
    if (conversationId === UNSAVED_CONVERSATION_ID) return;
    const title = String(rawTitle || "").replace(/\s+/g, " ").trim();
    if (!title || title.length > 200) return;
    try {
      const renamed = await conversationApi.renameConversation(conversationId, { title });
      applyRenameTitle(conversationId, renamed.data.title || title);
    } catch { /* 重命名失败不打断对话 */ }
  }, [applyRenameTitle]);

  const renameIfNeeded = useCallback(async (conversationId, fallbackTitle) => {
    if (!fallbackTitle) return;
    const title = String(fallbackTitle).replace(/\s+/g, " ").trim().slice(0, 24);
    if (!title) return;
    try {
      const renamed = await conversationApi.renameConversation(conversationId, { title });
      applyRenameTitle(conversationId, renamed.data.title || title);
    } catch { /* 自动命名失败不阻断聊天 */ }
  }, [applyRenameTitle]);

  // Stop = 取消正在执行的 active head（snapshot.active_run.id）。
  // 绝不取消 latest submitted：A running + B queued 时 Stop 必须作用于 A。
  const cancel = useCallback(async () => {
    const target = stopTargetRun(snapshot);
    if (!target) return;
    setRunError("");
    try {
      await conversationApi.cancelConversationRun(target);
      // worker 随后发 run_cancelled；这里立即拉一次让顶部状态快速归位
      if (active?.id) void refresh(active.id).catch(() => {});
    } catch (err) {
      const status = err?.response?.status;
      // 404/409：run 已终态（worker 已提升下一个 run）→ 视为取消已完成
      if (status !== 404 && status !== 409) {
        setError(String(err?.response?.data?.detail || err.message));
      }
    }
  }, [snapshot, active, refresh]);

  useEffect(() => {
    let disposed = false;
    const loadGeneration = generation.current;
    (async () => {
      try {
        const [caps, list] = await Promise.all([
          conversationApi.getConversationCapabilities(), conversationApi.listConversations(),
        ]);
        if (disposed) return;
        setCapabilities(caps.data);
        // 用户可能已在首次请求返回前点击“新对话”并发送。
        // 此时只合并历史列表，绝不能用旧响应切走当前草稿或中止首次提交。
        if (!shouldAdoptInitialConversation(loadGeneration, generation.current)) {
          setConversations((current) => mergeConversationSummaries(current, list.data));
          return;
        }
        setConversations(list.data);
        if (list.data.length) await openConversation(list.data[0]);
        else openUnsavedConversation();
      } catch (err) {
        if (!disposed) setError(String(err?.message || "对话加载失败"));
      }
    })();
    return () => { disposed = true; activeId.current = null; stopAll(); };
  }, [userId, openConversation, openUnsavedConversation, stopAll]);

  useEffect(() => {
    if (!active || isUnsavedConversation(active)
      || (!["queued", "running"].includes(phase) && !connectionError)) return undefined;
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

  const send = useCallback(async (text) => {
    if (!active || !text.trim()) return;
    if (!canSendMessage({ hasActive: true, phase, modelReady: capabilities?.model_ready })) {
      if (capabilities?.model_ready === false) {
        setRunError(runErrorMessage("configuration_not_ready"));
      }
      return;
    }
    setError("");
    setRunError("");
    const scope = generation.current;
    try {
      const target = isUnsavedConversation(active) ? await persistUnsavedConversation() : active;
      if (!target || scope !== generation.current) return;
      // queue_mode=follow_up：A running 时提交 B 会入队，不在 UI 层猜测状态；
      // 顶部 phase 由下方 refresh（snapshot）派生，B 的 queued 由 turnModel 显示。
      await conversationApi.submitTurn(target.id, {
        content: text.trim(),
        client_request_id: uid(),
        queue_mode: "follow_up",
      });
      if (scope !== generation.current) return;
      const result = await refresh(target.id);
      const firstUser = result?.msgs?.find((m) => m.role === "user");
      const isFirstUserMessage = (result?.msgs?.filter((m) => m.role === "user").length ?? 0) === 1;
      if ((!target.title || target.title === "新对话") && isFirstUserMessage) {
        void renameIfNeeded(target.id, firstUser ? extractText(firstUser.content) : text);
      }
    } catch (err) {
      if (scope === generation.current) setError(String(err?.response?.data?.detail || err.message));
    }
    // 注意：这里不设 busy——网络请求在途时依然允许继续输入/发送 follow-up。
  }, [active, phase, capabilities?.model_ready, persistUnsavedConversation, refresh, renameIfNeeded]);

  return {
    turns,
    conversations, active, snapshot, messages, activity, allEvents, streaming, phase,
    error: error || connectionError, runError, busy, capabilities,
    newConversation, openConversation, send, cancel, setTitle, refresh, STATE_LABELS, renameIfNeeded,
  };
}
