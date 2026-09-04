"""V2-P05-E Conversation Follow-up Queue 测试（服务层 + Worker E2E）。

覆盖提示词 §15 场景 1-14 与 §16 E2E：排队持久化、不可提前 claim、顺序提升、
run-bounded restore（A 不见 B / B 见 A 完整结果）、失败/中断 pause、取消提升、
queued follow-up cancel 跳过、幂等、双连接 promotion 唯一性、P05-D 回归。
"""
import asyncio
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy import text as sql_text

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.events import AssistantErrorEvent, AssistantDoneEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolRegistry
from app.core.database import SessionLocal
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.project import Project
from app.models.user import User
from app.services.agent import agent_run_service, agent_session_service, conversation_service
from app.services.agent.conversation_service import (
    ConversationConflict, ConversationTurnSubmission, conversation_queue_state,
    promote_next_conversation_run, submit_conversation_turn)
from app.workers.agent_worker import AgentWorker

USER_A = 101
USER_B = 202
WORKER = "followup-worker"


def usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def chat_reply(text):
    return AssistantMessage(message_id="template", timestamp=1, role="assistant",
        content=[TextContent(text=text)], api="chat", provider="fake", model="fake-model",
        usage=usage(), stop_reason="stop")


class ScriptedGateway:
    """每 run 一个 gateway；可慢速首轮；记录发给模型的历史（供上下文断言）。"""

    def __init__(self, reply_text, slow_seconds=0.0):
        self.reply_text = reply_text
        self.slow_seconds = slow_seconds
        self.requests = []
        self.aborted = False

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        reply = chat_reply(self.reply_text).model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                partial = reply.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                deadline = time.monotonic() + self.slow_seconds
                while time.monotonic() < deadline:
                    if control.cancel_event.is_set():
                        self.aborted = True
                        control.error_code = "canceled"
                        error = chat_reply("").model_copy(deep=True, update={
                            "message_id": context.message_id, "timestamp": context.timestamp,
                            "content": [], "stop_reason": "aborted"})
                        yield AssistantErrorEvent(reason="aborted", error=error)
                        return
                    await asyncio.sleep(0.005)
                yield AssistantDoneEvent(reason="stop", message=reply)
            yield events()
        return managed()


class FactoryRunner:
    def __init__(self, gateways):
        self._gateways = iter(gateways)
        self.created = []

    def __call__(self):
        gateway = next(self._gateways)
        self.created.append(gateway)
        return _build_runner(gateway)


_ID_COUNTER = iter(f"f{i}" for i in range(1, 500000))


def _build_runner(gateway):
    return RunnerAdapter(gateway)


class RunnerAdapter:
    def __init__(self, gateway):
        self.gateway = gateway
        self._runner = ConversationRunner(
            gateway=gateway,
            snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                      "key", "fake-model", max_tokens=20),
            tool_registry=ToolRegistry(),
            system_prompt="be helpful",
            limits=AgentLoopLimits(),
            provider_attempt_budget=AttemptBudget(limit=20),
            id_factory=lambda: next(_ID_COUNTER),  # 跨 Run 唯一，避免 message_id 碰撞
            timestamp_factory=lambda: 10,
        )

    async def run(self, db, run_id, cancel_event=None, **kwargs):
        return await self._runner.run(db, run_id, cancel_event=cancel_event, **kwargs)


def make_worker(factory, worker_id=WORKER, heartbeat_interval=0.02):
    return AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: None,
        worker_id=worker_id,
        poll_interval_seconds=0.1,
        stale_after_seconds=0.5,
        conversation_runner_factory=factory,
        heartbeat_interval_seconds=heartbeat_interval,
        heartbeat_failure_limit=1,
    )


# ---------------------------------------------------------------- 夹具

def seed_user(db, user_id=USER_A):
    db.add(User(id=user_id, username=f"user-{user_id}", password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.flush()


def conversation(db, user_id=USER_A, title="聊天"):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=user_id, title=title)
    db.commit()
    return row


def submit(db, session_id, content="hello", key="req", queue_mode="reject",
            user_id=USER_A):
    return submit_conversation_turn(
        db, session_id=session_id, requester_user_id=user_id, content=content,
        client_request_id=key, queue_mode=queue_mode,
        message_id_factory=lambda: f"user-{key}", timestamp_ms_factory=lambda: 10)


def rows(db, session_id):
    return db.query(AgentMessage).filter(AgentMessage.session_id == session_id).order_by(
        AgentMessage.sequence_no.asc()).all()


def run_status(db, run_id):
    return db.get(AgentRun, run_id)


def message_text(message):
    if isinstance(message, str):
        return message
    blocks = getattr(message, "content", []) or []
    return "".join(getattr(block, "text", "") for block in blocks)


# ---------------------------------------------------------------- 1/2/9/10：排队持久化与幂等

def test_follow_up_persisted_not_claimable_when_head_running(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="A")
    assert head.run.active_slot == 1
    # head 置 running（模拟 Worker 已 claim）
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()

    b = submit(db_session, chat.id, content="B", key="B", queue_mode="follow_up")
    c = submit(db_session, chat.id, content="C", key="C", queue_mode="follow_up")
    assert b.run.active_slot is None and c.run.active_slot is None
    assert b.run.status == "queued" and c.run.status == "queued"
    # follow-up 不可被 claim / 不出现在全局候选
    assert agent_run_service.next_queued_run_id(db_session) is None
    assert agent_run_service.claim_queued_run(db_session, b.run.id, WORKER,
                                              datetime.utcnow()) is None
    # 顺序稳定：按 id 升序
    queued = [run.id for run in db_session.query(AgentRun).filter(
        AgentRun.session_id == chat.id, AgentRun.active_slot.is_(None),
        AgentRun.status == "queued").order_by(AgentRun.id.asc()).all()]
    assert queued == [b.run.id, c.run.id]
    # 幂等：同 key 同内容 replay；同 key 不同内容 conflict
    replay = submit(db_session, chat.id, content="B", key="B", queue_mode="follow_up")
    assert replay.replayed is True and replay.run.id == b.run.id
    with pytest.raises(ConversationConflict):
        submit(db_session, chat.id, content="B-different", key="B", queue_mode="follow_up")
    # reject 默认仍 409
    with pytest.raises(ConversationConflict):
        submit(db_session, chat.id, content="X", key="X", queue_mode="reject")


# ---------------------------------------------------------------- 3/4：顺序提升

def test_promotion_only_promotes_oldest_queued_follow_up(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="A")
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    b = submit(db_session, chat.id, content="B", key="B", queue_mode="follow_up")
    c = submit(db_session, chat.id, content="C", key="C", queue_mode="follow_up")

    # A success（模拟 runner 终态）
    agent_run_service.transition_status(db_session, head.run, "succeeded")
    db_session.commit()
    assert promote_next_conversation_run(db_session, chat.id) == b.run.id
    db_session.commit()
    assert run_status(db_session, b.run.id).active_slot == 1
    assert run_status(db_session, c.run.id).active_slot is None  # 只提升一个
    # B 被 claim 后 success → 提升 C
    run_b = db_session.get(AgentRun, b.run.id)
    agent_run_service.transition_status(db_session, run_b, "running")
    agent_run_service.transition_status(db_session, run_b, "succeeded")
    db_session.commit()
    assert promote_next_conversation_run(db_session, chat.id) == c.run.id
    db_session.commit()
    assert run_status(db_session, c.run.id).active_slot == 1
    assert promote_next_conversation_run(db_session, chat.id) is None  # 队列空


# ---------------------------------------------------------------- 5：不同 Conversation 不互阻

def test_other_conversation_head_not_blocked_by_follow_up(db_session):
    seed_user(db_session, USER_A)
    seed_user(db_session, USER_B)
    chat1 = conversation(db_session, USER_A, "chat1")
    chat2 = conversation(db_session, USER_B, "chat2")

    head1 = submit(db_session, chat1.id, content="A", key="A1")
    agent_run_service.claim_queued_run(db_session, head1.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    submit(db_session, chat1.id, content="B", key="B1", queue_mode="follow_up")

    head2 = submit(db_session, chat2.id, content="X", key="X2", user_id=USER_B)
    assert head2.run.active_slot == 1
    # 全局候选跳过 chat1 的 queued follow-up，直接看到 chat2 head
    assert agent_run_service.next_queued_run_id(db_session) == head2.run.id


# ---------------------------------------------------------------- 6/7/8：终态队列语义

def _paused_head(db_session, terminal, key):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key=key)
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    # B 在 head running 时入队；随后 head 失败/中断 → 队列 pause
    submit(db_session, chat.id, content="B", key=f"B-{key}", queue_mode="follow_up")
    if terminal == "failed":
        agent_run_service.transition_status(db_session, head.run, "failed")
    else:
        agent_run_service.mark_interrupted(db_session, head.run.id, "stale", "x",
                                           datetime.utcnow())
    db_session.commit()
    assert promote_next_conversation_run(db_session, chat.id) is None
    state = conversation_queue_state(db_session, chat.id)
    assert state["state"] == "paused" and state["queued_follow_ups"] == 1


def test_failed_head_pauses_queue(db_session):
    _paused_head(db_session, "failed", "pf")


def test_interrupted_head_pauses_queue(db_session):
    _paused_head(db_session, "interrupted", "pi")


def test_cancelled_head_promotes_next(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="A-c")
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    b = submit(db_session, chat.id, content="B", key="B-c", queue_mode="follow_up")
    agent_run_service.transition_status(db_session, head.run, "cancelled")
    db_session.commit()
    assert promote_next_conversation_run(db_session, chat.id) == b.run.id
    assert conversation_queue_state(db_session, chat.id)["state"] == "executable"


def test_cancelled_queued_follow_up_is_skipped_by_promotion(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="A-s")
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    b = submit(db_session, chat.id, content="B", key="B-s", queue_mode="follow_up")
    c = submit(db_session, chat.id, content="C", key="C-s", queue_mode="follow_up")
    # 用户取消 queued follow-up B（queued → cancelled 合法）
    agent_run_service.transition_status(db_session, b.run, "cancelled")
    db_session.commit()
    agent_run_service.transition_status(db_session, head.run, "succeeded")
    db_session.commit()
    assert promote_next_conversation_run(db_session, chat.id) == c.run.id  # 跳过 B
    db_session.commit()
    assert run_status(db_session, c.run.id).active_slot == 1


# ---------------------------------------------------------------- 11/12：run-bounded restore

def test_run_bounded_restore_a_never_sees_b(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    a = submit(db_session, chat.id, content="A", key="bA")
    agent_run_service.claim_queued_run(db_session, a.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    b = submit(db_session, chat.id, content="B", key="bB", queue_mode="follow_up")
    b_seq = b.user_message.sequence_no
    # A 只看到 <= A user seq 的历史
    history_a = conversation_service.restore_conversation_messages(
        db_session, session_id=chat.id, requester_user_id=USER_A,
        until_sequence_no=a.user_message.sequence_no)
    assert [message.content for message in history_a] == ["A"]
    # 全量 restore 能看到 B（供提升后 B 使用）
    history_all = conversation_service.restore_conversation_messages(
        db_session, session_id=chat.id, requester_user_id=USER_A)
    assert [message.content for message in history_all] == ["A", "B"]
    assert b_seq > a.user_message.sequence_no


# ---------------------------------------------------------------- 13：promotion race

def test_concurrent_promotion_yields_single_active_slot(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="A-r")
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    b = submit(db_session, chat.id, content="B", key="B-r", queue_mode="follow_up")
    c = submit(db_session, chat.id, content="C", key="C-r", queue_mode="follow_up")
    agent_run_service.transition_status(db_session, head.run, "succeeded")
    db_session.commit()

    # SQLite 共享单连接无法真正并行事务；用两线程 + 失败重试模拟并发语义，
    # 等价断言：最终只有一个 active_slot、且恰有一次提升成功（赢家是 B）。
    results = []

    def promote_with_retry():
        from sqlalchemy.exc import OperationalError
        for _ in range(300):
            session = SessionLocal()
            try:
                promoted = promote_next_conversation_run(session, chat.id)
                session.commit()
                if promoted is not None:
                    results.append(promoted)
                break
            except OperationalError:
                session.rollback()
            finally:
                session.close()
            time.sleep(0.005)

    threads = [threading.Thread(target=promote_with_retry) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    active = [run.id for run in db_session.query(AgentRun).filter(
        AgentRun.session_id == chat.id, AgentRun.active_slot == 1).all()]
    assert len(active) == 1  # 双连接 promotion 最终只有一个 active_slot
    assert results.count(b.run.id) == 1


# ---------------------------------------------------------------- 14 + §16 E2E：A→B→C

def test_worker_follow_up_e2e_a_success_then_b_then_c(db_session):
    """§16 E2E：A 慢执行期间提交 B/C → A 成功后 B、C 顺序执行、不并行。"""
    seed_user(db_session)
    chat = conversation(db_session)
    a_sub = submit(db_session, chat.id, content="A", key="eA", queue_mode="reject")
    run_a_id = a_sub.run.id

    gateway_a = ScriptedGateway("reply-A", slow_seconds=0.5)
    gateways = [gateway_a, ScriptedGateway("reply-B"), ScriptedGateway("reply-C")]
    factory = FactoryRunner(gateways)
    worker = make_worker(factory)
    result_holder = {}

    def execute():
        result_holder["result"] = worker.run_once()  # 执行慢 A（含 promote）

    thread = threading.Thread(target=execute)
    thread.start()
    time.sleep(0.1)  # A 已 running
    with SessionLocal() as mid_session:
        assert mid_session.get(AgentRun, run_a_id).status == "running"
        b = submit(mid_session, chat.id, content="B", key="eB", queue_mode="follow_up")
        c = submit(mid_session, chat.id, content="C", key="eC", queue_mode="follow_up")
        assert b.run.active_slot is None and c.run.active_slot is None
        # A 执行期间 follow-up 不可被 claim
        assert agent_run_service.claim_queued_run(mid_session, b.run.id, WORKER,
                                                  datetime.utcnow()) is None
    thread.join(timeout=15)

    assert result_holder["result"].action == "completed"
    db_session.expire_all()
    assert db_session.get(AgentRun, run_a_id).status == "succeeded"
    # A 成功后 worker 已 promote B（B 为 queued head）
    promoted = db_session.query(AgentRun).filter(
        AgentRun.session_id == chat.id, AgentRun.active_slot == 1).one()
    assert promoted.status == "queued"

    assert worker.run_once().action == "completed"  # B
    assert worker.run_once().action == "completed"  # C
    db_session.expire_all()
    runs = db_session.query(AgentRun).filter(
        AgentRun.session_id == chat.id).order_by(AgentRun.id.asc()).all()
    assert [run.status for run in runs] == ["succeeded", "succeeded", "succeeded"]
    assert all(run.active_slot is None for run in runs)
    stored = rows(db_session, chat.id)
    # B/C 在 A 执行期间已入库（user,user,user 在前），随后各 assistant 依次落库
    assert [row.role for row in stored] == ["user", "user", "user",
                                            "assistant", "assistant", "assistant"]
    assert [row.content for row in stored if row.role == "assistant"] == [
        "reply-A", "reply-B", "reply-C"]
    # run-bounded context：B 看不到 C；C 看到 A+B+C 全部
    b_history = factory.created[1].requests[0].messages
    assert [m.content for m in b_history if m.role == "user"] == ["A", "B"]
    assert [message_text(m) for m in b_history if m.role == "assistant"] == ["reply-A"]
    c_history = factory.created[2].requests[0].messages
    assert [m.content for m in c_history if m.role == "user"] == ["A", "B", "C"]
    assert [message_text(m) for m in c_history if m.role == "assistant"] == ["reply-A", "reply-B"]


def test_worker_pauses_queue_when_head_failed(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    head = submit(db_session, chat.id, content="A", key="fA")
    agent_run_service.claim_queued_run(db_session, head.run.id, WORKER, datetime.utcnow())
    db_session.commit()
    submit(db_session, chat.id, content="B", key="fB", queue_mode="follow_up")
    # head 执行失败（不经 worker，模拟 runner 已落 failed）
    agent_run_service.transition_status(db_session, head.run, "failed")
    db_session.commit()

    worker = make_worker(FactoryRunner([ScriptedGateway("x")]))
    assert worker.run_once().action == "idle"  # 无可执行 head（pause，不 promote）
    state = conversation_queue_state(db_session, chat.id)
    assert state["state"] == "paused" and state["queued_follow_ups"] == 1
