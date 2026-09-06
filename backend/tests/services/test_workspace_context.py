"""P09.3A Workspace Context validation, snapshot and Runner injection."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from app.agents.conversation.events import AssistantDoneEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.tools.artifacts.runtime import build_artifact_runtime_context
from app.agents.tools.conversation_safe_tools import build_conversation_tool_registry
from app.core.database import SessionLocal
from app.models.agent.agent_run import AgentRun
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.services.agent import conversation_service
from app.services.agent.conversation_service import ConversationConflict, InvalidWorkspaceContext
from app.services.test_artifacts import artifact_service

USER_ID = 9301


@pytest.fixture()
def world(db_session):
    user = User(id=USER_ID, username="workspace-user", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db_session.add(user)
    db_session.commit()
    artifact = artifact_service.create_artifact(db_session, requester=user, title="功能用例")
    artifact_service.apply_operations(db_session, artifact_id=artifact.id, expected_revision=1,
        requester=user, operations=[
            {"operation_type": "add_node", "parent_id": artifact.root_node_id,
             "node_type": "module", "title": "登录", "ref": "login"},
            {"operation_type": "add_node", "parent_id": "@login",
             "node_type": "module", "title": "账号锁定", "ref": "lock"},
            {"operation_type": "add_node", "parent_id": "@lock",
             "node_type": "test_case", "title": "第五次失败锁定"},
            {"operation_type": "add_node", "parent_id": artifact.root_node_id,
             "node_type": "module", "title": "支付"},
        ])
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=user.id, title="workspace")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user)
    db_session.commit()
    nodes = {node.title: node for node in db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id).all()}
    return user, artifact, session, nodes


def _submit(db, session_id, key, workspace):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_ID,
        content="这里补三个边界", client_request_id=key,
        workspace_context=workspace,
        message_id_factory=lambda: f"message-{key}", timestamp_ms_factory=lambda: 1,
    ).run


def test_workspace_context_persisted_and_input_object_cannot_mutate_snapshot(world, db_session):
    _user, _artifact, session, nodes = world
    workspace = {"selected_module_id": nodes["账号锁定"].id,
                 "selected_case_id": None, "current_view": "mindmap"}
    run = _submit(db_session, session.id, "snapshot", workspace)
    run_id = run.id
    workspace["selected_module_id"] = nodes["支付"].id
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(AgentRun, run_id)
    assert stored.workspace_context_json == {
        "selected_module_id": nodes["账号锁定"].id,
        "selected_case_id": None, "current_view": "mindmap"}


def test_selected_module_in_focused_artifact_succeeds(world, db_session):
    _user, _artifact, session, nodes = world
    run = _submit(db_session, session.id, "module-ok", {
        "selected_module_id": nodes["登录"].id, "selected_case_id": None,
        "current_view": "list"})
    assert conversation_service.workspace_context_from_run(run)["selected_module_id"] == nodes["登录"].id


def test_module_from_another_artifact_is_rejected(world, db_session):
    user, _artifact, session, _nodes = world
    other = artifact_service.create_artifact(db_session, requester=user, title="其他")
    artifact_service.apply_operations(db_session, artifact_id=other.id, expected_revision=1,
        requester=user, operations=[{"operation_type": "add_node",
        "parent_id": other.root_node_id, "node_type": "module", "title": "外部模块"}])
    db_session.commit()
    foreign = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == other.id, ArtifactNode.node_type == "module").one()
    with pytest.raises(InvalidWorkspaceContext):
        _submit(db_session, session.id, "foreign", {
            "selected_module_id": foreign.id, "selected_case_id": None, "current_view": "list"})


def test_test_case_cannot_be_submitted_as_module(world, db_session):
    _user, _artifact, session, nodes = world
    with pytest.raises(InvalidWorkspaceContext):
        _submit(db_session, session.id, "wrong-type", {
            "selected_module_id": nodes["第五次失败锁定"].id,
            "selected_case_id": None, "current_view": "list"})


def test_selected_case_and_direct_parent_module_are_validated(world, db_session):
    _user, _artifact, session, nodes = world
    case = nodes["第五次失败锁定"]
    run = _submit(db_session, session.id, "case-ok", {
        "selected_module_id": nodes["账号锁定"].id,
        "selected_case_id": case.id, "current_view": "mindmap"})
    assert run.workspace_context_json["selected_case_id"] == case.id
    run.status = "cancelled"
    run.active_slot = None
    db_session.commit()
    with pytest.raises(InvalidWorkspaceContext):
        _submit(db_session, session.id, "case-parent-wrong", {
            "selected_module_id": nodes["登录"].id,
            "selected_case_id": case.id, "current_view": "list"})


def test_deleted_selection_is_rejected(world, db_session):
    user, artifact, session, nodes = world
    artifact_service.apply_operations(db_session, artifact_id=artifact.id,
        expected_revision=artifact.current_revision, requester=user, operations=[{
            "operation_type": "delete_node", "target_node_id": nodes["第五次失败锁定"].id}])
    db_session.commit()
    with pytest.raises(InvalidWorkspaceContext):
        _submit(db_session, session.id, "deleted", {
            "selected_module_id": None,
            "selected_case_id": nodes["第五次失败锁定"].id, "current_view": "list"})


def test_same_idempotency_key_with_different_workspace_conflicts(world, db_session):
    _user, _artifact, session, nodes = world
    first = {"selected_module_id": nodes["登录"].id, "selected_case_id": None, "current_view": "list"}
    run = _submit(db_session, session.id, "same-key", first)
    replay = _submit(db_session, session.id, "same-key", dict(first))
    assert replay.id == run.id
    with pytest.raises(ConversationConflict):
        _submit(db_session, session.id, "same-key", {
            "selected_module_id": nodes["支付"].id, "selected_case_id": None,
            "current_view": "list"})


class _Gateway:
    def __init__(self):
        self.requests = []

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        message = AssistantMessage(message_id=context.message_id, timestamp=context.timestamp,
            role="assistant", content=[TextContent(text="ok")], api="chat",
            provider="fake", model="fake", usage=Usage(input=1, output=1,
            cache_read=None, cache_write=None, total_tokens=2, cost=None), stop_reason="stop")
        @asynccontextmanager
        async def managed():
            async def events():
                yield AssistantStartEvent(partial=message.model_copy(update={"content": [], "stop_reason": "pending"}))
                yield AssistantDoneEvent(reason="stop", message=message)
            yield events()
        return managed()


def test_runner_injects_run_workspace_snapshot_as_short_system_hint(world, db_session):
    _user, _artifact, session, nodes = world
    run = _submit(db_session, session.id, "runner", {
        "selected_module_id": nodes["账号锁定"].id,
        "selected_case_id": nodes["第五次失败锁定"].id,
        "current_view": "mindmap"})
    captured = []
    gateway = _Gateway()
    runner = ConversationRunner(gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                  "key", "fake", max_tokens=20),
        tool_registry=build_conversation_tool_registry(),
        provider_attempt_budget=AttemptBudget(limit=5),
        application_context_factory=lambda **values: (
            captured.append(dict(values)) or build_artifact_runtime_context(SessionLocal, **values)))
    outcome = asyncio.run(runner.run(db_session, run.id))
    assert outcome.status == "succeeded"
    assert captured[0]["selected_module_id"] == nodes["账号锁定"].id
    assert captured[0]["selected_case_id"] == nodes["第五次失败锁定"].id
    prompt = gateway.requests[0].system_prompt
    assert f"selected module node id: {nodes['账号锁定'].id}" in prompt
    assert "UI selection hint, not permission" in prompt
    assert "read current Artifact nodes" in prompt
