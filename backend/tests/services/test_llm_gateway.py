"""LLMGateway 与 V1 兼容层（llm_client_service）测试。

- Gateway：Adapter 选择、有限重试、结构化本地校验、能力三态门控；
- 兼容层：旧函数签名与字符串合同、.env 回退边界（只在配置不可用时回退）、
  prompt_template 顺序；
- 全部零网络、零真实 Key。
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents.providers.base import Capability, ProviderCapabilities
from app.exceptions.llm_errors import (
    LLMConfigurationError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnsupportedFeatureError,
)
from app.models.llm.llm_model import LLMModel
from app.models.llm.llm_provider import LLMProvider
from app.models.llm.llm_scene_config import LLMSceneConfig
from app.schemas.llm.llm_gateway import LLMMessage, LLMRequest, LLMResult, LLMToolCall, LLMToolSpec
from app.services.llm import llm_client_service
from app.services.llm.llm_gateway import LLMGateway

PROVIDER = SimpleNamespace(provider_type="openai_compatible", name="FakeProvider")
MODEL = SimpleNamespace(model_name="fake-model", timeout_seconds=60)


class FakeAdapter:
    def __init__(self, provider_type, results=None, errors=None):
        self.provider_type = provider_type
        self.baseline_capabilities = ProviderCapabilities()
        self.calls = []
        self._results = list(results or [])
        self._errors = list(errors or [])

    def complete(self, provider, model, request, response_model=None, capabilities=None):
        self.calls.append(
            {"provider": provider, "model": model, "request": request, "capabilities": capabilities}
        )
        if self._errors:
            raise self._errors.pop(0)
        return self._results.pop(0)


def _result(content="ok", tool_calls=None):
    return LLMResult(
        content=content,
        tool_calls=tool_calls or [],
        provider_name="FakeProvider",
        model_name="fake-model",
        duration_ms=1,
    )


def _request(**kwargs):
    defaults = {"messages": [LLMMessage(role="user", content="你好")]}
    defaults.update(kwargs)
    return LLMRequest(**defaults)


def _gateway(adapter, **kwargs):
    return LLMGateway(adapters={"openai_compatible": adapter}, **kwargs)


# ── Adapter 选择（含 V1 前端可选类型别名） ──


def test_adapter_selection_aliases():
    openai_adapter = FakeAdapter("openai_compatible", results=[_result() for _ in range(6)])
    anthropic_adapter = FakeAdapter("anthropic", results=[_result()])
    gateway = LLMGateway(
        adapters={"openai_compatible": openai_adapter, "anthropic": anthropic_adapter},
        max_retries=0,
    )

    for provider_type in ["openai_compatible", "deepseek", "openai", "qwen", "custom"]:
        gateway.complete(
            SimpleNamespace(provider_type=provider_type, name="p"),
            MODEL,
            _request(),
        )
    gateway.complete(
        SimpleNamespace(provider_type="anthropic", name="p"),
        MODEL,
        _request(),
    )

    assert len(openai_adapter.calls) == 5
    assert len(anthropic_adapter.calls) == 1


def test_unknown_provider_type_unsupported():
    gateway = _gateway(FakeAdapter("openai_compatible"), max_retries=0)

    with pytest.raises(LLMUnsupportedFeatureError) as exc:
        gateway.complete(
            SimpleNamespace(provider_type="mistral", name="p"),
            MODEL,
            _request(),
        )
    assert "mistral" in str(exc.value)
    assert exc.value.error_code == "llm_unsupported_feature"


# ── 有限重试（可注入 sleeper，禁止真实 sleep） ──


def test_retry_on_retryable_with_backoff():
    adapter = FakeAdapter(
        "openai_compatible",
        errors=[LLMRateLimitError("限流"), LLMTimeoutError("超时")],
        results=[_result("最终成功")],
    )
    sleeps = []
    gateway = _gateway(adapter, max_retries=2, retry_delay_seconds=1.5, sleeper=sleeps.append)

    result = gateway.complete(PROVIDER, MODEL, _request())

    assert result.content == "最终成功"
    assert len(adapter.calls) == 3
    assert sleeps == [1.5, 3.0]  # 指数退避


def test_no_retry_on_non_retryable():
    adapter = FakeAdapter("openai_compatible", errors=[LLMProviderError("参数错误")])
    sleeps = []
    gateway = _gateway(adapter, max_retries=2, sleeper=sleeps.append)

    with pytest.raises(LLMProviderError):
        gateway.complete(PROVIDER, MODEL, _request())

    assert len(adapter.calls) == 1
    assert sleeps == []


def test_retry_respects_max_retries():
    adapter = FakeAdapter("openai_compatible", errors=[LLMRateLimitError("限流")] * 5)
    sleeps = []
    gateway = _gateway(adapter, max_retries=2, retry_delay_seconds=1.0, sleeper=sleeps.append)

    with pytest.raises(LLMRateLimitError):
        gateway.complete(PROVIDER, MODEL, _request())

    assert len(adapter.calls) == 3
    assert sleeps == [1.0, 2.0]


# ── 能力三态门控 ──


def test_tools_unsupported_gate():
    adapter = FakeAdapter("openai_compatible")
    gateway = LLMGateway(
        adapters={"openai_compatible": adapter},
        capability_overrides={
            ("openai_compatible", "*"): ProviderCapabilities(tools=Capability.UNSUPPORTED)
        },
        max_retries=0,
    )

    with pytest.raises(LLMUnsupportedFeatureError):
        gateway.complete(PROVIDER, MODEL, _request(tools=[LLMToolSpec(name="save_cases", description="保存")]))

    assert adapter.calls == []  # 被门控拦截，未发起调用


def test_capability_override_replaces_baseline():
    adapter = FakeAdapter("openai_compatible")
    adapter.baseline_capabilities = ProviderCapabilities(tools=Capability.SUPPORTED)
    gateway = LLMGateway(
        adapters={"openai_compatible": adapter},
        capability_overrides={
            ("openai_compatible", "fake-model"): ProviderCapabilities(tools=Capability.UNSUPPORTED)
        },
        max_retries=0,
    )

    with pytest.raises(LLMUnsupportedFeatureError):
        gateway.complete(PROVIDER, MODEL, _request(tools=[LLMToolSpec(name="t", description="d")]))


# ── 结构化输出本地校验层 ──


def test_json_parse_success():
    gateway = _gateway(FakeAdapter("openai_compatible", results=[_result('{"a": 1}')]), max_retries=0)

    result = gateway.complete(PROVIDER, MODEL, _request(response_mode="json"))

    assert result.parsed == {"a": 1}


def test_json_parse_failure():
    gateway = _gateway(FakeAdapter("openai_compatible", results=[_result("not json")]), max_retries=0)

    with pytest.raises(LLMOutputValidationError) as exc:
        gateway.complete(PROVIDER, MODEL, _request(response_mode="json"))
    assert exc.value.error_code == "llm_output_validation"
    assert exc.value.retryable is False


class CaseModel(BaseModel):
    n: int
    password: int


def test_pydantic_parse_success():
    gateway = _gateway(FakeAdapter("openai_compatible", results=[_result('{"n": 5, "password": 123}')]), max_retries=0)

    result = gateway.complete(PROVIDER, MODEL, _request(response_mode="pydantic"), response_model=CaseModel)

    assert isinstance(result.parsed, CaseModel)
    assert result.parsed.n == 5


def test_pydantic_parse_failure_safe_summary():
    gateway = _gateway(
        FakeAdapter("openai_compatible", results=[_result('{"n": "abc", "password": "super-secret-123"}')]),
        max_retries=0,
    )

    with pytest.raises(LLMOutputValidationError) as exc:
        gateway.complete(PROVIDER, MODEL, _request(response_mode="pydantic"), response_model=CaseModel)

    message = str(exc.value)
    assert "n" in message  # 字段级位置信息
    assert "super-secret-123" not in message  # 摘要不包含输入值
    assert "abc" not in message


# ── tool_calls 只透传、不执行 ──


def test_tool_calls_passthrough_no_execution():
    tool_call = LLMToolCall(id="call_1", name="save_cases", arguments_json='{"ids": [1]}')
    gateway = _gateway(FakeAdapter("openai_compatible", results=[_result(tool_calls=[tool_call])]), max_retries=0)

    result = gateway.complete(PROVIDER, MODEL, _request())

    assert result.tool_calls == [tool_call]
    # Gateway/Adapter 均不执行工具：本测试仅断言结果透传（执行循环属于后续 Runtime）


# ── 兼容层：旧函数签名与字符串合同 ──


class FakeGateway:
    def __init__(self, error=None):
        self.calls = []
        self._error = error

    def complete(self, provider, model, request, response_model=None):
        self.calls.append((provider, model, request))
        if self._error is not None:
            raise self._error
        return LLMResult(
            content="gateway-content",
            provider_name=provider.name,
            model_name=model.model_name,
            duration_ms=1,
        )


def _seed_provider_model(db, provider_type="openai_compatible"):
    provider = LLMProvider(
        name="FakeProvider",
        provider_type=provider_type,
        base_url="https://fake-llm.invalid/v1",
        api_key="fake-key-for-test",
        status="active",
        is_deleted=False,
    )
    db.add(provider)
    db.flush()
    model = LLMModel(
        provider_id=provider.id,
        model_name="fake-model",
        display_name="Fake Model",
        temperature=0.0,
        max_tokens=2048,
        timeout_seconds=60,
        status="active",
        is_deleted=False,
    )
    db.add(model)
    db.flush()
    return provider, model


def _seed_scene(db, scene_code, model_id=None, enabled=True, prompt_template=None):
    scene = LLMSceneConfig(
        scene_code=scene_code,
        scene_name=scene_code,
        model_id=model_id,
        enabled=enabled,
        prompt_template=prompt_template,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


def test_call_llm_with_model_returns_str(monkeypatch):
    fake_gateway = FakeGateway()
    monkeypatch.setattr(llm_client_service, "_gateway", fake_gateway)

    output = llm_client_service.call_llm_with_model(PROVIDER, MODEL, "你好", temperature=0.0, max_tokens=100)

    assert output == "gateway-content"  # 字符串返回合同
    assert isinstance(output, str)
    request = fake_gateway.calls[0][2]
    assert request.messages[0].role == "user"
    assert request.messages[0].content == "你好"
    assert request.temperature == 0.0
    assert request.max_tokens == 100


def test_get_model_config_by_scene_missing_is_value_error(db_session):
    with pytest.raises(ValueError) as exc:  # ValueError 兼容合同（LLMConfigurationError 是其子类）
        llm_client_service.get_model_config_by_scene(db_session, "requirement_to_function_case")
    assert isinstance(exc.value, LLMConfigurationError)
    assert "业务场景不存在: requirement_to_function_case" in str(exc.value)


def test_get_model_config_by_scene_disabled_error(db_session):
    _seed_scene(db_session, "requirement_to_function_case", enabled=False)

    with pytest.raises(ValueError) as exc:
        llm_client_service.get_model_config_by_scene(db_session, "requirement_to_function_case")
    assert "业务场景未启用" in str(exc.value)


def test_get_model_config_by_scene_returns_config(db_session):
    provider, model = _seed_provider_model(db_session)
    _seed_scene(db_session, "requirement_to_function_case", model_id=model.id)

    config = llm_client_service.get_model_config_by_scene(db_session, "requirement_to_function_case")

    assert config["model"].id == model.id
    assert config["provider"].id == provider.id
    assert config["scene_config"].scene_code == "requirement_to_function_case"


def test_call_llm_by_scene_env_fallback_only_on_config_error(db_session, monkeypatch):
    """场景未配置 + .env 可用 → 回退 .env；Gateway 不被调用。"""
    monkeypatch.setattr(llm_client_service.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_client_service.settings, "LLM_API_KEY", "env-key")
    monkeypatch.setattr(llm_client_service.settings, "LLM_BASE_URL", "https://env-llm.invalid/v1")
    monkeypatch.setattr(llm_client_service.settings, "LLM_MODEL", "env-model")
    env_calls = []
    monkeypatch.setattr(
        llm_client_service,
        "_call_llm_with_env",
        lambda prompt, temperature=0.0, max_tokens=2048: env_calls.append(prompt) or "env-content",
    )
    fake_gateway = FakeGateway()
    monkeypatch.setattr(llm_client_service, "_gateway", fake_gateway)

    output = llm_client_service.call_llm_by_scene(db_session, "requirement_to_function_case", "提示词")

    assert output == "env-content"
    assert env_calls == ["提示词"]
    assert fake_gateway.calls == []


def test_call_llm_by_scene_no_env_fallback_on_provider_error(db_session, monkeypatch):
    """场景已配置但 Provider 调用失败 → 直接抛错，绝不回退 .env。"""
    _, model = _seed_provider_model(db_session)
    _seed_scene(db_session, "requirement_to_function_case", model_id=model.id)
    monkeypatch.setattr(llm_client_service.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_client_service.settings, "LLM_API_KEY", "env-key")
    monkeypatch.setattr(llm_client_service.settings, "LLM_BASE_URL", "https://env-llm.invalid/v1")
    monkeypatch.setattr(llm_client_service.settings, "LLM_MODEL", "env-model")

    def env_must_not_run(prompt, temperature=0.0, max_tokens=2048):
        raise AssertionError(".env 回退不应被调用")

    monkeypatch.setattr(llm_client_service, "_call_llm_with_env", env_must_not_run)
    fake_gateway = FakeGateway(error=LLMProviderError("Provider 调用失败"))
    monkeypatch.setattr(llm_client_service, "_gateway", fake_gateway)

    with pytest.raises(LLMProviderError) as exc:
        llm_client_service.call_llm_by_scene(db_session, "requirement_to_function_case", "提示词")
    assert "Provider 调用失败" in str(exc.value)
    assert len(fake_gateway.calls) == 1


def test_call_llm_by_scene_config_and_env_missing(db_session):
    """场景未配置 + .env 不可用 → 返回被冻结的合并错误消息。"""

    with pytest.raises(ValueError) as exc:
        llm_client_service.call_llm_by_scene(db_session, "requirement_to_function_case", "提示词")
    assert "未在配置中心绑定模型" in str(exc.value)
    assert "LLM_PROVIDER=mock" in str(exc.value)  # conftest 强制 mock 环境


def test_call_llm_by_scene_prompt_template_order(db_session, monkeypatch):
    _, model = _seed_provider_model(db_session)
    _seed_scene(
        db_session,
        "requirement_to_function_case",
        model_id=model.id,
        prompt_template="【场景模板】{input}",
    )
    fake_gateway = FakeGateway()
    monkeypatch.setattr(llm_client_service, "_gateway", fake_gateway)

    llm_client_service.call_llm_by_scene(db_session, "requirement_to_function_case", "原始提示词")

    final_prompt = fake_gateway.calls[0][2].messages[0].content
    assert final_prompt == "【场景模板】原始提示词"  # {input} 替换顺序不变


def test_call_llm_by_scene_template_prefix_without_input(db_session, monkeypatch):
    _, model = _seed_provider_model(db_session)
    _seed_scene(
        db_session,
        "requirement_to_function_case",
        model_id=model.id,
        prompt_template="【前缀模板】",
    )
    fake_gateway = FakeGateway()
    monkeypatch.setattr(llm_client_service, "_gateway", fake_gateway)

    llm_client_service.call_llm_by_scene(db_session, "requirement_to_function_case", "原始提示词")

    final_prompt = fake_gateway.calls[0][2].messages[0].content
    assert final_prompt == "【前缀模板】\n\n原始提示词"


def test_test_llm_model_contract_success(db_session, monkeypatch):
    _, model = _seed_provider_model(db_session)
    monkeypatch.setattr(llm_client_service, "_gateway", FakeGateway())

    result = llm_client_service.test_llm_model(db_session, model.id)

    assert result == {"success": True, "output": "gateway-content", "error": None}


def test_test_llm_model_contract_error(db_session, monkeypatch):
    _, model = _seed_provider_model(db_session)
    monkeypatch.setattr(llm_client_service, "_gateway", FakeGateway(error=LLMProviderError("HTTP 401")))

    result = llm_client_service.test_llm_model(db_session, model.id)

    assert result["success"] is False
    assert "HTTP 401" in result["error"]


def test_test_llm_model_missing_model(db_session):
    result = llm_client_service.test_llm_model(db_session, 404404)

    assert result == {"success": False, "output": "", "error": "模型不存在或已删除"}


# ── 空内容响应（T08.2：模型 200 无内容不再永久失败） ──


def _empty_result(finish_reason="stop", request_id="req-empty-1"):
    return LLMResult(
        content="",
        tool_calls=[],
        provider_name="FakeProvider",
        model_name="fake-model",
        finish_reason=finish_reason,
        request_id=request_id,
        duration_ms=1,
    )


def test_empty_content_retried_then_success():
    adapter = FakeAdapter(
        "openai_compatible",
        results=[_empty_result(), _result("最终返回 JSON")],
    )
    sleeps = []
    gateway = _gateway(adapter, max_retries=2, retry_delay_seconds=1.0, sleeper=sleeps.append)

    result = gateway.complete(PROVIDER, MODEL, _request())

    assert result.content == "最终返回 JSON"
    assert len(adapter.calls) == 2
    assert sleeps == [1.0]


def test_empty_content_exhausted_fails_with_diagnostics():
    adapter = FakeAdapter(
        "openai_compatible",
        results=[_empty_result(), _empty_result("stop", "req-empty-2"), _empty_result("stop", "req-empty-3")],
    )
    sleeps = []
    gateway = _gateway(adapter, max_retries=2, retry_delay_seconds=1.0, sleeper=sleeps.append)

    with pytest.raises(LLMProviderError) as exc:
        gateway.complete(PROVIDER, MODEL, _request())

    assert exc.value.error_code == "llm_empty_content"
    assert exc.value.retryable is True
    assert exc.value.provider_name == "FakeProvider"
    assert exc.value.model_name == "fake-model"
    assert exc.value.finish_reason == "stop"
    assert exc.value.request_id == "req-empty-3"
    assert "空内容" in str(exc.value)
    assert len(adapter.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_empty_content_with_tool_calls_not_treated_empty():
    # 有 tool_calls 而 content 为空是合法返回，不应被当作“空内容”重试
    result = LLMResult(
        content="",
        tool_calls=[LLMToolCall(id="t1", name="fake_tool", arguments_json="{}")],
        provider_name="FakeProvider",
        model_name="fake-model",
        finish_reason="tool_calls",
        duration_ms=1,
    )
    adapter = FakeAdapter("openai_compatible", results=[result])
    gateway = _gateway(adapter, max_retries=2)

    out = gateway.complete(PROVIDER, MODEL, _request())

    assert out.tool_calls[0].name == "fake_tool"
    assert len(adapter.calls) == 1
