import request from "../services/api";

export function login(data) {
  return request.post("/auth/login", data);
}

export function logout() {
  return request.post("/auth/logout");
}

export function getCurrentUser() {
  return request.get("/auth/me");
}
