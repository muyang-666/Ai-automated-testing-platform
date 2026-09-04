"""Shared contracts, bounded SSE decoding and request conversion for V2-P02.

The message/event shape follows Pi at commit f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6.
Strict terminal JSON, explicit unknown usage, deadlines and resource bounds are
TestMind adaptations. Pi is MIT licensed (Copyright (c) 2025 Mario Zechner).
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Literal, TypeVar
from urllib.parse import urlsplit, urlunsplit

from app.agents.conversation.messages import AssistantMessage, Message, TextContent, ToolCall, ToolResultMessage, Usage, UserMessage
from app.schemas.llm.llm_gateway import LLMToolSpec

_FIXED = {
    "unsupported_parameter": "当前供应商或请求不支持该参数", "invalid_history": "消息历史无法安全转换为供应商请求",
    "mismatched_tool_result": "工具结果与历史工具请求不匹配", "invalid_tool_result": "工具结果载荷非法",
    "stream_limit": "流式解析超出资源限额", "protocol_error": "流式协议数据非法",
    "unsupported_stream_event": "遇到暂不支持的流式事件", "stream_incomplete": "流在完成信号前中断",
    "empty_response": "模型返回内容为空", "reasoning_only": "模型仅返回被忽略的推理内容",
    "refused": "模型拒绝回答", "canceled": "请求已取消", "budget_exhausted": "物理模型尝试预算已耗尽",
    "deadline_exceeded": "请求超过总截止时间", "network_error": "网络请求失败",
    "http_error": "供应商返回不可重试的 HTTP 错误", "retryable_http": "供应商返回可重试的 HTTP 错误",
    "configuration_error": "供应商配置无效", "stream_gateway_error": "流式调用内部失败",
}


def _safe_id(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        return None
    return value if all(c.isalnum() or c in "-_.:" for c in value) else None


class StreamError(Exception):
    """Stable, non-sensitive failure crossing the Adapter/Gateway boundary."""
    def __init__(self, error_code: str, *, retryable: bool | None = None,
                 request_id: str | None = None, response_id: str | None = None,
                 usage: Usage | None = None):
        self.error_code = error_code if error_code in _FIXED else "stream_gateway_error"
        self.retryable = self.error_code in {"network_error", "retryable_http"} if retryable is None else retryable
        self.request_id, self.response_id, self.usage = _safe_id(request_id), _safe_id(response_id), usage
        super().__init__(_FIXED[self.error_code])


def fixed_error_message(code: str) -> str:
    return _FIXED.get(code, _FIXED["stream_gateway_error"])


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.username is None:
            return value
        host = parsed.hostname or ""
        if parsed.port is not None:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except (TypeError, ValueError):
        return "<invalid-url>"


@dataclass(frozen=True)
class ProviderSnapshot:
    provider_type: str
    name: str
    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: float = 60.0
    max_tokens: int | None = None
    temperature: float | None = None
    api: str = "chat"

    def __repr__(self) -> str:
        return (f"ProviderSnapshot(provider_type={self.provider_type!r}, name={self.name!r}, "
                f"model_name={self.model_name!r}, base_url={_safe_url(self.base_url)!r}, api_key=<redacted>, "
                f"timeout_seconds={self.timeout_seconds!r}, max_tokens={self.max_tokens!r}, temperature={self.temperature!r})")

    def safe_dict(self) -> dict[str, Any]:
        return {"provider_type": self.provider_type, "name": self.name, "model_name": self.model_name,
                "base_url": _safe_url(self.base_url), "timeout_seconds": self.timeout_seconds,
                "max_tokens": self.max_tokens, "temperature": self.temperature}


@dataclass(frozen=True)
class StreamRequest:
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    tools: list[LLMToolSpec] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    request_usage: bool = True


@dataclass(frozen=True)
class StreamContext:
    message_id: str
    timestamp: int


@dataclass
class AttemptBudget:
    limit: int = 3
    used: int = 0
    def try_acquire(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


@dataclass
class AttemptRecord:
    attempt: int
    status: Literal["succeeded", "failed", "cancelled", "consumer_closed"]
    duration_ms: int
    request_id: str | None = None
    response_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    error_code: str | None = None
    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class StreamControl:
    cancel_event: asyncio.Event
    deadline: float | None = None
    budget: AttemptBudget | None = None
    consumer_closed: bool = False
    error_code: str | None = None
    attempt_records: list[AttemptRecord] = field(default_factory=list)
    current_request_id: str | None = None
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()
    def set_failure(self, code: str) -> None:
        self.error_code = code
    def clear_attempt_state(self) -> None:
        self.error_code = None
        self.current_request_id = None


@dataclass(frozen=True)
class StreamLimits:
    max_frame_bytes: int = 1024 * 1024
    max_tool_args_bytes: int = 1024 * 1024
    max_private_input_bytes: int = 8 * 1024 * 1024


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def effective_timeout(request: StreamRequest, snapshot: ProviderSnapshot) -> float:
    value = request.timeout_seconds if request.timeout_seconds is not None else snapshot.timeout_seconds
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise StreamError("configuration_error")
    return float(value)


def resolve_max_tokens(request: StreamRequest, snapshot: ProviderSnapshot) -> int:
    value = request.max_tokens if request.max_tokens is not None else snapshot.max_tokens
    if not _positive_int(value):
        raise StreamError("configuration_error")
    return value


def validate_stream_inputs(snapshot: ProviderSnapshot, request: StreamRequest, context: StreamContext,
                           control: StreamControl, limits: StreamLimits) -> float:
    required = (snapshot.provider_type, snapshot.name, snapshot.base_url, snapshot.api_key, snapshot.model_name, context.message_id)
    if not all(isinstance(v, str) and v for v in required) or type(context.timestamp) is not int or context.timestamp < 0:
        raise StreamError("configuration_error")
    if not all(_positive_int(v) for v in (limits.max_frame_bytes, limits.max_tool_args_bytes, limits.max_private_input_bytes)):
        raise StreamError("configuration_error")
    if not isinstance(request.system_prompt, str) or not isinstance(request.messages, list) or not isinstance(request.tools, list):
        raise StreamError("configuration_error")
    if type(request.request_usage) is not bool:
        raise StreamError("configuration_error")
    for temperature in (request.temperature, snapshot.temperature):
        if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
                                        or not math.isfinite(float(temperature))):
            raise StreamError("configuration_error")
    if control.deadline is not None and (isinstance(control.deadline, bool)
        or not isinstance(control.deadline, (int, float)) or not math.isfinite(float(control.deadline))):
        raise StreamError("configuration_error")
    budget = control.budget
    if budget is not None and (type(budget.limit) is not int or type(budget.used) is not int
                               or budget.limit < 0 or budget.used < 0 or budget.used > budget.limit):
        raise StreamError("configuration_error")
    resolve_max_tokens(request, snapshot)
    return effective_timeout(request, snapshot)


@dataclass(frozen=True)
class SSEFrame:
    event: str | None
    data: str


class BoundedSSEDecoder:
    """Incremental decoder that bounds a whole SSE frame and the whole stream."""
    def __init__(self, limits: StreamLimits):
        self._limits, self._line = limits, bytearray()
        self._frame_bytes, self._total = 0, 0
        self._data: list[str] = []
        self._event: str | None = None

    def feed(self, chunk: bytes) -> list[SSEFrame]:
        if not isinstance(chunk, bytes):
            raise StreamError("protocol_error")
        self._total += len(chunk)
        if self._total > self._limits.max_private_input_bytes:
            raise StreamError("stream_limit")
        self._line.extend(chunk)
        out: list[SSEFrame] = []
        while True:
            nl = self._line.find(b"\n")
            if nl < 0:
                if self._frame_bytes + len(self._line) > self._limits.max_frame_bytes:
                    raise StreamError("stream_limit")
                break
            raw = bytes(self._line[:nl]); del self._line[:nl + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            self._frame_bytes += len(raw) + 1
            if self._frame_bytes > self._limits.max_frame_bytes:
                raise StreamError("stream_limit")
            try:
                line = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise StreamError("protocol_error") from exc
            if not line:
                if self._data:
                    out.append(SSEFrame(self._event, "\n".join(self._data)))
                self._data, self._event, self._frame_bytes = [], None, 0
            elif line.startswith(":"):
                continue
            elif line.startswith("data:"):
                value = line[5:]; self._data.append(value[1:] if value.startswith(" ") else value)
            elif line.startswith("event:"):
                value = line[6:]; self._event = value[1:] if value.startswith(" ") else value
        return out

    def finish(self) -> list[SSEFrame]:
        if self._line:
            self._frame_bytes += len(self._line)
            if self._frame_bytes > self._limits.max_frame_bytes:
                raise StreamError("stream_limit")
            try:
                line = bytes(self._line).rstrip(b"\r").decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise StreamError("protocol_error") from exc
            self._line.clear()
            if line.startswith("data:"):
                value = line[5:]; self._data.append(value[1:] if value.startswith(" ") else value)
            elif line.startswith("event:"):
                value = line[6:]; self._event = value[1:] if value.startswith(" ") else value
        if not self._data:
            return []
        result = [SSEFrame(self._event, "\n".join(self._data))]
        self._data, self._event, self._frame_bytes = [], None, 0
        return result


T = TypeVar("T")
async def await_controlled(awaitable: Awaitable[T], control: StreamControl) -> T:
    """Await an operation while observing cancellation and one total deadline."""
    if control.cancelled():
        raise StreamError("canceled", retryable=False)
    remaining = None if control.deadline is None else control.deadline - time.monotonic()
    if remaining is not None and remaining <= 0:
        raise StreamError("deadline_exceeded", retryable=False)
    operation = asyncio.ensure_future(awaitable)
    cancel_wait = asyncio.create_task(control.cancel_event.wait())
    try:
        done, _ = await asyncio.wait({operation, cancel_wait}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        if operation in done:
            cancel_wait.cancel()
            return operation.result()
        operation.cancel(); await asyncio.gather(operation, return_exceptions=True)
        raise StreamError("canceled" if control.cancelled() else "deadline_exceeded", retryable=False)
    except asyncio.CancelledError:
        operation.cancel(); await asyncio.gather(operation, return_exceptions=True)
        raise
    finally:
        cancel_wait.cancel(); await asyncio.gather(cancel_wait, return_exceptions=True)


def _text(content: str | list[TextContent]) -> str:
    return content if isinstance(content, str) else "".join(x.text for x in content)


def _checked_messages(messages: list[Message]):
    pending: dict[str, str] = {}
    for message in messages:
        if isinstance(message, AssistantMessage):
            if pending:
                raise StreamError("mismatched_tool_result")
            ids: set[str] = set()
            for call in (b for b in message.content if isinstance(b, ToolCall)):
                if not call.id or not call.name or call.id in ids:
                    raise StreamError("invalid_history")
                ids.add(call.id); pending[call.id] = call.name
        elif isinstance(message, ToolResultMessage):
            if message.tool_call_id not in pending or message.tool_name != pending[message.tool_call_id]:
                raise StreamError("mismatched_tool_result")
            pending.pop(message.tool_call_id)
        elif pending:
            raise StreamError("mismatched_tool_result")
        yield message
    if pending:
        raise StreamError("mismatched_tool_result")


def to_openai_messages_and_tools(request: StreamRequest):
    messages: list[dict[str, Any]] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    try:
        for message in _checked_messages(request.messages):
            if isinstance(message, UserMessage):
                messages.append({"role": "user", "content": _text(message.content)})
            elif isinstance(message, AssistantMessage):
                text = "".join(b.text for b in message.content if isinstance(b, TextContent))
                calls = [b for b in message.content if isinstance(b, ToolCall)]
                item: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    item["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name,
                        "arguments": json.dumps(c.arguments, ensure_ascii=False, separators=(",", ":"), allow_nan=False)}} for c in calls]
                messages.append(item)
            else:
                messages.append({"role": "tool", "tool_call_id": message.tool_call_id,
                                 "content": "".join(x.text for x in message.content)})
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                  "parameters": t.input_schema}} for t in request.tools]
    except StreamError:
        raise
    except Exception as exc:
        raise StreamError("invalid_history") from exc
    try:
        json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StreamError("invalid_history") from exc
    return messages, tools


def to_anthropic_system_messages_and_tools(request: StreamRequest):
    messages: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    def flush() -> None:
        if results:
            messages.append({"role": "user", "content": list(results)}); results.clear()
    try:
        for message in _checked_messages(request.messages):
            if isinstance(message, ToolResultMessage):
                results.append({"type": "tool_result", "tool_use_id": message.tool_call_id,
                    "content": ([{"type": "text", "text": x.text} for x in message.content] or ""),
                    "is_error": message.is_error})
                continue
            flush()
            if isinstance(message, UserMessage):
                messages.append({"role": "user", "content": [{"type": "text", "text": _text(message.content)}]})
            else:
                blocks = [{"type": "text", "text": b.text} if isinstance(b, TextContent) else
                          {"type": "tool_use", "id": b.id, "name": b.name, "input": b.arguments}
                          for b in message.content]
                messages.append({"role": "assistant", "content": blocks})
        flush()
        tools = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in request.tools]
    except StreamError:
        raise
    except Exception as exc:
        raise StreamError("invalid_history") from exc
    try:
        json.dumps({"system": request.system_prompt or None, "messages": messages, "tools": tools},
                   ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StreamError("invalid_history") from exc
    return request.system_prompt or None, messages, tools
