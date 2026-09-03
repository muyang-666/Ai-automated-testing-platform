"""LLMGateway：统一 LLM 调用入口。

- 按 provider_type 选择 Adapter（含 V1 前端可选类型别名映射）；
- 负责有限重试：只重试 retryable 错误（timeout/连接错误/429/5xx），指数退避，
  sleeper 可注入（测试注入 fake，禁止真实 sleep）；
- 负责 json/pydantic 结构化解析与本地校验（两级降级中的本地校验层）；
  原生结构化输出由 Adapter 在能力为 SUPPORTED 时启用；
- 不执行 tool_calls，只透传解析结果；
- 不在 Gateway 内实现无限重试或 Prompt 修复循环。
"""

import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.providers.anthropic_adapter import AnthropicAdapter
from app.agents.providers.base import (
    PROVIDER_TYPE_ANTHROPIC,
    PROVIDER_TYPE_OPENAI_COMPATIBLE,
    Capability,
    ProviderCapabilities,
)
from app.agents.providers.openai_compatible_adapter import OpenAICompatibleAdapter
from app.exceptions.llm_errors import (
    LLMError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMUnsupportedFeatureError,
)
from app.schemas.llm.llm_gateway import LLMRequest, LLMResult

# V1 前端 provider_type 可选值中，除 anthropic 外均按 OpenAI-compatible 调用（历史行为兼容）
_OPENAI_COMPATIBLE_ALIASES = {
    PROVIDER_TYPE_OPENAI_COMPATIBLE,
    "deepseek",
    "openai",
    "qwen",
    "custom",
}


def _default_adapters() -> dict:
    return {
        PROVIDER_TYPE_OPENAI_COMPATIBLE: OpenAICompatibleAdapter(),
        PROVIDER_TYPE_ANTHROPIC: AnthropicAdapter(),
    }


class LLMGateway:
    def __init__(
        self,
        adapters: dict | None = None,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
        sleeper=None,
        capability_overrides: dict | None = None,
    ):
        self._adapters = adapters if adapters is not None else _default_adapters()
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper if sleeper is not None else time.sleep
        # capability_overrides: {(provider_type, model_name 或 "*"): ProviderCapabilities}
        self._capability_overrides = capability_overrides or {}

    # ── Adapter 选择 ──

    def _adapter_for(self, provider_type: str):
        normalized = (
            PROVIDER_TYPE_OPENAI_COMPATIBLE
            if provider_type in _OPENAI_COMPATIBLE_ALIASES
            else provider_type
        )
        adapter = self._adapters.get(normalized)
        if adapter is None:
            supported = sorted(set(self._adapters.keys()) | _OPENAI_COMPATIBLE_ALIASES)
            raise LLMUnsupportedFeatureError(
                f"不支持的供应商类型 '{provider_type}'，当前支持: {supported}。"
                f"请在模型管理中调整供应商类型。"
            )
        return adapter

    # ── 能力解析：override > Adapter 基线 ──

    def capabilities(self, provider, model) -> ProviderCapabilities:
        adapter = self._adapter_for(provider.provider_type)
        baseline = getattr(adapter, "baseline_capabilities", ProviderCapabilities())
        override = self._capability_overrides.get((provider.provider_type, model.model_name)) or self._capability_overrides.get(
            (provider.provider_type, "*")
        )
        return override if override is not None else baseline

    # ── 统一调用入口 ──

    def complete(
        self,
        provider,
        model,
        request: LLMRequest,
        response_model: type[BaseModel] | None = None,
    ) -> LLMResult:
        adapter = self._adapter_for(provider.provider_type)
        caps = self.capabilities(provider, model)

        if request.tools and caps.tools == Capability.UNSUPPORTED:
            raise LLMUnsupportedFeatureError(
                f"供应商 {provider.name} 不支持工具调用，请更换模型或移除 tools 参数。"
            )

        attempt = 0
        while True:
            try:
                result = adapter.complete(provider, model, request, response_model=response_model, capabilities=caps)
            except LLMError as e:
                if e.retryable and attempt < self.max_retries:
                    attempt += 1
                    self._sleeper(self.retry_delay_seconds * (2 ** (attempt - 1)))
                    continue
                raise
            # HTTP 200 但没有任何内容/工具调用：多为上游瞬时抖动，按可恢复异常有界重试，
            # 而不是当作“输出校验失败”直接永久失败。重试耗尽后带诊断信息失败。
            if not (result.content or "").strip() and not result.tool_calls:
                err = LLMProviderError(
                    "模型连续返回空内容，无法解析。请稍后重试，或检查该场景绑定的模型、API Key 与配额。"
                    if attempt >= self.max_retries
                    else "模型返回内容为空，正在重试。",
                    error_code="llm_empty_content",
                    retryable=True,
                )
                err.provider_name = result.provider_name or provider.name
                err.model_name = result.model_name or model.model_name
                err.finish_reason = result.finish_reason
                err.request_id = result.request_id
                if attempt < self.max_retries:
                    attempt += 1
                    self._sleeper(self.retry_delay_seconds * (2 ** (attempt - 1)))
                    continue
                raise err
            break

        return self._apply_structured_parsing(result, request, response_model)

    # ── 结构化输出本地校验层（两级降级中的第 2 级） ──

    def _apply_structured_parsing(
        self,
        result: LLMResult,
        request: LLMRequest,
        response_model: type[BaseModel] | None,
    ) -> LLMResult:
        if request.response_mode == "json":
            result.parsed = _parse_json_content(result.content)
        elif request.response_mode == "pydantic":
            if response_model is None:
                raise LLMOutputValidationError("response_mode=pydantic 时必须传入 response_model。")
            data = _parse_json_content(result.content)
            try:
                result.parsed = response_model.model_validate(data)
            except ValidationError as e:
                raise LLMOutputValidationError(_validation_summary(e)) from e
        return result


def _parse_json_content(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        raise LLMOutputValidationError("模型返回内容为空，无法解析为 JSON。")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMOutputValidationError(f"模型返回内容不是合法 JSON: {e}") from e


def _validation_summary(exc: ValidationError) -> str:
    """生成安全的字段级错误摘要：只包含字段位置/消息/类型，不包含输入值。"""
    items = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        items.append(f"{loc or '(root)'}: {err.get('msg', '')} [{err.get('type', '')}]")
    return "模型输出未通过 Schema 校验: " + "; ".join(items[:10])
