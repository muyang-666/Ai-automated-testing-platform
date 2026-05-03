import request from "../services/api";

export function getUserList(params) {
  return request.get("/users", { params });
}

export function createUser(data) {
  return request.post("/users", data);
}

export function updateUser(id, data) {
  return request.put(`/users/${id}`, data);
}

export function deleteUser(id) {
  return request.delete(`/users/${id}`);
}

export function updateUserRoles(id, data) {
  return request.put(`/users/${id}/roles`, data);
}

export function getRoleList() {
  return request.get("/users/roles");
}
