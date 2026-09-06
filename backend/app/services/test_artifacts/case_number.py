"""TestCase 展示编号（P09.1）：由 Server identity 派生，永久稳定。

TC-{ArtifactNode.id:06d}：移动 Module / reorder 不变；不需要抢号；LLM 无法制造重复。
前端必须使用同一格式（frontend/src/components/v2-workspace/caseNumber.js），不得另起一套。
"""


def format_case_number(node_id) -> str:
    if not isinstance(node_id, int) or node_id <= 0:
        return ""
    return f"TC-{node_id:06d}"
