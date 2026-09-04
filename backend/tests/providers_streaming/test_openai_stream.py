"""V2-P02：OpenAI-compatible 原始 SSE 流测试（Fake AsyncClient transport，零网络）。"""

import asyncio
import json

import httpx
import pytest

from app.agents.providers.openai_stream_adapter import OpenAIStreamAdapter, _SseDecoder
from app.agents.providers.streaming import (
    ProviderSnapshot,
    StreamContext,
    StreamControl,
    StreamLimits,
    StreamRequest,
)
from tests_streaming_kit import make_user

SNAP = ProviderSnapshot(provider_type="openai_compatible", name="p", base_url="https://x/api",
                        api_key="k", model_name="m", timeout_seconds=5, max_tokens=100, api="chat")
CTX = StreamContext(message_id="m1", timestamp=1)


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    async def handle_async_request(self, request):
        return httpx.Response(self.status, content=self.body, request=request)


def _run(coro):
    return asyncio.run(coro)


def _client(body: bytes) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=FakeTransport(body))


def _request(text="你好"):
    return StreamRequest(messages=[make_user(text=text)], max_tokens=100)


def _collect(body: bytes, **kw):
    ad = OpenAIStreamAdapter(async_client_factory=lambda: _client(body))
    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        return [ev async for ev in ad.stream(SNAP, kw.pop("request", _request()), CTX, ctrl,
                                             StreamLimits(max_private_input_bytes=4 * 1024 * 1024))]
    return _run(go())


def _sse(*data_lines):
    out = []
    for line in data_lines:
        out.append(f"data: {line}\r\n\r\n")
    return "".join(out).encode()


def test_plain_text_delta_and_done_with_usage():
    body = _sse(
        json.dumps({"choices": [{"delta": {"role": "assistant", "content": "你好"}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}),
        "[DONE]",
    )
    events = _collect(body)
    types = [e.type for e in events]
    assert types == ["start", "text_start", "text_delta", "text_end", "done"]
    final = events[-1].message
    assert final.stop_reason == "stop"
    assert final.content[0].text == "你好"
    assert final.usage.output == 2
    assert final.usage.total_tokens == 6


def test_usage_block_with_empty_choices_not_dropped_before_done():
    body = _sse(
        json.dumps({"choices": [{"delta": {"content": "x"}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}),
        "[DONE]",
    )
    final = _collect(body)[-1].message
    assert final.usage.output == 3
    assert final.content[0].text == "x"


def test_tool_calls_interleaved_deltas_and_done_tool_use():
    body = _sse(
        json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
                                                           "function": {"name": "echo", "arguments": ""}}]},
                                 "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0,
                                                           "function": {"arguments": "{\"value\": \"hi\"}"}}]},
                                 "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
        "[DONE]",
    )
    events = _collect(body)
    types = [e.type for e in events]
    assert "toolcall_start" in types
    assert "toolcall_end" in types
    assert events[-1].type == "done" and events[-1].reason == "toolUse"
    tool = [c for c in events[-1].message.content if getattr(c, "type", "") == "toolCall"][0]
    assert tool.id == "c1"
    assert tool.arguments == {"value": "hi"}


def test_incomplete_stream_without_done_is_error():
    body = _sse(json.dumps({"choices": [{"delta": {"content": "部分"}, "finish_reason": None}]}))
    events = _collect(body)
    assert events[-1].type == "error"


def test_length_finish_marks_length_not_executable():
    body = _sse(
        json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
                                                           "function": {"name": "echo", "arguments": "{\"value\": \"hi"}}]},
                                 "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "length"}]}),
        "[DONE]",
    )
    events = _collect(body)
    assert events[-1].type == "done"
    assert events[-1].reason == "length"
    # 未发布 toolcall_end（参数未完整）
    assert "toolcall_end" not in [e.type for e in events]


def test_frame_limit_is_checked_before_full_line():
    # 单条 data 行超过帧上限 → error，且不以成功截断
    line = "x" * (2 * 1024 * 1024)
    body = _sse(json.dumps({"choices": [{"delta": {"content": line}}]}))
    events = _collect(body, request=_request())
    assert events[-1].type == "error"


def test_reject_non_json_or_object_protocol():
    body = _sse("not json")
    events = _collect(body)
    assert events[-1].type == "error"


def test_error_status_maps_to_fixed_error():
    ad = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(
        transport=FakeTransport(b"", status=401)))
    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        with pytest.raises(Exception):
            async for _ in ad.stream(SNAP, _request(), CTX, ctrl):
                pass
    _run(go())


def test_authorization_header_uses_explicit_snapshot_key():
    seen = []
    body = _sse(
        json.dumps({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}),
        "[DONE]",
    )

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, content=body, request=request)

    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        return [event async for event in adapter.stream(SNAP, _request(), CTX, ctrl)]
    events = _run(go())
    assert events[-1].type == "done"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert "Bearer k" not in repr(SNAP)


def test_empty_object_is_valid_tool_arguments():
    body = _sse(
        json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
            "function": {"name": "no_args", "arguments": "{}"}}]}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}), "[DONE]",
    )
    events = _collect(body)
    assert events[-1].type == "done"
    assert events[-1].message.content[0].arguments == {}
    assert [e.type for e in events].count("toolcall_end") == 1


def test_one_valid_and_one_invalid_tool_makes_whole_message_error():
    body = _sse(
        json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "function": {"name": "a", "arguments": "{\"v\":1}"}},
            {"index": 1, "id": "c2", "function": {"name": "b", "arguments": "{"}},
        ]}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}), "[DONE]",
    )
    events = _collect(body)
    assert events[-1].type == "error"
    assert "toolcall_end" not in [e.type for e in events]


def test_sse_multiline_joins_with_newline_and_bounds_whole_frame():
    decoder = _SseDecoder(StreamLimits(max_frame_bytes=64, max_private_input_bytes=100))
    assert decoder.feed(b"data: A\ndata: B\n\n") == ["A\nB"]
    small = _SseDecoder(StreamLimits(max_frame_bytes=16, max_private_input_bytes=100))
    with pytest.raises(Exception):
        small.feed(b"data: 1234567890\ndata: 1234567890\n\n")


def test_two_tool_calls_really_interleave_and_keep_indices():
    body = _sse(
        json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "function": {"name": "a", "arguments": "{\"x\":"}},
            {"index": 1, "id": "c2", "function": {"name": "b", "arguments": "{\"y\":"}},
        ]}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": 1, "function": {"arguments": "2}"}},
            {"index": 0, "function": {"arguments": "1}"}},
        ]}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}), "[DONE]",
    )
    events = _collect(body)
    tools = [x for x in events[-1].message.content if x.type == "toolCall"]
    assert [(x.id, x.arguments) for x in tools] == [("c1", {"x": 1}), ("c2", {"y": 2})]
    assert [e.type for e in events].count("toolcall_start") == 2
    assert [e.type for e in events].count("toolcall_end") == 2


def test_early_adapter_close_closes_real_async_client():
    body = _sse(json.dumps({"choices": [{"delta": {"content": "later"}, "finish_reason": None}]}))
    client = _client(body)
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: client)
    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        events = adapter.stream(SNAP, _request(), CTX, ctrl)
        assert (await anext(events)).type == "start"
        await events.aclose()
    _run(go())
    assert client.is_closed


def test_multibyte_tool_arguments_use_utf8_byte_limit():
    body = _sse(json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
        "function": {"name": "echo", "arguments": "{\"v\":\"你\"}"}}]}, "finish_reason": None}]}, ensure_ascii=False))
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: _client(body))
    async def go():
        ctrl = StreamControl(cancel_event=asyncio.Event())
        return [event async for event in adapter.stream(
            SNAP, _request(), CTX, ctrl,
            StreamLimits(max_frame_bytes=1000, max_tool_args_bytes=9, max_private_input_bytes=4000))]
    events = _run(go())
    assert events[-1].type == "error"
    assert events[-1].error.error_message == "流式解析超出资源限额"


def test_cached_prompt_tokens_are_not_double_counted_as_uncached_input():
    body = _sse(
        json.dumps({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2,
            "total_tokens": 12, "prompt_tokens_details": {"cached_tokens": 4}}}), "[DONE]",
    )
    usage = _collect(body)[-1].message.usage
    assert (usage.input, usage.cache_read, usage.total_tokens) == (6, 4, 12)
