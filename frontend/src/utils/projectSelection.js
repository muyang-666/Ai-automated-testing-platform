const PROJECT_SELECTION_KEY = "testmind:selected_project_id";

export function getStoredProjectId() {
  const raw = localStorage.getItem(PROJECT_SELECTION_KEY);
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function storeProjectId(projectId) {
  if (projectId == null) {
    localStorage.removeItem(PROJECT_SELECTION_KEY);
    return;
  }
  localStorage.setItem(PROJECT_SELECTION_KEY, String(projectId));
}

export function resolveProjectId(projects, currentProjectId) {
  if (!projects.length) return null;

  const hasProject = (id) => projects.some((project) => project.id === id);

  if (currentProjectId != null && hasProject(currentProjectId)) {
    return currentProjectId;
  }

  const storedProjectId = getStoredProjectId();
  if (storedProjectId != null && hasProject(storedProjectId)) {
    return storedProjectId;
  }

  return projects[0].id;
}
