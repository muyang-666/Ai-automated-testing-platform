"""One physical Anthropic streaming request using the installed SDK's raw response.

Raw bytes are decoded locally so unknown SSE events and resource limits stay
observable. Event ordering follows Pi's locked anthropic-messages adapter.
"""
from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, AsyncIterator, Callable

from app.agents.conversation.events import (AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent,
    AssistantTextDeltaEvent, AssistantTextEndEvent, AssistantTextStartEvent, AssistantToolCallDeltaEvent,
    AssistantToolCallEndEvent, AssistantToolCallStartEvent)
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage
from app.agents.providers.streaming import (BoundedSSEDecoder, ProviderSnapshot, SSEFrame, StreamContext,
    StreamControl, StreamError, StreamLimits, StreamRequest, await_controlled, effective_timeout,
    fixed_error_message, resolve_max_tokens, to_anthropic_system_messages_and_tools)


def _strict_object(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class AnthropicStreamAdapter:
    provider_type = "anthropic"
    def __init__(self, anthropic_factory: Callable[[], Any] | None = None):
        self._factory = anthropic_factory

    def _client(self, snapshot: ProviderSnapshot, timeout: float):
        from anthropic import AsyncAnthropic
        return self._factory() if self._factory is not None else AsyncAnthropic(
            api_key=snapshot.api_key, base_url=snapshot.base_url or None, timeout=timeout, max_retries=0)

    async def stream(self, snapshot: ProviderSnapshot, request: StreamRequest, context: StreamContext,
                     control: StreamControl, limits: StreamLimits | None = None) -> AsyncIterator[Any]:
        if request.temperature is not None:
            raise StreamError("unsupported_parameter", retryable=False)
        limits = limits or StreamLimits()
        system, messages, tools = to_anthropic_system_messages_and_tools(request)
        timeout = effective_timeout(request, snapshot)
        payload: dict[str, Any] = {"model": snapshot.model_name, "messages": messages,
                                  "max_tokens": resolve_max_tokens(request, snapshot), "stream": True}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        client = self._client(snapshot, timeout)
        assembler = _AnthropicAssembler(snapshot, context, limits)
        response_cm, response, byte_stream = None, None, None
        try:
            response_cm = client.messages.with_streaming_response.create(**payload)
            response = await await_controlled(response_cm.__aenter__(), control)
            control.current_request_id = _safe_response_id(getattr(response, "request_id", None))
            yield assembler.start_event()
            decoder = BoundedSSEDecoder(limits)
            byte_stream = response.iter_bytes()
            iterator = byte_stream.__aiter__()
            while not assembler.finished:
                try:
                    raw = await await_controlled(anext(iterator), control)
                except StopAsyncIteration:
                    for frame in decoder.finish():
                        for event in assembler.process_frame(frame):
                            if event.type == "error":
                                control.set_failure(assembler.last_error_code or "stream_gateway_error")
                            yield event
                    break
                for frame in decoder.feed(raw):
                    for event in assembler.process_frame(frame):
                        if event.type == "error":
                            control.set_failure(assembler.last_error_code or "stream_gateway_error")
                        yield event
                    if assembler.finished:
                        break
            if not assembler.finished:
                control.set_failure("stream_incomplete")
                yield assembler.error_event("stream_incomplete")
        except StreamError as exc:
            if not exc.retryable:
                control.set_failure(exc.error_code)
                yield assembler.error_event(exc.error_code)
                return
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            translated = _translate_sdk_error(exc, control.current_request_id)
            raise translated from exc
        finally:
            if byte_stream is not None and hasattr(byte_stream, "aclose"):
                await byte_stream.aclose()
            if response_cm is not None and response is not None:
                await response_cm.__aexit__(None, None, None)
            await client.close()


def _translate_sdk_error(exc: Exception, request_id: str | None) -> StreamError:
    try:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return StreamError("network_error", retryable=True, request_id=request_id)
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            return StreamError("retryable_http" if status == 429 or (isinstance(status, int) and status >= 500)
                               else "http_error", request_id=request_id)
    except ImportError:  # pragma: no cover - adapter cannot run without the optional SDK
        pass
    return StreamError("stream_gateway_error", retryable=False, request_id=request_id)


def _safe_response_id(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        return None
    return value if all(c.isalnum() or c in "-_.:" for c in value) else None


class _AnthropicAssembler:
    def __init__(self, snapshot: ProviderSnapshot, context: StreamContext, limits: StreamLimits):
        self.snapshot, self.context, self.limits = snapshot, context, limits
        self.content: list[Any] = []
        self.blocks: dict[int, dict[str, Any]] = {}
        self.input_tokens = self.output_tokens = self.cache_read = self.cache_write = None
        self.stop_raw: str | None = None
        self.response_id: str | None = None
        self.finished = False
        self.saw_reasoning = False
        self.last_error_code: str | None = None

    def usage(self) -> Usage:
        fields = (self.input_tokens, self.output_tokens, self.cache_read, self.cache_write)
        total = sum(fields) if all(type(x) is int for x in fields) else None
        return Usage(input=self.input_tokens, output=self.output_tokens, cache_read=self.cache_read,
                     cache_write=self.cache_write, total_tokens=total, cost=None)

    def message(self, reason: str) -> AssistantMessage:
        return AssistantMessage(message_id=self.context.message_id, timestamp=self.context.timestamp, role="assistant",
            content=copy.deepcopy(self.content), api=self.snapshot.api, provider=self.snapshot.name,
            model=self.snapshot.model_name, usage=self.usage(), stop_reason=reason, response_id=self.response_id)

    def start_event(self):
        return AssistantStartEvent(partial=self.message("pending"))

    def process_frame(self, frame: SSEFrame) -> list[Any]:
        event_name = frame.event
        if event_name == "ping":
            return []
        if event_name == "error":
            self.finished = True
            return [self.error_event("refused")]
        try:
            data = json.loads(frame.data, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StreamError("protocol_error", retryable=False) from exc
        if not isinstance(data, dict):
            raise StreamError("protocol_error", retryable=False)
        event_type = data.get("type")
        if event_name and event_name != event_type:
            raise StreamError("unsupported_stream_event", retryable=False)
        return self.process(data)

    def process(self, data: dict[str, Any]) -> list[Any]:
        kind = data.get("type")
        if kind == "ping": return []
        if kind == "message_start":
            message = data.get("message") or {}; usage = message.get("usage") or {}
            self.response_id = _safe_response_id(message.get("id"))
            self.input_tokens, self.output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            self.cache_read, self.cache_write = usage.get("cache_read_input_tokens"), usage.get("cache_creation_input_tokens")
            return []
        if kind == "content_block_start": return self.block_start(data)
        if kind == "content_block_delta": return self.block_delta(data)
        if kind == "content_block_stop": return self.block_stop(data)
        if kind == "message_delta":
            delta, usage = data.get("delta") or {}, data.get("usage") or {}
            if delta.get("stop_reason") is not None: self.stop_raw = delta["stop_reason"]
            for source, target in (("output_tokens", "output_tokens"), ("cache_read_input_tokens", "cache_read"),
                                   ("cache_creation_input_tokens", "cache_write")):
                if usage.get(source) is not None: setattr(self, target, usage[source])
            return []
        if kind == "message_stop":
            self.finished = True
            return self.finalize()
        raise StreamError("unsupported_stream_event", retryable=False)

    def _index(self, data: dict[str, Any]) -> int:
        value = data.get("index")
        if type(value) is not int or value < 0: raise StreamError("protocol_error", retryable=False)
        return value

    def block_start(self, data: dict[str, Any]) -> list[Any]:
        index, raw = self._index(data), data.get("content_block") or {}
        if index in self.blocks or not isinstance(raw, dict): raise StreamError("protocol_error", retryable=False)
        kind = raw.get("type")
        if kind in {"thinking", "redacted_thinking"}:
            self.blocks[index] = {"kind": "ignored", "ended": False}; self.saw_reasoning = True; return []
        if kind == "text":
            initial = raw.get("text", "")
            if not isinstance(initial, str): raise StreamError("protocol_error", retryable=False)
            self.content.append(TextContent(text=initial)); local = len(self.content)-1
            self.blocks[index] = {"kind": "text", "local": local, "ended": False}
            return [AssistantTextStartEvent(content_index=local, partial=self.message("pending"))]
        if kind == "tool_use":
            call_id, name, initial = raw.get("id", ""), raw.get("name", ""), raw.get("input", {})
            if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(initial, dict):
                raise StreamError("protocol_error", retryable=False)
            self.content.append(ToolCall(id=call_id, name=name, arguments=initial)); local = len(self.content)-1
            self.blocks[index] = {"kind": "tool", "local": local, "raw": "", "initial": initial,
                                  "valid": True, "ended": False, "end_sent": False}
            return [AssistantToolCallStartEvent(content_index=local, partial=self.message("pending"))]
        raise StreamError("unsupported_stream_event", retryable=False)

    def block_delta(self, data: dict[str, Any]) -> list[Any]:
        index, delta = self._index(data), data.get("delta") or {}
        if index not in self.blocks or self.blocks[index]["ended"] or not isinstance(delta, dict):
            raise StreamError("protocol_error", retryable=False)
        state, kind = self.blocks[index], delta.get("type")
        if state["kind"] == "ignored" and kind in {"thinking_delta", "signature_delta"}:
            self.saw_reasoning = True; return []
        if kind == "text_delta" and state["kind"] == "text":
            value = delta.get("text", "")
            if not isinstance(value, str): raise StreamError("protocol_error", retryable=False)
            block = self.content[state["local"]]; block.text += value
            return [AssistantTextDeltaEvent(content_index=state["local"], delta=value, partial=self.message("pending"))]
        if kind == "input_json_delta" and state["kind"] == "tool":
            value = delta.get("partial_json", "")
            if not isinstance(value, str): raise StreamError("protocol_error", retryable=False)
            if len((state["raw"] + value).encode("utf-8")) > self.limits.max_tool_args_bytes:
                raise StreamError("stream_limit", retryable=False)
            state["raw"] += value
            parsed = _strict_object(state["raw"].strip()) if state["raw"].strip() else None
            state["valid"] = parsed is not None
            if parsed is not None: self.content[state["local"]].arguments = parsed
            return [AssistantToolCallDeltaEvent(content_index=state["local"], delta=value, partial=self.message("pending"))]
        raise StreamError("unsupported_stream_event", retryable=False)

    def block_stop(self, data: dict[str, Any]) -> list[Any]:
        index = self._index(data)
        if index not in self.blocks or self.blocks[index]["ended"]:
            raise StreamError("protocol_error", retryable=False)
        state = self.blocks[index]; state["ended"] = True
        if state["kind"] == "ignored": return []
        block = self.content[state["local"]]
        if state["kind"] == "text":
            return [AssistantTextEndEvent(content_index=state["local"], content=block.text, partial=self.message("pending"))]
        if state["raw"].strip():
            parsed = _strict_object(state["raw"].strip()); state["valid"] = parsed is not None
            if parsed is not None: block.arguments = parsed
        else:
            state["valid"] = isinstance(state["initial"], dict)
        if state["valid"] and block.id and block.name:
            state["end_sent"] = True
            return [AssistantToolCallEndEvent(content_index=state["local"], tool_call=copy.deepcopy(block), partial=self.message("pending"))]
        return []

    def finalize(self) -> list[Any]:
        mapped = {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "toolUse", "max_tokens": "length",
                  "refusal": "error", "sensitive": "error"}.get(self.stop_raw)
        if mapped == "length": return [AssistantDoneEvent(reason="length", message=self.message("length"))]
        active = [s for s in self.blocks.values() if s["kind"] != "ignored"]
        tools = [s for s in active if s["kind"] == "tool"]
        if any(not s["ended"] for s in active): return [self.error_event("protocol_error")]
        if tools and any(not s["valid"] or not self.content[s["local"]].id or not self.content[s["local"]].name for s in tools):
            return [self.error_event("protocol_error")]
        if mapped == "toolUse" and not tools: return [self.error_event("protocol_error")]
        if mapped in {"stop", "toolUse"}:
            has_text = any(isinstance(b, TextContent) and b.text.strip() for b in self.content)
            if not has_text and not tools: return [self.error_event("reasoning_only" if self.saw_reasoning else "empty_response")]
            return [AssistantDoneEvent(reason=mapped, message=self.message(mapped))]
        return [self.error_event("refused" if mapped == "error" else "unsupported_stream_event")]

    def error_event(self, code: str):
        self.last_error_code = code
        reason = "aborted" if code == "canceled" else "error"
        message = self.message(reason).model_copy(update={"error_message": fixed_error_message(code)})
        return AssistantErrorEvent(reason=reason, error=message)
