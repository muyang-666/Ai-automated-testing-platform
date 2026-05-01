import request from "../services/api";

export function getFunctionCaseList(params) {
  return request.get("/function-cases", { params });
}

export function getFunctionCaseDetail(caseId) {
  return request.get(`/function-cases/${caseId}`);
}

export function createFunctionCase(data) {
  return request.post("/function-cases", data);
}

export function updateFunctionCase(caseId, data) {
  return request.put(`/function-cases/${caseId}`, data);
}

export function deleteFunctionCase(caseId) {
  return request.delete(`/function-cases/${caseId}`);
}
