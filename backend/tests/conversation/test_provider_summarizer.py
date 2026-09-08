"""P10.1-B3 ProviderConversationSummarizer：复用 Provider abstraction 的正式 Summarizer。

验证：经 gateway.stream（P02 事件合同）取摘要文本与 usage；error/length/empty
一律抛错（由 Orchestrator 视为一次失败，不 while-retry）；usage/cost 可观测；
请求本身走 StreamRequest（同一 LLMGateway 通道，无第二套 SDK/HTTP）。
"""

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest

from app.agents.conversation.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantStartEvent,
)
from app.agents.conversation.messages import (
    AssistantMessage,
    TextContent,
    Usage,
    UsageCost,
)
from app.agents.conversation.summarizer import ProviderConversationSummarizer
from app.agents.providers.streaming import ProviderSnapshot, StreamError

TS = 1_700_000_000_000


def usage(**overrides):
    base = dict(input=1200, output=300, cache_read=200, cache_write=400,
                total_tokens=1500, cost=UsageCost(input=0.01, output=0.03,
                                                  cache_read=None, cache_write=None,
                                                  total=None))
    base.update(overrides)
    return Usage(**base)


def _assistant(text, *, stop_reason="stop", usage_value=None, provider="fake-sum",
               model="sum-model"):
    return AssistantMessage(message_id="m1", timestamp=TS, role="assistant",
                            api="chat", provider=provider, model=model,
                            content=[TextContent(text=text)],
                            usage=usage_value or usage(), stop_reason=stop_reason)


class FakeStreamGateway:
    """脚本化 gateway：按 terminal 类型产出 done/error；记录收到的请求与 control。"""

    def __init__(self, final=None, terminal="done", explode=False, error_code=None,
                 cancel_after_start=False):
        self.final = final
        self.terminal = terminal
        self.explode = explode
        self.error_code = error_code
        self.cancel_after_start = cancel_after_start
        self.requests = []
        self.controls = []

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        self.controls.append(control)
        if self.explode:
            @asynccontextmanager
            async def managed():
                raise RuntimeError("boom")
                yield  # pragma: no cover
            return managed()

        @asynccontextmanager
        async def managed():
            async def events():
                final = self.final
                partial = final.model_copy(deep=True,
                                           update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                if self.terminal == "error":
                    control.error_code = self.error_code or "synthetic_model_error"
                    yield AssistantErrorEvent(reason="error",
                                              error=final.model_copy(deep=True,
                                                                    update={"stop_reason": "error"}))
                elif self.cancel_after_start:
                    # 模拟 P02 协调器：帧间观察 control.cancel_event → 抛 canceled
                    import asyncio as _asyncio
                    await _asyncio.wait_for(control.cancel_event.wait(), timeout=5)
                    raise StreamError("canceled")
                elif self.terminal == "length":
                    yield AssistantDoneEvent(reason="length",
                                             message=final.model_copy(deep=True,
                                                                      update={"stop_reason": "length"}))
                else:
                    yield AssistantDoneEvent(reason="stop", message=final)
            yield events()
        return managed()


def _snapshot():
    return ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                            "key", "fake-model", max_tokens=100)


def _run(coro):
    return asyncio.run(coro)


def test_summarize_success_records_text_and_usage():
    gateway = FakeStreamGateway(final=_assistant("简明摘要：已实现 X，待办 Y。"))
    summarizer = ProviderConversationSummarizer(
        gateway, _snapshot(), id_factory=lambda: uuid.uuid4().hex)
    result = _run(summarizer.summarize(
        existing_summary="旧", messages=[], target_through_visible_rank=42,
        summary_token_budget=500))
    assert result.summary_text == "简明摘要：已实现 X，待办 Y。"
    assert result.through_visible_rank == 42
    assert result.estimated_tokens is not None and result.estimated_tokens > 0
    assert result.usage["input_tokens"] == 1200
    assert result.usage["output_tokens"] == 300
    assert result.usage["cache_read_tokens"] == 200
    assert result.usage["cache_write_tokens"] == 400
    assert result.usage["cost"]["input"] == 0.01 and result.usage["cost"]["output"] == 0.03
    assert result.model == "sum-model"
    request = gateway.requests[0]
    assert request.messages and request.messages[0].role == "user"
    assert "旧" in request.messages[0].content  # 增量正文带 existing summary
    assert not request.tools  # 摘要请求不带工具
    assert request.max_tokens == 500  # 与摘要预算对齐


@pytest.mark.parametrize("terminal,reason", [
    ("error", "model"), ("length", "length"), ("aborted_model", "aborted"),
])
def test_terminal_failures_raise(terminal, reason):
    final = _assistant("", stop_reason=reason if reason in {"error", "aborted"} else "length")
    terminal_kind = "error" if terminal in {"error", "aborted_model"} else "length"
    gateway = FakeStreamGateway(final=final, terminal=terminal_kind)
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())
    with pytest.raises(RuntimeError):
        _run(summarizer.summarize(
            existing_summary=None, messages=[], target_through_visible_rank=1,
            summary_token_budget=100))


def test_empty_content_raises():
    gateway = FakeStreamGateway(final=_assistant("   "))
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())
    with pytest.raises(RuntimeError):
        _run(summarizer.summarize(
            existing_summary=None, messages=[], target_through_visible_rank=1,
            summary_token_budget=100))


def test_stream_gateway_exception_propagates_as_failure():
    gateway = FakeStreamGateway(explode=True)
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())
    with pytest.raises(RuntimeError):
        _run(summarizer.summarize(
            existing_summary=None, messages=[], target_through_visible_rank=1,
            summary_token_budget=100))


# ------------------------------------------------------- 审计 #3：cancel/deadline

def test_canceled_before_call_raises_without_gateway_request():
    cancel_event = asyncio.Event()
    cancel_event.set()
    gateway = FakeStreamGateway(final=_assistant("摘要"))
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())
    with pytest.raises(RuntimeError):
        _run(summarizer.summarize(
            existing_summary=None, messages=[], target_through_visible_rank=1,
            summary_token_budget=100,
            runtime_context={"cancel_event": cancel_event}))
    assert gateway.requests == []  # 未发起任何 Provider 请求


def test_control_receives_run_cancel_event_and_deadline():
    cancel_event = asyncio.Event()
    deadline = 12345.0
    gateway = FakeStreamGateway(final=_assistant("摘要"))
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())
    _run(summarizer.summarize(
        existing_summary=None, messages=[], target_through_visible_rank=1,
        summary_token_budget=100,
        runtime_context={"cancel_event": cancel_event, "deadline": deadline}))
    control = gateway.controls[0]
    assert control.cancel_event is cancel_event
    assert control.deadline == deadline


def test_midstream_cancel_finishes_promptly():
    """streaming 中取消：transport（协调器）观察 control.cancel_event 抛 canceled，
    适配器快速失败，不长时间阻塞 context preparation。"""
    cancel_event = asyncio.Event()
    gateway = FakeStreamGateway(final=_assistant("摘要"), cancel_after_start=True)
    summarizer = ProviderConversationSummarizer(gateway, _snapshot())

    async def scenario():
        task = asyncio.create_task(summarizer.summarize(
            existing_summary=None, messages=[], target_through_visible_rank=1,
            summary_token_budget=100,
            runtime_context={"cancel_event": cancel_event, "deadline": None}))
        await asyncio.sleep(0.05)  # 让流进入 cancel_after_start 等待
        cancel_event.set()
        return await asyncio.wait_for(task, timeout=2.0)  # 2s 内必须返回

    with pytest.raises(RuntimeError):
        asyncio.run(scenario())
