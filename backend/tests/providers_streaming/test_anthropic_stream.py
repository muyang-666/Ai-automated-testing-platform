"""V2-P02：Anthropic 单次流测试（AsyncAnthropic + httpx2 Fake transport，零网络）。"""

import asyncio
import json

import httpx2

from anthropic import AsyncAnthropic

from app.agents.providers.anthropic_stream_adapter import AnthropicStreamAdapter
from app.agents.providers.streaming import (
    ProviderSnapshot,
    StreamContext,
    StreamControl,
    StreamLimits,
    StreamRequest,
)
from tests_streaming_kit import make_user

SNAP = ProviderSnapshot(provider_type="anthropic", name="anthropic", base_url="https://api.anthropic.com",
                        api_key="sk-synth", model_name="claude-x", timeout_seconds=5,
                        max_tokens=50, api="messages")
CTX = StreamContext(message_id="m1", timestamp=1)


def _sse(events):
    out = []
    for ev in events:
        out.append(f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n")
    return "".join(out).encode("utf-8")


def _text_stream(prefix="你好"):
    return _sse([
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                               "content": [], "model": "claude-x",
                                               "stop_reason": None, "stop_sequence": None,
                                               "usage": {"input_tokens": 5, "output_tokens": 1,
                                                         "cache_creation_input_tokens": 0,
                                                         "cache_read_input_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": prefix}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 2}},
        {"type": "message_stop"},
    ])


def _run(coro):
    return asyncio.run(coro)


def _collect(body):
    transport = _MemoryTransport(body)
    client = _httpx2_client(transport)

    def factory():
        return AsyncAnthropic(api_key="sk-synth", http_client=client, max_retries=0)

    adapter = AnthropicStreamAdapter(anthropic_factory=factory)
    request = StreamRequest(messages=[make_user(text="你好")], max_tokens=50)

    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        return [ev async for ev in adapter.stream(SNAP, request, CTX, ctrl,
                                                  StreamLimits(max_private_input_bytes=4 * 1024 * 1024))]
    return _run(go())


class _MemoryTransport(httpx2.AsyncBaseTransport):
    def __init__(self, body: bytes):
        self._body = body

    async def handle_async_request(self, request):
        return httpx2.Response(200, content=self._body, request=request)


def _httpx2_client(transport):
    return httpx2.AsyncClient(transport=transport)


def test_anthropic_text_stream_end_turn():
    events = _collect(_text_stream())
    types = [e.type for e in events]
    assert types[0] == "start"
    assert "text_delta" in types
    assert events[-1].type == "done"
    final = events[-1].message
    assert final.stop_reason == "stop"
    assert final.content[0].text == "你好"
    assert final.usage.output == 2
    assert final.usage.input == 5


def test_anthropic_ping_ignored_and_empty_not_success():
    # ping 忽略、空文本无工具不当作成功：end_turn + message_stop 后应明确 error
    body = _sse([
        {"type": "ping"},
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                               "content": [], "model": "claude-x", "stop_reason": None,
                                               "stop_sequence": None,
                                               "usage": {"input_tokens": 1, "output_tokens": 1,
                                                         "cache_creation_input_tokens": 0,
                                                         "cache_read_input_tokens": 0}}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ])
    events = _collect(body)
    assert events[-1].type == "error"


def test_anthropic_tool_use_with_partial_json():
    body = _sse([
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                               "content": [], "model": "claude-x", "stop_reason": None,
                                               "stop_sequence": None,
                                               "usage": {"input_tokens": 6, "output_tokens": 1,
                                                         "cache_creation_input_tokens": 0,
                                                         "cache_read_input_tokens": 0}}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "tool_use", "id": "c1", "name": "echo", "input": {}}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": "{\"value\": "}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": "\"hi\"}"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
         "usage": {"output_tokens": 3}},
        {"type": "message_stop"},
    ])
    events = _collect(body)
    types = [e.type for e in events]
    assert "toolcall_start" in types
    assert "toolcall_end" in types
    assert events[-1].type == "done" and events[-1].reason == "toolUse"
    tool = [c for c in events[-1].message.content if getattr(c, "type", "") == "toolCall"][0]
    assert tool.id == "c1"
    assert tool.arguments == {"value": "hi"}


def test_anthropic_invalid_tool_json_is_error_without_end():
    body = _sse([
        {"type": "message_start", "message": {"id": "msg_1", "usage": {"input_tokens": 1, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "tool_use", "id": "c1", "name": "echo", "input": {}}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": "{"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ])
    events = _collect(body)
    assert events[-1].type == "error"
    assert "toolcall_end" not in [event.type for event in events]


def test_anthropic_complete_tool_has_exactly_one_end_and_full_lifecycle():
    body = _sse([
        {"type": "message_start", "message": {"id": "msg_1", "usage": {"input_tokens": 1, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "tool_use", "id": "c1", "name": "echo", "input": {}}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ])
    events = _collect(body)
    types = [event.type for event in events]
    assert types == ["start", "toolcall_start", "toolcall_delta", "toolcall_end", "done"]
    assert events[-1].message.content[0].arguments == {}


def test_anthropic_unknown_raw_sse_event_fails_observably():
    body = _sse([{"type": "future_event", "payload": "secret-not-returned"}])
    events = _collect(body)
    assert events[-1].type == "error"


def test_anthropic_thinking_index_is_removed_from_public_indices():
    body = _sse([
        {"type": "message_start", "message": {"id": "msg_1", "usage": {"input_tokens": 1, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "hidden"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hidden2"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": "A"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "B"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
        {"type": "message_stop"},
    ])
    events = _collect(body)
    public = [event for event in events if hasattr(event, "content_index")]
    assert all(event.content_index == 0 for event in public)
    assert events[-1].message.content[0].text == "AB"
    assert "hidden" not in str([event.model_dump() for event in events])


def test_anthropic_missing_message_stop_is_incomplete_error():
    events = _collect(_sse([
        {"type": "message_start", "message": {"id": "msg_1", "usage": {"input_tokens": 1, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": "x"}},
        {"type": "content_block_stop", "index": 0},
    ]))
    assert events[-1].type == "error"
    assert events[-1].error.error_message == "流在完成信号前中断"
