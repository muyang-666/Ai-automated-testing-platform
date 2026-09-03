"""Anthropic Adapter：基于官方 Python SDK（anthropic==1.3.0）。

- SDK 客户端显式 max_retries=0，重试统一由 LLMGateway 控制，避免双重重试；
- 首期结构化输出同样走"JSON 提示约束 + Pydantic 本地校验"（由 Gateway 完成），
  不在本任务实现 Anthropic 原生结构化输出（structured_output 基线为 unsupported）；
- 注意：anthropic==1.3.0 的 messages.create 无 temperature 参数，
  请求 temperature 首期不转发（登记于开发记录）；
- SDK 惰性导入：未安装 anthropic 时不影响其他链路；
- 错误消息不包含 API Key / Authorization。
"""

import json
import time

from app.agents.providers.base import Capability, LLMProviderAdapter, ProviderCapabilities
from app.exceptions.llm_errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.schemas.llm.llm_gateway import LLMRequest, LLMResult, LLMToolCall


class AnthropicAdapter(LLMProviderAdapter):
    provider_type = "anthropic"

    baseline_capabilities = ProviderCapabilities(
        tools=Capability.SUPPORTED,
        structured_output=Capability.UNSUPPORTED,
        streaming=Capability.SUPPORTED,
    )

    def __init__(self, client_factory=None):
        # client_factory(provider, timeout_seconds) -> anthropic client；
        # 测试注入 fake 工厂实现零网络、零真实 Key。
        self._client_factory = client_factory or _default_client_factory

    def complete(
        self,
        provider,
        model,
        request: LLMRequest,
        response_model=None,
        capabilities: ProviderCapabilities | None = None,
    ) -> LLMResult:
        timeout = request.timeout_seconds if request.timeout_seconds is not None else float(model.timeout_seconds)
        client = self._client_factory(provider, timeout)
        started = time.monotonic()

        create_kwargs = {
            "model": model.model_name,
            "max_tokens": request.max_tokens if request.max_tokens is not None else model.max_tokens,
            "messages": self._build_messages(request.messages),
        }
        system = self._build_system(request.messages)
        if system:
            create_kwargs["system"] = system
        if request.tools:
            create_kwargs["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in request.tools
            ]

        try:
            response = client.messages.create(**create_kwargs)
        except Exception as e:
            self._raise_translated(e)

        duration_ms = int((time.monotonic() - started) * 1000)
        return self._parse_response(response, provider, model, duration_ms)

    def _build_system(self, messages) -> str | None:
        parts = [m.content or "" for m in messages if m.role == "system"]
        return "\n\n".join(parts) if parts else None

    def _build_messages(self, messages) -> list[dict]:
        result = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                # Anthropic 将 tool 结果映射为 user 消息的 tool_result 内容块
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id or "",
                                "content": message.content or "",
                            }
                        ],
                    }
                )
            else:
                result.append({"role": message.role, "content": message.content or ""})
        return result

    def _raise_translated(self, e: Exception) -> None:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        if isinstance(e, APITimeoutError):
            raise LLMTimeoutError(f"Anthropic 请求超时: {e}") from e
        if isinstance(e, APIConnectionError):
            raise LLMProviderError(f"Anthropic 请求失败（网络错误）: {e}", retryable=True) from e
        if isinstance(e, APIStatusError):
            status = getattr(e, "status_code", None)
            message = f"Anthropic 接口返回错误 HTTP {status}。请检查 API Key 和模型名称是否正确。"
            if isinstance(e, RateLimitError):
                raise LLMRateLimitError(message) from e
            if status is not None and status >= 500:
                raise LLMProviderError(message, retryable=True) from e
            raise LLMProviderError(message) from e
        raise LLMProviderError(f"Anthropic 请求失败: {e}") from e

    def _parse_response(self, response, provider, model, duration_ms: int) -> LLMResult:
        text_parts = []
        tool_calls = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif block_type == "tool_use":
                tool_calls.append(
                    LLMToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments_json=json.dumps(getattr(block, "input", {}) or {}, ensure_ascii=False),
                    )
                )

        usage = getattr(response, "usage", None)
        return LLMResult(
            content="".join(text_parts),
            tool_calls=tool_calls,
            provider_name=provider.name,
            model_name=getattr(response, "model", None) or model.model_name,
            prompt_tokens=getattr(usage, "input_tokens", None),
            completion_tokens=getattr(usage, "output_tokens", None),
            duration_ms=duration_ms,
            request_id=getattr(response, "id", None),
            finish_reason=getattr(response, "stop_reason", None),
            raw_metadata={},
        )


def _default_client_factory(provider, timeout_seconds: float):
    import anthropic  # 惰性导入：SDK 未安装时不影响其他链路

    return anthropic.Anthropic(
        api_key=provider.api_key,
        base_url=provider.base_url or None,
        timeout=timeout_seconds,
        max_retries=0,  # 重试统一由 LLMGateway 控制，避免 SDK/Gateway 双重重试
    )
