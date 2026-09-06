// P09.2 Case/Module 编辑器纯模型（无 React/DOM；node:test 可测）。
// 人工编辑 → 只产生 Artifact Operation 数组（绝不自造整棵 JSON 保存）。

export function normalizeEditorSteps(rawSteps) {
  const used = new Set();
  return (rawSteps || []).map((item) => {
    const provided = Number.isInteger(item?.step_no) ? item.step_no : null;
    const step = { step_no: null, action: item?.action ?? "", data: item?.data ?? null };
    if (provided != null) {
      if (provided <= 0 || used.has(provided)) {
        throw new Error("step_no 必须为正整数且唯一");
      }
      step.step_no = provided;
      used.add(provided);
    }
    return step;
  }).map((step) => {
    if (step.step_no != null) return step;
    let candidate = 1;
    while (used.has(candidate)) candidate += 1;
    used.add(candidate);
    return { ...step, step_no: candidate };
  });
}

export function editorToCaseOperations({ create, moduleId, nodeId, title, content, sourceRefs }) {
  const normalizedContent = {
    preconditions: (content?.preconditions || []).filter(Boolean),
    steps: normalizeEditorSteps(content?.steps).map((s) => ({
      step_no: s.step_no, action: s.action, data: s.data ?? null,
    })),
    expected_results: (content?.expected_results || []).map((item) => ({
      step_no: item.step_no ?? null, expected: item.expected,
    })),
    priority: content?.priority ?? "P1",
    tags: content?.tags || [],
  };
  if (create) {
    return [{
      operation_type: "add_node",
      parent_id: moduleId,
      node_type: "test_case",
      title,
      content: normalizedContent,
      source_refs: sourceRefs && sourceRefs.length ? sourceRefs : undefined,
    }];
  }
  const patch = { title, content: normalizedContent };
  return [{ operation_type: "update_node", target_node_id: nodeId, patch }];
}

export function moduleOps({ kind, parentId, nodeId, title, newParentId }) {
  if (kind === "create") {
    return [{ operation_type: "add_node", parent_id: parentId,
      node_type: "module", title }];
  }
  if (kind === "rename") {
    return [{ operation_type: "update_node", target_node_id: nodeId,
      patch: { title } }];
  }
  if (kind === "move") {
    return [{ operation_type: "move_node", target_node_id: nodeId,
      new_parent_id: newParentId }];
  }
  if (kind === "delete") {
    return [{ operation_type: "delete_node", target_node_id: nodeId }];
  }
  return [];
}

// 列出可作为新父节点的 module 候选（排除自身子树）
export function moduleParentCandidates(root, excludeId = null) {
  const result = [];
  const walk = (node) => {
    if (node.node_type === "module" && node.id === excludeId) return; // 整棵子树不可作父
    if (node.node_type === "module") result.push({ id: node.id, title: node.title });
    for (const child of (node.children || [])) walk(child);
  };
  walk(root);
  return result;
}

// MindMap scope：返回以 module/root 为根的子树节点对象
export function scopedRoot(root, scopeId) {
  if (scopeId == null || scopeId === root?.id) return root;
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (node.id === scopeId) return node;
    stack.push(...(node.children || []));
  }
  return root;
}

// P09.2.1：步骤重排序/增删后的稳定重编号与 expected 引用重映射。
// 语义：绑定跟随“逻辑步骤行”（重排时整行移动），删除某步时绑定该步的
// expected 降级为整体（step_no=null），不留下悬空引用。
export function renumberStepsAndExpected(steps, expectedResults) {
  const used = new Set(steps.map((s) => s.step_no).filter((n) => Number.isInteger(n)));
  const filled = steps.map((step) => {
    if (Number.isInteger(step.step_no)) return { ...step, step_no: step.step_no };
    let candidate = 1;
    while (used.has(candidate)) candidate += 1;
    used.add(candidate);
    return { ...step, step_no: candidate };
  });
  const oldToNew = new Map();
  const renumbered = filled.map((step, idx) => {
    oldToNew.set(step.step_no, idx + 1);
    return { ...step, step_no: idx + 1 };
  });
  const expected = expectedResults.map((item) => {
    if (item.step_no == null) return { ...item, step_no: null };
    return { ...item, step_no: oldToNew.get(item.step_no) ?? null };
  });
  return { steps: renumbered, expected };
}
