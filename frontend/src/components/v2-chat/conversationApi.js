// V2 Conversation API client（P06）。旧 agent.js（case-generation 悬浮台）保留但不再被新 Chat 使用。
import request from "../../services/api";
import { subscribeEventStream } from "./eventStream.js";

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

export function renameConversation(id, data) {
  return request.patch(`/agent/conversations/${id}`, data);
}

export function getConversationCapabilities() {
  return request.get("/agent/conversation-capabilities");
}

// One managed SSE subscription owns renewal, reconnects and cancellation.
export function streamConversationEvents({ conversationId, afterSequence = 0, onEvent, onError, onOpen }) {
  const configuredBase = String(request.defaults.baseURL || window.location.origin).replace(/\/+$/, "");
  const path = `${configuredBase}/agent/conversations/${conversationId}/events`;
  const url = new URL(path, window.location.origin);
  url.searchParams.set("after_sequence", String(afterSequence));
  url.searchParams.set("timeout_seconds", "25");
  return subscribeEventStream({
    url: url.toString(), afterSequence, onEvent, onError, onOpen,
    getHeaders: () => {
      const token = localStorage.getItem("auth_token");
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    onUnauthorized: () => {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_user");
      window.dispatchEvent(new Event("auth:unauthorized"));
    },
  });
}
