"""V2-P05-B ConversationRunner 测试：Fake Provider / 内存 SQLite。

验证链：AgentRun → ConversationRunner → restore → AgentLoop(Tool) → persist → finalize。
不请求真实 LLM；不启动 Worker/HTTP；不依赖前端。
"""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import BaseModel

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.events import AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.agents.runtime.errors import AgentError
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.project import Project
from app.models.user import User
from app.services.agent import agent_run_service, agent_session_service, conversation_service

USER_A = 101


# ---------------------------------------------------------------- 工具与消息夹具

class CalculatorInput(BaseModel):
    operation: Literal["add", "subtract", "multiply", "divide"]
    left: str
    right: str


def usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def assistant(*content, reason="stop", message_id="template"):
    return AssistantMessage(message_id=message_id, timestamp=1, role="assistant",
        content=list(content), api="chat", provider="fake", model="fake-model",
        usage=usage(), stop_reason=reason)


class FakeGateway:
    """脚本化 Fake：依次弹出响应；explode=True 时在 stream 入口抛异常。"""

    def __init__(self, responses, explode=False):
        self.responses = list(responses)
        self.requests = []
        self.explode = explode

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        if self.explode:
            @asynccontextmanager
            async def managed():
                raise RuntimeError("provider-boom")
                yield  # pragma: no cover
            return managed()
        final = self.responses.pop(0).model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                partial = final.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                if final.stop_reason in {"error", "aborted"}:
                    control.error_code = "synthetic_model_error" if final.stop_reason == "error" else "canceled"
                    yield AssistantErrorEvent(reason=final.stop_reason, error=final)
                else:
                    yield AssistantDoneEvent(reason=final.stop_reason, message=final)
            yield events()
        return managed()


def calculator_registry() -> ToolRegistry:
    def calculate(arguments, runtime):
        left, right = Decimal(arguments["left"]), Decimal(arguments["right"])
        operations = {
            "add": lambda: left + right,
            "subtract": lambda: left - right,
            "multiply": lambda: left * right,
            "divide": lambda: left / right,
        }
        return str(operations[arguments["operation"]]())
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="calculator", input_model=CalculatorInput,
                                     handler=calculate))
    return registry


def make_runner(responses, *, tools=None, id_counter=None, explode=False,
                limits=None) -> tuple[ConversationRunner, FakeGateway]:
    if id_counter is None:
        id_counter = iter(f"m{i}" for i in range(1, 500))
    gateway = FakeGateway(responses, explode=explode)
    runner = ConversationRunner(
        gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                  "key", "fake-model", max_tokens=20),
        tool_registry=tools or ToolRegistry(),
        system_prompt="be helpful",
        limits=limits or AgentLoopLimits(),
        provider_attempt_budget=AttemptBudget(limit=20),
        id_factory=lambda: next(id_counter),
        timestamp_factory=lambda: 10,
    )
    return runner, gateway


def seed_user(db):
    db.add(User(id=USER_A, username="user-a", password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.flush()


def conversation(db):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=USER_A, title="聊天")
    db.commit()
    return row


def submit(db, session_id, content="hello", key="request-1"):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, message_id_factory=lambda: f"user-{key}",
        timestamp_ms_factory=lambda: 10)


def rows(db):
    return db.query(AgentMessage).order_by(AgentMessage.sequence_no.asc()).all()


def event_types(db, run_id):
    return [event.event_type for event in db.query(AgentEvent).filter(
        AgentEvent.run_id == run_id).order_by(AgentEvent.sequence_no.asc()).all()]


# ---------------------------------------------------------------- Case 1：无 Tool

def test_plain_chat_restores_persists_and_succeeds_without_duplicating_user_message(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="t1")
    runner, gateway = make_runner([assistant(TextContent(text="hi"))])
    outcome = run_async(runner.run(db_session, first.run.id))

    assert outcome.status == "succeeded" and outcome.model_calls == 1
    assert gateway.requests[0].messages[-1].role == "user"
    stored = rows(db_session)
    assert [row.role for row in stored] == ["user", "assistant"]
    assert stored[0].content == "hello" and stored[1].content == "hi"
    assert len(outcome.persisted_message_ids) == 1
    assert event_types(db_session, first.run.id) == ["run_started", "run_succeeded"]
    run = db_session.get(AgentRun, first.run.id)
    assert run.status == "succeeded" and run.active_slot is None
    assert run.llm_calls_used == 1 and run.tool_calls_used == 0


# ---------------------------------------------------------------- Case 2：一次 ToolCall

def test_tool_call_flow_round_trips_and_persists_new_messages_in_order(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="计算 12 + 7", key="calc")
    runner, gateway = make_runner([
        assistant(ToolCall(id="c1", name="calculator",
                           arguments={"operation": "add", "left": "12", "right": "7"}),
                  reason="toolUse"),
        assistant(TextContent(text="结果是 19")),
    ], tools=calculator_registry())
    outcome = run_async(runner.run(db_session, first.run.id))

    assert outcome.status == "succeeded"
    assert outcome.model_calls == 2 and outcome.tool_calls == 1
    assert len(outcome.persisted_message_ids) == 3  # toolCall assistant + toolResult + final
    stored = rows(db_session)
    assert [row.role for row in stored] == ["user", "assistant", "toolResult", "assistant"]
    assert stored[1].content_json["content"][0]["type"] == "toolCall"
    assert stored[2].role == "toolResult"
    assert stored[3].content == "结果是 19"
    # 第二次模型请求确实收到了工具结果
    second_history = gateway.requests[1].messages
    assert [message.role for message in second_history][-2:] == ["assistant", "toolResult"]
    assert second_history[-1].tool_call_id == "c1"


# ---------------------------------------------------------------- Case 3：多轮恢复

def test_second_turn_uses_persisted_history_and_only_persists_new_messages(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="记住数字 17", key="mem")
    runner1, _ = make_runner([assistant(TextContent(text="好"))])
    run_async(runner1.run(db_session, first.run.id))

    second = submit(db_session, chat.id, content="我刚才给你的数字是什么？", key="ask")
    counter = iter(f"n{i}" for i in range(1, 500))
    runner2, gateway2 = make_runner([assistant(TextContent(text="17"))], id_counter=counter)
    outcome = run_async(runner2.run(db_session, second.run.id))

    history = gateway2.requests[0].messages
    assert [message.role for message in history] == ["user", "assistant", "user"]
    assert history[0].content == "记住数字 17"
    assert history[1].content[0].text == "好"
    assert history[2].content == "我刚才给你的数字是什么？"

    stored = rows(db_session)
    assert [row.role for row in stored] == ["user", "assistant", "user", "assistant"]
    assert [row.message_id for row in stored] == ["user-mem", "m1", "user-ask", "n1"]
    assert len(outcome.persisted_message_ids) == 1  # 只新增本轮的 assistant
    assert db_session.get(AgentRun, second.run.id).status == "succeeded"


# ---------------------------------------------------------------- Case 4：Provider 异常

def test_provider_exception_marks_run_failed_without_phantom_assistant(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="boom")
    runner, _ = make_runner([], explode=True)
    outcome = run_async(runner.run(db_session, first.run.id))

    assert outcome.status == "failed" and outcome.error_code == "runner_execution_error"
    stored = rows(db_session)
    assert len(stored) == 1 and stored[0].role == "user"  # 无伪助手消息
    run = db_session.get(AgentRun, first.run.id)
    assert run.status == "failed" and run.error_code == "runner_execution_error"
    assert event_types(db_session, first.run.id) == ["run_started", "run_failed"]


def test_model_error_result_maps_run_to_failed(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="modelerr")
    runner, _ = make_runner([assistant(reason="error", message_id="x1")])  # content=[] 的错误助手消息
    outcome = run_async(runner.run(db_session, first.run.id))

    assert outcome.status == "failed" and outcome.error_code == "synthetic_model_error"
    run = db_session.get(AgentRun, first.run.id)
    assert run.status == "failed" and run.error_message is not None
    assert "run_failed" in event_types(db_session, first.run.id)


# ---------------------------------------------------------------- Case 5：Cancel

def test_cancel_event_before_run_marks_run_cancelled_without_model_call(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="cancel")
    runner, gateway = make_runner([assistant(TextContent(text="hi"))])
    cancel_event = asyncio.Event()
    cancel_event.set()
    outcome = run_async(runner.run(db_session, first.run.id, cancel_event=cancel_event))

    assert outcome.status == "cancelled" and outcome.error_code == "canceled"
    assert gateway.requests == []  # 未发起任何模型请求
    assert len(rows(db_session)) == 1  # 只保留用户消息，无伪助手消息
    run = db_session.get(AgentRun, first.run.id)
    assert run.status == "cancelled"
    assert event_types(db_session, first.run.id) == ["run_started", "run_cancelled"]


# ---------------------------------------------------------------- 事务边界（P05-C 最小修复验证）

def test_no_active_db_transaction_during_model_wait(db_session):
    """LLM 网络等待期间 DB Session 不得持有 active transaction。

    共享 StaticPool 单连接：若 Runner 在读校验后未 rollback 就进入 run_agent_loop，
    gateway 内用另一 Session 发起查询会触发 "cannot start a transaction
    within a transaction" / database locked；探测成功即证明事务已释放。
    """
    from sqlalchemy import text as sql_text
    from app.core.database import SessionLocal

    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="tx")

    probe = {"result": None, "error": None}

    class ProbingGateway(FakeGateway):
        def stream(self, snapshot, request, *, context, control, limits=None):
            @asynccontextmanager
            async def managed():
                async def events():
                    try:
                        with SessionLocal() as probe_session:
                            probe_session.execute(sql_text("SELECT 1")).scalar()
                        probe["result"] = "ok"
                    except Exception as exc:  # pragma: no cover - 只在回归时出现
                        probe["result"] = "blocked"
                        probe["error"] = type(exc).__name__
                    final = assistant(TextContent(text="hi")).model_copy(
                        deep=True, update={"message_id": context.message_id, "timestamp": context.timestamp})
                    partial = final.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                    yield AssistantStartEvent(partial=partial)
                    yield AssistantDoneEvent(reason="stop", message=final)
                yield events()
            return managed()

    gateway = ProbingGateway([assistant(TextContent(text="hi"))])
    runner = ConversationRunner(
        gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                  "key", "fake-model", max_tokens=20),
        tool_registry=ToolRegistry(),
        system_prompt="be helpful",
        provider_attempt_budget=AttemptBudget(limit=20),
        id_factory=iter(f"t{i}" for i in range(1, 500)).__next__,
        timestamp_factory=lambda: 10,
    )
    outcome = run_async(runner.run(db_session, first.run.id))
    assert outcome.status == "succeeded", f"outcome={outcome!r} probe={probe}"
    assert probe["result"] == "ok", f"模型等待期间仍持有 DB 事务: {probe}"


# ---------------------------------------------------------------- 状态与身份边界

def test_terminal_run_is_not_startable(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    first = submit(db_session, chat.id, content="hello", key="done")
    runner, _ = make_runner([assistant(TextContent(text="hi"))])
    run_async(runner.run(db_session, first.run.id))
    with pytest.raises(AgentError) as exc:
        run_async(runner.run(db_session, first.run.id))
    assert exc.value.error_code == "agent_run_not_startable"


def test_legacy_workflow_run_is_rejected(db_session):
    seed_user(db_session)
    project = Project(id=7, name="p", status="active", is_deleted=False)
    db_session.add(project)
    db_session.commit()
    legacy_session = agent_session_service.create_session(db_session, USER_A, 7, "旧")
    db_session.commit()
    run = agent_run_service.create_run(db_session, legacy_session, "case_generation",
                                       USER_A, 7, input_json={})
    db_session.commit()
    runner, _ = make_runner([assistant(TextContent(text="x"))])
    with pytest.raises(AgentError) as exc:
        run_async(runner.run(db_session, run.id))
    assert exc.value.error_code == "agent_run_not_conversation"


def run_async(awaitable):
    return asyncio.run(awaitable)
