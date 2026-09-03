"""OpenAI-compatible Adapter 测试：httpx.MockTransport 零网络、零真实 Key。"""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.agents.providers.base import Capability, ProviderCapabilities
from app.agents.providers.openai_compatible_adapter import OpenAICompatibleAdapter
from app.exceptions.llm_errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.schemas.llm.llm_gateway import (
    LLMMessage,
    LLMRequest,
    LLMToolCall,
    LLMToolSpec,
)

FAKE_KEY = "sk-test-secret"

PROVIDER = SimpleNamespace(
    name="FakeProvider",
    provider_type="openai_compatible",
    base_url="https://fake-llm.invalid/v1",
    api_key=FAKE_KEY,
)
MODEL = SimpleNamespace(
    model_name="fake-model",
    temperature=0.7,
    max_tokens=2048,
    timeout_seconds=60,
)


def _adapter(handler):
    return OpenAICompatibleAdapter(transport=httpx.MockTransport(handler))


def _capture(handler):
    captured = {}

    def wrapper(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return handler(request)

    return wrapper, captured


def _request(**kwargs):
    defaults = {"messages": [LLMMessage(role="user", content="你好")]}
    defaults.update(kwargs)
    return LLMRequest(**defaults)


def _ok_response(payload):
    def handler(request):
        return httpx.Response(
            200,
            json=payload,
            headers={"x-request-id": "req-abc-123"},
        )

    return handler


# ── URL / 认证 / 默认参数 ──


def test_url_auth_and_defaults():
    handler, captured = _capture(
        _ok_response(
            {
                "id": "chatcmpl-1",
                "created": 1700000000,
                "choices": [{"message": {"content": "回复"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6},
            }
        )
    )
    adapter = _adapter(handler)

    adapter.complete(PROVIDER, MODEL, _request())

    assert captured["url"] == "https://fake-llm.invalid/v1/chat/completions"
    assert captured["headers"]["authorization"] == f"Bearer {FAKE_KEY}"  # httpx 统一小写头名
    payload = captured["json"]
    assert payload["model"] == "fake-model"
    assert payload["temperature"] == 0.7  # 缺省取 model 值
    assert payload["max_tokens"] == 2048
    assert payload["messages"] == [{"role": "user", "content": "你好"}]
    assert "response_format" not in payload  # 默认 unknown 能力不加原生结构化标志
    assert "tools" not in payload


def test_url_with_existing_chat_completions_suffix():
    provider = SimpleNamespace(**{**PROVIDER.__dict__, "base_url": "https://fake-llm.invalid/v1/chat/completions"})
    handler, captured = _capture(
        _ok_response({"choices": [{"message": {"content": "ok"}}], "usage": {}})
    )
    adapter = _adapter(handler)

    adapter.complete(provider, MODEL, _request())

    assert captured["url"] == "https://fake-llm.invalid/v1/chat/completions"


# ── 消息映射 ──


def test_message_mapping_all_roles():
    handler, captured = _capture(_ok_response({"choices": [{"message": {"content": "ok"}}]}))
    adapter = _adapter(handler)

    request = _request(
        messages=[
            LLMMessage(role="system", content="你是测试助手"),
            LLMMessage(role="user", content="问题"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[LLMToolCall(id="call_1", name="list_cases", arguments_json='{"project_id": 3}')],
            ),
            LLMMessage(role="tool", tool_call_id="call_1", name="list_cases", content='[{"id": 1}]'),
        ]
    )
    adapter.complete(PROVIDER, MODEL, request)

    assert captured["json"]["messages"] == [
        {"role": "system", "content": "你是测试助手"},
        {"role": "user", "content": "问题"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "list_cases", "arguments": '{"project_id": 3}'}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '[{"id": 1}]', "name": "list_cases"},
    ]


# ── tools / tool_choice ──


def test_tools_payload_and_tool_choice():
    handler, captured = _capture(_ok_response({"choices": [{"message": {"content": "ok"}}]}))
    adapter = _adapter(handler)

    adapter.complete(
        PROVIDER,
        MODEL,
        _request(tools=[LLMToolSpec(name="list_cases", description="查询用例", input_schema={"type": "object", "properties": {}})]),
    )

    payload = captured["json"]
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {"name": "list_cases", "description": "查询用例", "parameters": {"type": "object", "properties": {}}},
        }
    ]
    assert payload["tool_choice"] == "auto"


# ── 响应解析 ──


def test_text_response_usage_and_metadata():
    adapter = _adapter(
        _ok_response(
            {
                "id": "chatcmpl-1",
                "created": 1700000000,
                "choices": [{"message": {"content": "模型回复"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            }
        )
    )

    result = adapter.complete(PROVIDER, MODEL, _request())

    assert result.content == "模型回复"
    assert result.provider_name == "FakeProvider"
    assert result.model_name == "fake-model"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34
    assert result.finish_reason == "stop"
    assert result.request_id == "req-abc-123"
    assert result.raw_metadata == {"id": "chatcmpl-1", "created": 1700000000}
    assert result.duration_ms >= 0
    assert result.tool_calls == []


def test_tool_calls_parsed():
    adapter = _adapter(
        _ok_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_9",
                                    "type": "function",
                                    "function": {"name": "list_cases", "arguments": '{"project_id": 3}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )
    )

    result = adapter.complete(PROVIDER, MODEL, _request())

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_9"
    assert result.tool_calls[0].name == "list_cases"
    assert result.tool_calls[0].arguments_json == '{"project_id": 3}'
    assert result.finish_reason == "tool_calls"


# ── 结构化输出原生标志：仅在能力 SUPPORTED 时附加 ──


def test_response_format_only_when_supported():
    handler, captured = _capture(_ok_response({"choices": [{"message": {"content": "{}"}}]}))
    adapter = _adapter(handler)

    adapter.complete(PROVIDER, MODEL, _request(response_mode="json"))
    assert "response_format" not in captured["json"]  # 默认 unknown → 不附加

    supported = ProviderCapabilities(structured_output=Capability.SUPPORTED)
    adapter.complete(PROVIDER, MODEL, _request(response_mode="json"), capabilities=supported)
    assert captured["json"]["response_format"] == {"type": "json_object"}


# ── 错误分类 ──


def test_timeout_raises_llm_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    adapter = _adapter(handler)

    with pytest.raises(LLMTimeoutError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert exc.value.error_code == "llm_timeout"
    assert FAKE_KEY not in str(exc.value)


def test_429_raises_rate_limit_retryable():
    def handler(request):
        return httpx.Response(429, json={"error": "slow down"})

    adapter = _adapter(handler)

    with pytest.raises(LLMRateLimitError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert exc.value.error_code == "llm_rate_limit"
    assert FAKE_KEY not in str(exc.value)


def test_5xx_raises_provider_error_retryable():
    def handler(request):
        return httpx.Response(500, json={"error": "internal"})

    adapter = _adapter(handler)

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True
    assert "HTTP 500" in str(exc.value)


@pytest.mark.parametrize("status", [400, 401, 403])
def test_4xx_raises_provider_error_not_retryable(status):
    def handler(request):
        return httpx.Response(status, json={"error": "bad request"})

    adapter = _adapter(handler)

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is False
    assert f"HTTP {status}" in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_connection_error_retryable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    adapter = _adapter(handler)

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert exc.value.retryable is True


# ── malformed response ──


def test_non_json_response_body():
    def handler(request):
        return httpx.Response(200, content=b"<html>not json</html>")

    adapter = _adapter(handler)

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert "不是合法 JSON" in str(exc.value)
    assert exc.value.retryable is False


def test_missing_choices_field():
    adapter = _adapter(_ok_response({"usage": {}}))

    with pytest.raises(LLMProviderError) as exc:
        adapter.complete(PROVIDER, MODEL, _request())
    assert "缺少 choices" in str(exc.value)
