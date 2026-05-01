import request from "../services/api";

export function getModuleTree(projectId) {
  return request.get("/modules/tree", { params: { project_id: projectId } });
}

export function createModule(data) {
  return request.post("/modules", data);
}

export function updateModule(moduleId, data) {
  return request.put(`/modules/${moduleId}`, data);
}

export function deleteModule(moduleId) {
  return request.delete(`/modules/${moduleId}`);
}

export function reorderModules(data) {
  return request.put("/modules/reorder", data);
}
