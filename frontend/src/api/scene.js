import request from "../services/api";

// 场景 CRUD
export function getSceneList() {
  return request.get("/scenes");
}

export function createScene(data) {
  return request.post("/scenes", data);
}

export function updateScene(sceneId, data) {
  return request.put(`/scenes/${sceneId}`, data);
}

export function deleteScene(sceneId) {
  return request.delete(`/scenes/${sceneId}`);
}

// 场景步骤
export function getSceneSteps(sceneId) {
  return request.get(`/scenes/${sceneId}/steps`);
}

export function createSceneStep(sceneId, data) {
  return request.post(`/scenes/${sceneId}/steps`, data);
}

export function deleteSceneStep(stepId) {
  return request.delete(`/scenes/steps/${stepId}`);
}

// 场景执行
export function executeScene(sceneId) {
  return request.post(`/scenes/${sceneId}/execute`);
}

// 已有测试用例列表（复用）
export function getCaseList() {
  return request.get("/cases");
}