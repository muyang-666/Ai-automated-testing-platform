import request from "../services/api";

export function getRequirementList(params) {
  return request.get("/requirements", { params });
}

export function getRequirementDetail(requirementId) {
  return request.get(`/requirements/${requirementId}`);
}

export function createRequirement(data) {
  return request.post("/requirements", data);
}

export function updateRequirement(requirementId, data) {
  return request.put(`/requirements/${requirementId}`, data);
}

export function deleteRequirement(requirementId) {
  return request.delete(`/requirements/${requirementId}`);
}
