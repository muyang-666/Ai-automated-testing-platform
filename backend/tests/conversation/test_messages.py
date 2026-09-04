"""P01 合同：消息/用量/JSON 边界的构造与往返测试（合成数据）。"""

import pytest
from pydantic import ValidationError

from app.agents.conversation.messages import (
    AssistantMessage,
    DeferredHandle,
    TextContent,
    ToolResultMessage,
    Usage,
    UserMessage,
    parse_message,
)
from app.agents.conversation.contracts import ConversationTurn, ModelTurn
from conversation_samples import make_assistant, make_echo_call, make_usage


# ── 构造与往返 ──


def test_user_plain_text_roundtrip_keeps_id_and_content():
    user = UserMessage(message_id="m-u1", role="user", content="你好", timestamp=1700000000000)
    data = user.model_dump()
    parsed = parse_message(data)
    assert parsed.role == "user"
    assert parsed.message_id == "m-u1"
    assert parsed.content == "你好"  # 正文是普通文本，不是 JSON


def test_assistant_mixed_content_roundtrip_preserves_order():
    assistant = make_assistant(
        message_id="m-a1",
        content=[TextContent(text="先文本"), make_echo_call("c1"), make_echo_call("c2", "again")],
        stop_reason="toolUse",
    )
    parsed = parse_message(assistant.model_dump())
    assert parsed.message_id == "m-a1"
    kinds = [item.type for item in parsed.content]
    assert kinds == ["text", "toolCall", "toolCall"]
    assert parsed.content[1].id == "c1" and parsed.content[2].id == "c2"


def test_message_union_rejects_unknown_role():
    payload = {"message_id": "x", "schema_version": 1, "role": "system", "content": "hi", "timestamp": 1}
    with pytest.raises(ValidationError):
        parse_message(payload)


# ── schema_version / content 必填与空列表 ──


@pytest.mark.parametrize("bad", [True, 1.0, "1", 2])
def test_schema_version_rejects_true_float_string_two(bad):
    with pytest.raises(ValidationError):
        make_assistant(content=[TextContent(text="x")], schema_version=bad)


def test_schema_version_int_one_accepted():
    msg = make_assistant(content=[TextContent(text="x")], schema_version=1)
    assert msg.schema_version == 1


def test_assistant_content_missing_rejected_empty_allowed():
    with pytest.raises(ValidationError):
        # 不传 content 字段 → 缺必填字段被拒绝
        AssistantMessage(
            message_id="m", role="assistant", timestamp=1700000000000,
            api="chat", provider="fake", model="fake-model",
            usage=make_usage(), stop_reason="stop",
        )
    empty = make_assistant(content=[], stop_reason="length")
    assert empty.content == []


def test_tool_result_content_missing_rejected_empty_allowed():
    base = dict(message_id="m-tr", role="toolResult", timestamp=1700000000000,
                tool_call_id="c1", tool_name="echo", is_error=False)
    with pytest.raises(ValidationError):
        ToolResultMessage(**base)  # 缺 content 字段被拒绝
    ok = ToolResultMessage(**base, content=[])
    assert ok.content == []


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        make_assistant(content=[TextContent(text="x")], extra_field="boom")  # type: ignore[call-arg]


# ── Usage：None 与 0 区分、负数/错误类型/bool/NaN/Infinity ──


def test_usage_explicit_none_distinct_from_zero():
    usage = make_usage(input=0, output=None, total_tokens=0)
    assert usage.input == 0
    assert usage.output is None  # 未知不是 0
    assert usage.total_tokens == 0


@pytest.mark.parametrize("field", ["input", "output", "cache_read", "cache_write", "total_tokens"])
def test_usage_negative_counts_rejected(field):
    kwargs = {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1, "total_tokens": 1, "cost": None}
    kwargs[field] = -1
    with pytest.raises(ValidationError):
        Usage(**kwargs)


@pytest.mark.parametrize("bad", [True, 1.5, "10", object()])
def test_usage_bool_float_string_rejected(bad):
    with pytest.raises(ValidationError):
        make_usage(input=bad)


def test_usage_cost_non_finite_and_negative_rejected():
    from app.agents.conversation.messages import UsageCost

    with pytest.raises(ValidationError):
        UsageCost(input=float("nan"), output=1, cache_read=1, cache_write=1, total=1)
    with pytest.raises(ValidationError):
        UsageCost(input=1, output=-0.5, cache_read=1, cache_write=1, total=1)
    ok = UsageCost(input=1.5, output=0, cache_read=None, cache_write=None, total=None)
    assert ok.input == 1.5


def test_usage_required_fields_must_be_present():
    with pytest.raises(ValidationError):
        Usage(output=1)  # 缺 input/cache_read/.../cost


# ── DeferredHandle.data JSON 边界 ──


def test_deferred_data_accepts_json_and_rejects_tuple_non_json():
    ok = DeferredHandle(provider="openai", model_id="m", api="responses", id="r1",
                        data={"items": [1, "a", None, True], "nested": {"k": "v"}})
    assert ok.data["items"][1] == "a"
    for bad in [(1, 2), {"a", "b"}, b"bytes", object()]:
        with pytest.raises(ValidationError):
            DeferredHandle(provider="openai", model_id="m", api="responses", id="r2", data=bad)


def test_deferred_expires_and_poll_reject_bool():
    with pytest.raises(ValidationError):
        DeferredHandle(provider="openai", model_id="m", api="responses", id="r3", expires_at=True)
    with pytest.raises(ValidationError):
        DeferredHandle(provider="openai", model_id="m", api="responses", id="r3", poll_after_ms=1.0)


# ── 最小元数据 ──


def test_conversation_turn_and_model_turn_roundtrip():
    turn = ConversationTurn(session_id=1, run_id=2, user_message_id="m-u1")
    model = ModelTurn(run_id=2, model_turn_id="t1", model_turn_index=1)
    assert turn.model_dump()["run_id"] == 2
    assert model.model_turn_index == 1
    with pytest.raises(ValidationError):
        ConversationTurn(session_id=0, run_id=1, user_message_id="m")  # session 必须为正整数
