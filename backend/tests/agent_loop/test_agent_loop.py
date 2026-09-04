"""V2-P03 pure Agent Loop and sequential tool execution tests."""
import asyncio
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import BaseModel

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.events import AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent
from app.agents.conversation.loop import AgentLoopConfig, AgentLoopContext, run_agent_loop
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage, UserMessage
from app.agents.conversation.policy import ToolPolicyDecision
from app.agents.conversation.tool_executor import ToolExecutionResult
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry


class EchoInput(BaseModel):
    value: str


class CountInput(BaseModel):
    count: int


class CalculatorInput(BaseModel):
    operation: Literal["add", "subtract", "multiply", "divide"]
    left: str
    right: str


def usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None, total_tokens=2, cost=None)


def assistant(*content, reason="stop", message_id="template"):
    return AssistantMessage(message_id=message_id, timestamp=1, role="assistant", content=list(content),
        api="chat", provider="fake", model="fake-model", usage=usage(), stop_reason=reason)


def user(text="hello", message_id="u1"):
    return UserMessage(message_id=message_id, timestamp=1, role="user", content=text)


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        final = self.responses.pop(0).model_copy(deep=True, update={
            "message_id": context.message_id,
            "timestamp": context.timestamp,
        })

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


def registry(*definitions):
    result = ToolRegistry()
    for definition in definitions:
        result.register(definition)
    return result


def run(responses, *, tools=None, limits=None, policy=None, cancel_event=None,
        metadata=None, event_sink=None):
    events = []
    sink = event_sink or events.append
    gateway = FakeGateway(responses)
    sequence = iter(f"m{i}" for i in range(1, 50))
    config = AgentLoopConfig(
        gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid", "key", "fake-model", max_tokens=20),
        event_sink=sink,
        cancel_event=cancel_event or asyncio.Event(),
        limits=limits or AgentLoopLimits(),
        provider_attempt_budget=AttemptBudget(limit=20),
        policy=policy,
        id_factory=lambda: next(sequence),
        timestamp_factory=lambda: 10,
    )
    context = AgentLoopContext(system_prompt="be helpful", messages=[],
        tool_registry=tools or ToolRegistry(), metadata=metadata or {})

    async def go():
        result = await run_agent_loop(prompts=[user()], context=context, config=config)
        return result
    return asyncio.run(go()), events, gateway


def test_plain_chat_completes_without_tool_execution():
    result, events, gateway = run([assistant(TextContent(text="hi"))])
    assert result.status == "completed"
    assert result.model_calls == 1 and result.tool_calls == 0
    assert [message.role for message in result.new_messages] == ["user", "assistant"]
    assert [event.type for event in events] == [
        "agent_start", "message_start", "message_end", "turn_start",
        "message_start", "message_end", "turn_end", "agent_end",
    ]
    assert len(gateway.requests) == 1


def test_tool_result_is_sent_back_to_model_before_final_reply():
    calls = []
    async def echo(arguments, runtime):
        calls.append(arguments)
        return arguments["value"]
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=echo))
    result, events, gateway = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "hi"}), reason="toolUse"),
        assistant(TextContent(text="result is hi")),
    ], tools=tools)
    assert result.status == "completed" and result.model_calls == 2 and result.tool_calls == 1
    assert calls == [{"value": "hi"}]
    second_history = gateway.requests[1].messages
    assert [message.role for message in second_history][-2:] == ["assistant", "toolResult"]
    assert second_history[-1].tool_call_id == "c1" and second_history[-1].content[0].text == "hi"
    types = [event.type for event in events]
    assert types.index("tool_execution_end") < types.index("turn_end")


def test_two_tools_execute_serially_and_results_keep_call_order():
    order = []
    async def echo(arguments, runtime):
        order.append(arguments["value"])
        await asyncio.sleep(0)
        return arguments["value"]
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=echo))
    result, events, gateway = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "a"}),
                  ToolCall(id="c2", name="echo", arguments={"value": "b"}), reason="toolUse"),
        assistant(TextContent(text="done")),
    ], tools=tools)
    assert order == ["a", "b"]
    results = [message for message in result.new_messages if message.role == "toolResult"]
    assert [message.tool_call_id for message in results] == ["c1", "c2"]
    assert [event.tool_call_id for event in events if event.type == "tool_execution_start"] == ["c1", "c2"]


def test_multiple_model_turns_can_each_request_a_tool_before_final_reply():
    calls = []
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
        handler=lambda arguments, runtime: calls.append(arguments["value"]) or arguments["value"]))
    result, events, gateway = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "a"}), reason="toolUse"),
        assistant(ToolCall(id="c2", name="echo", arguments={"value": "b"}), reason="toolUse"),
        assistant(TextContent(text="final")),
    ], tools=tools)
    assert calls == ["a", "b"]
    assert (result.turns, result.model_calls, result.tool_calls) == (3, 3, 2)
    assert len(gateway.requests) == 3
    assert [event.type for event in events].count("turn_end") == 3


def test_unknown_tool_becomes_error_result_then_model_can_repair():
    result, _, gateway = run([
        assistant(ToolCall(id="c1", name="ghost", arguments={}), reason="toolUse"),
        assistant(TextContent(text="I cannot use it")),
    ])
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert tool_result.is_error is True
    assert tool_result.details == {"error_code": "unknown_tool"}
    assert len(gateway.requests) == 2 and result.status == "completed"


def test_invalid_arguments_never_call_handler_and_can_be_repaired():
    called = []
    tools = registry(ToolDefinition(name="count", input_model=CountInput,
                                    handler=lambda arguments, runtime: called.append(arguments)))
    result, _, _ = run([
        assistant(ToolCall(id="c1", name="count", arguments={"count": "7"}), reason="toolUse"),
        assistant(TextContent(text="bad arguments")),
    ], tools=tools)
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert called == [] and tool_result.details == {"error_code": "invalid_arguments"}


def test_policy_rewrite_is_strictly_revalidated():
    called = []
    tools = registry(ToolDefinition(name="count", input_model=CountInput,
                                    handler=lambda arguments, runtime: called.append(arguments) or "ok"))
    class InvalidRewrite:
        async def evaluate(self, context):
            return ToolPolicyDecision.allow(arguments={"count": "8"})
    result, _, _ = run([
        assistant(ToolCall(id="c1", name="count", arguments={"count": 1}), reason="toolUse"),
        assistant(TextContent(text="rewrite rejected")),
    ], tools=tools, policy=InvalidRewrite())
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert called == [] and tool_result.details == {"error_code": "invalid_arguments"}


def test_policy_exception_is_safe_and_never_reaches_handler():
    marker, called = "POLICY-SECRET", []
    class BrokenPolicy:
        async def evaluate(self, context):
            raise RuntimeError(marker)
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
                                    handler=lambda arguments, runtime: called.append(arguments)))
    result, events, _ = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse")
    ], tools=tools, policy=BrokenPolicy())
    exported = str([message.model_dump() for message in result.new_messages]) + str([event.model_dump() for event in events])
    assert called == [] and marker not in exported
    assert result.status == "stopped" and "invalid_policy" in exported


def test_valid_policy_rewrite_reaches_handler():
    called = []
    tools = registry(ToolDefinition(name="count", input_model=CountInput,
        handler=lambda arguments, runtime: called.append(arguments) or {"seen": arguments["count"]}))
    policy = lambda context: ToolPolicyDecision.allow(arguments={"count": 2})
    result, _, _ = run([
        assistant(ToolCall(id="c1", name="count", arguments={"count": 1}), reason="toolUse"),
        assistant(TextContent(text="ok")),
    ], tools=tools, policy=policy)
    assert called == [{"count": 2}]
    assert [message for message in result.new_messages if message.role == "toolResult"][0].is_error is False


def test_decimal_calculator_fixture_does_not_use_eval():
    def calculate(arguments, runtime):
        left, right = Decimal(arguments["left"]), Decimal(arguments["right"])
        operations = {
            "add": lambda: left + right,
            "subtract": lambda: left - right,
            "multiply": lambda: left * right,
            "divide": lambda: left / right,
        }
        return str(operations[arguments["operation"]]())
    tools = registry(ToolDefinition(name="calculator", input_model=CalculatorInput, handler=calculate))
    result, _, _ = run([
        assistant(ToolCall(id="c1", name="calculator",
            arguments={"operation": "add", "left": "0.1", "right": "0.2"}), reason="toolUse"),
        assistant(TextContent(text="0.3")),
    ], tools=tools)
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert tool_result.content[0].text == "0.3"


@pytest.mark.parametrize("definition,code", [
    (ToolDefinition(name="write", input_model=EchoInput, handler=lambda *_: "x", read_only=False), "write_tool_blocked"),
    (ToolDefinition(name="approve", input_model=EchoInput, handler=lambda *_: "x", requires_approval=True), "approval_required"),
    (ToolDefinition(name="private", input_model=EchoInput, handler=lambda *_: "x", required_permission="project.read"), "permission_required"),
])
def test_default_policy_blocks_unavailable_authority(definition, code):
    result, _, _ = run([
        assistant(ToolCall(id="c1", name=definition.name, arguments={"value": "x"}), reason="toolUse"),
        assistant(TextContent(text="blocked")),
    ], tools=registry(definition))
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert tool_result.details == {"error_code": code}


def test_tool_exception_is_safe_error_feedback_and_loop_continues():
    marker = "SECRET-FROM-TOOL"
    def boom(arguments, runtime):
        raise RuntimeError(marker)
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=boom))
    result, events, _ = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse"),
        assistant(TextContent(text="recovered")),
    ], tools=tools)
    exported = str([message.model_dump() for message in result.new_messages]) + str([event.model_dump() for event in events])
    assert marker not in exported
    assert "tool_execution_failed" in exported


def test_tool_progress_is_emitted_before_end():
    async def handler(arguments, runtime):
        assert await runtime.report_update({"step": 1}) is True
        return "done"
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=handler))
    _, events, _ = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse"),
        assistant(TextContent(text="final")),
    ], tools=tools)
    types = [event.type for event in events]
    assert types.index("tool_execution_start") < types.index("tool_execution_update") < types.index("tool_execution_end")


def test_length_tool_call_never_invokes_handler_but_is_returned_as_error():
    called = []
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
                                    handler=lambda arguments, runtime: called.append(arguments)))
    result, _, _ = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="length"),
        assistant(TextContent(text="retried safely")),
    ], tools=tools)
    tool_result = [message for message in result.new_messages if message.role == "toolResult"][0]
    assert called == [] and tool_result.details == {"error_code": "truncated_tool_call"}


def test_tool_batch_limit_is_atomic_and_executes_none():
    called = []
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
                                    handler=lambda arguments, runtime: called.append(arguments)))
    result, events, gateway = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "a"}),
                  ToolCall(id="c2", name="echo", arguments={"value": "b"}), reason="toolUse")
    ], tools=tools, limits=AgentLoopLimits(max_turns=2, max_model_calls=2, max_tool_calls=1))
    assert result.status == "limit" and result.error_code == "max_tool_calls"
    assert called == [] and result.tool_calls == 0 and len(gateway.requests) == 1
    assert "tool_execution_start" not in [event.type for event in events]


def test_duplicate_tool_call_ids_are_rejected_before_any_execution():
    called = []
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
                                    handler=lambda arguments, runtime: called.append(arguments)))
    result, events, _ = run([assistant(
        ToolCall(id="same", name="echo", arguments={"value": "a"}),
        ToolCall(id="same", name="echo", arguments={"value": "b"}), reason="toolUse")], tools=tools)
    assert result.status == "error" and result.error_code == "invalid_tool_calls"
    assert called == [] and "tool_execution_start" not in [event.type for event in events]


@pytest.mark.parametrize("limits,expected", [
    (AgentLoopLimits(max_turns=1, max_model_calls=3, max_tool_calls=3), "max_turns"),
    (AgentLoopLimits(max_turns=3, max_model_calls=1, max_tool_calls=3), "max_model_calls"),
])
def test_turn_and_model_call_limits_are_hard(limits, expected):
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=lambda *_: "ok"))
    result, _, gateway = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse"),
        assistant(TextContent(text="never reached")),
    ], tools=tools, limits=limits)
    assert result.status == "limit" and result.error_code == expected
    assert len(gateway.requests) == 1
    assert [event.type for event in _].count("turn_start") == [event.type for event in _].count("turn_end")


def test_expired_deadline_makes_zero_model_calls():
    result, events, gateway = run([assistant(TextContent(text="never"))],
        limits=AgentLoopLimits(deadline=time.monotonic() - 1))
    assert result.status == "limit" and result.error_code == "deadline_exceeded"
    assert result.model_calls == 0 and gateway.requests == []
    assert [event.type for event in events][-1] == "agent_end"


def test_cancel_before_loop_makes_zero_model_calls():
    cancel = asyncio.Event(); cancel.set()
    result, events, gateway = run([assistant(TextContent(text="never"))], cancel_event=cancel)
    assert result.status == "aborted" and result.model_calls == 0
    assert gateway.requests == []
    assert [event.type for event in events] == ["agent_start", "message_start", "message_end", "agent_end"]


def test_model_error_ends_current_run_but_returns_transcript():
    result, events, _ = run([assistant(reason="error")])
    assert result.status == "error" and result.error_code == "synthetic_model_error"
    assert result.new_messages[-1].role == "assistant"
    assert [event.type for event in events][-2:] == ["turn_end", "agent_end"]


def test_tool_stop_and_wait_signals_end_without_another_model_call():
    for signal, status in (("stop", "stopped"), ("wait", "waiting")):
        async def handler(arguments, runtime, current=signal):
            return ToolExecutionResult(content=[TextContent(text=current)], signal=current)
        tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=handler))
        result, _, gateway = run([
            assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse")
        ], tools=tools)
        assert result.status == status and len(gateway.requests) == 1


def test_cancel_during_async_tool_stops_remaining_batch():
    entered = asyncio.Event()
    cancel = asyncio.Event()
    async def slow(arguments, runtime):
        entered.set()
        await asyncio.Event().wait()
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=slow))
    gateway = FakeGateway([assistant(
        ToolCall(id="c1", name="echo", arguments={"value": "a"}),
        ToolCall(id="c2", name="echo", arguments={"value": "b"}), reason="toolUse")])
    events = []
    ids = iter(["m1", "m2", "m3"])
    config = AgentLoopConfig(gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid", "key", "m", max_tokens=10),
        event_sink=events.append, cancel_event=cancel, id_factory=lambda: next(ids), timestamp_factory=lambda: 1)
    context = AgentLoopContext("", [], tools)
    async def go():
        task = asyncio.create_task(run_agent_loop(prompts=[user()], context=context, config=config))
        await asyncio.wait_for(entered.wait(), 1)
        cancel.set()
        return await asyncio.wait_for(task, 1)
    result = asyncio.run(go())
    assert result.status == "aborted"
    assert [event.tool_call_id for event in events if event.type == "tool_execution_start"] == ["c1", "c2"]
    results = [message for message in result.new_messages if message.role == "toolResult"]
    assert [message.tool_call_id for message in results] == ["c1", "c2"]
    assert all(message.is_error for message in results)


def test_cancel_interrupts_async_policy_before_handler():
    entered, cancel, called = asyncio.Event(), asyncio.Event(), []
    class SlowPolicy:
        async def evaluate(self, context):
            entered.set()
            await asyncio.Event().wait()
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput,
        handler=lambda arguments, runtime: called.append(arguments)))
    gateway = FakeGateway([assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse")])
    events, ids = [], iter(["m1", "m2"])
    config = AgentLoopConfig(gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid", "key", "m", max_tokens=10),
        event_sink=events.append, cancel_event=cancel, policy=SlowPolicy(),
        id_factory=lambda: next(ids), timestamp_factory=lambda: 1)
    context = AgentLoopContext("", [], tools)
    async def go():
        task = asyncio.create_task(run_agent_loop(prompts=[user()], context=context, config=config))
        await asyncio.wait_for(entered.wait(), 1)
        cancel.set()
        return await asyncio.wait_for(task, 1)
    result = asyncio.run(go())
    assert result.status == "aborted" and called == []
    assert [event.type for event in events].count("tool_execution_end") == 1


def test_deadline_interrupts_async_tool_and_closes_turn():
    entered = asyncio.Event()
    async def slow(arguments, runtime):
        entered.set()
        await asyncio.Event().wait()
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=slow))
    result, events, _ = run([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse")
    ], tools=tools, limits=AgentLoopLimits(deadline=time.monotonic() + 0.03))
    assert entered.is_set()
    assert result.status == "limit" and result.error_code == "deadline_exceeded"
    assert [event.type for event in events].count("turn_start") == [event.type for event in events].count("turn_end")


def test_late_tool_progress_after_result_is_discarded():
    late_tasks = []
    async def handler(arguments, runtime):
        async def late():
            await asyncio.sleep(0.01)
            await runtime.report_update({"late": True})
        late_tasks.append(asyncio.create_task(late()))
        return "done"
    tools = registry(ToolDefinition(name="echo", input_model=EchoInput, handler=handler))
    events = []
    gateway = FakeGateway([
        assistant(ToolCall(id="c1", name="echo", arguments={"value": "x"}), reason="toolUse"),
        assistant(TextContent(text="final")),
    ])
    ids = iter(f"m{i}" for i in range(5))
    config = AgentLoopConfig(gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid", "key", "m", max_tokens=10),
        event_sink=events.append, cancel_event=asyncio.Event(), id_factory=lambda: next(ids), timestamp_factory=lambda: 1)
    context = AgentLoopContext("", [], tools)
    async def go():
        result = await run_agent_loop(prompts=[user()], context=context, config=config)
        await asyncio.gather(*late_tasks)
        return result
    result = asyncio.run(go())
    assert result.status == "completed"
    assert "tool_execution_update" not in [event.type for event in events]
