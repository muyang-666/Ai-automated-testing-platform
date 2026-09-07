export const EMPTY_FUNCTIONAL_WORKSPACE = Object.freeze({
  page: null, projectId: null, projectName: "", artifactId: null, artifactTitle: "",
  selectedModuleId: null, selectedCaseId: null, modulePath: [], caseLabel: "",
  viewMode: null, selectionError: "", artifactStatus: null,
});

function modulePath(index, moduleId) {
  const result = [];
  const visited = new Set();
  let current = moduleId == null ? null : index.get(moduleId);
  while (current?.node_type === "module" && !visited.has(current.id)) {
    visited.add(current.id);
    result.unshift(current.title);
    current = current.parent_id == null ? null : index.get(current.parent_id);
  }
  return result;
}

export function deriveFunctionalWorkspace({ project, artifact, index, scopeId,
  selectedNodeId, viewMode, artifactStatus }) {
  // P09.3B.1 #2：artifactStatus = loading | ready | empty | error；默认按 artifact 推导。
  const status = artifactStatus ?? (artifact ? "ready" : "empty");
  const selected = selectedNodeId == null ? null : index.get(selectedNodeId) || null;
  const scoped = scopeId == null ? null : index.get(scopeId) || null;
  const selectedCaseId = selected?.node_type === "test_case" ? selected.id : null;
  const selectedModuleId = selected?.node_type === "module" ? selected.id
    : selectedCaseId != null && index.get(selected.parent_id)?.node_type === "module" ? selected.parent_id
      : scoped?.node_type === "module" ? scoped.id : null;
  return {
    page: "functionCases",
    projectId: project?.id ?? null,
    projectName: project?.name || "",
    artifactId: artifact?.id ?? null,
    artifactTitle: artifact?.title || "",
    selectedModuleId,
    selectedCaseId,
    modulePath: modulePath(index, selectedModuleId),
    caseLabel: selectedCaseId == null ? "" : `TC-${String(selectedCaseId).padStart(6, "0")}`,
    viewMode: viewMode === "mindmap" ? "mindmap" : "list",
    selectionError: "",
    artifactStatus: status,
  };
}

export function functionalWorkspaceReducer(state, action) {
  if (action.type === "set") return { ...EMPTY_FUNCTIONAL_WORKSPACE, ...action.value };
  if (action.type === "clear-selection") return {
    ...state, selectedModuleId: null, selectedCaseId: null,
    modulePath: [], caseLabel: "", selectionError: action.message || "",
  };
  if (action.type === "leave") return { ...EMPTY_FUNCTIONAL_WORKSPACE };
  return state;
}

export function workspaceTurnPayload(workspace) {
  if (workspace?.page !== "functionCases" || workspace.artifactId == null) return null;
  return {
    selected_module_id: workspace.selectedModuleId ?? null,
    selected_case_id: workspace.selectedCaseId ?? null,
    current_view: workspace.viewMode || null,
  };
}
