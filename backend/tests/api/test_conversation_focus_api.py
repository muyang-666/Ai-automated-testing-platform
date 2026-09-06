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


# ── P08.2：可信 Requirement binding 入口（API） ──


def _seed_requirement_scene(db_session):
    from app.models.project import Project
    from app.models.requirement_doc import RequirementDoc
    from app.models.role import Role
    from app.models.user_role import UserRole

    for code in ("system_admin",):
        if not db_session.query(Role).filter(Role.code == code).first():
            db_session.add(Role(code=code, name=code, status="active"))
    db_session.flush()
    role = db_session.query(Role).filter(Role.code == "system_admin").one()
    user = db_session.query(User).filter(User.id == USER_A).first()
    if user is None:
        user = User(id=USER_A, username="focus-req-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db_session.add(user)
        db_session.flush()
    if not db_session.query(UserRole).filter(UserRole.user_id == USER_A).first():
        db_session.add(UserRole(user_id=USER_A, role_id=role.id))
    req_project = Project(id=8702, name="需求项目", status="active", is_deleted=False)
    requirement = RequirementDoc(project_id=8702, title="登录需求", content="需求",
                                 requirement_type="功能需求", status="confirmed",
                                 is_deleted=False)
    db_session.add_all([req_project, requirement])
    db_session.commit()
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="绑定会话", project_id=8702)
    db_session.commit()
    return user, session.id, requirement.id


def test_requirement_bind_endpoint_success_and_project_mismatch(db_session):
    from app.main import app

    user, cid, req_id = _seed_requirement_scene(db_session)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        ok = client.post(f"/agent/conversations/{cid}/requirements/{req_id}/focus")
        assert ok.status_code == 200
        body = ok.json()
        assert body["requirement_id"] == req_id and body["project_id"] == 8702
        # 幂等（同 requirement 重复绑定）仍 200
        assert client.post(
            f"/agent/conversations/{cid}/requirements/{req_id}/focus").status_code == 200
        # 项目不一致 → 409
        from app.models.project import Project
        if not db_session.query(Project).filter(Project.id == 8703).first():
            db_session.add(Project(id=8703, name="另一项目", status="active", is_deleted=False))
            db_session.commit()
        other_session = conversation_service.create_conversation_session(
            db_session, requester_user_id=USER_A, title="其他项目会话", project_id=8703)
        db_session.commit()
        mismatch = client.post(
            f"/agent/conversations/{other_session.id}/requirements/{req_id}/focus")
        assert mismatch.status_code == 409
    app.dependency_overrides.clear()
