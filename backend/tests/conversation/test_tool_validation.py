"""P01 合同：工具参数纯校验与结果构造（handler 永不执行）。"""

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_serializer

from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.agents.conversation.messages import TextContent, ToolCall
from app.agents.conversation.tool_validation import (
    ToolValidationError,
    build_tool_result_message,
    prepare_tool_call,
    validate_tool_calls_from_final_message,
)
from conversation_samples import make_assistant, make_echo_call


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str = Field(min_length=1)


class NoInputToolCallData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="echo", description="echo", input_model=EchoInput,
                                     handler=lambda *a: (_ for _ in ()).throw(AssertionError("handler 不应被调用"))))
    registry.register(ToolDefinition(name="no_input_model", description="no model"))
    registry.register(ToolDefinition(name="noop", description="noop", input_model=None))
    return registry


def test_valid_arguments_pass_under_stop_and_tooluse():
    registry = _registry()
    call = make_echo_call("c1", "hi")
    for reason in ("stop", "toolUse"):
        prepared = validate_tool_calls_from_final_message(
            make_assistant(content=[call], stop_reason=reason), registry
        )
        assert len(prepared) == 1
        assert prepared[0].tool_call_id == "c1"
        assert prepared[0].tool_name == "echo"
        assert prepared[0].arguments == {"value": "hi"}


def test_prepare_tool_call_unknown_tool_fails_safely():
    registry = _registry()
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x1", name="ghost", arguments={"value": "hi"}))
    assert exc.value.error_code == "unknown_tool"
    assert "ghost" not in str(exc.value)  # 固定文案，不转发动态工具名


def test_missing_input_model_fails():
    registry = _registry()
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x2", name="no_input_model", arguments={"value": "hi"}))
    assert exc.value.error_code == "invalid_config"


def test_invalid_arguments_fail_without_echoing_value():
    registry = _registry()
    secret_value = "sk-secret-xyz"
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x3", name="echo", arguments={"value": secret_value, "extra": 1}))
    assert exc.value.error_code == "invalid_arguments"
    # 固定文案，不回显原始敏感值，也不转发字段名（含未知字段名）
    assert secret_value not in str(exc.value)
    assert "extra" not in str(exc.value)
    assert "参数校验未通过" in str(exc.value)


@pytest.mark.parametrize("reason", ["length", "pending", "error", "aborted", "deferred"])
def test_incomplete_stop_reasons_never_produce_candidates(reason):
    registry = _registry()
    with pytest.raises(ToolValidationError) as exc:
        validate_tool_calls_from_final_message(
            make_assistant(content=[make_echo_call("c-len", "hi")], stop_reason=reason), registry
        )
    assert exc.value.error_code == "not_complete"


def test_partial_toolcall_delta_never_enters_validation():
    # toolcall_delta 的原始字符串参数分片属于事件层，不进入本校验入口
    from app.agents.conversation.events import AssistantEventEnvelope
    from conversation_samples import make_assistant as ma

    envelope = AssistantEventEnvelope(
        schema_version=1, session_id=1, run_id=1, message_id="m-assistant-1",
        sequence_no=1,
        event={"type": "toolcall_delta", "content_index": 0, "delta": '{"value": "h',
               "partial": ma(content=[make_echo_call("c1", "hi")])},
    )
    assert envelope.event.delta == '{"value": "h'


def test_tool_result_builder_uses_original_call_ids_and_normalizes_content():
    call = make_echo_call("c1", "hi")
    result = build_tool_result_message(
        call, message_id="m-tr", timestamp=1700000000000, is_error=False,
        content=[TextContent(text="hi")],
    )
    assert result.tool_call_id == "c1"
    assert result.tool_name == "echo"
    assert result.is_error is False
    assert result.content[0].text == "hi"

    empty = build_tool_result_message(call, message_id="m-tr2", timestamp=1, is_error=False, content=None)
    assert empty.content == []  # Pi createToolResultMessage 的 content 归一化

    failed = build_tool_result_message(call, message_id="m-tr3", timestamp=1, is_error=True,
                                       content=[TextContent(text="boom")])
    assert failed.is_error is True


def test_validation_never_invokes_handler():
    registry = _registry()
    registry.get("echo").handler  # 只读引用 handler，绝不调用
    prepared = validate_tool_calls_from_final_message(
        make_assistant(content=[make_echo_call("c1", "hi")], stop_reason="toolUse"), registry
    )
    assert prepared[0].arguments == {"value": "hi"}


def test_strict_input_model_rejects_bool_and_wrong_types():
    registry = _registry()
    with pytest.raises(ToolValidationError):
        prepare_tool_call(registry, ToolCall(id="x4", name="echo", arguments={"value": True}))
    with pytest.raises(ValidationError):
        NoInputToolCallData.model_validate({"value": 123})  # 对照：严格模型本身拒绝错误类型


# ── P01 集中修正回归：安全错误 / 无效配置 / 入口严格 ──


class LeakyValidatorInput(BaseModel):
    """合成：field_validator 把输入值写进 ValueError（模拟真实错误消息回显输入）。"""

    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _leak(cls, value: str) -> str:
        raise ValueError(f"SYNTHETIC_MARKER_LEAKED value={value}")


class PlainCountInput(BaseModel):
    """未启用 strict 的普通模型：入口的 strict=True 必须仍拒绝 "7"/True。"""

    count: int


class NotAModel:
    pass


class BoomDumpModel(BaseModel):
    """校验通过但 model_dump 抛异常的模型：入口须安全失败。"""

    count: int = 0

    def model_dump(self, *args, **kwargs):
        raise RuntimeError("RAW_BOOM_SECRET")


def _registry_with(entries):
    registry = ToolRegistry()
    for definition in entries:
        registry.register(definition)
    return registry


def test_custom_validator_leaked_value_not_in_safe_summary():
    registry = _registry_with([ToolDefinition(name="leaky", input_model=LeakyValidatorInput)])
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x1", name="leaky", arguments={"value": "hi"}))
    assert exc.value.error_code == "invalid_arguments"
    assert "SYNTHETIC_MARKER_LEAKED" not in str(exc.value)
    assert "hi" not in str(exc.value)
    assert "参数校验未通过" in str(exc.value)


@pytest.mark.parametrize("bad_model", ["not-a-model", NotAModel, None, 42])
def test_invalid_input_model_config_fails_safely(bad_model):
    registry = _registry_with([ToolDefinition(name="broken", input_model=bad_model)])
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x2", name="broken", arguments={"value": "hi"}))
    assert exc.value.error_code == "invalid_config"
    assert "AttributeError" not in str(exc.value)


def test_validation_internal_failure_has_safe_message():
    registry = _registry_with([ToolDefinition(name="boom_dump", input_model=BoomDumpModel)])
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x3", name="boom_dump", arguments={"count": 1}))
    assert exc.value.error_code == "validation_failed"
    assert "RAW_BOOM_SECRET" not in str(exc.value)


def test_entry_forces_strict_even_without_model_strict_config():
    registry = _registry_with([ToolDefinition(name="plain_count", input_model=PlainCountInput)])
    for bad_args in ({"count": "7"}, {"count": True}, {"count": 1.5}):
        with pytest.raises(ToolValidationError) as exc:
            prepare_tool_call(registry, ToolCall(id="x4", name="plain_count", arguments=bad_args))
        assert exc.value.error_code == "invalid_arguments"
    prepared = prepare_tool_call(registry, ToolCall(id="x5", name="plain_count", arguments={"count": 7}))
    assert prepared.arguments == {"count": 7}


def test_handler_never_called_on_any_path():
    calls = []
    registry = _registry_with([ToolDefinition(name="echo", input_model=EchoInput,
                                              handler=lambda *a: calls.append("handled"))])
    # 成功、参数错误、unknown、length 截断路径都不允许调用 handler
    prepare_tool_call(registry, make_echo_call("c1", "hi"))
    with pytest.raises(ToolValidationError):
        prepare_tool_call(registry, ToolCall(id="c2", name="echo", arguments={"value": 1}))
    with pytest.raises(ToolValidationError):
        prepare_tool_call(registry, ToolCall(id="c3", name="nope", arguments={}))
    assert calls == []


# ── P01 复审收尾回归：动态字段/type 归一化、序列化形状、空 ID 边界 ──

from pydantic_core import PydanticCustomError  # noqa: E402


class DictKeysInput(BaseModel):
    """动态键来自用户输入：即使键“长得像标识符”，也不是可信字段。"""

    values: dict[str, int]


class TypeMarkerInput(BaseModel):
    """合成：校验器用输入标记作为 PydanticCustomError 的错误 type。"""

    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _custom_type(cls, value: str) -> str:
        raise PydanticCustomError(
            "SYNTHETIC_CUSTOM_TYPE_MARKER",
            "bad value {value}",
            {"value": value},
        )


class SerializerStringInput(BaseModel):
    """合成：model_serializer 返回合成字符串（非字典）。"""

    count: int = 0

    @model_serializer
    def _to_string(self):
        return "SYNTHETIC_SERIALIZED_STRING"


class SerializerListInput(BaseModel):
    """合成：model_serializer 返回列表（非字典）。"""

    count: int = 0

    @model_serializer
    def _to_list(self):
        return ["SYNTHETIC_SERIALIZED_LIST"]


def test_dynamic_dict_key_marker_not_leaked():
    registry = _registry_with([ToolDefinition(name="dict_keys", input_model=DictKeysInput)])
    marker = "SYNTHETIC_PRIVATE_FIELD"
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x1", name="dict_keys",
                                             arguments={"values": {marker: "not-an-int"}}))
    assert exc.value.error_code == "invalid_arguments"
    assert marker not in str(exc.value)


def test_extra_forbidden_unknown_field_name_marker_not_leaked():
    registry = _registry_with([ToolDefinition(name="echo", input_model=EchoInput)])
    marker = "SYNTHETIC_PRIVATE_FIELD"
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x2", name="echo",
                                             arguments={"value": "ok", marker: 1}))
    assert exc.value.error_code == "invalid_arguments"
    assert marker not in str(exc.value)


def test_pydantic_custom_error_type_marker_not_leaked():
    registry = _registry_with([ToolDefinition(name="type_marker", input_model=TypeMarkerInput)])
    marker = "SYNTHETIC_CUSTOM_TYPE_MARKER"
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x3", name="type_marker", arguments={"value": "x"}))
    assert exc.value.error_code == "invalid_arguments"
    assert marker not in str(exc.value)


@pytest.mark.parametrize("model_cls,marker", [
    (SerializerStringInput, "SYNTHETIC_SERIALIZED_STRING"),
    (SerializerListInput, "SYNTHETIC_SERIALIZED_LIST"),
])
def test_non_dict_serializer_output_fails_safely(model_cls, marker):
    registry = _registry_with([ToolDefinition(name="serializer_bad", input_model=model_cls)])
    with pytest.raises(ToolValidationError) as exc:
        prepare_tool_call(registry, ToolCall(id="x4", name="serializer_bad", arguments={"count": 1}))
    assert exc.value.error_code == "validation_failed"
    assert marker not in str(exc.value)


def test_empty_call_id_never_produces_candidate_or_result():
    registry = _registry()
    empty_call = ToolCall(id="", name="echo", arguments={"value": "hi"})
    with pytest.raises(ToolValidationError) as exc:
        validate_tool_calls_from_final_message(make_assistant(content=[empty_call], stop_reason="toolUse"), registry)
    assert exc.value.error_code == "empty_call_id"
    with pytest.raises(ToolValidationError) as exc:
        build_tool_result_message(empty_call, message_id="m-tr", timestamp=1, is_error=False)
    assert exc.value.error_code == "empty_call_id"


def test_early_streaming_empty_id_block_is_representable():
    # Pi ensureToolCallBlock：toolcall_start/delta 可携带 id=""/name/{} 的临时块；
    # 本文件只验证该公有形状可经消息/事件解析（不是可执行候选）。
    from app.agents.conversation.events import AssistantEventEnvelope
    from conversation_samples import make_assistant as ma

    early = ToolCall(id="", name="echo", arguments={})
    partial = ma(message_id="m-s", content=[early], stop_reason="pending")
    for kind, extra in (
        ("toolcall_start", {}),
        ("toolcall_delta", {"delta": '{"value": "h'}),
    ):
        envelope = AssistantEventEnvelope(
            schema_version=1, session_id=1, run_id=1, message_id="m-s", sequence_no=1,
            event={"type": kind, "content_index": 0, "partial": partial, **extra},
        )
        assert envelope.event.type == kind
    assert early.id == ""  # 不伪造调用 ID
