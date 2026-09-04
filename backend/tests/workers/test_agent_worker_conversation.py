"""V2-P05-C Worker Dispatch + Conversation Claim 测试。

覆盖：
- Case 1/集成链：submit → worker.run_once() → ConversationRunner → Fake Provider → Run succeeded；
- Case 2/3：dispatch 路由（conversation → ConversationRunner；legacy → AgentRunner）；
- Case 4：无 queued Run → idle；
- Case 5：conversation runner unexpected exception → Worker 不 crash、单一 finalize；
- Case 6：claim service 不再排除 conversation queued Run。

不请求真实 LLM；不启动 HTTP；全部 SQLite（conftest 内存库 + SessionLocal）。
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import text as sql_text

from app.agents.conversation.events import AssistantDoneEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, Usage
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.core.database import SessionLocal
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.project import Project
from app.models.user import User
from app.services.agent import agent_run_service, agent_session_service, conversation_service
from app.workers.agent_worker import AgentWorker, WorkerRunResult

WORKER_A = "worker-conv-a"
USER_A = 101


# ---------------------------------------------------------------- 夹具

def seed_user(db, user_id=USER_A):
    if not db.query(User).filter(User.id == user_id).first():
        db.add(User(id=user_id, username=f"user_{user_id}", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()


def conversation_session(db, user_id=USER_A):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=user_id, title="聊天")
    db.commit()
    return row


def submit_turn(db, session_id, content="hello", key="req"):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, message_id_factory=lambda: f"user-{key}",
        timestamp_ms_factory=lambda: 10)


def seed_legacy_run(db, user_id=1, project_id=101, code="legacy-spy"):
    seed_user(db, user_id)
    if not db.query(Project).filter(Project.id == project_id).first():
        db.add(Project(id=project_id, name="Worker 项目", status="active", is_deleted=False))
        db.flush()
    session = agent_session_service.create_session(db, user_id, project_id, "旧")
    db.commit()
    run = agent_run_service.create_run(db, session, code, user_id, project_id, input_json={})
    db.commit()
    return run


def make_usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def chat_reply(text):
    return AssistantMessage(message_id="reply-template", timestamp=1, role="assistant",
        content=[TextContent(text=text)], api="chat", provider="fake", model="fake-model",
        usage=make_usage(), stop_reason="stop")


class ChatGateway:
    """脚本化聊天 Fake：流式返回预设文本；可在流期间执行 DB 探测。"""

    def __init__(self, replies, on_stream=None):
        self.replies = list(replies)
        self.requests = []
        self.on_stream = on_stream

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        reply = self.replies.pop(0).model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                if self.on_stream is not None:
                    self.on_stream()
                partial = reply.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                yield AssistantDoneEvent(reason="stop", message=reply)
            yield events()
        return managed()


class RaisingConversationRunner:
    """Case 5：模拟 ConversationRunner 抛 unexpected exception（claim 之后）。"""

    def __init__(self):
        self.called = False

    async def run(self, db, run_id, cancel_event=None):
        self.called = True
        raise RuntimeError("conversation-runner-boom")


class RecordingConversationRunner:
    """dispatch spy：记录被调用，不推进状态。"""

    def __init__(self):
        self.called_run_ids = []

    async def run(self, db, run_id, cancel_event=None):
        self.called_run_ids.append(run_id)
        return None


class RecordingLegacyRunner:
    """dispatch spy（sync，替代 AgentRunner）。"""

    def __init__(self):
        self.called_run_ids = []

    def run(self, db, run):
        self.called_run_ids.append(run.id)


def make_worker(*, conversation_factory_calls=None, conversation_runner=None,
                runtime_factory=None, clock=None, worker_id=WORKER_A) -> AgentWorker:
    clock = clock or FakeClock()

    def conversation_runner_factory():
        if conversation_factory_calls is not None:
            conversation_factory_calls.append(1)
        if conversation_runner is not None:
            return conversation_runner
        return ChatConversationRunner()

    if runtime_factory is None:
        runtime_factory = lambda hook: RecordingLegacyRunner()

    return AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=runtime_factory,
        worker_id=worker_id,
        now_provider=clock,
        sleeper=lambda _s: None,
        poll_interval_seconds=0.1,
        stale_after_seconds=300.0,
        conversation_runner_factory=conversation_runner_factory,
    )


class FakeClock:
    def __init__(self, start=None):
        self.t = start or datetime(2026, 1, 1)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t = self.t.replace(second=self.t.second + int(seconds))


class ChatConversationRunner:
    """用真实 ConversationRunner 的最小装配（Fake gateway + 空工具集）。"""

    def __init__(self, gateway=None):
        from app.agents.conversation.budget import AgentLoopLimits
        from app.agents.conversation.runner import ConversationRunner
        from app.agents.registry.tool_registry import ToolRegistry
        self.gateway = gateway or ChatGateway([chat_reply("hi")])
        self._runner = ConversationRunner(
            gateway=self.gateway,
            snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                      "key", "fake-model", max_tokens=20),
            tool_registry=ToolRegistry(),
            system_prompt="be helpful",
            limits=AgentLoopLimits(),
            provider_attempt_budget=AttemptBudget(limit=20),
            id_factory=iter(f"w{i}" for i in range(1, 500)).__next__,
            timestamp_factory=lambda: 10,
        )

    async def run(self, db, run_id, cancel_event=None):
        return await self._runner.run(db, run_id, cancel_event=cancel_event)


def fresh_run(db_session, run_id):
    db_session.expire_all()  # worker 用独立 Session 提交，先清 db_session 身份映射缓存
    return db_session.get(AgentRun, run_id)


def event_types_for(db, run_id):
    return [e.event_type for e in db.query(AgentEvent).filter(
        AgentEvent.run_id == run_id).order_by(AgentEvent.sequence_no.asc()).all()]


# ---------------------------------------------------------------- Case 1 + 集成链

def test_worker_claims_and_executes_conversation_run_end_to_end(db_session):
    seed_user(db_session)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="e2e")
    run_id = submission.run.id
    assert submission.run.status == "queued"

    probe = {"result": None, "error": None}

    def on_stream():
        try:
            with SessionLocal() as probe_session:
                probe_session.execute(sql_text("SELECT 1")).scalar()
            probe["result"] = "ok"
        except Exception as exc:  # pragma: no cover - 回归时才会出现
            probe["result"] = "blocked"
            probe["error"] = type(exc).__name__

    gateway = ChatGateway([chat_reply("hi")], on_stream=on_stream)
    worker = make_worker(conversation_runner=ChatConversationRunner(gateway=gateway))
    result = worker.run_once()

    assert result.action == "completed" and result.final_status == "succeeded"
    run = fresh_run(db_session, run_id)
    assert run.status == "succeeded" and run.worker_id == WORKER_A
    assert run.active_slot is None
    assert run.llm_calls_used == 1
    stored = db_session.query(AgentMessage).filter(
        AgentMessage.session_id == chat.id).order_by(AgentMessage.sequence_no.asc()).all()
    assert [row.role for row in stored] == ["user", "assistant"]
    assert event_types_for(db_session, run_id) == ["run_started", "run_succeeded"]  # 无重复 run_started
    assert probe["result"] == "ok", f"LLM 等待期间持有 DB 事务: {probe['error']}"


# ---------------------------------------------------------------- Case 2/3：dispatch

def test_dispatch_routes_conversation_run_to_conversation_runner(db_session):
    seed_user(db_session)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="conv")
    conv_runner = RecordingConversationRunner()
    factory_calls = []
    legacy_runner = RecordingLegacyRunner()

    worker = AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: legacy_runner,
        worker_id=WORKER_A,
        now_provider=FakeClock(),
        sleeper=lambda _s: None,
        poll_interval_seconds=0.1,
        stale_after_seconds=300.0,
        conversation_runner_factory=lambda: (factory_calls.append(1), conv_runner)[1],
    )
    result = worker.run_once()

    assert result.action == "completed"
    assert conv_runner.called_run_ids == [submission.run.id]
    assert legacy_runner.called_run_ids == []  # conversation 绝不进 legacy AgentRunner
    assert factory_calls == [1]


def test_dispatch_routes_legacy_run_to_legacy_runner(db_session):
    run = seed_legacy_run(db_session, code="legacy-spy")
    conv_runner = RecordingConversationRunner()
    legacy_runner = RecordingLegacyRunner()

    worker = AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: legacy_runner,
        worker_id=WORKER_A,
        now_provider=FakeClock(),
        sleeper=lambda _s: None,
        poll_interval_seconds=0.1,
        stale_after_seconds=300.0,
        conversation_runner_factory=lambda: conv_runner,
    )
    result = worker.run_once()

    assert result.action == "completed"
    assert legacy_runner.called_run_ids == [run.id]
    assert conv_runner.called_run_ids == []  # legacy 不进 ConversationRunner


# ---------------------------------------------------------------- Case 4：无任务 idle

def test_run_once_idle_when_no_queued_run(db_session):
    seed_user(db_session)
    conversation_session(db_session)  # 只有会话没有 Run
    worker = make_worker()
    result = worker.run_once()
    assert result == WorkerRunResult(action="idle")


# ---------------------------------------------------------------- Case 5：runner 异常

def test_conversation_runner_unexpected_exception_marks_failed_and_worker_survives(db_session):
    seed_user(db_session)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="boom")
    run_id = submission.run.id

    worker = make_worker(conversation_runner=RaisingConversationRunner())
    result = worker.run_once()

    assert result.action == "failed" and result.final_status == "failed"
    run = fresh_run(db_session, run_id)
    assert run.status == "failed"
    assert run.error_code == "agent_runtime_error"
    assert "conversation-runner-boom" in run.error_message
    # 单一 finalize：fake runner 在写入生命周期前就抛异常，worker 只标记一次
    # （无 run_started 是 fake 语义；真实 ConversationRunner 的异常路径见 runner 测试）
    assert event_types_for(db_session, run_id) == ["run_failed"]

    # Worker 存活：下一次 tick 正常 idle
    assert worker.run_once().action == "idle"


def test_conversation_without_configured_runner_fails_cleanly(db_session):
    seed_user(db_session)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="nofac")
    run_id = submission.run.id
    worker = AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: RecordingLegacyRunner(),
        worker_id=WORKER_A,
        now_provider=FakeClock(),
        sleeper=lambda _s: None,
        poll_interval_seconds=0.1,
        stale_after_seconds=300.0,
        conversation_runner_factory=None,
    )
    result = worker.run_once()
    assert result.action == "failed"
    run = fresh_run(db_session, run_id)
    assert run.status == "failed" and run.error_code == "agent_unknown_workflow"


# ---------------------------------------------------------------- Case 6：claim service

def test_claim_service_no_longer_excludes_conversation_queued_run(db_session):
    seed_user(db_session)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="claim")
    run_id = submission.run.id

    session = SessionLocal()
    try:
        assert agent_run_service.next_queued_run_id(session) == run_id
        assert agent_run_service.claim_queued_run(session, run_id, "worker-x", datetime(2026, 1, 1)) is True
        session.commit()
    finally:
        session.close()

    run = fresh_run(db_session, run_id)
    assert run.status == "running" and run.worker_id == "worker-x"


def test_conversation_and_legacy_queued_runs_share_one_queue_ordered_by_id(db_session):
    legacy_run = seed_legacy_run(db_session, code="legacy-spy")  # id 较小
    seed_user(db_session, USER_A)
    chat = conversation_session(db_session)
    submission = submit_turn(db_session, chat.id, content="hello", key="mixed")
    conv_run_id = submission.run.id

    session = SessionLocal()
    try:
        candidates = []
        candidate = agent_run_service.next_queued_run_id(session)
        while candidate is not None:
            candidates.append(candidate)
            assert agent_run_service.claim_queued_run(
                session, candidate, "worker-x", datetime(2026, 1, 1)) is True
            session.commit()
            candidate = agent_run_service.next_queued_run_id(session)
    finally:
        session.close()

    assert candidates == sorted([legacy_run.id, conv_run_id])
