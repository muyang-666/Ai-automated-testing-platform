"""One physical OpenAI-compatible streaming request for V2-P02.

Block allocation and event order follow Pi's ``ensureToolCallBlock`` at the
locked upstream commit. This adapter does not retry or execute tools.
"""
from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, AsyncIterator, Callable

import httpx

from app.agents.conversation.events import (AssistantDoneEvent, AssistantErrorEvent, AssistantMessageEvent,
    AssistantStartEvent, AssistantTextDeltaEvent, AssistantTextEndEvent, AssistantTextStartEvent,
    AssistantToolCallDeltaEvent, AssistantToolCallEndEvent, AssistantToolCallStartEvent)
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage
from app.agents.providers.streaming import (BoundedSSEDecoder, ProviderSnapshot, StreamContext, StreamControl,
    StreamError, StreamLimits, StreamRequest, await_controlled, effective_timeout, resolve_max_tokens,
    fixed_error_message, to_openai_messages_and_tools)

_DONE = "[DONE]"


class _SseDecoder(BoundedSSEDecoder):
    """Compatibility shim for existing focused tests; OpenAI uses data only."""
    def feed(self, chunk: bytes) -> list[str]:
        return [frame.data for frame in super().feed(chunk)]
    def finish(self) -> list[str]:
        return [frame.data for frame in super().finish()]


class OpenAIStreamAdapter:
    provider_type = "openai_compatible"
    def __init__(self, async_client_factory: Callable[[], httpx.AsyncClient] | None = None):
        self._factory = async_client_factory

    def _client(self) -> httpx.AsyncClient:
        client = self._factory() if self._factory is not None else httpx.AsyncClient()
        if not isinstance(client, httpx.AsyncClient):
            raise StreamError("configuration_error")
        return client

    async def stream(self, snapshot: ProviderSnapshot, request: StreamRequest, context: StreamContext,
                     control: StreamControl, limits: StreamLimits | None = None) -> AsyncIterator[AssistantMessageEvent]:
        limits = limits or StreamLimits()
        messages, tools = to_openai_messages_and_tools(request)
        timeout = effective_timeout(request, snapshot)
        payload: dict[str, Any] = {"model": snapshot.model_name, "messages": messages, "stream": True,
                                   "max_tokens": resolve_max_tokens(request, snapshot)}
        temperature = request.temperature if request.temperature is not None else snapshot.temperature
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools
        if request.request_usage:
            payload["stream_options"] = {"include_usage": True}
        url = snapshot.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        headers = {"Authorization": f"Bearer {snapshot.api_key}", "Content-Type": "application/json"}
        assembler = _OpenAIAssembler(snapshot, context, limits)
        client, response_cm, response, chunks = self._client(), None, None, None
        try:
            response_cm = client.stream("POST", url, headers=headers, json=payload, timeout=timeout)
            response = await await_controlled(response_cm.__aenter__(), control)
            control.current_request_id = _header_id(response.headers)
            if response.status_code >= 400:
                code = "retryable_http" if response.status_code == 429 or response.status_code >= 500 else "http_error"
                raise StreamError(code, request_id=control.current_request_id)
            yield assembler.start_event()
            decoder = _SseDecoder(limits)
            chunks = response.aiter_bytes()
            iterator = chunks.__aiter__()
            while not assembler.finished:
                try:
                    raw = await await_controlled(anext(iterator), control)
                except StopAsyncIteration:
                    for data in decoder.finish():
                        for event in assembler.process(data):
                            if event.type == "error":
                                control.set_failure(assembler.last_error_code or "stream_gateway_error")
                            yield event
                    break
                for data in decoder.feed(raw):
                    for event in assembler.process(data):
                        if event.type == "error":
                            control.set_failure(assembler.last_error_code or "stream_gateway_error")
                        yield event
                    if assembler.finished:
                        break
            if not assembler.finished:
                control.set_failure("stream_incomplete")
                yield assembler.error_event("stream_incomplete")
        except StreamError as exc:
            if exc.error_code in {"canceled", "deadline_exceeded"}:
                control.set_failure(exc.error_code)
                yield assembler.error_event(exc.error_code)
                return
            if not exc.retryable and exc.error_code not in {"http_error", "configuration_error", "unsupported_parameter"}:
                control.set_failure(exc.error_code)
                yield assembler.error_event(exc.error_code)
                return
            raise
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException as exc:
            raise StreamError("network_error", retryable=True, request_id=control.current_request_id) from exc
        except httpx.NetworkError as exc:
            raise StreamError("network_error", retryable=True, request_id=control.current_request_id) from exc
        except Exception as exc:
            raise StreamError("stream_gateway_error", retryable=False, request_id=control.current_request_id) from exc
        finally:
            if chunks is not None:
                await chunks.aclose()
            if response_cm is not None and response is not None:
                await response_cm.__aexit__(None, None, None)
            await client.aclose()


def _header_id(headers: Any) -> str | None:
    for name in ("x-request-id", "request-id"):
        value = headers.get(name)
        if isinstance(value, str) and 1 <= len(value) <= 200 and all(c.isalnum() or c in "-_.:" for c in value):
            return value
    return None


def _strict_object(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class _OpenAIAssembler:
    def __init__(self, snapshot: ProviderSnapshot, context: StreamContext, limits: StreamLimits):
        self.snapshot, self.context, self.limits = snapshot, context, limits
        self.content: list[Any] = []
        self.tools: dict[int, dict[str, Any]] = {}
        self.tool_order: list[int] = []
        self.text_index: int | None = None
        self.finish_reason: str | None = None
        self.usage_raw: dict[str, Any] = {}
        self.response_id: str | None = None
        self.finished = False
        self.saw_done = False
        self.saw_reasoning = False
        self.last_error_code: str | None = None

    def usage(self) -> Usage:
        raw, details = self.usage_raw, self.usage_raw.get("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        prompt = raw.get("prompt_tokens")
        uncached = prompt - cached if type(prompt) is int and type(cached) is int and prompt >= cached else prompt
        completion_details = raw.get("completion_tokens_details")
        reasoning = completion_details.get("reasoning_tokens") if isinstance(completion_details, dict) else None
        return Usage(input=uncached, output=raw.get("completion_tokens"), cache_read=cached, cache_write=None,
                     reasoning=reasoning, total_tokens=raw.get("total_tokens"), cost=None)

    def message(self, reason: str) -> AssistantMessage:
        return AssistantMessage(message_id=self.context.message_id, timestamp=self.context.timestamp, role="assistant",
            content=copy.deepcopy(self.content), api=self.snapshot.api, provider=self.snapshot.name,
            model=self.snapshot.model_name, usage=self.usage(), stop_reason=reason, response_id=self.response_id)

    def start_event(self):
        return AssistantStartEvent(partial=self.message("pending"))

    def process(self, data: str) -> list[Any]:
        if data == _DONE:
            self.saw_done, self.finished = True, True
            return self.finalize()
        try:
            obj = json.loads(data, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StreamError("protocol_error", retryable=False) from exc
        if not isinstance(obj, dict):
            raise StreamError("protocol_error", retryable=False)
        if isinstance(obj.get("id"), str):
            self.response_id = obj["id"]
        if obj.get("error") is not None:
            self.finished = True
            return [self.error_event("refused")]
        events: list[Any] = []
        choices = obj.get("choices", [])
        if not isinstance(choices, list):
            raise StreamError("protocol_error", retryable=False)
        for choice in choices:
            if not isinstance(choice, dict):
                raise StreamError("protocol_error", retryable=False)
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                raise StreamError("protocol_error", retryable=False)
            if choice.get("finish_reason") is not None:
                reason = choice["finish_reason"]
                if self.finish_reason is not None and reason != self.finish_reason:
                    raise StreamError("protocol_error", retryable=False)
                self.finish_reason = reason
            text = delta.get("content")
            if text is not None:
                if not isinstance(text, str):
                    raise StreamError("protocol_error", retryable=False)
                if text:
                    if self.text_index is None:
                        self.content.append(TextContent(text="")); self.text_index = len(self.content) - 1
                        events.append(AssistantTextStartEvent(content_index=self.text_index, partial=self.message("pending")))
                    block = self.content[self.text_index]; block.text += text
                    events.append(AssistantTextDeltaEvent(content_index=self.text_index, delta=text, partial=self.message("pending")))
            if delta.get("reasoning_content") or delta.get("reasoning"):
                self.saw_reasoning = True
            if delta.get("refusal"):
                self.finished = True; return [self.error_event("refused")]
            calls = delta.get("tool_calls") or []
            if not isinstance(calls, list):
                raise StreamError("protocol_error", retryable=False)
            for call in calls:
                events.extend(self.tool_delta(call))
        if isinstance(obj.get("usage"), dict):
            self.usage_raw = obj["usage"]
        return events

    def tool_delta(self, item: Any) -> list[Any]:
        if not isinstance(item, dict) or type(item.get("index")) is not int or item["index"] < 0:
            raise StreamError("protocol_error", retryable=False)
        provider_index = item["index"]
        events: list[Any] = []
        if provider_index not in self.tools:
            self.content.append(ToolCall(id="", name="", arguments={}))
            self.tools[provider_index] = {"content_index": len(self.content)-1, "id": "", "name": "", "raw": "", "valid": False}
            self.tool_order.append(provider_index)
            events.append(AssistantToolCallStartEvent(content_index=len(self.content)-1, partial=self.message("pending")))
        state = self.tools[provider_index]; block = self.content[state["content_index"]]
        call_id = item.get("id")
        if call_id is not None:
            if not isinstance(call_id, str) or (state["id"] and state["id"] != call_id):
                raise StreamError("protocol_error", retryable=False)
            if call_id: state["id"] = block.id = call_id
        function = item.get("function") or {}
        if not isinstance(function, dict):
            raise StreamError("protocol_error", retryable=False)
        name = function.get("name")
        if name is not None:
            if not isinstance(name, str) or (state["name"] and state["name"] != name):
                raise StreamError("protocol_error", retryable=False)
            if name: state["name"] = block.name = name
        fragment = function.get("arguments")
        if fragment is not None:
            if not isinstance(fragment, str):
                raise StreamError("protocol_error", retryable=False)
            if fragment:
                if len((state["raw"] + fragment).encode("utf-8")) > self.limits.max_tool_args_bytes:
                    raise StreamError("stream_limit", retryable=False)
                state["raw"] += fragment
                parsed = _strict_object(state["raw"].strip())
                state["valid"] = parsed is not None
                if parsed is not None: block.arguments = parsed
                events.append(AssistantToolCallDeltaEvent(content_index=state["content_index"], delta=fragment,
                                                            partial=self.message("pending")))
        return events

    def _tools_valid(self) -> bool:
        if not self.tool_order:
            return False
        for index in self.tool_order:
            state = self.tools[index]
            raw = state["raw"].strip()
            parsed = _strict_object(raw) if raw else None
            if not state["id"] or not state["name"] or parsed is None:
                return False
            state["valid"] = True
            self.content[state["content_index"]].arguments = parsed
        return True

    def finalize(self) -> list[Any]:
        events: list[Any] = []
        if self.text_index is not None:
            block = self.content[self.text_index]
            events.append(AssistantTextEndEvent(content_index=self.text_index, content=block.text, partial=self.message("pending")))
        if self.finish_reason == "length":
            events.append(AssistantDoneEvent(reason="length", message=self.message("length"))); return events
        if self.finish_reason in {"tool_calls", "stop"}:
            if self.tool_order and not self._tools_valid():
                return events + [self.error_event("protocol_error")]
            if self.finish_reason == "tool_calls" and not self.tool_order:
                return events + [self.error_event("protocol_error")]
            if self.tool_order:
                for index in self.tool_order:
                    state = self.tools[index]; block = self.content[state["content_index"]]
                    events.append(AssistantToolCallEndEvent(content_index=state["content_index"], tool_call=copy.deepcopy(block),
                                                             partial=self.message("pending")))
            has_text = any(isinstance(b, TextContent) and b.text.strip() for b in self.content)
            if not has_text and not self.tool_order:
                return events + [self.error_event("reasoning_only" if self.saw_reasoning else "empty_response")]
            reason = "toolUse" if self.finish_reason == "tool_calls" else "stop"
            events.append(AssistantDoneEvent(reason=reason, message=self.message(reason))); return events
        return events + [self.error_event("refused" if self.finish_reason == "content_filter" else "protocol_error")]

    def error_event(self, code: str):
        self.last_error_code = code
        stop = "aborted" if code == "canceled" else "error"
        message = self.message(stop).model_copy(update={"error_message": fixed_error_message(code)})
        return AssistantErrorEvent(reason=stop, error=message)
