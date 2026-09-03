import request from "../services/api";
import { caseRunRequest } from "../components/test-agent/agentContract";

export function createAgentSession(data) {
  return request.post("/agent/sessions", data);
}

export function getAgentSessions(params) {
  return request.get("/agent/sessions", { params });
}

export function getAgentSession(sessionId) {
  return request.get(`/agent/sessions/${sessionId}`);
}

export function appendAgentMessage(sessionId, data) {
  return request.post(`/agent/sessions/${sessionId}/messages`, data);
}

export function getAgentMessages(sessionId, params) {
  return request.get(`/agent/sessions/${sessionId}/messages`, { params });
}

export function getAgentEvents(sessionId, params) {
  return request.get(`/agent/sessions/${sessionId}/events`, { params });
}

export function createAgentRun(sessionId, data) {
  return request.post("/agent/runs/case-generation", caseRunRequest(sessionId, data));
}

export function getAgentSessionRuns(sessionId) {
  return request.get(`/agent/sessions/${sessionId}/runs`);
}

export function getAgentRun(runId) {
  return request.get(`/agent/runs/${runId}`);
}

export function getAgentRunSteps(runId, params) {
  return request.get(`/agent/runs/${runId}/steps`, { params });
}

export function getAgentRunArtifacts(runId, params) {
  return request.get(`/agent/runs/${runId}/artifacts`, { params });
}

export function getAgentRunApprovals(runId, params) {
  return request.get(`/agent/runs/${runId}/approvals`, { params });
}

export function cancelAgentRun(runId) {
  return request.post(`/agent/runs/${runId}/cancel`);
}

export function resolveAgentApproval(approvalId, data) {
  return request.post(`/agent/approvals/${approvalId}/resolve`, { status: data.decision, resolution_json: data.resolution || {} });
}

export function saveAgentCandidates(runId, data) {
  return request.post(`/agent/runs/${runId}/save-candidates`, { candidate_ids: data.candidate_ids });
}
