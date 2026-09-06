"""P08 action-risk policy; approval persistence/resume remains P10."""
from __future__ import annotations

from app.agents.conversation.policy import DefaultToolPolicy, ToolPolicyDecision
from app.agents.tools.artifacts.runtime import ArtifactRuntimeContext
from app.models.user import User
from app.services.test_artifacts import artifact_service

MAX_BATCH_OPERATIONS = 10
MAX_AUTO_ADD_NODES = 5
MAX_AUTO_AFFECTED_NODES = 5
LARGE_DELETE_THRESHOLD = 10

READ_TOOLS = {
    "calculator", "load_skill", "get_current_artifact", "read_artifact_outline",
    "read_artifact_nodes", "search_artifact", "get_artifact_diff", "read_requirement",
    "validate_test_artifact", "find_duplicate_cases", "analyze_test_coverage",
}
WRITE_TOOLS = {
    "add_artifact_node", "update_artifact_node", "delete_artifact_node",
    "move_artifact_node", "batch_apply_artifact_operations",
}


def _blocked(code: str, message: str, data: dict | None = None) -> ToolPolicyDecision:
    return ToolPolicyDecision.block(code, details={
        "status": "error", "message": message, "data": data or {}, "retryable": False,
    })


class ArtifactToolPolicy(DefaultToolPolicy):
    async def evaluate(self, context):
        if context.definition.name in READ_TOOLS:
            return await super().evaluate(context)
        if context.definition.name not in WRITE_TOOLS:
            return _blocked("tool_policy_denied", "Tool is not allowed by Artifact policy.")
        runtime = context.application_context
        if not isinstance(runtime, ArtifactRuntimeContext) or runtime.artifact_id is None:
            return _blocked("artifact_not_focused", "No current Artifact is focused.")
        if "artifact:write" not in runtime.permissions:
            return _blocked("permission_required", "Artifact write permission is required.")
        args = context.prepared.arguments
        if context.definition.name in {"add_artifact_node", "update_artifact_node", "move_artifact_node"}:
            return ToolPolicyDecision.allow()
        if context.definition.name == "delete_artifact_node":
            impact = self._delete_impact(runtime, args["target_node_id"])
            if impact["total_affected_nodes"] >= LARGE_DELETE_THRESHOLD:
                return _blocked("approval_required", "Large deletion requires human approval.", impact)
            return ToolPolicyDecision.allow()
        operations = args.get("operations") or []
        if len(operations) > MAX_BATCH_OPERATIONS:
            return _blocked("tool_policy_denied", "Artifact batch is too large.")
        added = sum(1 for op in operations if op.get("operation_type") == "add_node")
        impacts = [self._delete_impact(runtime, op["target_node_id"])
                   for op in operations if op.get("operation_type") == "delete_node"]
        affected = added + sum(item["total_affected_nodes"] for item in impacts)
        affected += sum(1 for op in operations if op.get("operation_type") in {"update_node", "move_node"})
        if added > MAX_AUTO_ADD_NODES or affected > MAX_AUTO_AFFECTED_NODES or any(
                item["total_affected_nodes"] >= LARGE_DELETE_THRESHOLD for item in impacts):
            return _blocked("approval_required", "Large Artifact batch requires human approval.", {
                "operation": "batch", "affected_nodes": affected,
                "delete_impacts": impacts,
            })
        return ToolPolicyDecision.allow()

    @staticmethod
    def _delete_impact(runtime: ArtifactRuntimeContext, node_id: int) -> dict:
        db = runtime.session_factory()
        try:
            requester = db.get(User, runtime.user_id)
            if requester is None:
                return {"target_node_id": node_id, "total_affected_nodes": LARGE_DELETE_THRESHOLD}
            return artifact_service.get_delete_impact(
                db, artifact_id=runtime.artifact_id, node_id=node_id, requester=requester,
            )
        except Exception:
            return {"target_node_id": node_id, "total_affected_nodes": LARGE_DELETE_THRESHOLD}
        finally:
            db.close()
