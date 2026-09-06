"""P09.3A submit-turn Workspace Context HTTP contract."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.services.agent import conversation_service
from app.services.test_artifacts import artifact_service

USER_ID = 9401


@pytest.fixture()
def setup(db_session):
    user = User(id=USER_ID, username="workspace-api", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db_session.add(user)
    db_session.commit()
    artifact = artifact_service.create_artifact(db_session, requester=user, title="功能用例")
    artifact_service.apply_operations(db_session, artifact_id=artifact.id, expected_revision=1,
        requester=user, operations=[
            {"operation_type": "add_node", "parent_id": artifact.root_node_id,
             "node_type": "module", "title": "登录", "ref": "login"},
            {"operation_type": "add_node", "parent_id": "@login",
             "node_type": "test_case", "title": "登录成功"},
        ])
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=user.id, title="API")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user)
    db_session.commit()
    nodes = {node.node_type: node for node in db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id, ArtifactNode.node_type != "root").all()}
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, db_session, session, artifact, nodes
    app.dependency_overrides.clear()


def _submit(client, session_id, key, workspace):
    return client.post(f"/agent/conversations/{session_id}/turns", json={
        "content": "这里有哪些用例？", "client_request_id": key,
        "queue_mode": "follow_up", "workspace_context": workspace,
    })


def test_submit_workspace_context_persists_formal_snapshot(setup):
    client, db, session, _artifact, nodes = setup
    response = _submit(client, session.id, "api-workspace", {
        "selected_module_id": nodes["module"].id,
        "selected_case_id": nodes["test_case"].id, "current_view": "list"})
    assert response.status_code == 202
    from app.models.agent.agent_run import AgentRun
    db.expire_all()
    run = db.get(AgentRun, response.json()["run_id"])
    assert run.workspace_context_json == {
        "selected_module_id": nodes["module"].id,
        "selected_case_id": nodes["test_case"].id, "current_view": "list"}


def test_wrong_type_cross_artifact_and_deleted_selection_return_400(setup):
    client, db, session, artifact, nodes = setup
    wrong_type = _submit(client, session.id, "wrong-type", {
        "selected_module_id": nodes["test_case"].id,
        "selected_case_id": None, "current_view": "list"})
    assert wrong_type.status_code == 400
    assert wrong_type.json()["detail"]["error_code"] == "invalid_workspace_context"
    other = artifact_service.create_artifact(db, requester=db.get(User, USER_ID), title="其他")
    artifact_service.apply_operations(db, artifact_id=other.id, expected_revision=1,
        requester=db.get(User, USER_ID), operations=[{"operation_type": "add_node",
        "parent_id": other.root_node_id, "node_type": "module", "title": "外部"}])
    db.commit()
    foreign = db.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == other.id, ArtifactNode.node_type == "module").one()
    assert _submit(client, session.id, "foreign", {
        "selected_module_id": foreign.id, "selected_case_id": None,
        "current_view": "list"}).status_code == 400
    artifact_service.apply_operations(db, artifact_id=artifact.id, expected_revision=2,
        requester=db.get(User, USER_ID), operations=[{
            "operation_type": "delete_node", "target_node_id": nodes["test_case"].id}])
    db.commit()
    assert _submit(client, session.id, "deleted", {
        "selected_module_id": None, "selected_case_id": nodes["test_case"].id,
        "current_view": "mindmap"}).status_code == 400


def test_workspace_schema_rejects_arbitrary_dict_and_view(setup):
    client, _db, session, _artifact, _nodes = setup
    assert _submit(client, session.id, "extra", {
        "selected_module_id": None, "selected_case_id": None,
        "current_view": "list", "node_title": "untrusted"}).status_code == 422
    assert _submit(client, session.id, "view", {
        "selected_module_id": None, "selected_case_id": None,
        "current_view": "kanban"}).status_code == 422
