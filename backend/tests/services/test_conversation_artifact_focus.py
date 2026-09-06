"""P08.1 focus guard：正在运行的 Turn 不允许切换 focused Artifact（Service 层）。

- 已聚焦同一 Artifact → 幂等成功（不打断当前 Turn）；
- 存在 queued/running active run 且切换到不同 Artifact → ConversationConflict(409)；
- active run 终态后切换成功。
"""

import pytest

from app.models.user import User
from app.services.agent import conversation_service
from app.services.agent.conversation_service import ConversationConflict
from app.services.test_artifacts import artifact_service

USER_A = 8201


def _seed(db):
    user = db.query(User).filter(User.id == USER_A).first()
    if user is None:
        user = User(id=USER_A, username="focus-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db.add(user)
        db.commit()
    return user


def _submit_turn(db, session_id, client_request_id):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content="运行中的 Turn",
        client_request_id=client_request_id,
        message_id_factory=lambda: f"msg-{client_request_id}",
        timestamp_ms_factory=lambda: 1,
    ).run


def test_refocus_same_artifact_is_idempotent_even_while_running(db_session):
    user = _seed(db_session)
    artifact = artifact_service.create_artifact(db_session, requester=user, title="A")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user)
    db_session.commit()
    run = _submit_turn(db_session, session.id, "c1")
    assert run.status in ("queued", "running")
    db_session.commit()
    # 同 Artifact 重聚焦 → 幂等成功（不触发 guard、不 409）
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user)
    db_session.commit()
    assert conversation_service.focused_artifact_id(
        db_session.get(type(session), session.id)) == artifact.id


def test_switch_artifact_while_running_conflicts(db_session):
    user = _seed(db_session)
    art_a = artifact_service.create_artifact(db_session, requester=user, title="A")
    art_b = artifact_service.create_artifact(db_session, requester=user, title="B")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_a.id, requester=user)
    db_session.commit()
    run = _submit_turn(db_session, session.id, "c2")
    assert run.status in ("queued", "running")
    db_session.commit()
    with pytest.raises(ConversationConflict):
        conversation_service.focus_conversation_artifact(
            db_session, session_id=session.id, artifact_id=art_b.id, requester=user)
    db_session.rollback()
    assert conversation_service.focused_artifact_id(
        db_session.get(type(session), session.id)) == art_a.id


def test_switch_artifact_after_run_terminal_succeeds(db_session):
    user = _seed(db_session)
    art_a = artifact_service.create_artifact(db_session, requester=user, title="A")
    art_b = artifact_service.create_artifact(db_session, requester=user, title="B")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_a.id, requester=user)
    db_session.commit()
    run = _submit_turn(db_session, session.id, "c3")
    db_session.commit()
    run.status = "succeeded"  # 终态 → 允许切换
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_b.id, requester=user)
    db_session.commit()
    assert conversation_service.focused_artifact_id(
        db_session.get(type(session), session.id)) == art_b.id


# ── P08.2：Run-scope Artifact Context Snapshot ──


def _seed_with_admin(db):
    from app.models.role import Role
    from app.models.user_role import UserRole

    role = Role(code="system_admin", name="system_admin", status="active")
    db.add(role)
    db.flush()
    user = User(id=USER_A, username="focus-a", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def test_run_snapshot_keeps_artifact_after_session_focus_change(db_session):
    from app.models.agent.agent_run import AgentRun

    user = _seed(db_session)
    art_a = artifact_service.create_artifact(db_session, requester=user, title="A")
    art_b = artifact_service.create_artifact(db_session, requester=user, title="B")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_a.id, requester=user)
    db_session.commit()
    run = _submit_turn(db_session, session.id, "snap-1")
    db_session.commit()
    # 快照在 submit 时固化：artifact=A
    assert conversation_service.artifact_context_from_run(run)["artifact_id"] == art_a.id
    # 终态后切换会话 focus 到 B；Run 快照仍为 A（Runner 只读 Run 快照）
    run.status = "succeeded"
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_b.id, requester=user)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(AgentRun, run.id)
    assert conversation_service.artifact_context_from_run(stored)["artifact_id"] == art_a.id


def test_queued_follow_up_snapshot_matches_submit_time_focus(db_session):
    from app.models.agent.agent_run import AgentRun

    user = _seed(db_session)
    art_a = artifact_service.create_artifact(db_session, requester=user, title="A")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话")
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art_a.id, requester=user)
    db_session.commit()
    head = _submit_turn(db_session, session.id, "snap-head")  # running/queued head
    follow = conversation_service.submit_conversation_turn(
        db_session, session_id=session.id, requester_user_id=USER_A, content="排队消息",
        client_request_id="snap-queue", queue_mode="follow_up",
        message_id_factory=lambda: "msg-queue", timestamp_ms_factory=lambda: 2,
    ).run
    db_session.commit()
    assert follow.active_slot is None  # queued follow-up
    db_session.expire_all()
    for run_row in (head, follow):
        ctx = conversation_service.artifact_context_from_run(
            db_session.get(AgentRun, run_row.id))
        assert ctx["artifact_id"] == art_a.id


def test_requirement_binding_snapshotted_into_new_turn(db_session):
    from app.models.agent.agent_run import AgentRun
    from app.models.project import Project
    from app.models.requirement_doc import RequirementDoc

    user = _seed_with_admin(db_session)
    project = Project(id=8701, name="需求项目", status="active", is_deleted=False)
    requirement = RequirementDoc(project_id=8701, title="登录需求", content="需求内容",
                                 requirement_type="功能需求", status="confirmed",
                                 is_deleted=False)
    db_session.add_all([project, requirement])
    db_session.commit()
    art = artifact_service.create_artifact(db_session, requester=user, title="P资产",
                                           project_id=8701)
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A, title="会话", project_id=8701)
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=art.id, requester=user)
    db_session.commit()
    conversation_service.focus_conversation_requirement(
        db_session, session_id=session.id, requirement_id=requirement.id, requester=user)
    db_session.commit()
    run = _submit_turn(db_session, session.id, "snap-req")
    db_session.commit()
    ctx = conversation_service.artifact_context_from_run(
        db_session.get(AgentRun, run.id))
    assert ctx["artifact_id"] == art.id
    assert ctx["requirement_id"] == requirement.id
    assert ctx["project_id"] == 8701
