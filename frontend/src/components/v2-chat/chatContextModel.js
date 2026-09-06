import { workspaceTurnPayload } from "../v2-workspace/functionalWorkspaceModel.js";

export function messageNeedsWorkspaceContext(text) {
  return /(这里|这边|这个模块|当前模块|这个用例|当前用例|选中的|所选)/.test(String(text || ""));
}

export function planWorkspaceSubmission({ isUnsaved, snapshotReady = true,
  focusedArtifactId, phase, workspace, message = "" }) {
  if (workspace?.page === "functionCases" && workspace.artifactId == null) {
    return { action: "workspace-loading", workspaceContext: null };
  }
  const payload = workspaceTurnPayload(workspace);
  if (!payload) return { action: "submit", workspaceContext: null };
  if (isUnsaved) return { action: "focus-then-submit", workspaceContext: payload };
  if (!snapshotReady) return { action: "loading", workspaceContext: null };
  if (focusedArtifactId == null) {
    return ["queued", "running"].includes(phase)
      ? { action: messageNeedsWorkspaceContext(message) ? "busy" : "submit", workspaceContext: null }
      : { action: "focus-then-submit", workspaceContext: payload };
  }
  if (focusedArtifactId !== workspace.artifactId) {
    return { action: messageNeedsWorkspaceContext(message) ? "mismatch" : "submit",
             workspaceContext: null };
  }
  return { action: "submit", workspaceContext: payload };
}

export function buildContextIndicator({ snapshot, workspace, isUnsaved = false }) {
  const onFunctionalPage = workspace?.page === "functionCases";
  const hasPageArtifact = onFunctionalPage && workspace.artifactId != null;
  const focused = snapshot?.focused_artifact || null;
  if (!focused && !hasPageArtifact) return null;
  if (!focused && hasPageArtifact) {
    return {
      label: [workspace.projectName || workspace.artifactTitle || "功能用例", "功能用例",
        ...workspace.modulePath, workspace.caseLabel].filter(Boolean).join(" · "),
      pending: true, mismatch: false, warning: "",
    };
  }
  const mismatch = onFunctionalPage && (
    (workspace.artifactId != null && focused.id !== workspace.artifactId)
    || (workspace.projectId != null && focused.project_id != null
        && focused.project_id !== workspace.projectId)
  );
  const aligned = hasPageArtifact && !mismatch;
  const project = focused.project_name || (aligned ? workspace.projectName : "")
    || focused.title || `Artifact #${focused.id}`;
  return {
    label: [project, "功能用例", ...(aligned ? workspace.modulePath : []),
      aligned ? workspace.caseLabel : ""].filter(Boolean).join(" · "),
    pending: isUnsaved && hasPageArtifact,
    mismatch,
    warning: mismatch
      ? `当前页面是「${workspace.projectName || workspace.artifactTitle}」，Agent 仍绑定「${project}」。`
      : "",
  };
}
