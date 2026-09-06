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
        "parent_id": root_id, "node": {"node_type": "module", "title": "账号锁定"}}, runtime)
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


def test_read_requirement_node_source_refs_do_not_authorize(project_runtime_fixture, db_session):
    """P08.1：read_requirement 只认 Conversation 绑定；node 上的 source_refs（即使是模型
    写入且属于同项目）不授予读取能力——SourceRef = provenance，不是 permission。"""
    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    # 在 node 上写入"属于本项目 req_a"的引用（模型可写），但 read 仍只认会话绑定
    added, _ = _execute("add_artifact_node", {
        "expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_case", "title": "TC-REF",
                 "source_refs": [{"source_type": "requirement", "source_id": str(req_a)}]},
    }, runtime)
    assert added.message.is_error is False
    # 会话未绑定任何 requirement 的项目 Artifact：即使 node 引用存在也不可读
    user = db_session.get(User, USER_A)
    artifact_free = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=9302, requester=user, title="P2无绑定Artifact")
    session_free = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="无绑定会话", project_id=9302)
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session_free.id, artifact_id=artifact_free.id, requester=user)
    db_session.commit()
    runtime_free = ArtifactRuntimeContext(
        session_factory=SessionLocal, user_id=USER_A, conversation_id=session_free.id,
        run_id=None, artifact_id=artifact_free.id, project_id=9301,
        permissions=frozenset({"artifact:read", "artifact:write"}),
    )
    ref_added, _ = _execute("add_artifact_node", {
        "expected_revision": 1, "parent_id": artifact_free.root_node_id,
        "node": {"node_type": "test_case", "title": "TC-REF2",
                 "source_refs": [{"source_type": "requirement", "source_id": str(req_b)}]},
    }, runtime_free)
    assert ref_added.message.is_error is False
    unbound, _ = _execute("read_requirement", {"requirement_id": req_b}, runtime_free)
    assert unbound.message.is_error is True
    assert unbound.error_code == "requirement_not_bound"


def test_batch_add_update_move_and_single_revision(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    batch, _ = _execute("batch_apply_artifact_operations", {"expected_revision": 1,
        "summary": "新增两个分支", "operations": [
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "module", "title": "锁定"}, "ref": "lock"},
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "module", "title": "解锁"}},
        ]}, runtime)
    assert batch.message.details["data"]["revision"] == 2
    assert len(batch.message.details["data"]["affected_node_ids"]) == 2
    lock, unlock = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact_id, ArtifactNode.node_type == "module",
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
        "node": {"node_type": "module", "title": "A"}}, runtime)
    stale, _ = _execute("add_artifact_node", {"expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "module", "title": "B"}}, runtime)
    assert stale.message.is_error is True
    assert stale.message.details["error_code"] == "revision_conflict"
    assert stale.message.details["retryable"] is True
    assert stale.message.details["data"] == {"expected_revision": 1, "current_revision": 2}


def test_forged_identity_and_server_fields_are_rejected_before_handler(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    before = _revision(db_session, artifact_id)
    for extra in ({"user_id": USER_B}, {"project_id": 999}, {"owner_user_id": USER_B}):
        args = {"expected_revision": before, "parent_id": root_id,
                "node": {"node_type": "module", "title": "forged"}} | extra
        outcome, _ = _execute("add_artifact_node", args, runtime)
        assert outcome.message.is_error is True
        assert outcome.error_code == "invalid_arguments"
    assert _revision(db_session, artifact_id) == before


def test_cross_user_denied_and_changed_focus_uses_run_snapshot(runtime_fixture, db_session):
    """P08.3：跨用户仍拒绝；同一用户改 Session focus 后，工具按 Run 快照继续工作。"""
    runtime, artifact_id, root_id = runtime_fixture
    other = ArtifactRuntimeContext(
        session_factory=SessionLocal, user_id=USER_B, conversation_id=runtime.conversation_id,
        run_id=runtime.run_id, artifact_id=artifact_id, project_id=None,
        permissions=frozenset({"artifact:read", "artifact:write"}),
    )
    denied, _ = _execute("get_current_artifact", {}, other)
    assert denied.message.is_error is True
    assert denied.error_code == "runtime_context_invalid"
    session = conversation_service._owned_conversation(
        db_session, runtime.conversation_id, USER_A, require_active=False)
    session.context_json = {"focused_artifact_id": artifact_id + 999}
    db_session.commit()
    ok, _ = _execute("get_current_artifact", {}, runtime)
    assert ok.message.is_error is False
    assert ok.message.details["data"]["artifact_id"] == artifact_id

def test_batch_failure_rolls_back_every_operation(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    outcome, _ = _execute("batch_apply_artifact_operations", {"expected_revision": 1,
        "operations": [
            {"operation_type": "add_node", "parent_id": root_id,
             "node": {"node_type": "module", "title": "should rollback"}},
            {"operation_type": "move_node", "target_node_id": 999999, "new_parent_id": root_id},
        ]}, runtime)
    assert outcome.message.is_error
    assert _revision(db_session, artifact_id) == 1
    assert db_session.query(ArtifactNode).filter(ArtifactNode.title == "should rollback").count() == 0


def test_large_delete_requires_approval_and_does_not_mutate(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    operations = [{"operation_type": "add_node", "parent_id": root_id,
                   "node_type": "module", "title": "large", "ref": "large"}]
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
            {"operation_type": "add_node", "parent_id": root_id, "node_type": "module",
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
        "parent_id": root_id, "node": {"node_type": "module", "title": "cancelled"}},
        runtime, cancel=True)
    assert outcome.error_code == "canceled"
    assert _revision(db_session, artifact_id) == 1


def test_write_audit_and_events_link_conversation_and_run(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    _execute("add_artifact_node", {"expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "module", "title": "audit"}}, runtime)
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


# ── P08.1：Requirement 绑定（SourceRef ≠ 授权）+ NodePatch null 合同 ──


@pytest.fixture()
def project_runtime_fixture(db_session):
    from app.models.requirement_doc import RequirementDoc
    from app.models.user_role import UserRole

    role = db_session.query(Role).filter(Role.code == "system_admin").first()
    if role is None:
        role = Role(code="system_admin", name="system_admin", status="active")
        db_session.add(role)
    db_session.flush()
    user = db_session.get(User, USER_A)
    if user is None:
        user = User(id=USER_A, username="p08-project-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db_session.add(user)
        db_session.flush()
    if not db_session.query(UserRole).filter(UserRole.user_id == USER_A).first():
        db_session.add(UserRole(user_id=USER_A, role_id=role.id))
    project_a = Project(id=9301, name="项目A", status="active", is_deleted=False)
    project_b = Project(id=9302, name="项目B", status="active", is_deleted=False)
    req_a = RequirementDoc(project_id=9301, title="项目A需求", content="需求A：用户可登录",
                           requirement_type="功能需求", status="confirmed", is_deleted=False)
    req_b = RequirementDoc(project_id=9302, title="项目B需求", content="需求B：账户可锁定",
                           requirement_type="功能需求", status="confirmed", is_deleted=False)
    db_session.add_all([project_a, project_b, req_a, req_b])
    db_session.commit()
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=9301, requester=user, title="P1资产")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="P08-项目会话", project_id=9301,
        context_json={"source_type": "requirement", "source_id": req_a.id},
    )
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user)
    db_session.commit()
    runtime = ArtifactRuntimeContext(
        session_factory=SessionLocal, user_id=USER_A, conversation_id=session.id,
        run_id=None, artifact_id=artifact.id, project_id=9301,
        permissions=frozenset({"artifact:read", "artifact:write"}),
    )
    return runtime, artifact.id, artifact.root_node_id, req_a.id, req_b.id


def test_read_requirement_same_project_bound_allowed(project_runtime_fixture, db_session):
    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    outcome, _ = _execute("read_requirement", {}, runtime)
    assert outcome.message.is_error is False
    data = outcome.message.details["data"]
    assert data["requirement_id"] == req_a
    assert data["project_id"] == 9301
    assert "需求A" in data["content"]


def test_read_requirement_other_requirement_rejected_even_same_user(project_runtime_fixture):
    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    outcome, _ = _execute("read_requirement", {"requirement_id": req_b}, runtime)
    assert outcome.message.is_error is True
    assert outcome.message.details["error_code"] == "requirement_not_bound"


def test_forged_source_ref_cannot_expand_requirement_read(project_runtime_fixture, db_session):
    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    # 模型把 source_ref 指向项目 B 的 Requirement → 写入口拒绝（SourceRef≠授权）
    outcome, _ = _execute("add_artifact_node", {
        "expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_case", "title": "TC-FORGE",
                 "source_refs": [{"source_type": "requirement", "source_id": str(req_b)}]},
    }, runtime)
    assert outcome.message.is_error is True
    assert outcome.message.details["error_code"] == "invalid_operation"
    assert _revision(db_session, artifact_id) == 1
    # 即使模型把 source_ref 指向本项目的 req_a，也不能因此读取——read 只认会话绑定
    added, _ = _execute("add_artifact_node", {
        "expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_case", "title": "TC-BOUND",
                 "source_refs": [{"source_type": "requirement", "source_id": str(req_a)}]},
    }, runtime)
    assert added.message.is_error is False
    # 更换会话绑定后原 node 的 ref 不授予读取其他需求（此处绑定仍 req_a，读 req_a 可、req_b 不可）
    read_ok, _ = _execute("read_requirement", {}, runtime)
    assert read_ok.message.is_error is False and read_ok.message.details["data"]["requirement_id"] == req_a
    read_other, _ = _execute("read_requirement", {"requirement_id": req_b}, runtime)
    assert read_other.message.is_error is True


def test_read_requirement_projectless_artifact_not_bound(runtime_fixture):
    runtime, artifact_id, root_id = runtime_fixture
    outcome, _ = _execute("read_requirement", {}, runtime)
    assert outcome.message.is_error is True
    assert outcome.message.details["error_code"] == "requirement_not_bound"


def _add_manual_ref_case(runtime, db_session, root_id, title="TC1"):
    outcome, _ = _execute("add_artifact_node", {
        "expected_revision": 1, "parent_id": root_id,
        "node": {"node_type": "test_case", "title": title,
                 "source_refs": [{"source_type": "manual", "source_id": "M-1"}]},
    }, runtime)
    assert outcome.message.is_error is False
    node_id = outcome.message.details["data"]["affected_node_ids"][0]
    return node_id, outcome.message.details["data"]["revision"]


def test_update_patch_null_rejected_and_empty_array_clears(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    node_id, revision = _add_manual_ref_case(runtime, db_session, root_id)
    # 单条 update：显式 null → 拒绝（schema 层），Revision 不推进
    nulled, _ = _execute("update_artifact_node", {
        "expected_revision": revision, "target_node_id": node_id,
        "patch": {"source_refs": None},
    }, runtime)
    assert nulled.message.is_error is True
    assert _revision(db_session, artifact_id) == revision
    # batch update：显式 null 同样拒绝
    batch_null, _ = _execute("batch_apply_artifact_operations", {
        "expected_revision": revision,
        "operations": [{"operation_type": "update_node", "target_node_id": node_id,
                        "patch": {"title": None}}],
    }, runtime)
    assert batch_null.message.is_error is True
    assert _revision(db_session, artifact_id) == revision
    # source_refs=[] 清空（单条），patch 不被 Handler 静默变空：title 与 source_refs 同时生效
    cleared, _ = _execute("update_artifact_node", {
        "expected_revision": revision, "target_node_id": node_id,
        "patch": {"title": "TC1-改名", "source_refs": []},
    }, runtime)
    assert cleared.message.is_error is False
    assert _revision(db_session, artifact_id) == revision + 1
    db_session.expire_all()
    row = db_session.get(ArtifactNode, node_id)
    assert row.title == "TC1-改名"
    assert row.source_refs_json is None


def test_batch_update_empty_array_clears(runtime_fixture, db_session):
    runtime, artifact_id, root_id = runtime_fixture
    node_id, revision = _add_manual_ref_case(runtime, db_session, root_id)
    cleared, _ = _execute("batch_apply_artifact_operations", {
        "expected_revision": revision,
        "operations": [{"operation_type": "update_node", "target_node_id": node_id,
                        "patch": {"source_refs": []}}],
    }, runtime)
    assert cleared.message.is_error is False
    assert _revision(db_session, artifact_id) == revision + 1
    db_session.expire_all()
    assert db_session.get(ArtifactNode, node_id).source_refs_json is None


# ── P08.2：Artifact 写 fencing / restore 历史 provenance / Requirement 绑定入口 ──


def test_artifact_write_fence_rejects_stale_owner_and_cancel(runtime_fixture, db_session):
    from dataclasses import replace

    from app.models.agent.agent_run import AgentRun

    runtime, artifact_id, root_id = runtime_fixture
    assert runtime.run_id is not None
    run = db_session.get(AgentRun, runtime.run_id)
    run.status = "running"
    run.worker_id = "w-1"
    run.execution_token = 1
    db_session.commit()

    owned = replace(runtime, worker_id="w-1", execution_token=1)
    added, _ = _execute("add_artifact_node", {"expected_revision": 1,
        "parent_id": root_id, "node": {"node_type": "module", "title": "锁定"}}, owned)
    assert added.message.is_error is False
    assert added.message.details["data"]["revision"] == 2
    node_id = added.message.details["data"]["affected_node_ids"][0]

    # 场景 A：claim 被重新赋值（execution_token 1 → 2）后旧 token 提交 → fencing 拒绝
    run = db_session.get(AgentRun, runtime.run_id)
    run.execution_token = 2
    db_session.commit()
    stale, _ = _execute("update_artifact_node", {"expected_revision": 2,
        "target_node_id": node_id, "patch": {"title": "改名"}}, owned)
    assert stale.message.is_error is True
    assert stale.error_code == "ownership_lost"
    assert _revision(db_session, artifact_id) == 2  # 未提交任何 Artifact Revision

    # 场景 B：cancel 竞态（run 已终态）→ fencing 拒绝
    run = db_session.get(AgentRun, runtime.run_id)
    run.status = "cancelled"
    run.worker_id = "w-1"
    run.execution_token = 2
    db_session.commit()
    cancelled, _ = _execute("update_artifact_node", {"expected_revision": 2,
        "target_node_id": node_id, "patch": {"title": "改名"}}, replace(runtime, worker_id="w-1",
                                                                        execution_token=2))
    assert cancelled.message.is_error is True
    assert cancelled.error_code == "ownership_lost"
    assert _revision(db_session, artifact_id) == 2


def test_restore_historical_provenance_allowed_after_requirement_soft_delete(
        project_runtime_fixture, db_session):
    """rev N 引用 requirement → requirement 后来软删 → internal undo/restore 成功；
    read_requirement 对已删除 requirement 仍拒绝。"""
    from app.models.requirement_doc import RequirementDoc

    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    user = db_session.get(User, USER_A)
    # 显式模块（避免隐式默认模块参与批内 affected 推导）
    module = artifact_service.get_or_create_default_module(
        db_session, artifact_id=artifact_id, requester=user)
    rev_base = artifact_service.get_artifact(
        db_session, artifact_id=artifact_id, requester=user).current_revision
    added, _ = _execute("add_artifact_node", {"expected_revision": rev_base,
        "parent_id": module.id,
        "node": {"node_type": "test_case", "title": "TC-REQ",
                 "source_refs": [{"source_type": "requirement", "source_id": str(req_a)}]}},
        runtime)
    assert added.message.is_error is False
    node_id = added.message.details["data"]["affected_node_ids"][0]
    revision = added.message.details["data"]["revision"]
    cleared, _ = _execute("update_artifact_node", {"expected_revision": revision,
        "target_node_id": node_id, "patch": {"source_refs": []}}, runtime)
    assert cleared.message.is_error is False
    cleared_rev = cleared.message.details["data"]["revision"]
    requirement = db_session.get(RequirementDoc, req_a)
    requirement.is_deleted = True
    db_session.commit()
    db_session.expire_all()
    result = artifact_service.undo_latest(db_session, artifact_id=artifact_id, requester=user)
    db_session.commit()
    assert result["new_revision"] == cleared_rev + 1
    db_session.expire_all()
    row = db_session.get(ArtifactNode, node_id)
    assert row.source_refs_json[0]["source_id"] == str(req_a)

def test_read_requirement_rejects_soft_deleted_requirement(project_runtime_fixture, db_session):
    from app.models.requirement_doc import RequirementDoc

    runtime, artifact_id, root_id, req_a, req_b = project_runtime_fixture
    ok, _ = _execute("read_requirement", {}, runtime)
    assert ok.message.is_error is False
    db_session.get(RequirementDoc, req_a).is_deleted = True
    db_session.commit()
    read, _ = _execute("read_requirement", {"requirement_id": req_a}, runtime)
    assert read.message.is_error is True
    assert read.error_code == "requirement_not_found"


# ── P08.3：Tool 使用 Run Snapshot，不再依赖当前 Session focus ──


def test_tool_uses_run_snapshot_after_focus_switch_before_promote(runtime_fixture, db_session):
    """A 运行中排队 follow-up（快照 A）→ A 终态 → 会话切到 B → follow-up promote 后
    工具仍按 Run 快照 A 工作，不因 Session focus=B 失效。"""
    from dataclasses import replace

    from app.models.agent.agent_run import AgentRun

    runtime, artifact_id, root_id = runtime_fixture
    follow = conversation_service.submit_conversation_turn(
        db_session, session_id=runtime.conversation_id, requester_user_id=USER_A,
        content="排队", client_request_id="p083-queue", queue_mode="follow_up",
        message_id_factory=lambda: "p083-queue-msg", timestamp_ms_factory=lambda: 4,
    ).run
    head = db_session.get(AgentRun, runtime.run_id)
    head.status = "succeeded"
    db_session.commit()
    art_b = artifact_service.create_artifact(db_session, requester=db_session.get(User, USER_A),
                                             title="B")
    conversation_service.focus_conversation_artifact(
        db_session, session_id=runtime.conversation_id, artifact_id=art_b.id,
        requester=db_session.get(User, USER_A))
    db_session.commit()
    follow.status = "running"  # promote 后成为新 head（快照仍 A）
    db_session.commit()
    follow_runtime = replace(runtime, run_id=follow.id)
    meta, _ = _execute("get_current_artifact", {}, follow_runtime)
    assert meta.message.is_error is False
    assert meta.message.details["data"]["artifact_id"] == artifact_id
    added, _ = _execute("add_artifact_node", {"expected_revision": 1,
        "parent_id": root_id, "node": {"node_type": "test_case", "title": "TC-A"}},
        follow_runtime)
    assert added.message.is_error is False
    assert added.message.details["data"]["revision"] == 2
    db_session.expire_all()
    session = conversation_service._owned_conversation(
        db_session, runtime.conversation_id, USER_A, require_active=False)
    assert conversation_service.focused_artifact_id(session) == art_b.id
    assert artifact_service.get_artifact(
        db_session, artifact_id=artifact_id, requester=db_session.get(User, USER_A)
    ).current_revision == 2
