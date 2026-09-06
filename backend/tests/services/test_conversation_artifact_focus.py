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
