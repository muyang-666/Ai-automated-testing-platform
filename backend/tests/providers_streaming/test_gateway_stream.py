"""V2-P02：流式 Gateway 重试/预算/预检/取消测试（Fake 适配器，零网络）。"""

import asyncio
import time

import httpx
import pytest

from app.agents.conversation.events import AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent
from app.agents.providers.openai_stream_adapter import OpenAIStreamAdapter
from app.agents.providers.base import Capability, ProviderCapabilities
from app.agents.providers.streaming import (
    AttemptBudget,
    ProviderSnapshot,
    StreamContext,
    StreamControl,
    StreamError,
    StreamRequest,
)
from app.services.llm.llm_stream_gateway import LLMStreamGateway
from app.schemas.llm.llm_gateway import LLMToolSpec
from tests_streaming_kit import make_assistant, make_usage, make_user


class CountingFakeAdapter:
    def __init__(self, fail_first: bool = True, error_code: str = "retryable_http"):
        self.attempts = 0
        self.fail_first = fail_first
        self.error_code = error_code

    async def stream(self, snapshot, request, context, control, limits=None):
        self.attempts += 1
        if self.fail_first and self.attempts == 1:
            raise StreamError(self.error_code)
        yield AssistantDoneEvent(reason="stop", message=make_assistant(content=[], stop_reason="stop"))


class AlwaysFailAdapter(CountingFakeAdapter):
    async def stream(self, snapshot, request, context, control, limits=None):
        self.attempts += 1
        raise StreamError("retryable_http")
        yield  # pragma: no cover —— 保持 async generator 语义


SNAP = ProviderSnapshot(provider_type="openai_compatible", name="p", base_url="u", api_key="k",
                        model_name="m", max_tokens=10, api="chat")
CTX = StreamContext(message_id="m", timestamp=1)
REQ = StreamRequest(messages=[make_user(text="hi")], max_tokens=10)


def _run(coro):
    return asyncio.run(coro)


def _gateway(adapter, max_retries=1, **kw):
    return LLMStreamGateway(max_retries=max_retries, retry_delay_seconds=0.0,
                            openai_stream_factory=adapter, capability_overrides=kw.get("overrides"))


def _collect(gw, *, control=None, budget=None):
    async def go():
        out = []
        async for ev in gw.stream(SNAP, REQ, CTX, control=control, budget=budget):
            out.append(ev)
        return out
    return _run(go())


def test_success_single_attempt_passthrough():
    adapter = CountingFakeAdapter(fail_first=False)
    events = _collect(_gateway(adapter))
    assert adapter.attempts == 1
    assert events[-1].type == "done"


def test_retry_after_transient_error_then_success():
    adapter = CountingFakeAdapter(fail_first=True)
    events = _collect(_gateway(adapter, max_retries=2))
    assert adapter.attempts == 2
    assert events[-1].type == "done"


def test_budget_limit_blocks_second_attempt_and_emits_error():
    adapter = AlwaysFailAdapter()
    budget = AttemptBudget(limit=1)
    events = _collect(_gateway(adapter, max_retries=3), budget=budget)
    assert adapter.attempts == 1  # 第二次未发起（预算耗尽）
    assert events[-1].type == "error"


def test_preflight_tools_unsupported_is_zero_request():
    adapter = CountingFakeAdapter(fail_first=False)
    caps = ProviderCapabilities(tools=Capability.UNSUPPORTED, structured_output=Capability.UNKNOWN,
                                streaming=Capability.UNKNOWN)
    gw = LLMStreamGateway(openai_stream_factory=adapter,
                          capability_overrides={("openai_compatible", "*"): caps})
    from app.agents.providers.streaming import StreamError as SE

    async def go():
        with pytest.raises(SE) as exc:
            async for _ in gw.stream(SNAP, StreamRequest(messages=[make_user()],
                                     tools=[LLMToolSpec(name="echo", input_schema={"type": "object"})], max_tokens=10),
                                     CTX):
                pass
        assert exc.value.error_code == "unsupported_parameter"
    _run(go())
    assert adapter.attempts == 0


def test_cancel_before_start_is_zero_request():
    adapter = CountingFakeAdapter(fail_first=False)
    ctrl = StreamControl(cancel_event=asyncio.Event())
    ctrl.cancel_event.set()
    events = _collect(_gateway(adapter), control=ctrl)
    assert adapter.attempts == 0
    assert events[-1].type == "error"
    assert events[-1].reason == "aborted"


def test_content_already_emitted_is_not_replayed():
    class PartialThenFail(CountingFakeAdapter):
        async def stream(self, snapshot, request, context, control, limits=None):
            self.attempts += 1
            from app.agents.conversation.events import AssistantTextDeltaEvent
            from app.agents.conversation.messages import TextContent
            if self.attempts == 1:
                msg = make_assistant(content=[TextContent(text="部分")], stop_reason="pending")
                yield AssistantTextDeltaEvent(content_index=0, delta="部分", partial=msg)
                raise StreamError("retryable_http")
            yield AssistantDoneEvent(reason="stop", message=make_assistant(content=[], stop_reason="stop"))

    adapter = PartialThenFail()
    events = _collect(_gateway(adapter, max_retries=2))
    assert adapter.attempts == 1  # 已发出内容不透明重放
    assert events[-1].type == "error"


def test_retry_suppresses_duplicate_logical_start_and_records_each_attempt():
    class StartThenFail(CountingFakeAdapter):
        async def stream(self, snapshot, request, context, control, limits=None):
            self.attempts += 1
            yield AssistantStartEvent(partial=make_assistant(message_id="m", content=[], stop_reason="pending"))
            if self.attempts == 1:
                raise StreamError("network_error")
            yield AssistantDoneEvent(reason="stop", message=make_assistant(message_id="m", content=[], stop_reason="stop"))

    adapter = StartThenFail()
    control = StreamControl(cancel_event=asyncio.Event())
    events = _collect(_gateway(adapter, max_retries=2), control=control)
    assert [event.type for event in events].count("start") == 1
    assert events[-1].type == "done"
    assert [record.status for record in control.attempt_records] == ["failed", "succeeded"]
    assert control.error_code is None


def test_prefilled_shared_budget_does_not_replace_local_retry_count():
    adapter = CountingFakeAdapter(fail_first=True)
    budget = AttemptBudget(limit=10, used=5)
    control = StreamControl(cancel_event=asyncio.Event(), budget=budget)
    events = _collect(_gateway(adapter, max_retries=2), control=control)
    assert adapter.attempts == 2
    assert budget.used == 7
    assert events[-1].type == "done"


def test_real_httpx_connect_error_is_retried_before_output():
    requests = 0
    local_snap = ProviderSnapshot(provider_type="openai_compatible", name="p", base_url="https://x",
                                  api_key="k", model_name="m", max_tokens=10)
    body = (b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n')
    async def handler(request):
        nonlocal requests
        requests += 1
        if requests == 1:
            raise httpx.ConnectError("synthetic", request=request)
        return httpx.Response(200, content=body, request=request)
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    control = StreamControl(cancel_event=asyncio.Event())
    async def collect():
        return [event async for event in _gateway(adapter, max_retries=2).stream(
            local_snap, REQ, CTX, control=control)]
    events = _run(collect())
    assert requests == 2
    assert events[-1].type == "done"
    assert [record.error_code for record in control.attempt_records] == ["network_error", None]


def test_closing_outer_generator_closes_inner_and_records_consumer_close():
    class CloseAware:
        def __init__(self): self.closed = False
        async def stream(self, snapshot, request, context, control, limits=None):
            try:
                yield AssistantStartEvent(partial=make_assistant(message_id="m", content=[], stop_reason="pending"))
                await asyncio.Event().wait()
            finally:
                self.closed = True
    adapter, control = CloseAware(), StreamControl(cancel_event=asyncio.Event())
    async def go():
        stream = _gateway(adapter).stream(SNAP, REQ, CTX, control=control)
        assert (await anext(stream)).type == "start"
        await stream.aclose()
    _run(go())
    assert adapter.closed is True
    assert control.consumer_closed is True
    assert control.attempt_records[-1].status == "consumer_closed"


def test_cancel_interrupts_waiting_for_response_headers():
    entered = asyncio.Event()
    release = asyncio.Event()
    requests = 0
    async def handler(request):
        nonlocal requests
        requests += 1
        entered.set()
        await release.wait()
        return httpx.Response(200, content=b"", request=request)
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        task = asyncio.create_task(_collect_async(_gateway(adapter), control))
        await asyncio.wait_for(entered.wait(), 1)
        control.cancel_event.set()
        events = await asyncio.wait_for(task, 1)
        release.set()
        return events
    events = _run(go())
    assert requests == 1
    assert events[-1].type == "error" and events[-1].reason == "aborted"
    assert control.error_code == "canceled"
    assert control.attempt_records[-1].status == "cancelled"


async def _collect_async(gateway, control):
    return [event async for event in gateway.stream(SNAP, REQ, CTX, control=control)]


def test_existing_llm_gateway_exposes_managed_stream_context():
    from app.services.llm.llm_gateway import LLMGateway
    adapter = CountingFakeAdapter(fail_first=False)
    gateway = LLMGateway(max_retries=0, stream_adapters={"openai_compatible": adapter})
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        async with gateway.stream(SNAP, REQ, context=CTX, control=control) as events:
            return [event async for event in events]
    events = _run(go())
    assert events[-1].type == "done"


@pytest.mark.parametrize("status,code", [(402, "insufficient_balance"), (401, "provider_auth_error"),
                                       (403, "provider_auth_error"), (400, "provider_request_error")])
def test_provider_account_errors_are_specific_and_not_retried(status, code):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "synthetic-private-marker"}})
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    async def go():
        control = StreamControl(cancel_event=asyncio.Event())
        snapshot = ProviderSnapshot("openai_compatible", "p", "https://example.invalid", "synthetic-key", "m", max_tokens=10)
        events = [event async for event in _gateway(adapter, max_retries=2).stream(snapshot, REQ, CTX, control=control)]
        assert events[-1].type == "error"
        assert control.error_code == code
        assert len(control.attempt_records) == 1
        assert "synthetic-private-marker" not in events[-1].error.error_message
        if status == 402:
            assert "余额不足" in events[-1].error.error_message
    _run(go())
    assert len(calls) == 1


def test_deadline_interrupts_headers_and_records_distinct_code():
    entered = asyncio.Event()
    async def handler(request):
        entered.set()
        await asyncio.Event().wait()
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    control = StreamControl(cancel_event=asyncio.Event(), deadline=time.monotonic() + 0.03)
    events = _collect(_gateway(adapter), control=control)
    assert entered.is_set()
    assert events[-1].type == "error"
    assert control.error_code == "deadline_exceeded"
    assert control.attempt_records[-1].error_code == "deadline_exceeded"


def test_outer_task_cancel_is_rethrown_and_closes_request():
    entered, closed = asyncio.Event(), asyncio.Event()
    class BlockingAdapter:
        async def stream(self, snapshot, request, context, control, limits=None):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield
            finally:
                closed.set()
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        task = asyncio.create_task(_collect_async(_gateway(BlockingAdapter()), control))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(closed.wait(), 1)
    _run(go())
    assert control.attempt_records[-1].status == "cancelled"


def test_preflight_invalid_max_tokens_is_zero_attempts():
    adapter = CountingFakeAdapter(fail_first=False)
    control = StreamControl(cancel_event=asyncio.Event())
    bad = StreamRequest(messages=[make_user()], max_tokens=True)
    async def go():
        with pytest.raises(StreamError) as exc:
            async for _ in _gateway(adapter).stream(SNAP, bad, CTX, control=control):
                pass
        assert exc.value.error_code == "configuration_error"
    _run(go())
    assert adapter.attempts == 0 and control.attempt_records == []


def test_two_concurrent_streams_keep_context_and_usage_isolated():
    class ByContext:
        async def stream(self, snapshot, request, context, control, limits=None):
            await asyncio.sleep(0)
            yield AssistantDoneEvent(reason="stop", message=make_assistant(
                message_id=context.message_id, content=[], stop_reason="stop",
                usage=make_usage(input=context.timestamp, output=1, total_tokens=None)))
    gateway = _gateway(ByContext(), max_retries=0)
    async def one(message_id, timestamp):
        control = StreamControl(cancel_event=asyncio.Event())
        context = StreamContext(message_id=message_id, timestamp=timestamp)
        events = [event async for event in gateway.stream(SNAP, REQ, context, control=control)]
        return events[-1].message, control
    async def go():
        return await asyncio.gather(one("m1", 1), one("m2", 2))
    first, second = _run(go())
    assert (first[0].message_id, first[0].usage.input) == ("m1", 1)
    assert (second[0].message_id, second[0].usage.input) == ("m2", 2)
    assert first[1].attempt_records is not second[1].attempt_records


def test_sensitive_transport_error_is_not_returned():
    marker = "SYNTHETIC-SECRET-XYZ"
    async def handler(request):
        raise httpx.ConnectError(marker, request=request)
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    control = StreamControl(cancel_event=asyncio.Event())
    events = _collect(_gateway(adapter, max_retries=0), control=control)
    exported = str(events[-1].model_dump()) + str([record.as_dict() for record in control.attempt_records])
    assert marker not in exported
    assert control.error_code == "network_error"


def test_real_429_retries_but_real_400_does_not():
    async def exercise(first_status):
        requests = 0
        body = (b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
                b'data: [DONE]\n\n')
        async def handler(request):
            nonlocal requests
            requests += 1
            return httpx.Response(first_status if requests == 1 else 200,
                                  content=b"" if requests == 1 else body, request=request)
        adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        snap = ProviderSnapshot("openai_compatible", "p", "https://x", "k", "m", max_tokens=10)
        control = StreamControl(cancel_event=asyncio.Event())
        events = [event async for event in _gateway(adapter, max_retries=2).stream(snap, REQ, CTX, control=control)]
        return requests, events, control
    retried = _run(exercise(429))
    rejected = _run(exercise(400))
    assert retried[0] == 2 and retried[1][-1].type == "done"
    assert rejected[0] == 1 and rejected[1][-1].type == "error"
    assert rejected[2].error_code == "provider_request_error"


def test_request_and_response_ids_are_kept_separate_in_attempt_record():
    body = (b'data: {"id":"resp_1","choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n')
    async def handler(request):
        return httpx.Response(200, content=body, headers={"x-request-id": "req_1"}, request=request)
    adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    snap = ProviderSnapshot("openai_compatible", "p", "https://x", "k", "m", max_tokens=10)
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        return [event async for event in _gateway(adapter, max_retries=0).stream(snap, REQ, CTX, control=control)]
    events = _run(go())
    assert events[-1].message.response_id == "resp_1"
    assert (control.attempt_records[0].request_id, control.attempt_records[0].response_id) == ("req_1", "resp_1")


def test_cancel_interrupts_retry_backoff_without_second_request():
    entered = asyncio.Event()
    async def sleeper(_delay):
        entered.set()
        await asyncio.Event().wait()
    adapter = AlwaysFailAdapter()
    gateway = LLMStreamGateway(max_retries=2, retry_delay_seconds=1,
        openai_stream_factory=adapter, async_sleeper=sleeper)
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        task = asyncio.create_task(_collect_async(gateway, control))
        await asyncio.wait_for(entered.wait(), 1)
        control.cancel_event.set()
        return await asyncio.wait_for(task, 1)
    events = _run(go())
    assert adapter.attempts == 1
    assert events[-1].reason == "aborted" and control.error_code == "canceled"


def test_unserializable_tool_schema_fails_before_attempt_without_leak():
    marker = "SERIALIZER-MARKER"
    class Bad:
        def __repr__(self): return marker
    request = StreamRequest(messages=[make_user()], max_tokens=10,
        tools=[LLMToolSpec(name="bad", input_schema={"value": Bad()})])
    adapter = CountingFakeAdapter(fail_first=False)
    control = StreamControl(cancel_event=asyncio.Event())
    async def go():
        with pytest.raises(StreamError) as exc:
            async for _ in _gateway(adapter).stream(SNAP, request, CTX, control=control): pass
        assert exc.value.error_code == "invalid_history"
        assert marker not in str(exc.value)
    _run(go())
    assert adapter.attempts == 0 and control.attempt_records == []
