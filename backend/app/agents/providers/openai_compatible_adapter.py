"""OpenAI-compatible Adapter：使用 httpx 直连 /chat/completions，不引入 OpenAI SDK。

能力基线：tools / structured_output / streaming 均为 unknown（不同供应商差异大，
不做统一假定）。原生 response_format 仅在 capabilities.structured_output == SUPPORTED
时附加；默认（unknown/unsupported）由 Gateway 走"JSON 提示约束 + Pydantic 本地校验"。

- 保留 Base URL 自动补 /chat/completions 的历史行为；
- 不做重试（重试统一由 LLMGateway 负责）；
- 错误消息不包含 API Key / Authorization。
"""

import time

import httpx

from app.agents.providers.base import Capability, LLMProviderAdapter, ProviderCapabilities
from app.exceptions.llm_errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.schemas.llm_gateway import LLMRequest, LLMResult, LLMToolCall


class OpenAICompatibleAdapter(LLMProviderAdapter):
    provider_type = "openai_compatible"

    baseline_capabilities = ProviderCapabilities(
        tools=Capability.UNKNOWN,
        structured_output=Capability.UNKNOWN,
        streaming=Capability.UNKNOWN,
    )

    def __init__(self, transport: httpx.BaseTransport | None = None):
        # 测试注入 httpx.MockTransport，实现零网络
        self._transport = transport

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport)
        return httpx.Client()

    def complete(
        self,
        provider,
        model,
        request: LLMRequest,
        response_model=None,
        capabilities: ProviderCapabilities | None = None,
    ) -> LLMResult:
        caps = capabilities or self.baseline_capabilities
        base_url = provider.base_url.rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

        timeout = request.timeout_seconds if request.timeout_seconds is not None else float(model.timeout_seconds)
        temperature = request.temperature if request.temperature is not None else model.temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else model.max_tokens

        payload: dict = {
            "model": model.model_name,
            "messages": self._build_messages(request.messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = "auto"
        if request.response_mode in ("json", "pydantic") and caps.structured_output == Capability.SUPPORTED:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }

        started = time.monotonic()
        try:
            with self._client() as client:
                response = client.post(url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"请求超时（{timeout}秒）。请检查 Base URL 是否正确、网络是否可达。当前 URL: {url}"
            ) from e
        except httpx.HTTPStatusError as e:
            self._raise_http_error(e, url)
        except httpx.NetworkError as e:
            raise LLMProviderError(f"请求失败（网络错误）: {e}。URL: {url}", retryable=True) from e
        except Exception as e:
            raise LLMProviderError(
                f"请求失败: {e}。URL: {url}。"
                f"请检查 Base URL 格式是否正确（如 https://api.deepseek.com），"
                f"不要包含 /chat/completions 后缀。"
            ) from e

        duration_ms = int((time.monotonic() - started) * 1000)
        return self._parse_response(response, provider, model, duration_ms)

    def _raise_http_error(self, e: httpx.HTTPStatusError, url: str) -> None:
        status = e.response.status_code
        detail = ""
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        message = (
            f"LLM 接口返回错误 HTTP {status}。URL: {url}\n"
            f"请检查 API Key 和模型名称是否正确。\n响应详情: {detail}"
        )
        if status == 429:
            raise LLMRateLimitError(message) from e
        if status >= 500:
            raise LLMProviderError(message, retryable=True) from e
        raise LLMProviderError(message) from e

    def _build_messages(self, messages) -> list[dict]:
        result = []
        for message in messages:
            if message.role == "tool":
                item = {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id or "",
                    "content": message.content or "",
                }
                if message.name:
                    item["name"] = message.name
                result.append(item)
            elif message.role == "assistant" and message.tool_calls:
                item = {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": tool_call.arguments_json,
                            },
                        }
                        for tool_call in message.tool_calls
                    ],
                }
                result.append(item)
            else:
                result.append({"role": message.role, "content": message.content})
        return result

    def _parse_response(self, response: httpx.Response, provider, model, duration_ms: int) -> LLMResult:
        try:
            data = response.json()
        except Exception as e:
            raise LLMProviderError("LLM 响应不是合法 JSON，无法解析。") from e

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMProviderError("LLM 响应结构缺失: 缺少 choices 字段。") from e

        message = choice.get("message") or {}
        tool_calls = [
            LLMToolCall(
                id=tool_call.get("id", ""),
                name=(tool_call.get("function") or {}).get("name", ""),
                arguments_json=(tool_call.get("function") or {}).get("arguments", "{}"),
            )
            for tool_call in (message.get("tool_calls") or [])
        ]
        usage = data.get("usage") or {}

        return LLMResult(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            provider_name=provider.name,
            model_name=model.model_name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            duration_ms=duration_ms,
            request_id=response.headers.get("x-request-id"),
            finish_reason=choice.get("finish_reason"),
            raw_metadata={"id": data.get("id"), "created": data.get("created")},
        )
