"""Pure bounded Agent Loop translated from Pi's V2-P03 control flow.

The loop owns conversation/turn/message/tool event order. Provider-specific
streaming stays in P02; persistence, workers, approvals and Skills stay out.
"""
from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel

from app.agents.conversation.budget import AgentLimitError, AgentLoopBudget, AgentLoopLimits
from app.agents.conversation.events import (AgentEndEvent, AgentStartEvent, MessageEndEvent,
    MessageStartEvent, MessageUpdateEvent, TurnEndEvent, TurnStartEvent)
from app.agents.conversation.messages import AssistantMessage, Message, ToolCall, ToolResultMessage, Usage
from app.agents.conversation.tool_executor import ToolExecutionOutcome, execute_tool_call
from app.agents.providers.streaming import (AttemptBudget, ProviderSnapshot, StreamContext, StreamControl,
    StreamError, StreamLimits, StreamRequest, fixed_error_message)
from app.agents.registry.tool_registry import ToolRegistry
from app.schemas.llm.llm_gateway import LLMToolSpec

EventSink = Callable[[Any], Awaitable[None] | None]


@dataclass
class AgentLoopContext:
    system_prompt: str
    messages: list[Message]
    tool_registry: ToolRegistry
    metadata: dict[str, Any] = field(default_factory=dict)
    application_context: Any = None


@dataclass
class AgentLoopConfig:
    gateway: Any
    snapshot: ProviderSnapshot
    event_sink: EventSink
    cancel_event: asyncio.Event
    limits: AgentLoopLimits = field(default_factory=AgentLoopLimits)
    provider_attempt_budget: AttemptBudget = field(default_factory=lambda: AttemptBudget(limit=24))
    stream_limits: StreamLimits = field(default_factory=StreamLimits)
    policy: Any = None
    id_factory: Callable[[], str] = field(default_factory=lambda: lambda: uuid.uuid4().hex)
    timestamp_factory: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time() * 1000))


@dataclass(frozen=True)
class AgentLoopResult:
    status: Literal["completed", "error", "aborted", "limit", "stopped", "waiting"]
    messages: list[Message]
    new_messages: list[Message]
    turns: int
    model_calls: int
    tool_calls: int
    error_code: str | None = None


async def _emit(sink: EventSink, event: Any) -> None:
    result = sink(event)
    if inspect.isawaitable(result):
        await result


def _tool_specs(registry: ToolRegistry) -> list[LLMToolSpec]:
    specs: list[LLMToolSpec] = []
    for definition in registry.list():
        schema: dict[str, Any] = {}
        model = definition.input_model
        if isinstance(model, type) and issubclass(model, BaseModel):
            try:
                schema = model.model_json_schema()
            except Exception:
                schema = {}
        specs.append(LLMToolSpec(name=definition.name, description=definition.description,
                                 input_schema=schema))
    return specs


def _error_message(config: AgentLoopConfig, message_id: str, timestamp: int,
                   code: str) -> AssistantMessage:
    return AssistantMessage(message_id=message_id, timestamp=timestamp, role="assistant", content=[],
        api=config.snapshot.api, provider=config.snapshot.name, model=config.snapshot.model_name,
        usage=Usage(input=None, output=None, cache_read=None, cache_write=None,
                    total_tokens=None, cost=None),
        stop_reason="aborted" if code == "canceled" else "error",
        error_message=fixed_error_message(code))


async def _stream_assistant(transcript: list[Message], new_messages: list[Message],
                            context: AgentLoopContext, config: AgentLoopConfig,
                            budget: AgentLoopBudget) -> tuple[AssistantMessage, str | None]:
    message_id, timestamp = config.id_factory(), config.timestamp_factory()
    control = StreamControl(cancel_event=config.cancel_event, deadline=config.limits.deadline,
                            budget=config.provider_attempt_budget)
    request = StreamRequest(system_prompt=context.system_prompt, messages=list(transcript),
                            tools=_tool_specs(context.tool_registry))
    current: AssistantMessage | None = None
    added = False
    try:
        async with config.gateway.stream(config.snapshot, request, context=StreamContext(
            message_id=message_id, timestamp=timestamp), control=control,
            limits=config.stream_limits) as events:
            async for event in events:
                if event.type == "start":
                    current = event.partial
                    transcript.append(current); new_messages.append(current); added = True
                    await _emit(config.event_sink, MessageStartEvent(message=current))
                elif event.type in {"text_start", "text_delta", "text_end",
                                   "toolcall_start", "toolcall_delta", "toolcall_end"}:
                    current = event.partial
                    if added:
                        transcript[-1] = current; new_messages[-1] = current
                    else:
                        transcript.append(current); new_messages.append(current); added = True
                        await _emit(config.event_sink, MessageStartEvent(message=current))
                    await _emit(config.event_sink, MessageUpdateEvent(
                        message=current, assistant_message_event=event))
                elif event.type in {"done", "error"}:
                    final = event.message if event.type == "done" else event.error
                    current = final
                    if added:
                        transcript[-1] = final; new_messages[-1] = final
                    else:
                        transcript.append(final); new_messages.append(final); added = True
                        await _emit(config.event_sink, MessageStartEvent(message=final))
                    await _emit(config.event_sink, MessageEndEvent(message=final))
                    return final, control.error_code
    except StreamError as exc:
        current = _error_message(config, message_id, timestamp, exc.error_code)
        transcript.append(current); new_messages.append(current)
        await _emit(config.event_sink, MessageStartEvent(message=current))
        await _emit(config.event_sink, MessageEndEvent(message=current))
        return current, exc.error_code
    if current is None or current.stop_reason == "pending":
        current = _error_message(config, message_id, timestamp, "stream_incomplete")
        if added:
            transcript[-1] = current; new_messages[-1] = current
        else:
            transcript.append(current); new_messages.append(current)
            await _emit(config.event_sink, MessageStartEvent(message=current))
        await _emit(config.event_sink, MessageEndEvent(message=current))
    return current, "stream_incomplete"


def _status_for_message(message: AssistantMessage, code: str | None) -> tuple[str, str | None]:
    if message.stop_reason == "aborted" or code == "canceled":
        return "aborted", code or "canceled"
    if message.stop_reason == "error":
        return "error", code or "model_error"
    return "completed", None


def _result(status: str, transcript: list[Message], new_messages: list[Message],
            budget: AgentLoopBudget, error_code: str | None = None) -> AgentLoopResult:
    return AgentLoopResult(status=status, messages=list(transcript), new_messages=list(new_messages),
        turns=budget.turns, model_calls=budget.model_calls, tool_calls=budget.tool_calls,
        error_code=error_code)


async def run_agent_loop(*, prompts: list[Message], context: AgentLoopContext,
                         config: AgentLoopConfig) -> AgentLoopResult:
    """Run one bounded conversation request until a final reply or hard stop."""
    transcript = list(context.messages)
    new_messages: list[Message] = []
    budget = AgentLoopBudget(config.limits)
    await _emit(config.event_sink, AgentStartEvent())
    for prompt in prompts:
        transcript.append(prompt); new_messages.append(prompt)
        await _emit(config.event_sink, MessageStartEvent(message=prompt))
        await _emit(config.event_sink, MessageEndEvent(message=prompt))

    while True:
        if config.cancel_event.is_set():
            result = _result("aborted", transcript, new_messages, budget, "canceled")
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result
        try:
            budget.begin_model_turn()
            await _emit(config.event_sink, TurnStartEvent())
            assistant, model_code = await _stream_assistant(
                transcript, new_messages, context, config, budget)
        except AgentLimitError as exc:
            result = _result("limit", transcript, new_messages, budget, exc.error_code)
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result

        tool_calls = [block for block in assistant.content if isinstance(block, ToolCall)]
        if assistant.stop_reason in {"error", "aborted", "deferred"}:
            await _emit(config.event_sink, TurnEndEvent(message=assistant, tool_results=[]))
            status, code = _status_for_message(assistant, model_code)
            result = _result(status, transcript, new_messages, budget, code)
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result

        if not tool_calls:
            await _emit(config.event_sink, TurnEndEvent(message=assistant, tool_results=[]))
            result = _result("completed", transcript, new_messages, budget)
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result

        call_ids = [call.id for call in tool_calls]
        if any(not call.id or not call.name for call in tool_calls) or len(set(call_ids)) != len(call_ids):
            await _emit(config.event_sink, TurnEndEvent(message=assistant, tool_results=[]))
            result = _result("error", transcript, new_messages, budget, "invalid_tool_calls")
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result

        try:
            budget.reserve_tool_batch(len(tool_calls))
        except AgentLimitError as exc:
            await _emit(config.event_sink, TurnEndEvent(message=assistant, tool_results=[]))
            result = _result("limit", transcript, new_messages, budget, exc.error_code)
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result

        tool_results: list[ToolResultMessage] = []
        stop_signal: str | None = None
        for call in tool_calls:
            forced_code = "truncated_tool_call" if assistant.stop_reason == "length" else None
            if stop_signal is not None:
                forced_code = (stop_signal if stop_signal in {"canceled", "deadline_exceeded"}
                               else "tool_batch_stopped")
            elif config.cancel_event.is_set():
                stop_signal = "canceled"
                forced_code = "canceled"
            outcome: ToolExecutionOutcome = await execute_tool_call(
                assistant_message=assistant, tool_call=call, registry=context.tool_registry,
                policy=config.policy, cancel_event=config.cancel_event,
                deadline=config.limits.deadline, event_sink=config.event_sink,
                message_id=config.id_factory(), timestamp=config.timestamp_factory(),
                metadata=context.metadata, application_context=context.application_context,
                forced_error_code=forced_code,
            )
            tool_results.append(outcome.message)
            transcript.append(outcome.message); new_messages.append(outcome.message)
            await _emit(config.event_sink, MessageStartEvent(message=outcome.message))
            await _emit(config.event_sink, MessageEndEvent(message=outcome.message))
            if outcome.error_code in {"canceled", "deadline_exceeded", "tool_not_executable"}:
                stop_signal = outcome.error_code
            elif outcome.signal in {"stop", "wait"}:
                stop_signal = outcome.signal

        await _emit(config.event_sink, TurnEndEvent(message=assistant, tool_results=tool_results))
        if stop_signal is not None:
            if stop_signal == "wait": status = "waiting"
            elif stop_signal == "canceled": status = "aborted"
            elif stop_signal == "deadline_exceeded": status = "limit"
            else: status = "stopped"
            result = _result(status, transcript, new_messages, budget, stop_signal)
            await _emit(config.event_sink, AgentEndEvent(messages=result.new_messages))
            return result
