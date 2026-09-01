export function getStoredCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem("auth_user") || "null");
  } catch {
    return null;
  }
}

export function hasAnyRole(user, roles) {
  const userRoles = user?.roles || [];
  return roles.some((role) => userRoles.includes(role));
}

export function isAdminUser(user) {
  return hasAnyRole(user, ["system_admin", "admin"]);
}

export function isViewerOnly(user) {
  const roles = user?.roles || [];
  return roles.includes("viewer") && !roles.includes("tester") && !isAdminUser(user);
}

export function canOperateProject(projectId, user = getStoredCurrentUser()) {
  if (!user || isViewerOnly(user)) return false;
  if (isAdminUser(user)) return true;
  if (!user.roles?.includes("tester")) return false;
  if (projectId === null || projectId === undefined) return false;
  return (user.project_ids || []).includes(Number(projectId));
}
