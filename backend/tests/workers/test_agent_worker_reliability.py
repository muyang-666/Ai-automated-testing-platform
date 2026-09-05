"""V2-P05-D Worker Execution Ownership Reliability 测试。

覆盖域（提示词 §26）：
A. claim token 单调递增；B. fenced heartbeat（正确/旧 token）；C. 长 LLM 期间 heartbeat
持续刷新且另一 Session 不被阻塞；D. stale recovery → interrupted 且旧 token 失效；
E. ownership lost（执行中被替换）→ 旧 Worker 不 finalize、不写消息；
F. cancel propagation（DB cancel → cancel_event → AgentLoop abort → Run cancelled）；
G/H. legacy 与 conversation 回归由既有套件覆盖（本文件只做服务级断言 + 两个 E2E）。
"""
import asyncio
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from sqlalchemy import text as sql_text

from app.agents.conversation.events import (
    AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent, ToolExecutionStartEvent,
)
from app.agents.conversation.messages import AssistantMessage, TextContent, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.conversation.budget import AgentLoopLimits
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolRegistry
from app.core.database import SessionLocal
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.user import User
from app.services.agent import agent_run_service, conversation_service
from app.workers.agent_worker import AgentWorker
from app.workers.conversation_event_persister import ConversationEventPersister

WORKER_A = "reliability-a"
WORKER_B = "reliability-b"
USER_A = 101

HEARTBEAT_INTERVAL = 0.02
STALE_AFTER = 0.2


def usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def chat_reply(text="hi"):
    return AssistantMessage(message_id="reply-template", timestamp=1, role="assistant",
        content=[TextContent(text=text)], api="chat", provider="fake", model="fake-model",
        usage=usage(), stop_reason="stop")


class SlowGateway:
    """长等待 Fake：持续小睡并观察 control.cancel_event；取消时以 aborted 终止。

    协作式取消：一旦 cancel_event 置位，尽快 yield AssistantErrorEvent(aborted)，
    不假装"即时杀死"Provider。
    """

    def __init__(self, wait_seconds=0.3, on_start=None):
        self.wait_seconds = wait_seconds
        self.requests = []
        self.on_start = on_start
        self.aborted = False

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        reply = chat_reply().model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                if self.on_start is not None:
                    self.on_start()
                partial = reply.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                deadline = time.monotonic() + self.wait_seconds
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


class FencedConversationRunner:
    """真实 ConversationRunner + SlowGateway；透传 worker_id/execution_token。"""

    def __init__(self, gateway, heartbeat_counter=None):
        self.gateway = gateway
        self._runner = ConversationRunner(
            gateway=gateway,
            snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                      "key", "fake-model", max_tokens=20),
            tool_registry=ToolRegistry(),
            system_prompt="be helpful",
            limits=AgentLoopLimits(),
            provider_attempt_budget=AttemptBudget(limit=20),
            id_factory=iter(f"r{i}" for i in range(1, 1000)).__next__,
            timestamp_factory=lambda: int(time.time() * 1000),
        )

    async def run(self, db, run_id, cancel_event=None, **kwargs):
        return await self._runner.run(db, run_id, cancel_event=cancel_event, **kwargs)


# ---------------------------------------------------------------- 夹具

def seed_user(db):
    db.add(User(id=USER_A, username="user-a", password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.flush()


def conversation(db):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=USER_A, title="聊天")
    db.commit()
    return row


def submit(db, session_id, content="hello", key="req"):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, message_id_factory=lambda: f"user-{key}",
        timestamp_ms_factory=lambda: 10)


def make_worker(conversation_runner, worker_id=WORKER_A, heartbeat_interval=None):
    return AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: None,  # 本文件只测 conversation 路径
        worker_id=worker_id,
        poll_interval_seconds=0.1,
        stale_after_seconds=STALE_AFTER,
        conversation_runner_factory=lambda: conversation_runner,
        heartbeat_interval_seconds=heartbeat_interval or HEARTBEAT_INTERVAL,
        heartbeat_failure_limit=1,
    )


def events_for(db, run_id):
    return [e.event_type for e in db.query(AgentEvent).filter(
        AgentEvent.run_id == run_id).order_by(AgentEvent.sequence_no.asc()).all()]


def test_mark_interrupted_toctou_respects_fresh_heartbeat(db_session):
    """P05-E preflight A：find stale 之后若 heartbeat 已刷新，mark 不得误中断。"""
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="toctou")
    run_id = sub.run.id
    token = agent_run_service.claim_queued_run(db_session, run_id, WORKER_A,
                                               datetime.utcnow() - timedelta(seconds=100))
    db_session.commit()
    # 执行中 heartbeat 已刷新（stale_before 之前）
    agent_run_service.heartbeat(db_session, run_id, WORKER_A, datetime.utcnow(),
                                execution_token=token)
    db_session.commit()
    stale_before = datetime.utcnow() - timedelta(seconds=STALE_AFTER)
    assert agent_run_service.mark_interrupted(
        db_session, run_id, "agent_worker_heartbeat_timeout", "stale",
        datetime.utcnow(), stale_before=stale_before) is False
    db_session.rollback()
    assert db_session.get(AgentRun, run_id).status == "running"


# ---------------------------------------------------------------- A. Claim token

def test_claim_token_starts_at_one_and_increments_after_reacquisition(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="token-a")
    run_id = sub.run.id

    token1 = agent_run_service.claim_queued_run(db_session, run_id, WORKER_A,
                                                datetime.utcnow())
    db_session.commit()
    assert token1 == 1

    # 模拟 stale recovery 后重新排队并再次 claim：token 必须递增且不同
    agent_run_service.mark_interrupted(db_session, run_id, "agent_worker_heartbeat_timeout",
                                       "stale", datetime.utcnow())
    db_session.commit()
    agent_run_service.transition_status(db_session, db_session.get(AgentRun, run_id), "queued")
    db_session.commit()
    token2 = agent_run_service.claim_queued_run(db_session, run_id, WORKER_B,
                                                datetime.utcnow())
    db_session.commit()
    assert token2 == token1 + 1
    run = db_session.get(AgentRun, run_id)
    assert run.execution_token == 2 and run.worker_id == WORKER_B


# ---------------------------------------------------------------- B. Fenced heartbeat

def test_fenced_heartbeat_accepts_current_token_and_rejects_stale(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="hb")
    run_id = sub.run.id
    token = agent_run_service.claim_queued_run(db_session, run_id, WORKER_A,
                                               datetime.utcnow())
    db_session.commit()

    now = datetime.utcnow()
    assert agent_run_service.heartbeat(db_session, run_id, WORKER_A, now,
                                       execution_token=token) == 1
    assert agent_run_service.heartbeat(db_session, run_id, WORKER_A, now,
                                       execution_token=token + 1) == 0  # 旧 token 被拒
    assert agent_run_service.heartbeat(db_session, run_id, WORKER_B, now,
                                       execution_token=token) == 0  # 非 owner 被拒


# ---------------------------------------------------------------- C. 长 LLM 期间 heartbeat 持续

def test_heartbeat_refreshes_during_long_model_wait_and_db_not_blocked(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="long")
    run_id = sub.run.id
    probe = {"ok": None, "error": None}

    def on_start():
        try:
            with SessionLocal() as probe_session:
                probe_session.execute(sql_text("SELECT 1")).scalar()
            probe["ok"] = True
        except Exception as exc:  # pragma: no cover
            probe["ok"] = False
            probe["error"] = type(exc).__name__

    gateway = SlowGateway(wait_seconds=0.18, on_start=on_start)
    worker = make_worker(FencedConversationRunner(gateway))
    started = datetime.utcnow()
    result = worker.run_once()
    finished = datetime.utcnow()

    assert result.action == "completed" and result.final_status == "succeeded"
    assert probe["ok"] is True, f"长等待期间 DB 被阻塞: {probe['error']}"
    db_session.expire_all()
    run = db_session.get(AgentRun, run_id)
    assert run.heartbeat_at is not None
    # 等待约 0.18s、heartbeat interval 0.02s → heartbeat_at 应明显晚于 started_at
    assert run.heartbeat_at >= started + timedelta(seconds=0.05)
    assert run.finished_at is not None and run.finished_at >= started
    assert run.status == "succeeded"


# ---------------------------------------------------------------- D. Stale recovery

def test_stale_recovery_interrupts_and_old_token_cannot_heartbeat(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="stale")
    run_id = sub.run.id
    token = agent_run_service.claim_queued_run(
        db_session, run_id, WORKER_A, datetime.utcnow() - timedelta(seconds=STALE_AFTER + 1))
    db_session.commit()

    worker = make_worker(FencedConversationRunner(SlowGateway(wait_seconds=0.01)))
    # 不用 worker.recover（其 now 取自真实时间），直接调用 service：heartbeat 已超时
    assert agent_run_service.mark_interrupted(
        db_session, run_id, "agent_worker_heartbeat_timeout", "stale", datetime.utcnow()) is True
    db_session.commit()

    run = db_session.get(AgentRun, run_id)
    assert run.status == "interrupted"
    # 旧 token 心跳必须失败
    assert agent_run_service.heartbeat(db_session, run_id, WORKER_A, datetime.utcnow(),
                                       execution_token=token) == 0
    assert worker.run_once().action == "idle"  # 不自动 requeue


# ---------------------------------------------------------------- E. Ownership lost

def test_ownership_replaced_mid_execution_old_worker_does_not_finalize(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="lost")
    run_id = sub.run.id

    gateway = SlowGateway(wait_seconds=5.0)  # 足够长，等待测试线程接管
    worker = make_worker(FencedConversationRunner(gateway))
    result_holder = {}

    def execute():
        result_holder["result"] = worker.run_once()

    thread = threading.Thread(target=execute)
    thread.start()
    time.sleep(0.15)  # 等待 claim + 首次 heartbeat 之后
    with SessionLocal() as takeover:
        run = takeover.get(AgentRun, run_id)
        assert run.status == "running" and run.execution_token == 1
        run.worker_id = WORKER_B
        run.execution_token = 2  # 模拟 stale recovery + 重新分配（保持 running）
        takeover.commit()
    thread.join(timeout=10)

    result = result_holder["result"]
    assert gateway.aborted is True  # cancel_event 已传给 AgentLoop
    db_session.expire_all()
    run = db_session.get(AgentRun, run_id)
    assert run.status == "running"  # 旧 Worker 未改任何终态
    assert run.worker_id == WORKER_B and run.execution_token == 2  # 新 ownership 未被覆盖
    # 旧 Worker 未写成功/失败、未产生 assistant 消息
    assert result.action == "completed"
    assert db_session.query(AgentMessage).filter(
        AgentMessage.session_id == chat.id, AgentMessage.role != "user").count() == 0


def test_stale_worker_cannot_persist_conversation_events(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="stale-event")
    token = agent_run_service.claim_queued_run(
        db_session, sub.run.id, WORKER_A, datetime.utcnow(),
    )
    db_session.commit()

    persister = ConversationEventPersister(
        SessionLocal, session_id=chat.id, run_id=sub.run.id,
        worker_id=WORKER_A, execution_token=token,
    )
    with SessionLocal() as takeover:
        run = takeover.get(AgentRun, sub.run.id)
        run.worker_id = WORKER_B
        run.execution_token = token + 1
        takeover.commit()

    persister(ToolExecutionStartEvent(
        tool_call_id="stale-call", tool_name="calculator", args={},
    ))
    db_session.expire_all()
    assert "conversation_tool_started" not in events_for(db_session, sub.run.id)


# ---------------------------------------------------------------- F. Cancel propagation

def test_db_cancel_propagates_to_agent_loop_and_run_stays_cancelled(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="cancel")
    run_id = sub.run.id

    gateway = SlowGateway(wait_seconds=5.0)
    worker = make_worker(FencedConversationRunner(gateway))
    result_holder = {}

    def execute():
        result_holder["result"] = worker.run_once()

    thread = threading.Thread(target=execute)
    thread.start()
    time.sleep(0.15)
    with SessionLocal() as cancel_session:
        run = cancel_session.get(AgentRun, run_id)
        assert run.status == "running"
        agent_run_service.transition_status(cancel_session, run, "cancelled")
        agent_run_service.append_event(cancel_session, run.session_id, run.id, "run_cancelled", {})
        cancel_session.commit()
    thread.join(timeout=10)

    db_session.expire_all()
    run = db_session.get(AgentRun, run_id)
    assert run.status == "cancelled"
    assert gateway.aborted is True
    # 生命周期事件：run_started（Runner 启动时）+ run_cancelled（取消方）恰好各一次；
    # 压力负载下 cancel 可能落在 Runner 写 run_started 前后，事件顺序不参与断言。
    events = events_for(db_session, run_id)
    assert events.count("run_started") == 1 and events.count("run_cancelled") == 1
    assert "run_succeeded" not in events and "run_failed" not in events
    assert db_session.query(AgentMessage).filter(
        AgentMessage.session_id == chat.id, AgentMessage.role != "user").count() == 0


# ---------------------------------------------------------------- G/H. 服务级回归（代表断言）

def test_run_level_ownership_lost_outcome_does_not_persist(db_session):
    """Runner 直调 + 显式 fencing：ownership 已被替换时 outcome.run_finalized=False。"""
    seed_user(db_session)
    chat = conversation(db_session)
    sub = submit(db_session, chat.id, key="rlost")
    run_id = sub.run.id
    token = agent_run_service.claim_queued_run(db_session, run_id, WORKER_A, datetime.utcnow())
    db_session.commit()
    with SessionLocal() as takeover:
        run = takeover.get(AgentRun, run_id)
        run.worker_id = WORKER_B
        run.execution_token = token + 1
        takeover.commit()

    gateway = SlowGateway(wait_seconds=0.05)
    runner = FencedConversationRunner(gateway)._runner
    outcome = asyncio.run(runner.run(db_session, run_id, worker_id=WORKER_A,
                                     execution_token=token))
    assert outcome.status == "failed" and outcome.error_code == "ownership_lost"
    assert outcome.run_finalized is False
    run = db_session.get(AgentRun, run_id)
    assert run.status == "running" and run.worker_id == WORKER_B
    assert db_session.query(AgentMessage).filter(
        AgentMessage.session_id == chat.id, AgentMessage.role != "user").count() == 0
