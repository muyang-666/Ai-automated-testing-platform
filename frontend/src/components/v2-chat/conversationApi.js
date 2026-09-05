// V2 Conversation API client（P06）。旧 agent.js（case-generation 悬浮台）保留但不再被新 Chat 使用。
import request from "../../services/api";

export function createConversation(data) {
  return request.post("/agent/conversations", data);
}

export function listConversations(params) {
  return request.get("/agent/conversations", { params });
}

export function getConversation(id) {
  return request.get(`/agent/conversations/${id}`);
}

export function getMessages(id, params) {
  return request.get(`/agent/conversations/${id}/messages`, { params });
}

export function submitTurn(id, data) {
  return request.post(`/agent/conversations/${id}/turns`, data);
}

export function cancelConversationRun(runId) {
  return request.post(`/agent/conversation-runs/${runId}/cancel`, {});
}

export function getConversationCapabilities() {
  return request.get("/agent/conversation-capabilities");
}

// SSE：fetch + ReadableStream（Bearer 头），Token 不进 URL；断线时 onClose 回调由调用方重连。
export function streamConversationEvents({ conversationId, afterSequence = 0, onEvent, onError, onClose }) {
  const controller = new AbortController();
  const token = localStorage.getItem("auth_token");
  const configuredBase = String(request.defaults.baseURL || window.location.origin).replace(/\/+$/, "");
  const path = `${configuredBase}/agent/conversations/${conversationId}/events`;
  const url = new URL(path, window.location.origin);
  url.searchParams.set("after_sequence", String(afterSequence));
  url.searchParams.set("timeout_seconds", "25");
  const run = async () => {
    try {
      const response = await fetch(url.toString(), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
        credentials: "include",
      });
      if (!response.ok || !response.body) {
        if (response.status === 401) {
          localStorage.removeItem("auth_token");
          localStorage.removeItem("auth_user");
          window.dispatchEvent(new Event("auth:unauthorized"));
        }
        onError?.(new Error(`SSE HTTP ${response.status}`));
        onClose?.();
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            onEvent(JSON.parse(dataLine.slice(6)));
          } catch {
            /* 忽略坏帧 */
          }
        }
      }
      onClose?.();
    } catch (error) {
      if (error?.name !== "AbortError") onError?.(error);
    }
  };
  run();
  return () => controller.abort();
}
