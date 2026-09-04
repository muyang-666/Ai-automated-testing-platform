"""V2-P02 coordinator: one logical stream, bounded physical attempts."""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable

from app.agents.conversation.events import AssistantErrorEvent
from app.agents.conversation.messages import AssistantMessage, Usage
from app.agents.providers.anthropic_adapter import AnthropicAdapter
from app.agents.providers.anthropic_stream_adapter import AnthropicStreamAdapter
from app.agents.providers.base import Capability
from app.agents.providers.openai_compatible_adapter import OpenAICompatibleAdapter
from app.agents.providers.openai_stream_adapter import OpenAIStreamAdapter
from app.agents.providers.streaming import (AttemptBudget, AttemptRecord, ProviderSnapshot, StreamContext,
    StreamControl, StreamError, StreamLimits, StreamRequest, await_controlled, effective_timeout,
    fixed_error_message, to_anthropic_system_messages_and_tools, to_openai_messages_and_tools,
    validate_stream_inputs)

_OPENAI_ALIASES = {"openai_compatible", "deepseek", "openai", "qwen", "custom"}
_CONTENT_EVENTS = {"text_start", "text_delta", "text_end", "toolcall_start", "toolcall_delta", "toolcall_end"}


def _empty_usage() -> Usage:
    return Usage(input=None, output=None, cache_read=None, cache_write=None, total_tokens=None, cost=None)


def _error_event(snapshot: ProviderSnapshot, context: StreamContext, code: str,
                 partial: AssistantMessage | None = None) -> AssistantErrorEvent:
    reason = "aborted" if code == "canceled" else "error"
    if partial is None:
        message = AssistantMessage(message_id=context.message_id, timestamp=context.timestamp, role="assistant",
            content=[], api=snapshot.api, provider=snapshot.name, model=snapshot.model_name,
            usage=_empty_usage(), stop_reason=reason, error_message=fixed_error_message(code))
    else:
        message = partial.model_copy(deep=True, update={"stop_reason": reason, "error_message": fixed_error_message(code)})
    return AssistantErrorEvent(reason=reason, error=message)


def _usage_of(event: Any) -> Usage | None:
    message = getattr(event, "message", None) or getattr(event, "error", None)
    return getattr(message, "usage", None)


def _message_of(event: Any) -> AssistantMessage | None:
    return getattr(event, "partial", None) or getattr(event, "message", None) or getattr(event, "error", None)


class LLMStreamGateway:
    def __init__(self, *, max_retries: int = 2, retry_delay_seconds: float = 0.5,
                 openai_stream_factory: Any = None, anthropic_stream_factory: Any = None,
                 capability_overrides: dict | None = None,
                 capability_resolver: Callable[[ProviderSnapshot], Any] | None = None,
                 async_sleeper: Callable[[float], Any] | None = None):
        self._max_retries = max(0, max_retries)
        self._retry_delay = max(0.0, retry_delay_seconds)
        self._openai = openai_stream_factory or OpenAIStreamAdapter()
        self._anthropic = anthropic_stream_factory or AnthropicStreamAdapter()
        self._overrides = capability_overrides or {}
        self._capability_resolver = capability_resolver
        self._sleeper = async_sleeper or asyncio.sleep

    def _adapter(self, snapshot: ProviderSnapshot):
        if snapshot.provider_type in _OPENAI_ALIASES: return self._openai
        if snapshot.provider_type == "anthropic": return self._anthropic
        raise StreamError("configuration_error", retryable=False)

    def _capabilities(self, snapshot: ProviderSnapshot):
        if self._capability_resolver is not None:
            return self._capability_resolver(snapshot)
        baseline = (OpenAICompatibleAdapter().baseline_capabilities if snapshot.provider_type in _OPENAI_ALIASES
                    else AnthropicAdapter().baseline_capabilities if snapshot.provider_type == "anthropic" else None)
        if baseline is None: raise StreamError("configuration_error", retryable=False)
        return (self._overrides.get((snapshot.provider_type, snapshot.model_name))
                or self._overrides.get((snapshot.provider_type, "*")) or baseline)

    def _preflight(self, snapshot: ProviderSnapshot, request: StreamRequest, context: StreamContext,
                   control: StreamControl, limits: StreamLimits) -> float:
        timeout = validate_stream_inputs(snapshot, request, context, control, limits)
        capabilities = self._capabilities(snapshot)
        if request.tools and getattr(capabilities, "tools", Capability.UNKNOWN) == Capability.UNSUPPORTED:
            raise StreamError("unsupported_parameter", retryable=False)
        if getattr(capabilities, "streaming", Capability.UNKNOWN) == Capability.UNSUPPORTED:
            raise StreamError("unsupported_parameter", retryable=False)
        if snapshot.provider_type == "anthropic" and request.temperature is not None:
            raise StreamError("unsupported_parameter", retryable=False)
        if snapshot.provider_type in _OPENAI_ALIASES:
            to_openai_messages_and_tools(request)
        else:
            to_anthropic_system_messages_and_tools(request)
        return timeout

    async def stream(self, snapshot: ProviderSnapshot, request: StreamRequest, context: StreamContext,
                     *, control: StreamControl | None = None, limits: StreamLimits | None = None,
                     budget: AttemptBudget | None = None) -> AsyncIterator[Any]:
        control = control or StreamControl(cancel_event=asyncio.Event())
        limits = limits or StreamLimits()
        effective_budget = budget or control.budget or AttemptBudget(limit=self._max_retries + 1)
        control.budget = effective_budget
        timeout = self._preflight(snapshot, request, context, control, limits)
        if control.deadline is None:
            control.deadline = time.monotonic() + timeout
        if control.cancelled():
            control.set_failure("canceled"); yield _error_event(snapshot, context, "canceled"); return

        adapter = self._adapter(snapshot)
        retry_no, logical_start_sent = 0, False
        last_message: AssistantMessage | None = None
        while True:
            if control.cancelled():
                control.set_failure("canceled"); yield _error_event(snapshot, context, "canceled", last_message); return
            if control.deadline is not None and time.monotonic() >= control.deadline:
                control.set_failure("deadline_exceeded"); yield _error_event(snapshot, context, "deadline_exceeded", last_message); return
            if not effective_budget.try_acquire():
                control.set_failure("budget_exhausted"); yield _error_event(snapshot, context, "budget_exhausted", last_message); return

            attempt_number, started = len(control.attempt_records) + 1, time.monotonic()
            content_emitted, terminal, recorded = False, False, False
            control.clear_attempt_state()
            inner = adapter.stream(snapshot, request, context, control, limits)
            try:
                async for event in inner:
                    message = _message_of(event)
                    if message is not None: last_message = message
                    if event.type == "start":
                        if logical_start_sent: continue
                        logical_start_sent = True
                    if event.type in _CONTENT_EVENTS: content_emitted = True
                    if event.type in {"done", "error"}:
                        terminal = True
                        code = None if event.type == "done" else (control.error_code or "stream_gateway_error")
                        usage = _usage_of(event)
                        control.attempt_records.append(_record(attempt_number, started,
                            "succeeded" if event.type == "done" else ("cancelled" if code == "canceled" else "failed"),
                            control.current_request_id, message, usage, code))
                        recorded = True
                    yield event
                    if terminal: return
                raise StreamError("stream_incomplete", retryable=False)
            except asyncio.CancelledError:
                control.attempt_records.append(_record(attempt_number, started, "cancelled",
                    control.current_request_id, last_message, _usage_from_message(last_message), "canceled"))
                recorded = True
                raise
            except StreamError as exc:
                code = "canceled" if control.cancelled() else exc.error_code
                control.attempt_records.append(_record(attempt_number, started,
                    "cancelled" if code == "canceled" else "failed", exc.request_id or control.current_request_id,
                    last_message, exc.usage or _usage_from_message(last_message), code))
                recorded = True
                can_retry = (exc.retryable and not content_emitted and not control.cancelled()
                             and retry_no < self._max_retries and effective_budget.used < effective_budget.limit)
                if can_retry:
                    retry_no += 1
                    try:
                        await await_controlled(self._sleeper(self._retry_delay * (2 ** (retry_no - 1))), control)
                    except StreamError as wait_error:
                        code = wait_error.error_code
                        control.set_failure(code); yield _error_event(snapshot, context, code, last_message); return
                    continue
                control.set_failure(code)
                yield _error_event(snapshot, context, code, last_message)
                return
            except Exception:
                code = "stream_gateway_error"
                control.attempt_records.append(_record(attempt_number, started, "failed", control.current_request_id,
                    last_message, _usage_from_message(last_message), code))
                recorded = True; control.set_failure(code)
                yield _error_event(snapshot, context, code, last_message); return
            finally:
                await inner.aclose()
                if not recorded:
                    control.consumer_closed = True
                    control.attempt_records.append(_record(attempt_number, started, "consumer_closed",
                        control.current_request_id, last_message, _usage_from_message(last_message), None))


def _usage_from_message(message: AssistantMessage | None) -> Usage | None:
    return message.usage if message is not None else None


def _record(attempt: int, started: float, status: str, request_id: str | None,
            message: AssistantMessage | None, usage: Usage | None, code: str | None) -> AttemptRecord:
    return AttemptRecord(attempt=attempt, status=status, duration_ms=max(0, int((time.monotonic()-started)*1000)),
        request_id=request_id, response_id=message.response_id if message else None,
        prompt_tokens=usage.input if usage else None, completion_tokens=usage.output if usage else None,
        cache_read_tokens=usage.cache_read if usage else None, cache_write_tokens=usage.cache_write if usage else None,
        error_code=code)
