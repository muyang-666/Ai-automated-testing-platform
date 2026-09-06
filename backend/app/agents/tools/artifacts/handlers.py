"""Thin P08 handlers: adapt trusted context to TestArtifact application services."""
from __future__ import annotations

import json
from contextlib import contextmanager

from app.agents.conversation.messages import TextContent
from app.agents.conversation.tool_executor import ToolExecutionResult, ToolReportedError
from app.agents.tools.artifacts.runtime import ArtifactRuntimeContext
from app.models.agent.agent_session import AgentSession
from app.models.user import User
from app.services.agent import agent_run_service, conversation_service
from app.services.permission_service import can_read_project
from app.services import requirement_doc_service
from app.services.test_artifacts import artifact_service, quality_service
from app.services.test_artifacts.errors import (
    RevisionConflictError, TestArtifactError, TestArtifactNotFoundError,
    TestArtifactPermissionError, TestArtifactValidationError,
)


def _reported(error_code: str, message: str, *, data: dict | None = None,
              retryable: bool = False) -> ToolReportedError:
    payload = {"status": "error", "error_code": error_code, "message": message,
               "data": data or {}, "retryable": retryable}
    return ToolReportedError(error_code, ToolExecutionResult(
        content=[TextContent(text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))],
        details=payload,
    ))


def _translate(exc: TestArtifactError) -> ToolReportedError:
    if isinstance(exc, RevisionConflictError):
        return _reported("revision_conflict", "Artifact changed after it was read.",
                         data=exc.detail, retryable=True)
    if isinstance(exc, TestArtifactNotFoundError):
        return _reported("artifact_not_found", "Current Artifact is unavailable.")
    if isinstance(exc, TestArtifactPermissionError):
        return _reported("permission_denied", "Artifact write permission is required.")
    if isinstance(exc, TestArtifactValidationError):
        return _reported("invalid_operation", "Artifact operation was rejected.")
    return _reported("artifact_service_error", "Artifact service failed safely.")


def _trusted(runtime) -> ArtifactRuntimeContext:
    value = getattr(runtime, "application_context", runtime)
    if not isinstance(value, ArtifactRuntimeContext):
        raise _reported("runtime_context_invalid", "Trusted Artifact context is unavailable.")
    return value


@contextmanager
def _context(runtime, *, write: bool = False):
    runtime = _trusted(runtime)
    if not isinstance(runtime, ArtifactRuntimeContext) or runtime.artifact_id is None:
        raise _reported("artifact_not_focused", "No current Artifact is focused.")
    if "artifact:write" not in runtime.permissions and write:
        raise _reported("permission_denied", "Artifact write permission is required.")
    if "artifact:read" not in runtime.permissions:
        raise _reported("permission_denied", "Artifact read permission is required.")
    db = runtime.session_factory()
    try:
        user = db.get(User, runtime.user_id)
        session = db.get(AgentSession, runtime.conversation_id)
        if user is None or session is None or session.user_id != runtime.user_id \
                or session.mode != "conversation" \
                or conversation_service.focused_artifact_id(session) != runtime.artifact_id:
            raise _reported("runtime_context_invalid", "Trusted Artifact context is no longer valid.")
        if write and runtime.worker_id is not None and runtime.execution_token is not None:
            agent_run_service.assert_execution_ownership(
                db, runtime.run_id, runtime.worker_id, runtime.execution_token,
            )
        yield db, user, session
    except ToolReportedError:
        db.rollback()
        raise
    except TestArtifactError as exc:
        db.rollback()
        raise _translate(exc) from None
    except Exception:
        db.rollback()
        raise _reported("artifact_service_error", "Artifact service failed safely.") from None
    finally:
        db.close()


def _ok(summary: str, data: dict, diff_ref: str | None = None) -> ToolExecutionResult:
    payload = {"status": "ok", "summary": summary, "data": data}
    if diff_ref is not None:
        payload["diff_ref"] = diff_ref
    return ToolExecutionResult(
        content=[TextContent(text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))],
        details=payload,
    )


def get_current_artifact(arguments, runtime):
    runtime = _trusted(runtime)
    del arguments
    with _context(runtime) as (db, user, _session):
        row = artifact_service.get_artifact(db, artifact_id=runtime.artifact_id, requester=user)
        return _ok("Current Artifact metadata", {
            "artifact_id": row.id, "title": row.title, "artifact_type": row.artifact_type,
            "current_revision": row.current_revision, "root_node_id": row.root_node_id,
            "status": row.status, "project_id": row.project_id,
        })


def _find_tree_node(root: dict | None, node_id: int) -> dict | None:
    if root is None:
        return None
    stack = [root]
    while stack:
        node = stack.pop()
        if node["id"] == node_id:
            return node
        stack.extend(reversed(node.get("children") or []))
    return None


def read_artifact_outline(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        tree = artifact_service.get_tree(db, artifact_id=runtime.artifact_id, requester=user)
        root = tree["root"]
        if arguments.get("root_node_id") is not None:
            root = _find_tree_node(root, arguments["root_node_id"])
            if root is None:
                raise _reported("node_not_found", "Requested Artifact node is unavailable.")
        count = 0
        truncated = False

        def walk(node: dict, depth: int) -> dict:
            nonlocal count, truncated
            count += 1
            children = node.get("children") or []
            result = {"node_id": node["id"], "node_type": node["node_type"],
                      "title": node["title"], "parent_id": node["parent_id"],
                      "children_count": len(children), "order_key": node["order_key"],
                      "children": []}
            if depth >= arguments["max_depth"]:
                truncated |= bool(children)
                return result
            for child in children:
                if count >= arguments["max_nodes"]:
                    truncated = True
                    break
                result["children"].append(walk(child, depth + 1))
            return result

        outline = walk(root, 0) if root is not None else None
        return _ok("Artifact outline", {"artifact_id": runtime.artifact_id,
            "revision": tree["current_revision"], "outline": outline,
            "returned_nodes": count, "truncated": truncated})


def read_artifact_nodes(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        nodes = artifact_service.get_nodes(db, artifact_id=runtime.artifact_id,
            node_ids=arguments["node_ids"], requester=user)
        row = artifact_service.get_artifact(db, artifact_id=runtime.artifact_id, requester=user)
        return _ok("Artifact nodes", {"artifact_id": runtime.artifact_id,
                                      "revision": row.current_revision, "nodes": nodes})


def search_artifact(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        nodes = artifact_service.search_nodes(db, artifact_id=runtime.artifact_id,
            requester=user, keyword=arguments.get("keyword"), node_type=arguments.get("node_type"),
            tag=arguments.get("tag"), limit=arguments["limit"])
        row = artifact_service.get_artifact(db, artifact_id=runtime.artifact_id, requester=user)
        return _ok("Artifact search results", {"artifact_id": runtime.artifact_id,
                                      "revision": row.current_revision, "nodes": nodes})


def get_artifact_diff(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        diff = artifact_service.get_recent_diff(db, artifact_id=runtime.artifact_id,
            requester=user, revision_count=arguments["revision_count"])
        changes = diff["changes"]
        diff["changes"] = changes[:arguments["max_changes"]]
        diff["truncated"] = len(changes) > arguments["max_changes"]
        return _ok("Recent Artifact diff", diff,
                   f"{diff['from_revision']}..{diff['to_revision']}")


def _context_bound_requirement_id(session: AgentSession) -> int | None:
    """Conversation 建立时明确绑定的 Requirement（可信来源）。

    SourceRef = provenance metadata，不是 permission/capability：Artifact node 上的
    source_refs（即使是模型写入的）绝不扩大 Requirement 读取范围。
    """
    context = session.context_json if isinstance(session.context_json, dict) else {}
    if context.get("source_type") in {"requirement", "requirement_doc"}:
        value = context.get("source_id")
        if type(value) is int and value > 0:
            return value
    return None


def read_requirement(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, session):
        row = artifact_service.get_artifact(db, artifact_id=runtime.artifact_id, requester=user)
        bound_id = _context_bound_requirement_id(session)
        if bound_id is None:
            raise _reported("requirement_not_bound", "This Conversation has no bound requirement.")
        requested = arguments.get("requirement_id")
        if requested is None:
            requested = bound_id
        # 唯一权威：Conversation 明确绑定的 Requirement。模型写入的 source_refs 不参与。
        if requested != bound_id:
            raise _reported("requirement_not_bound", "The requirement is not bound to this Conversation.")
        requirement = requirement_doc_service.get_requirement_doc_by_id(db, requested)
        # effective project scope = 当前 Artifact 的 project（focus 已保证 Artifact 与
        # Conversation 项目一致）；服务端再次验证 Requirement 归属与用户可读。
        # projectless Artifact（effective_project=None）一律拒绝读取项目 Requirement。
        if requirement is None or row.project_id is None \
                or requirement.project_id != row.project_id or requirement.is_deleted \
                or not can_read_project(db, user, requirement.project_id):
            raise _reported("requirement_not_found", "Bound requirement is unavailable.")
        content = requirement.content or ""
        return _ok("Bound requirement", {"requirement_id": requirement.id,
            "title": requirement.title,
            "content": content[:arguments["max_chars"]],
            "truncated": len(content) > arguments["max_chars"],
            "status": requirement.status, "project_id": requirement.project_id})


def _node_operation(node: dict, *, parent_id=None, order_key=None, ref=None) -> dict:
    operation = {"operation_type": "add_node", "parent_id": parent_id,
                 "node_type": node["node_type"], "title": node["title"]}
    if node.get("content") is not None:
        operation["content"] = node["content"]
    if node.get("source_refs") is not None:
        operation["source_refs"] = node["source_refs"]
    if order_key is not None:
        operation["order_key"] = order_key
    if ref is not None:
        operation["ref"] = ref
    return operation


def _apply_write(runtime, expected_revision: int, operations: list[dict], summary: str):
    runtime = _trusted(runtime)
    with _context(runtime, write=True) as (db, user, _session):
        result = artifact_service.apply_operations(db, artifact_id=runtime.artifact_id,
            expected_revision=expected_revision, operations=operations, requester=user,
            actor_type="agent", actor_user_id=user.id, conversation_id=runtime.conversation_id,
            run_id=runtime.run_id, summary=summary)
        db.flush()
        diff = artifact_service.get_diff(db, artifact_id=runtime.artifact_id,
            from_revision=expected_revision, to_revision=result["new_revision"], requester=user)
        affected = [change.get("node_id") for change in diff["changes"] if change.get("node_id") is not None]
        event_payload = {"artifact_id": runtime.artifact_id, "revision": result["new_revision"],
                         "run_id": runtime.run_id, "conversation_id": runtime.conversation_id,
                         "summary": summary}
        agent_run_service.append_event(db, runtime.conversation_id, runtime.run_id,
                                       "artifact_revision_created", event_payload)
        agent_run_service.append_event(db, runtime.conversation_id, runtime.run_id,
                                       "artifact_diff_created", event_payload | {"changes": diff["changes"]})
        db.commit()
        return _ok(summary, {"revision": result["new_revision"],
            "affected_node_ids": affected, "changes": diff["changes"]},
            f"{expected_revision}..{result['new_revision']}")


def add_artifact_node(arguments, runtime):
    node = arguments["node"]
    return _apply_write(runtime, arguments["expected_revision"], [
        _node_operation(node, parent_id=arguments["parent_id"], order_key=arguments.get("order_key")),
    ], f"Added {node['node_type']}: {node['title']}")


def update_artifact_node(arguments, runtime):
    # P08.1 null 合同：NodePatch schema 已拒绝"显式 null"；验证通过的 patch 中残留的
    # None 只可能是未设置字段的模型默认值 → 这里剔除默认值，不会静默吞掉任何用户语义
    # （source_refs=[] 是清空语义，[] 不是 None，不会被剔除）。
    patch = {key: value for key, value in arguments["patch"].items() if value is not None}
    return _apply_write(runtime, arguments["expected_revision"], [{
        "operation_type": "update_node", "target_node_id": arguments["target_node_id"],
        "patch": patch,
    }], f"Updated node {arguments['target_node_id']}")


def delete_artifact_node(arguments, runtime):
    return _apply_write(runtime, arguments["expected_revision"], [{
        "operation_type": "delete_node", "target_node_id": arguments["target_node_id"],
    }], f"Deleted node {arguments['target_node_id']}")


def move_artifact_node(arguments, runtime):
    operation = {"operation_type": "move_node", "target_node_id": arguments["target_node_id"],
                 "new_parent_id": arguments["new_parent_id"]}
    if arguments.get("new_order_key") is not None:
        operation["new_order_key"] = arguments["new_order_key"]
    return _apply_write(runtime, arguments["expected_revision"], [operation],
                        f"Moved node {arguments['target_node_id']}")


def batch_apply_artifact_operations(arguments, runtime):
    operations = []
    for item in arguments["operations"]:
        if item["operation_type"] == "add_node":
            operations.append(_node_operation(item["node"], parent_id=item["parent_id"],
                order_key=item.get("order_key"), ref=item.get("ref")))
        elif item["operation_type"] == "update_node":
            # 与 update_artifact_node 同一 null 合同：schema 拒显式 null，这里只剔除缺省 None
            patch = {key: value for key, value in item["patch"].items() if value is not None}
            operations.append({"operation_type": "update_node", "target_node_id": item["target_node_id"],
                               "patch": patch})
        elif item["operation_type"] == "delete_node":
            operations.append({"operation_type": "delete_node", "target_node_id": item["target_node_id"]})
        else:
            operation = {"operation_type": "move_node", "target_node_id": item["target_node_id"],
                         "new_parent_id": item["new_parent_id"]}
            if item.get("new_order_key") is not None:
                operation["new_order_key"] = item["new_order_key"]
            operations.append(operation)
    return _apply_write(runtime, arguments["expected_revision"], operations,
                        arguments.get("summary") or f"Applied {len(operations)} Artifact operations")


def validate_test_artifact(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        data = quality_service.validate_artifact(db, artifact_id=runtime.artifact_id,
            requester=user, root_node_id=arguments.get("root_node_id"))
        return _ok("Artifact validation", data)


def find_duplicate_cases(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        data = quality_service.find_duplicates(db, artifact_id=runtime.artifact_id,
            requester=user, root_node_id=arguments.get("root_node_id"),
            threshold=arguments["threshold"], limit=arguments["limit"])
        return _ok("Duplicate case candidates", data)


def analyze_test_coverage(arguments, runtime):
    runtime = _trusted(runtime)
    with _context(runtime) as (db, user, _session):
        data = quality_service.analyze_coverage(db, artifact_id=runtime.artifact_id,
            requester=user, root_node_id=arguments.get("root_node_id"))
        return _ok("Rule-based coverage analysis", data)
