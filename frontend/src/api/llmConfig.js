import request from "../services/api";

// Provider
export function getProviderList(params) {
  return request.get("/llm-config/providers", { params });
}

export function createProvider(data) {
  return request.post("/llm-config/providers", data);
}

export function updateProvider(id, data) {
  return request.put(`/llm-config/providers/${id}`, data);
}

export function deleteProvider(id) {
  return request.delete(`/llm-config/providers/${id}`);
}

// Model
export function getModelList(params) {
  return request.get("/llm-config/models", { params });
}

export function createModel(data) {
  return request.post("/llm-config/models", data);
}

export function updateModel(id, data) {
  return request.put(`/llm-config/models/${id}`, data);
}

export function deleteModel(id) {
  return request.delete(`/llm-config/models/${id}`);
}

export function testModel(id, data) {
  return request.post(`/llm-config/models/${id}/test`, data || {});
}

// Scene Config
export function getSceneConfigList() {
  return request.get("/llm-config/scenes");
}

export function updateSceneConfig(id, data) {
  return request.put(`/llm-config/scenes/${id}`, data);
}
