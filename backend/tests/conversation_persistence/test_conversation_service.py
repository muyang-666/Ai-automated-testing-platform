"""V2-P04 conversation transaction, recovery, isolation and concurrency tests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.agents.conversation.messages import (AssistantMessage, TextContent, ToolCall,
    ToolResultMessage, Usage)
from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.core.database import Base
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.project import Project
from app.models.user import User
from app.services.agent import agent_run_service, agent_session_service, conversation_repository, conversation_service
from app.services.agent.conversation_service import ConversationConflict, ConversationDataError

USER_A = 101
USER_B = 202


def seed_user(db, user_id, name):
    db.add(User(id=user_id, username=name, password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.flush()


def conversation(db, user_id=USER_A, title="聊天"):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=user_id, title=title)
    db.commit()
    return row


def submit(db, session_id, content="hello", key="request-1"):
    return conversation_service.submit_conversation_turn(db, session_id=session_id,
        requester_user_id=USER_A, content=content, client_request_id=key,
        message_id_factory=lambda: f"message-{key}", timestamp_ms_factory=lambda: 10)


def make_usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def test_projectless_conversation_and_legacy_project_session_stay_distinct(db_session):
    seed_user(db_session, USER_A, "user-a")
    chat = conversation(db_session)
    assert chat.mode == "conversation" and chat.project_id is None

    project = Project(id=9, name="legacy-project", status="active", is_deleted=False)
    db_session.add(project); db_session.commit()
    legacy = agent_session_service.create_session(db_session, USER_A, project.id, "旧工作流")
    db_session.commit()
    assert legacy.mode == "legacy_workflow" and legacy.project_id == project.id

    with pytest.raises(AgentError) as exc:
        agent_run_service.create_run(db_session, chat, "case_generation", USER_A, None)
    assert exc.value.error_code == "agent_session_mode_mismatch"


def test_turn_submission_is_atomic_and_idempotent(db_session):
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    first = submit(db_session, session.id)
    second = submit(db_session, session.id)
    assert first.replayed is False and second.replayed is True
    assert first.run.id == second.run.id and first.user_message.id == second.user_message.id
    assert db_session.query(AgentRun).count() == 1
    assert db_session.query(AgentMessage).count() == 1
    assert first.user_message.run_id == first.run.id
    assert first.run.user_message_id == first.user_message.id

    with pytest.raises(ConversationConflict):
        submit(db_session, session.id, content="different", key="request-1")
    with pytest.raises(ConversationConflict):
        submit(db_session, session.id, content="second", key="request-2")


def test_terminal_run_releases_active_slot_for_next_turn(db_session):
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    first = submit(db_session, session.id)
    agent_run_service.transition_status(db_session, first.run, "running")
    agent_run_service.transition_status(db_session, first.run, "succeeded")
    db_session.commit()
    assert first.run.active_slot is None
    second = submit(db_session, session.id, content="next", key="request-2")
    assert second.user_message.sequence_no == 2 and second.run.active_slot == 1


def test_worker_selector_claims_conversation_queued_run_after_p05(db_session):
    """P05-C：claim 不再排除 conversation；分发由 Worker 按 workflow_code 决定。

    旧行为（P05 前：selector/claim 显式跳过 conversation queued 行）已随
    P05-C 移除，历史断言随特性更新。
    """
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    submitted = submit(db_session, session.id)
    assert submitted.run.status == "queued"
    assert agent_run_service.next_queued_run_id(db_session) == submitted.run.id
    assert agent_run_service.claim_queued_run(
        db_session, submitted.run.id, "worker-x", datetime.utcnow()) is True
    db_session.commit()
    assert db_session.get(AgentRun, submitted.run.id).status == "running"


def test_failure_after_message_flush_rolls_back_message_and_run(db_session, monkeypatch):
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(agent_run_service, "create_run", fail)
    with pytest.raises(RuntimeError):
        submit(db_session, session.id)
    assert db_session.query(AgentMessage).count() == 0
    assert db_session.query(AgentRun).count() == 0
    db_session.refresh(session)
    assert session.next_message_sequence == 1


def test_full_tool_history_round_trips_in_order(db_session):
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    submitted = submit(db_session, session.id)
    assistant_call = AssistantMessage(message_id="a1", timestamp=11, role="assistant",
        content=[TextContent(text="calling"), ToolCall(id="c1", name="echo", arguments={"value": "hi"})],
        api="chat", provider="fake", model="m", usage=make_usage(), stop_reason="toolUse")
    tool_result = ToolResultMessage(message_id="t1", timestamp=12, role="toolResult",
        tool_call_id="c1", tool_name="echo", content=[TextContent(text="hi")], is_error=False)
    assistant_final = AssistantMessage(message_id="a2", timestamp=13, role="assistant",
        content=[TextContent(text="result is hi")], api="chat", provider="fake", model="m",
        usage=make_usage(), stop_reason="stop")
    rows = conversation_service.persist_conversation_messages(db_session,
        session_id=session.id, requester_user_id=USER_A, run_id=submitted.run.id,
        messages=[assistant_call, tool_result, assistant_final])
    assert [row.sequence_no for row in rows] == [2, 3, 4]
    restored = conversation_service.restore_conversation_messages(db_session,
        session_id=session.id, requester_user_id=USER_A)
    assert [message.message_id for message in restored] == ["message-request-1", "a1", "t1", "a2"]
    assert restored[1].content[1].id == restored[2].tool_call_id == "c1"
    assert [message.model_dump() for message in restored[1:]] == [
        assistant_call.model_dump(), tool_result.model_dump(), assistant_final.model_dump()]


def test_restore_rejects_corrupt_contract_and_cross_owner(db_session):
    seed_user(db_session, USER_A, "user-a")
    seed_user(db_session, USER_B, "user-b")
    session = conversation(db_session)
    submitted = submit(db_session, session.id)
    with pytest.raises(AgentPermissionError):
        conversation_service.restore_conversation_messages(db_session,
            session_id=session.id, requester_user_id=USER_B)
    submitted.user_message.content_json = {"role": "user", "schema_version": 99}
    db_session.commit()
    with pytest.raises(ConversationDataError):
        conversation_service.restore_conversation_messages(db_session,
            session_id=session.id, requester_user_id=USER_A)


def file_database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}",
                           connect_args={"check_same_thread": False, "timeout": 10})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        cursor = connection.cursor(); cursor.execute("PRAGMA foreign_keys=ON"); cursor.close()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_user(db, USER_A, "user-a")
        session = conversation_service.create_conversation_session(
            db, requester_user_id=USER_A, title="concurrent")
        db.commit()
        session_id = session.id
    return engine, factory, session_id


def test_two_connections_same_idempotency_key_create_one_turn(tmp_path):
    engine, factory, session_id = file_database(tmp_path)
    barrier = Barrier(2)
    def worker(index):
        with factory() as db:
            barrier.wait(timeout=5)
            result = conversation_service.submit_conversation_turn(db,
                session_id=session_id, requester_user_id=USER_A,
                content="same", client_request_id="same-key",
                message_id_factory=lambda: f"m-{index}", timestamp_ms_factory=lambda: index)
            return result.run.id, result.user_message.id, result.replayed
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, (1, 2)))
    with factory() as db:
        assert db.query(AgentRun).count() == 1
        assert db.query(AgentMessage).count() == 1
        assert {item[0] for item in results} == {db.query(AgentRun.id).scalar()}
        assert {item[1] for item in results} == {db.query(AgentMessage.id).scalar()}
        assert sorted(item[2] for item in results) == [False, True]
    engine.dispose()


def test_two_connections_same_key_different_content_conflict(tmp_path):
    engine, factory, session_id = file_database(tmp_path)
    barrier = Barrier(2)
    def worker(item):
        index, content = item
        with factory() as db:
            barrier.wait(timeout=5)
            try:
                result = conversation_service.submit_conversation_turn(db,
                    session_id=session_id, requester_user_id=USER_A,
                    content=content, client_request_id="shared-key",
                    message_id_factory=lambda: f"m-{index}", timestamp_ms_factory=lambda: index)
                return "created", result.run.id
            except ConversationConflict:
                return "conflict", None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ((1, "one"), (2, "two"))))
    assert sorted(item[0] for item in results) == ["conflict", "created"]
    with factory() as db:
        assert db.query(AgentRun).count() == 1 and db.query(AgentMessage).count() == 1
    engine.dispose()


def test_two_connections_allocate_distinct_message_sequences(tmp_path):
    engine, factory, session_id = file_database(tmp_path)
    barrier = Barrier(2)
    def worker(index):
        with factory() as db:
            barrier.wait(timeout=5)
            sequence = conversation_repository.allocate_sequence(
                db, session_id, "next_message_sequence")
            db.add(AgentMessage(session_id=session_id, role="user", message_type="text",
                                content=f"m{index}", sequence_no=sequence))
            db.commit()
            return sequence
    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = sorted(pool.map(worker, (1, 2)))
    with factory() as db:
        assert sequences == [1, 2]
        assert [row.sequence_no for row in db.query(AgentMessage).order_by(AgentMessage.sequence_no)] == [1, 2]
        assert db.get(AgentSession, session_id).next_message_sequence == 3
    engine.dispose()


def test_persist_batch_rolls_back_all_rows_on_duplicate_message_id(db_session):
    seed_user(db_session, USER_A, "user-a")
    session = conversation(db_session)
    submitted = submit(db_session, session.id)
    one = AssistantMessage(message_id="duplicate", timestamp=11, role="assistant",
        content=[TextContent(text="one")], api="chat", provider="fake", model="m",
        usage=make_usage(), stop_reason="stop")
    two = one.model_copy(deep=True, update={"timestamp": 12, "content": [TextContent(text="two")]})
    with pytest.raises(IntegrityError):
        conversation_service.persist_conversation_messages(db_session,
            session_id=session.id, requester_user_id=USER_A, run_id=submitted.run.id,
            messages=[one, two])
    assert db_session.query(AgentMessage).count() == 1
    db_session.refresh(session)
    assert session.next_message_sequence == 2
