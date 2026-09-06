import { workspaceTurnPayload } from "../v2-workspace/functionalWorkspaceModel.js";
import { planSubmitWithMismatch, looksLikeAssetDirective } from "../v2-workspace/artifactMismatchGuard.js";

export function messageNeedsWorkspaceContext(text) {
  return /(这里|这边|这个模块|当前模块|这个用例|当前用例|选中的|所选)/.test(String(text || ""));
}

export function planWorkspaceSubmission({ isUnsaved, snapshotReady = true,
  focusedArtifactId, phase, workspace, message = "" }) {
  if (workspace?.page === "functionCases" && workspace.artifactId == null) {
    // P09.3B §2.3/§60：无可用 Artifact（加载中/空/无权限创建）时，普通聊天照常允许；
    // 引用“这里/这个模块”或资产型指令明确提示当前无可用功能测试资产，不伪造上下文。
    const assetIntent = messageNeedsWorkspaceContext(message) || looksLikeAssetDirective(message);
    return { action: assetIntent ? "no-artifact" : "submit", workspaceContext: null };
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
    // P09.3B §2.1：mismatch 时普通 continuation（继续解释/为什么…）允许继续旧 Conversation；
    // 资产型指令或无法可靠判断的内容一律阻止提交，避免改错项目。
    const plan = planSubmitWithMismatch({
      content: message,
      mismatch: true,
      messageNeedsWorkspaceContext: messageNeedsWorkspaceContext(message),
    });
    return { action: plan.allowed ? "submit" : "mismatch", workspaceContext: null };
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
