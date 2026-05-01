import request from "../services/api";

export function getProjectList(params) {
  return request.get("/projects", { params });
}

export function createProject(data) {
  return request.post("/projects", data);
}

export function updateProject(projectId, data) {
  return request.put(`/projects/${projectId}`, data);
}

export function deleteProject(projectId) {
  return request.delete(`/projects/${projectId}`);
}
