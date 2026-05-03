import request from "../services/api";

export function getApiDocumentList(params) {
  return request.get("/api-documents", { params });
}

export function getApiDocumentDetail(id) {
  return request.get(`/api-documents/${id}`);
}

export function createApiDocument(data) {
  return request.post("/api-documents", data);
}

export function updateApiDocument(id, data) {
  return request.put(`/api-documents/${id}`, data);
}

export function deleteApiDocument(id) {
  return request.delete(`/api-documents/${id}`);
}

export function generateApiCasesFromDocument(data) {
  return request.post("/api-documents/generate-cases", data);
}

export function saveGeneratedApiCases(data) {
  return request.post("/api-documents/save-generated-cases", data);
}
