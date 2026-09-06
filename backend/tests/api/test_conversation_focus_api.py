"""P08.1 focus guard API 测试：409 conversation_conflict / 幂等 / 终态后可切换。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.services.agent import conversation_service
from app.services.test_artifacts import artifact_service

USER_A = 8301


def _seed(db):
    user = db.query(User).filter(User.id == USER_A).first()
    if user is None:
        user = User(id=USER_A, username="focus-api-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db.add(user)
        db.commit()
    return user


@pytest.fixture()
def setup(db_session):
    user = _seed(db_session)
    art_a = artifact_service.create_artifact(db_session, requester=user, title="A")
    art_b = artifact_service.create_artifact(db_session, requester=user, title="B")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_a.id, requester=user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, session.id, art_a.id, art_b.id, db_session, user
    app.dependency_overrides.clear()


def _focus(client, cid, artifact_id):
    return client.post(f"/agent/conversations/{cid}/artifacts/{artifact_id}/focus")


def test_switch_while_active_run_conflicts_409(setup):
    client, cid, art_a, art_b, db_session, user = setup
    run = conversation_service.submit_conversation_turn(
        db_session, session_id=cid, requester_user_id=USER_A, content="运行",
        client_request_id="api-focus-1",
        message_id_factory=lambda: "msg-api-1", timestamp_ms_factory=lambda: 1,
    ).run
    db_session.commit()
    assert run.status in ("queued", "running")
    conflict = _focus(client, cid, art_b)
    assert conflict.status_code == 409
    assert "切换" in conflict.json()["detail"]
    # 同 Artifact 幂等 200
    assert _focus(client, cid, art_a).status_code == 200
    # 终态后可切换
    run.status = "cancelled"
    db_session.commit()
    assert _focus(client, cid, art_b).status_code == 200


def test_focus_owner_isolation_404(setup):
    client, cid, art_a, art_b, db_session, user = setup
    other = User(id=USER_A + 1, username="focus-api-b", password_hash="x", salt="y",
                 status="active", is_deleted=False)
    db_session.add(other)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: other
    assert _focus(client, cid, art_b).status_code == 404
