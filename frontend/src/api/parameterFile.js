import request from "../services/api";

export function getParameterFile() {
  return request.get("/parameter-file");
}

export function updateParameterFile(data) {
  return request.put("/parameter-file", data);
}