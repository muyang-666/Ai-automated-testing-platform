"""Anthropic Adapter 测试：注入 fake SDK 客户端工厂，零网络、零真实 Key。

异常翻译使用真实 anthropic SDK 异常对象（基于 httpx2），
响应解析使用真实 SDK 类型（TextBlock / ToolUseBlock / Usage）。
"""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.agents.providers.anthropic_adapter import AnthropicAdapter, _default_client_factory
from app.exceptions.llm_errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.schemas.llm_gateway import LLMMessage, LLMRequest, LLMToolCall, LLMToolSpec

FAKE_KEY = "sk-ant-test-secret"

PROVIDER = SimpleNamespace(
    name="FakeAnthropic",
    provider_type="anthropic",
    base_url="https://api.anthropic.com",
    api_key=FAKE_KEY,
)
MODEL = SimpleNamespace(
    model_name="claude-fake-model",
    temperature=0.7,
    max_tokens=2048,
    timeout_seconds=60,
)


class FakeSDKMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.create_kwargs = None
        self.create_calls = 0

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        self.create_calls += 1
        if self._error is not None:
            raise self._error
        return self._response


class FakeSDKClient:
    def __init__(self, messages):
        self.messages = messages


def _message(**kwargs):
    defaults = {
        "content": [
            anthropic.types.TextBlock(type="text", text="模型回复内容"),
        ],
        "usage": anthropic.types.Usage(input_tokens=12, output_tokens=34),
        "stop_reason": "end_turn",
        "model": "claude-fake-model",
        "id": "msg_123",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _adapter(response=None, error=None):
    fake_messages = FakeSDKMessages(response=response, error=error)
    calls = {}

    def factory(provider, timeout_seconds):
        calls["provider"] = provider
        calls["timeout_seconds"] = timeout_seconds
        return FakeSDKClient(fake_messages)

    return AnthropicAdapter(client_factory=factory), fake_messages, calls


def _request(**kwargs):
    defaults = {"messages": [LLMMessage(role="user", content="你好")]}
    defaults.update(kwargs)
    return LLMRequest(**defaults)


# ── 消息与参数映射 ──


def test_system_merged_and_messages_mapped():
    adapter, fake_messages, calls = _adapter(response=_message())

    adapter.complete(
        PROVIDER,
        MODEL,
        _request(
            messages=[
                LLMMessage(role="system", content="规则一"),
                LLMMessage(role="system", content="规则二"),
                LLMMessage(role="user", content="问题"),
                LLMMessage(role="assistant", content="回答"),
                LLMMessage(role="tool", tool_call_id="toolu_1", content='[{"id": 1}]'),
            ]
        ),
    )

    kwargs = fake_messages.create_kwargs
    assert kwargs["system"] == "规则一\n\n规则二"
    assert kwargs["messages"] == [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '[{"id": 1}]'}]},
    ]
    assert calls["provider"] is PROVIDER
    assert calls["timeout_seconds"] == 60.0


def test_create_kwargs_no_temperature_and_max_tokens_default():
    adapter, fake_messages, _ = _adapter(response=_message())

    adapter.complete(PROVIDER, MODEL, _request(temperature=0.3))

    kwargs = fake_messages.create_kwargs
    assert kwargs["model"] == "claude-fake-model"
    assert kwargs["max_tokens"] == 2048
    # anthropic==1.3.0 的 messages.create 无 temperature 参数，首期不转发（冻结该事实）
    assert "temperature" not in kwargs


def test_tools_mapping():
    adapter, fake_messages, _ = _adapter(response=_message())

    adapter.complete(
        PROVIDER,
        MODEL,
        _request(tools=[LLMToolSpec(name="list_cases", description="查询用例", input_schema={"type": "object"})]),
    )

    assert fake_messages.create_kwargs["tools"] == [
        {"name": "list_cases", "description": "查询用例", "input_schema": {"type": "object"}}
    ]


# ── 响应解析 ──


def test_text_and_usage_mapping():
    adapter, _, _ = _adapter(response=_message())

    result = adapter.complete(PROVIDER, MODEL, _request())

    assert result.content == "模型回复内容"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34
    assert result.finish_reason == "end_turn"
    assert result.request_id == "msg_123"
    assert result.model_name == "claude-fake-model"
    assert result.provider_name == "FakeAnthropic"
    assert result.duration_ms >= 0


def test_tool_use_parsed():
    response = _message(
        content=[
            anthropic.types.TextBlock(type="text", text="我将查询用例。"),
            anthropic.types.ToolUseBlock(type="tool_use", id="toolu_9", name="list_cases", input={"project_id": 3}),
        ],
        stop_reason="tool_use",
    )
    adapter, _, _ = _adapter(response=response)

    result = adapter.complete(PROVIDER, MODEL, _request())

    assert result.content == "我将查询用例。"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "toolu_9"
    assert result.tool_calls[0].name == "list_cases"
    assert result.tool_calls[0].arguments_json == '{"project_id": 3}'
    assert result.finish_reason == "tool_use"


# ── 错误翻译（真实 SDK 异常对象） ──


def _sdk_request():
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _sdk_response(status):
    return httpx2.Response(status, request=_sdk_request(), json={"error": {"message": "x"}})


def test_timeout_error_translated():
    adapter, _, _ = _adapter(error=anthropic.APITimeoutError(request=_sdk_request()))

    with pytest.raises(LLMTimeoutError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert exc.value.error_code == "llm_timeout"
    assert FAKE_KEY not in str(exc.value)


def test_connection_error_translated_retryable():
    adapter, _, _ = _adapter(error=anthropic.APIConnectionError(request=_sdk_request()))

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True


def test_rate_limit_translated():
    adapter, _, _ = _adapter(
        error=anthropic.RateLimitError("rate limited", response=_sdk_response(429), body=None)
    )

    with pytest.raises(LLMRateLimitError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert exc.value.error_code == "llm_rate_limit"
    assert FAKE_KEY not in str(exc.value)


def test_5xx_translated_retryable():
    adapter, _, _ = _adapter(
        error=anthropic.APIStatusError("server error", response=_sdk_response(500), body=None)
    )

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert "HTTP 500" in str(exc.value)


def test_4xx_translated_not_retryable():
    adapter, _, _ = _adapter(
        error=anthropic.BadRequestError("bad request", response=_sdk_response(400), body=None)
    )

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is False
    assert "HTTP 400" in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_unknown_error_translated_not_retryable():
    adapter, _, _ = _adapter(error=RuntimeError("boom"))

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is False


# ── 默认客户端工厂：max_retries=0，避免 SDK/Gateway 双重重试 ──


def test_default_client_factory_disables_sdk_retry():
    client = _default_client_factory(PROVIDER, 30.0)

    assert client.max_retries == 0
    assert client.timeout == 30.0
