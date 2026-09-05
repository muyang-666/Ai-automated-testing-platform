import { useCallback, useEffect, useRef, useState } from "react";
import * as conversationApi from "./conversationApi";

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
const RUN_ERROR_MESSAGES = {
  configuration_not_ready: "Agent 对话模型尚未配置，请先在模型管理中为“Agent 对话”绑定模型。",
  agent_runtime_error: "Agent Worker 执行失败，请检查 Worker 日志后重试。",
  model_error: "模型调用失败，请稍后重试或检查模型配置。",
  canceled: "本轮回答已取消。",
};

function runErrorMessage(errorCode) {
  return RUN_ERROR_MESSAGES[errorCode] || "本轮没有生成回答，请稍后重试。";
}

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
  const [activity, setActivity] = useState([]); // tool/run 活动行
  const [streaming, setStreaming] = useState("");
  const [phase, setPhase] = useState("idle"); // idle/queued/running/paused/failed/interrupted/cancelled
  const [error, setError] = useState("");
  const [runError, setRunError] = useState("");
  const [busy, setBusy] = useState(false);
  const [capabilities, setCapabilities] = useState(null);
  const lastEventSequence = useRef(0);
  const lastMessageSequence = useRef(0);
  const stopStream = useRef(null);
  const runRef = useRef(null);
  const reconnects = useRef(0);
  const reconnectTimer = useRef(null);

  const refresh = useCallback(async (conversationId) => {
    const [snapRes, msgRes] = await Promise.all([
      conversationApi.getConversation(conversationId),
      conversationApi.getMessages(conversationId),
    ]);
    const snap = snapRes.data;
    const msgs = msgRes.data;
    setSnapshot(snap);
    setMessages(msgs);
    lastMessageSequence.current = msgs.length ? msgs[msgs.length - 1].sequence_no : 0;
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
  }, []);

  const connectEvents = useCallback((conversationId) => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    stopStream.current?.();
    stopStream.current = conversationApi.streamConversationEvents({
      conversationId,
      afterSequence: lastEventSequence.current,
      onEvent: (event) => {
        reconnects.current = 0;
        if (event.sequence_no > lastEventSequence.current) {
          lastEventSequence.current = event.sequence_no;
        }
        if (event.event_type === "conversation_text_delta") {
          setStreaming((prev) => prev + (event.payload?.text || ""));
        } else if (event.event_type === "conversation_tool_started") {
          setActivity((prev) => [...prev.slice(-49), { id: event.sequence_no, text: `✓ 调用工具 ${event.payload?.tool_name || ""}` }]);
        } else if (event.event_type === "conversation_tool_finished") {
          setActivity((prev) => [...prev.slice(-49), { id: event.sequence_no, text: `✓ 工具 ${event.payload?.tool_name || ""} 完成` }]);
        } else if (["run_started", "run_resumed"].includes(event.event_type)) {
          setPhase("running");
          setRunError("");
        } else if (event.event_type === "run_succeeded") {
          setPhase("idle");
          setStreaming("");
          refresh(conversationId);
        } else if (event.event_type === "run_failed") {
          setPhase("failed");
          setRunError(runErrorMessage(event.payload?.error_code));
          refresh(conversationId);
        } else if (event.event_type === "run_cancelled") {
          setPhase("cancelled");
          refresh(conversationId);
        } else if (event.event_type === "run_interrupted") {
          setPhase("interrupted");
          setRunError("Agent Worker 已中断，本轮没有生成回答，请重新发送。");
          refresh(conversationId);
        } else if (event.event_type === "conversation_message_committed") {
          refresh(conversationId);
        }
      },
      onError: () => setError("事件流连接失败，将自动重连"),
      onClose: () => {
        if (reconnects.current < 5) {
          reconnects.current += 1;
          reconnectTimer.current = setTimeout(() => connectEvents(conversationId), 800);
        }
      },
    });
  }, [refresh]);

  const openConversation = useCallback(async (conversation) => {
    setActive(conversation);
    setError("");
    setRunError("");
    setStreaming("");
    setMessages([]);
    setActivity([]);
    reconnects.current = 0;
    const { snap } = await refresh(conversation.id);
    // A snapshot replaces all state before the stream starts, so only events
    // after its dedicated event cursor need to be consumed.  Message sequence
    // is intentionally separate.
    lastEventSequence.current = snap.latest_event_sequence || 0;
    connectEvents(conversation.id);
  }, [refresh, connectEvents]);

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

  const loadList = useCallback(async () => {
    try {
      const res = await conversationApi.listConversations();
      setConversations(res.data);
      if (!active && res.data.length) await openConversation(res.data[0]);
    } catch (err) {
      setError(String(err?.response?.data?.detail || err.message));
    }
  }, [active, openConversation]);

  const send = useCallback(async (text) => {
    if (!active || !text.trim()) return;
    if (capabilities?.model_ready === false) {
      setRunError(RUN_ERROR_MESSAGES.configuration_not_ready);
      return;
    }
    setError("");
    setRunError("");
    setBusy(true);
    try {
      const res = await conversationApi.submitTurn(active.id, {
        content: text.trim(),
        client_request_id: uid(),
        queue_mode: "follow_up",
      });
      const submission = res.data;
      runRef.current = submission.run_id;
      if (submission.queue_state === "executable") setPhase("running");
      else if (submission.queue_state === "paused") setPhase("paused");
      else setPhase("queued");
      await refresh(active.id);
    } catch (err) {
      setError(String(err?.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
    }
  }, [active, capabilities?.model_ready, refresh]);

  const cancel = useCallback(async () => {
    if (!runRef.current) return;
    try {
      await conversationApi.cancelConversationRun(runRef.current);
      setPhase("cancelled");
    } catch (err) {
      setError(String(err?.response?.data?.detail || err.message));
    }
  }, []);

  const stopAll = useCallback(() => {
    stopStream.current?.();
    stopStream.current = null;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectTimer.current = null;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const caps = await conversationApi.getConversationCapabilities();
        setCapabilities(caps.data);
      } catch {
        setCapabilities(null);
      }
      await loadList();
    })();
    return stopAll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  return {
    conversations, active, snapshot, messages, activity, streaming, phase, error, runError, busy, capabilities,
    newConversation, openConversation, send, cancel, refresh, STATE_LABELS,
  };
}
