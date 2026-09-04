"""Sequential, policy-gated tool execution for the pure V2-P03 loop.

The executor translates validation/policy/tool failures into ToolResultMessage
objects so the model can correct a call. Infrastructure limits and cancellation
are surfaced separately so the loop can stop. It never discovers tools or
imports database/application services.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel

from app.agents.conversation.events import (ToolExecutionEndEvent, ToolExecutionStartEvent,
    ToolExecutionUpdateEvent)
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, ToolResultMessage, Usage
from app.agents.conversation.policy import (DefaultToolPolicy, ToolPolicyContext, ToolPolicyDecision,
    evaluate_policy)
from app.agents.conversation.tool_validation import (ToolValidationError, build_tool_result_message,
    prepare_tool_call)
from app.agents.registry.tool_registry import ToolRegistry

EventSink = Callable[[Any], Awaitable[None] | None]

_ERROR_TEXT = {
    "unknown_tool": "未知工具，未执行",
    "invalid_arguments": "工具参数无效，未执行",
    "invalid_config": "工具配置无效，未执行",
    "validation_failed": "工具参数校验失败，未执行",
    "empty_call_id": "工具调用标识无效，未执行",
    "tool_policy_denied": "工具策略拒绝执行",
    "approval_required": "工具需要人工批准，当前未执行",
    "permission_required": "工具需要额外权限，当前未执行",
    "write_tool_blocked": "写入工具尚未开放，当前未执行",
    "invalid_policy": "工具策略配置无效，未执行",
    "tool_execution_failed": "工具执行失败",
    "tool_result_invalid": "工具返回结果无效",
    "tool_not_executable": "工具没有可执行入口",
    "truncated_tool_call": "工具参数可能被截断，未执行",
    "canceled": "工具执行已取消",
    "deadline_exceeded": "工具执行超过截止时间",
    "tool_batch_stopped": "本批次已停止，工具未执行",
}


class ToolExecutionStopped(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(_ERROR_TEXT.get(error_code, "工具执行已停止"))


@dataclass(frozen=True)
class ToolExecutionResult:
    content: list[TextContent]
    details: Any = None
    usage: Usage | None = None
    signal: Literal["continue", "stop", "wait"] = "continue"


@dataclass(frozen=True)
class ToolExecutionOutcome:
    message: ToolResultMessage
    error_code: str | None = None
    signal: Literal["continue", "stop", "wait"] = "continue"


class ToolHandlerContext:
    """Runtime services visible to a registered P03 handler."""
    def __init__(self, *, cancel_event: asyncio.Event, deadline: float | None,
                 metadata: dict[str, Any], update: Callable[[Any], Awaitable[bool]],
                 application_context: Any = None):
        self.cancel_event = cancel_event
        self.deadline = deadline
        self.metadata = dict(metadata)
        self.application_context = application_context
        self._update = update

    async def report_update(self, partial_result: Any) -> bool:
        return await self._update(partial_result)


async def _emit(sink: EventSink, event: Any) -> None:
    result = sink(event)
    if inspect.isawaitable(result):
        await result


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item) for key, item in value.items())
    return False


def _fixed_result(code: str, *, signal: Literal["continue", "stop", "wait"] = "continue") -> ToolExecutionResult:
    return ToolExecutionResult(content=[TextContent(text=_ERROR_TEXT.get(code, "工具执行失败"))],
                               details={"error_code": code}, signal=signal)


def _normalize_result(value: Any, output_model: Any) -> ToolExecutionResult:
    if isinstance(value, ToolExecutionResult):
        if value.signal not in {"continue", "stop", "wait"} or not all(isinstance(x, TextContent) for x in value.content):
            raise ToolExecutionStopped("tool_result_invalid")
        if not _json_safe(value.details):
            raise ToolExecutionStopped("tool_result_invalid")
        return value

    if output_model is not None:
        if not isinstance(output_model, type) or not issubclass(output_model, BaseModel):
            raise ToolExecutionStopped("tool_result_invalid")
        try:
            validated = value if isinstance(value, output_model) else output_model.model_validate(value, strict=True)
            value = validated.model_dump(mode="json")
        except Exception as exc:
            raise ToolExecutionStopped("tool_result_invalid") from exc
    elif isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    if isinstance(value, str):
        return ToolExecutionResult(content=[TextContent(text=value)], details=None)
    if value is None:
        return ToolExecutionResult(content=[], details=None)
    if not _json_safe(value):
        raise ToolExecutionStopped("tool_result_invalid")
    return ToolExecutionResult(
        content=[TextContent(text=json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))],
        details=value,
    )


async def _await_handler(awaitable: Awaitable[Any], *, cancel_event: asyncio.Event,
                         deadline: float | None,
                         on_complete: Callable[[], None] | None = None) -> Any:
    if cancel_event.is_set():
        raise ToolExecutionStopped("canceled")
    loop = asyncio.get_running_loop()
    remaining = None if deadline is None else deadline - loop.time()
    if remaining is not None and remaining <= 0:
        raise ToolExecutionStopped("deadline_exceeded")
    operation = asyncio.ensure_future(awaitable)
    cancel_wait = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait({operation, cancel_wait}, timeout=remaining,
                                     return_when=asyncio.FIRST_COMPLETED)
        if operation in done:
            if on_complete is not None:
                on_complete()
            cancel_wait.cancel()
            return operation.result()
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        raise ToolExecutionStopped("canceled" if cancel_event.is_set() else "deadline_exceeded")
    except asyncio.CancelledError:
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        raise
    finally:
        cancel_wait.cancel()
        await asyncio.gather(cancel_wait, return_exceptions=True)


async def execute_tool_call(
    *,
    assistant_message: AssistantMessage,
    tool_call: ToolCall,
    registry: ToolRegistry,
    policy: Any | None,
    cancel_event: asyncio.Event,
    deadline: float | None,
    event_sink: EventSink,
    message_id: str,
    timestamp: int,
    metadata: dict[str, Any] | None = None,
    application_context: Any = None,
    forced_error_code: str | None = None,
) -> ToolExecutionOutcome:
    """Validate, authorize and execute one call; all calls are invoked serially by the loop."""
    await _emit(event_sink, ToolExecutionStartEvent(
        tool_call_id=tool_call.id, tool_name=tool_call.name, args=tool_call.arguments))

    accepting_updates = True
    validated_arguments: dict[str, Any] = dict(tool_call.arguments)

    async def update(partial_result: Any) -> bool:
        if not accepting_updates or cancel_event.is_set() or not _json_safe(partial_result):
            return False
        await _emit(event_sink, ToolExecutionUpdateEvent(
            tool_call_id=tool_call.id, tool_name=tool_call.name,
            args=validated_arguments, partial_result=partial_result))
        return True

    def stop_updates() -> None:
        nonlocal accepting_updates
        accepting_updates = False

    result: ToolExecutionResult
    code: str | None = None
    try:
        if forced_error_code is not None:
            code, result = forced_error_code, _fixed_result(forced_error_code)
        elif cancel_event.is_set():
            raise ToolExecutionStopped("canceled")
        else:
            try:
                prepared = prepare_tool_call(registry, tool_call)
                definition = registry.get(tool_call.name)
            except ToolValidationError as exc:
                code, result = exc.error_code, _fixed_result(exc.error_code)
            else:
                try:
                    decision = await _await_handler(
                        evaluate_policy(policy or DefaultToolPolicy(), ToolPolicyContext(
                            assistant_message=assistant_message, tool_call=tool_call, prepared=prepared,
                            definition=definition, metadata=dict(metadata or {}))),
                        cancel_event=cancel_event, deadline=deadline,
                    )
                except ToolExecutionStopped:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception:
                    decision = ToolPolicyDecision.block("invalid_policy", terminate=True)
                if not decision.allowed:
                    code = decision.error_code or "tool_policy_denied"
                    result = _fixed_result(code, signal="stop" if decision.terminate else "continue")
                else:
                    if decision.arguments is not None:
                        if not isinstance(decision.arguments, dict):
                            code, result = "invalid_policy", _fixed_result("invalid_policy", signal="stop")
                        else:
                            rewritten = tool_call.model_copy(deep=True, update={"arguments": decision.arguments})
                            try:
                                prepared = prepare_tool_call(registry, rewritten)
                            except ToolValidationError as exc:
                                code, result = exc.error_code, _fixed_result(exc.error_code)
                    if code is None:
                        validated_arguments = dict(prepared.arguments)
                        runtime = ToolHandlerContext(cancel_event=cancel_event, deadline=deadline,
                            metadata=dict(metadata or {}), update=update, application_context=application_context)
                        try:
                            if definition.handler is not None:
                                raw = definition.handler(dict(validated_arguments), runtime)
                            elif definition.tool is not None:
                                payload = definition.input_model.model_validate(validated_arguments, strict=True)
                                raw = definition.tool.execute(application_context, payload)
                            else:
                                raise ToolExecutionStopped("tool_not_executable")
                            if inspect.isawaitable(raw):
                                raw = await _await_handler(raw, cancel_event=cancel_event,
                                    deadline=deadline, on_complete=stop_updates)
                            else:
                                stop_updates()
                                if cancel_event.is_set():
                                    raise ToolExecutionStopped("canceled")
                                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                                    raise ToolExecutionStopped("deadline_exceeded")
                            result = _normalize_result(raw, definition.output_model)
                        except ToolExecutionStopped:
                            raise
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            code, result = "tool_execution_failed", _fixed_result("tool_execution_failed")
    except ToolExecutionStopped as exc:
        code = exc.error_code
        signal = "stop" if code in {"canceled", "deadline_exceeded", "tool_not_executable"} else "continue"
        result = _fixed_result(code, signal=signal)
    finally:
        stop_updates()

    event_result = {
        "content": [item.model_dump() for item in result.content],
        "details": result.details,
        "signal": result.signal,
    }
    await _emit(event_sink, ToolExecutionEndEvent(
        tool_call_id=tool_call.id, tool_name=tool_call.name,
        result=event_result, is_error=code is not None))
    message = build_tool_result_message(
        tool_call, message_id=message_id, timestamp=timestamp,
        is_error=code is not None, content=result.content,
        details=result.details, usage=result.usage,
    )
    return ToolExecutionOutcome(message=message, error_code=code, signal=result.signal)
