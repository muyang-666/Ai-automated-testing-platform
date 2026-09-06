"""P08 Artifact Tool deterministic tests; SQLite + Fake calls, no LLM/network."""
import asyncio

import pytest

from app.agents.conversation.messages import AssistantMessage, ToolCall, Usage
from app.agents.conversation.tool_executor import execute_tool_call
from app.agents.tools.artifacts.policy import ArtifactToolPolicy
from app.agents.tools.artifacts.runtime import ArtifactRuntimeContext
from app.agents.tools.conversation_safe_tools import build_conversation_tool_registry
from app.core.database import SessionLocal
from app.models.agent.agent_event import AgentEvent
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.role import Role
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.models.user_role import UserRole
from app.services.agent import conversation_service
from app.services.test_artifacts import artifact_service

USER_A = 8101
USER_B = 8102


def _usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def _case(tags=None, expected=None):
    return {"preconditions": [], "steps": [{"action": "执行操作", "data": None}],
            "expected_results": expected or ["观察到结果"], "priority": "P2",
            "tags": tags or []}


@pytest.fixture()
def runtime_fixture(db_session):
    role = Role(code="system_admin", name="system_admin", status="active")
    db_session.add(role)
    db_session.add_all([
        User(id=USER_A, username="p08-a", password_hash="x", salt="y", status="active", is_deleted=False),
        User(id=USER_B, username="p08-b", password_hash="x", salt="y", status="active", is_deleted=False),
    ])
    db_session.flush()
    db_session.add(UserRole(user_id=USER_A, role_id=role.id))
    db_session.commit()
    user = db_session.get(User, USER_A)
    artifact = artifact_service.create_artifact(db_session, requester=user, title="登录测试")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="P08",
    )
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user,
    )
    db_session.commit()
    submission = conversation_service.submit_conversation_turn(
        db_session, session_id=session.id, requester_user_id=USER_A,
        content="edit", client_request_id="p08-turn",
        message_id_factory=lambda: "p08-user", timestamp_ms_factory=lambda: 1,
    )
    return ArtifactRuntimeContext(
        session_factory=SessionLocal, user_id=USER_A, conversation_id=session.id,
        run_id=submission.run.id, artifact_id=artifact.id, project_id=None,
        permissions=frozenset({"artifact:read", "artifact:write"}),
    ), artifact.id, artifact.root_node_id


def _execute(name, arguments, runtime, *, cancel=False):
    registry = build_conversation_tool_registry()
    call = ToolCall(id=f"call-{name}", name=name, arguments=arguments)
    assistant = AssistantMessage(message_id=f"assistant-{name}", timestamp=1,
        role="assistant", content=[call], api="chat", provider="fake", model="fake",
        usage=_usage(), stop_reason="toolUse")
    cancel_event = asyncio.Event()
    if cancel:
        cancel_event.set()
    events = []
    outcome = asyncio.run(execute_tool_call(
        assistant_message=assistant, tool_call=call, registry=registry,
        policy=ArtifactToolPolicy(), cancel_event=cancel_event, deadline=None,
        event_sink=events.append, message_id=f"result-{name}", timestamp=2,
        metadata={"artifact_id": runtime.artifact_id}, application_context=runtime,
    ))
    return outcome, events


def _revision(db, artifact_id):
    db.expire_all()
    return artifact_service.get_artifact(
        db, artifact_id=artifact_id, requester=db.get(User, USER_A),
    ).current_revision


def test_registry_and_current_metadata(runtime_fixture):
    runtime, artifact_id, root_id = runtime_fixture
    names = {definition.name for definition in build_conversation_tool_registry().list()}
    assert len(names) == 16
    assert {"load_skill", "get_current_artifact", "batch_apply_artifact_operations",
            "analyze_test_coverage"} <= names
    outcome, _ = _execute("get_current_artifact", {}, runtime)
    assert outcome.message.is_error is False
    assert outcome.message.details["data"]["root_node_id"] == root_id
    assert outcome.message.details["data"]["artifact_id"] == artifact_id


def test_add_read_search_outline_and_recent_diff(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    added, _ = _execute("add_artifact_node", {"expected_revision": 1,
        "parent_id": root_id, "node": {"node_type": "test_point", "title": "账号锁定"}}, runtime)
    assert added.message.details["data"]["revision"] == 2
    node_id = added.message.details["data"]["affected_node_ids"][0]
    read, _ = _execute("read_artifact_nodes", {"node_ids": [node_id]}, runtime)
    assert read.message.details["data"]["nodes"][0]["title"] == "账号锁定"
    search, _ = _execute("search_artifact", {"keyword": "锁定", "limit": 10}, runtime)
    assert [node["id"] for node in search.message.details["data"]["nodes"]] == [node_id]
    outline, _ = _execute("read_artifact_outline", {"max_depth": 3, "max_nodes": 10}, runtime)
    assert outline.message.details["data"]["outline"]["children"][0]["node_id"] == node_id
    diff, _ = _execute("get_artifact_diff", {"revision_count": 1}, runtime)
    assert diff.message.details["data"]["changes"][0]["change"] == "added"


def test_read_requirement_only_uses_bound_source(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    project = Project(id=9101, name="需求项目", status="active", is_deleted=False)
    requirement = RequirementDoc(id=9102, project_id=project.id, title="登录需求",
                                 content="连续失败五次锁定账号", status="confirmed", is_deleted=False)
    db_session.add_all([project, requirement])
    artifact_service.apply_operations(db_session, artifact_id=artifact_id,
        expected_revision=1, requester=db_session.get(User, USER_A), operations=[{
            "operation_type": "update_node", "target_node_id": root_id,
            "patch": {"source_refs": [{"source_type": "requirement",
                       "source_id": str(requirement.id)}]},
        }])
    db_session.commit()
    result, _ = _execute("read_requirement", {"requirement_id": requirement.id}, runtime)
    assert result.message.details["data"]["content"] == "连续失败五次锁定账号"
    rejected, _ = _execute("read_requirement", {"requirement_id": requirement.id + 1}, runtime)
    assert rejected.error_code == "requirement_not_bound"


def test_batch_add_update_move_and_single_revision(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    batch, _ = _execute("batch_apply_artifact_operations", {"expected_revision": 1,
        "summary": "新增两个分支", "operations": [
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "test_point", "title": "锁定"}, "ref": "lock"},
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "test_point", "title": "解锁"}},
        ]}, runtime)
    assert batch.message.details["data"]["revision"] == 2
    assert len(batch.message.details["data"]["affected_node_ids"]) == 2
    lock, unlock = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact_id, ArtifactNode.node_type == "test_point",
    ).order_by(ArtifactNode.id).all()
    updated, _ = _execute("update_artifact_node", {"expected_revision": 2,
        "target_node_id": lock.id, "patch": {"title": "账号锁定"}}, runtime)
    assert updated.message.details["data"]["revision"] == 3
    case, _ = _execute("add_artifact_node", {"expected_revision": 3,
        "parent_id": lock.id, "node": {"node_type": "test_case", "title": "第5次锁定",
        "content": _case(["边界"])}}, runtime)
    case_id = case.message.details["data"]["affected_node_ids"][0]
    moved, _ = _execute("move_artifact_node", {"expected_revision": 4,
        "target_node_id": case_id, "new_parent_id": unlock.id}, runtime)
    assert moved.message.details["data"]["revision"] == 5
    db_session.expire_all()
    assert db_session.get(ArtifactNode, case_id).parent_id == unlock.id


def test_stale_revision_is_machine_readable_and_retryable(runtime_fixture):
    runtime, _artifact_id, root_id = runtime_fixture
    _execute("add_artifact_node", {"expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_point", "title": "A"}}, runtime)
    stale, _ = _execute("add_artifact_node", {"expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_point", "title": "B"}}, runtime)
    assert stale.message.is_error is True
    assert stale.message.details["error_code"] == "revision_conflict"
    assert stale.message.details["retryable"] is True
    assert stale.message.details["data"] == {"expected_revision": 1, "current_revision": 2}


def test_forged_identity_and_server_fields_are_rejected_before_handler(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    before = _revision(db_session, artifact_id)
    for extra in ({"user_id": USER_B}, {"project_id": 999}, {"owner_user_id": USER_B}):
        args = {"expected_revision": before, "parent_id": root_id,
                "node": {"node_type": "test_point", "title": "forged"}} | extra
        outcome, _ = _execute("add_artifact_node", args, runtime)
        assert outcome.message.is_error is True
        assert outcome.error_code == "invalid_arguments"
    assert _revision(db_session, artifact_id) == before


def test_cross_user_and_changed_focus_are_denied(runtime_fixture, db_session):
    runtime, artifact_id, _root_id = runtime_fixture
    foreign = ArtifactRuntimeContext(session_factory=SessionLocal, user_id=USER_B,
        conversation_id=runtime.conversation_id, run_id=runtime.run_id,
        artifact_id=artifact_id, project_id=None,
        permissions=frozenset({"artifact:read", "artifact:write"}))
    outcome, _ = _execute("get_current_artifact", {}, foreign)
    assert outcome.message.is_error and outcome.message.details["error_code"] == "runtime_context_invalid"
    session = db_session.get(__import__("app.models.agent.agent_session", fromlist=["AgentSession"]).AgentSession,
                             runtime.conversation_id)
    session.context_json = {"focused_artifact_id": artifact_id + 999}
    db_session.commit()
    outcome, _ = _execute("get_current_artifact", {}, runtime)
    assert outcome.message.details["error_code"] == "runtime_context_invalid"


def test_batch_failure_rolls_back_every_operation(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    outcome, _ = _execute("batch_apply_artifact_operations", {"expected_revision": 1,
        "operations": [
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "test_point", "title": "should rollback"}},
            {"operation_type": "move_node", "target_node_id": 999999, "new_parent_id": root_id},
        ]}, runtime)
    assert outcome.message.is_error
    assert _revision(db_session, artifact_id) == 1
    assert db_session.query(ArtifactNode).filter(ArtifactNode.title == "should rollback").count() == 0


def test_large_delete_requires_approval_and_does_not_mutate(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    operations = [{"operation_type": "add_node", "parent_id": root_id,
                   "node_type": "test_point", "title": "large", "ref": "large"}]
    operations += [{"operation_type": "add_node", "parent_id": "@large",
                    "node_type": "test_case", "title": f"case-{index}", "content": _case()}
                   for index in range(9)]
    result = artifact_service.apply_operations(db_session, artifact_id=artifact_id,
        expected_revision=1, operations=operations, requester=db_session.get(User, USER_A))
    db_session.commit()
    target = db_session.query(ArtifactNode).filter(ArtifactNode.title == "large").one()
    outcome, _ = _execute("delete_artifact_node", {"expected_revision": result["new_revision"],
                                                    "target_node_id": target.id}, runtime)
    assert outcome.message.is_error and outcome.error_code == "approval_required"
    assert outcome.message.details["status"] == "error"
    assert outcome.message.details["data"]["total_affected_nodes"] == 10
    assert _revision(db_session, artifact_id) == 2


def test_quality_tools_are_deterministic_and_read_only(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    result = artifact_service.apply_operations(db_session, artifact_id=artifact_id,
        expected_revision=1, requester=db_session.get(User, USER_A), operations=[
            {"operation_type": "add_node", "parent_id": root_id, "node_type": "test_point",
             "title": "边界与状态转换", "ref": "point"},
            {"operation_type": "add_node", "parent_id": "@point", "node_type": "test_case",
             "title": "锁定边界", "content": _case(["边界", "状态转换"])},
            {"operation_type": "add_node", "parent_id": "@point", "node_type": "test_case",
             "title": "锁定边界", "content": _case(["边界", "状态转换"])},
            {"operation_type": "add_node", "parent_id": "@point", "node_type": "test_case",
             "title": "空步骤", "content": {"preconditions": [], "steps": [],
             "expected_results": [], "priority": "P2", "tags": []}},
        ])
    db_session.commit()
    before = result["new_revision"]
    validation, _ = _execute("validate_test_artifact", {"root_node_id": None}, runtime)
    duplicates, _ = _execute("find_duplicate_cases", {"threshold": 0.88, "limit": 20,
                                                       "root_node_id": None}, runtime)
    coverage, _ = _execute("analyze_test_coverage", {"root_node_id": None}, runtime)
    assert {issue["code"] for issue in validation.message.details["data"]["issues"]} >= {
        "missing_steps", "missing_expected_results"}
    assert duplicates.message.details["data"]["pairs"][0]["score"] == 1.0
    assert {"boundary", "state_transition"} <= set(coverage.message.details["data"]["covered"])
    assert _revision(db_session, artifact_id) == before


def test_cancel_prevents_write(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    outcome, _ = _execute("add_artifact_node", {"expected_revision": 1,
        "parent_id": root_id, "node": {"node_type": "test_point", "title": "cancelled"}},
        runtime, cancel=True)
    assert outcome.error_code == "canceled"
    assert _revision(db_session, artifact_id) == 1


def test_write_audit_and_events_link_conversation_and_run(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    _execute("add_artifact_node", {"expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_point", "title": "audit"}}, runtime)
    revisions = artifact_service.list_revisions(db_session, artifact_id=artifact_id,
                                                 requester=db_session.get(User, USER_A))
    latest = revisions[-1]
    assert latest.actor_type == "agent" and latest.actor_user_id == USER_A
    assert latest.conversation_id == runtime.conversation_id and latest.run_id == runtime.run_id
    event_types = [row.event_type for row in db_session.query(AgentEvent).filter(
        AgentEvent.run_id == runtime.run_id).all()]
    assert {"artifact_revision_created", "artifact_diff_created"} <= set(event_types)


def test_load_skill_is_allowlisted_versioned_and_path_safe(runtime_fixture):
    runtime, *_ = runtime_fixture
    loaded, _ = _execute("load_skill", {"name": "test-design"}, runtime)
    data = loaded.message.details["data"]
    assert data["version"] == "1.0.0" and len(data["sha256"]) == 64
    assert "Read an existing node" in data["content"]
    invalid, _ = _execute("load_skill", {"name": "../../secret"}, runtime)
    assert invalid.error_code == "invalid_arguments"
    unknown, _ = _execute("load_skill", {"name": "not-registered"}, runtime)
    assert unknown.error_code == "unknown_skill"
