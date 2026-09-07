// P09.3B §18-21：人工 Draft 与 Agent Realtime 并发。
// Editor 必须记住 baseRevision；realtime 刷新不得覆盖/重置 Draft；
// 保存时 expected_revision 恒等于 editor.baseRevision（Agent 已 20→21 时后端返回 409）。

export function openEditorWithBase({ nodeId, kind, baseRevision, currentRevision, content, view }) {
  return {
    nodeId,
    kind, // module | test_case | move | delete
    baseRevision: Number(baseRevision),
    currentRevision: Number(currentRevision ?? baseRevision),
    content,
    view: view ?? null,
    draftTouched: false,
    warning: null,
  };
}

// realtime 只更新背景 revision 快照，绝不触碰 draft
export function applyAgentRevision(editor, agentRevision) {
  if (editor == null) return null;
  return { ...editor, currentRevision: agentRevision, warning: null };
}

export function markDraftTouched(editor) {
  if (editor == null) return null;
  return { ...editor, draftTouched: true };
}

// 提交时使用 baseRevision；若后端 revision 已前进则给出明确冲突（由后端 409 主导）
export function expectedRevisionForSave(editor) {
  return editor == null ? null : editor.baseRevision;
}

export function shouldWarnConcurrency(editor, currentTreeRevision) {
  if (editor == null || !editor.draftTouched) return null;
  if (Number(currentTreeRevision) > editor.baseRevision) {
    return {
      baseRevision: editor.baseRevision,
      currentRevision: Number(currentTreeRevision),
      message: `测试资产已更新。当前编辑内容基于版本 ${editor.baseRevision}。`,
    };
  }
  return null;
}
