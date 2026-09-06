// P09.1 TestArtifact API client（复用统一 axios request，不做组件内裸 fetch）。
import request from "../services/api";

export function listArtifacts() {
  return request.get("/test-artifacts");
}

export function createArtifact({ title, project_id = null, artifact_type = "test_design" }) {
  return request.post("/test-artifacts", { title, artifact_type, project_id });
}

// P09.1：确保项目主 Functional TestArtifact（后端负责并发/唯一）
export function ensureProjectArtifact({ project_id, title = null }) {
  return request.post("/test-artifacts/ensure-project-functional", { project_id, title });
}

export function getArtifact(id) {
  return request.get(`/test-artifacts/${id}`);
}

// 整树一次拉取：MindMap 基本渲染只依赖这一个请求（含完整 content/source_refs）
export function getArtifactTree(id) {
  return request.get(`/test-artifacts/${id}/tree`);
}
// P09.2 编辑/历史能力
export function applyArtifactOperations(id, payload) {
  return request.post(`/test-artifacts/${id}/operations`, payload);
}

export function getArtifactRevisions(id) {
  return request.get(`/test-artifacts/${id}/revisions`);
}

export function getArtifactDiff(id, params) {
  return request.get(`/test-artifacts/${id}/diff`, { params });
}

export function undoArtifact(id, expectedRevision) {
  return request.post(`/test-artifacts/${id}/undo`, { expected_revision: expectedRevision });
}

export function restoreArtifact(id, targetRevision, expectedRevision) {
  return request.post(`/test-artifacts/${id}/restore`, {
    target_revision: targetRevision, expected_revision: expectedRevision,
  });
}
