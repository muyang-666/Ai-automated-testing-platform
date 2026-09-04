"""P01 合同：两层事件（AssistantMessageEvent / AgentEvent）与外壳测试。

partial/delta 只为合法中间形状的合同验证，不把流式数据当作完整工具调用。
"""

import pytest
from pydantic import ValidationError

from app.agents.conversation.events import (
    AgentEventEnvelope,
    AssistantEventEnvelope,
    parse_agent_event,
    parse_assistant_event,
)
from app.agents.conversation.messages import TextContent
from conversation_samples import make_assistant, make_echo_call, make_echo_result, make_user


def _partial_assistant(message_id="m-assistant-1", blocks=None, stop_reason="pending"):
    return make_assistant(message_id=message_id, content=list(blocks or []), stop_reason=stop_reason)


def _text_partial(text="你", message_id="m-assistant-1"):
    return _partial_assistant(message_id=message_id, blocks=[TextContent(text=text)])


def _tool_partial(message_id="m-assistant-1"):
    return _partial_assistant(message_id=message_id, blocks=[TextContent(text="x"), make_echo_call("c1", "hi")])


def _assistant_payload(kind, **extra):
    payload = {
        "start": {"type": "start", "partial": _partial_assistant(blocks=[])},
        "text_start": {"type": "text_start", "content_index": 0, "partial": _text_partial()},
        "text_delta": {"type": "text_delta", "content_index": 0, "delta": "你好", "partial": _text_partial("你")},
        "text_end": {"type": "text_end", "content_index": 0, "content": "你好", "partial": _text_partial("你好")},
        "toolcall_start": {"type": "toolcall_start", "content_index": 1, "partial": _tool_partial()},
        "toolcall_delta": {"type": "toolcall_delta", "content_index": 1, "delta": '{"val', "partial": _tool_partial()},
        "toolcall_end": {"type": "toolcall_end", "content_index": 1, "tool_call": make_echo_call(), "partial": _tool_partial()},
    }[kind]
    payload.update(extra)
    return payload


@pytest.mark.parametrize("kind", ["start", "text_start", "text_delta", "text_end", "toolcall_start", "toolcall_delta", "toolcall_end"])
def test_each_assistant_partial_event_valid_with_envelope(kind):
    envelope = AssistantEventEnvelope(
        schema_version=1, session_id=1, run_id=1,
        message_id="m-assistant-1", sequence_no=1,
        tool_call_id="c1" if kind == "toolcall_end" else None,
        event=_assistant_payload(kind),
    )
    assert envelope.event.type == kind


def test_done_and_error_reason_consistency():
    done = parse_assistant_event({
        "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-done",
        "sequence_no": 2,
        "event": {"type": "done", "reason": "stop",
                  "message": make_assistant(message_id="m-done", content=[TextContent(text="完成")], stop_reason="stop")},
    })
    assert done.event.reason == "stop"
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-done", "sequence_no": 3,
            "event": {"type": "done", "reason": "stop",
                      "message": make_assistant(message_id="m-done", content=[TextContent(text="截断")], stop_reason="length")},
        })
    ok_error = parse_assistant_event({
        "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-err", "sequence_no": 4,
        "event": {"type": "error", "reason": "aborted",
                  "error": make_assistant(message_id="m-err", content=[], stop_reason="aborted")},
    })
    assert ok_error.event.reason == "aborted"


def test_inner_events_are_strict_and_forbid_extra():
    # content_index=True 不得被静默转换成 0
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1", "sequence_no": 1,
            "event": {"type": "text_delta", "content_index": True, "delta": "x", "partial": _text_partial()},
        })
    # delta=bytes 不得被隐式转 str
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1", "sequence_no": 1,
            "event": {"type": "text_delta", "content_index": 0, "delta": b"x", "partial": _text_partial()},
        })
    # 未声明字段必须拒绝（不只最外层严格）
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1", "sequence_no": 1,
            "event": {"type": "text_delta", "content_index": 0, "delta": "x", "partial": _text_partial(), "bogus": 1},
        })
    # content_index 超出 partial 内容块范围 / 指向错误块类型
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1", "sequence_no": 1,
            "event": {"type": "text_end", "content_index": 5, "content": "x", "partial": _text_partial()},
        })
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1", "sequence_no": 1,
            "event": {"type": "toolcall_end", "content_index": 0, "tool_call": make_echo_call(), "partial": _tool_partial()},
        })


def test_toolcall_end_requires_partial_snapshot_equality():
    # partial 同一索引里是 c2，事件宣告 c1 → 矛盾拒绝
    mismatched_partial = _partial_assistant(blocks=[TextContent(text="x"), make_echo_call("c2", "other")])
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1",
            "sequence_no": 1, "tool_call_id": "c1",
            "event": {"type": "toolcall_end", "content_index": 1, "tool_call": make_echo_call("c1", "hi"),
                      "partial": mismatched_partial},
        })
    # 一致快照 + 外壳 ID 一致 → 通过
    ok = parse_assistant_event({
        "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-assistant-1",
        "sequence_no": 1, "tool_call_id": "c1",
        "event": _assistant_payload("toolcall_end"),
    })
    assert ok.event.tool_call.id == "c1"


def test_envelope_association_checks():
    # partial.message_id 与外壳不一致 → 拒绝
    with pytest.raises(ValidationError):
        AssistantEventEnvelope(
            schema_version=1, session_id=1, run_id=1, message_id="other-id",
            sequence_no=1, event=_assistant_payload("text_start"),
        )
    # sequence_no 非法 → 拒绝
    with pytest.raises(ValidationError):
        AssistantEventEnvelope(
            schema_version=1, session_id=1, run_id=1, message_id="m-assistant-1",
            sequence_no=0, event=_assistant_payload("start"),
        )


def test_unknown_and_disallowed_event_types_rejected():
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-x",
            "sequence_no": 1,
            "event": {"type": "thinking_start", "content_index": 0, "partial": make_assistant(content=[])},
        })
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-x",
            "sequence_no": 1,
            "event": {"type": "done", "reason": "pending", "message": make_assistant(content=[], stop_reason="stop")},
        })


def _agent_event_payload(kind, message=None, **extra):
    user = message or make_user(message_id="m-user")
    assistant_snapshot = make_assistant(
        message_id="m-a1", content=[TextContent(text="你")], stop_reason="pending"
    )
    nested = {"type": "text_delta", "content_index": 0, "delta": "好",
              "partial": make_assistant(message_id="m-a1", content=[TextContent(text="你")], stop_reason="pending")}
    base = {
        "agent_start": {"type": "agent_start"},
        "agent_end": {"type": "agent_end", "messages": [user]},
        "turn_start": {"type": "turn_start"},
        "turn_end": {"type": "turn_end", "message": assistant_snapshot, "tool_results": []},
        "message_start": {"type": "message_start", "message": user},
        "message_update": {"type": "message_update", "message": assistant_snapshot,
                           "assistant_message_event": nested},
        "message_end": {"type": "message_end", "message": user},
        "tool_execution_start": {"type": "tool_execution_start", "tool_call_id": "c1", "tool_name": "echo", "args": {"value": "hi"}},
        "tool_execution_update": {"type": "tool_execution_update", "tool_call_id": "c1", "tool_name": "echo", "args": {}, "partial_result": {"done": False}},
        "tool_execution_end": {"type": "tool_execution_end", "tool_call_id": "c1", "tool_name": "echo", "result": {"out": "hi"}, "is_error": False},
    }[kind]
    base.update(extra)
    return base


@pytest.mark.parametrize("kind", ["agent_start", "agent_end", "turn_start", "turn_end",
                                  "message_start", "message_update", "message_end",
                                  "tool_execution_start", "tool_execution_update", "tool_execution_end"])
def test_each_agent_event_valid_with_envelope(kind):
    message_id = {"turn_end": "m-a1", "message_update": "m-a1",
                  "message_start": "m-user", "message_end": "m-user"}.get(kind)
    tool_call_id = "c1" if kind.startswith("tool_execution_") else None
    envelope = AgentEventEnvelope(
        schema_version=1, session_id=1, run_id=1,
        message_id=message_id, tool_call_id=tool_call_id, sequence_no=5,
        event=_agent_event_payload(kind),
    )
    assert envelope.event.type == kind


def test_message_update_must_reference_same_assistant_message():
    # user 快照嵌套另一 assistant 流事件 → 拒绝（修正原错误正例）
    with pytest.raises(ValidationError):
        parse_agent_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-user", "sequence_no": 1,
            "event": {"type": "message_update", "message": make_user(message_id="m-user"),
                      "assistant_message_event": {"type": "text_delta", "content_index": 0, "delta": "x",
                                                  "partial": make_assistant(message_id="m-a1", content=[TextContent(text="x")], stop_reason="pending")}},
        })
    # 外层 assistant 快照与嵌套 partial 不是同一 message_id → 拒绝
    with pytest.raises(ValidationError):
        parse_agent_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-a1", "sequence_no": 1,
            "event": {"type": "message_update",
                      "message": make_assistant(message_id="m-a1", content=[], stop_reason="pending"),
                      "assistant_message_event": {"type": "text_delta", "content_index": 0, "delta": "x",
                                                  "partial": make_assistant(message_id="m-other", content=[TextContent(text="x")], stop_reason="pending")}},
        })
    # 一致 → 通过
    ok = parse_agent_event({
        "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-a1", "sequence_no": 1,
        "event": _agent_event_payload("message_update"),
    })
    assert ok.event.assistant_message_event.partial.message_id == "m-a1"


def test_turn_end_tool_results_required_but_empty_allowed():
    with pytest.raises(ValidationError):
        parse_agent_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-a1", "sequence_no": 1,
            "event": {"type": "turn_end", "message": make_assistant(message_id="m-a1", content=[], stop_reason="stop")},
        })
    ok = parse_agent_event({
        "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-a1", "sequence_no": 1,
        "event": {"type": "turn_end", "message": make_assistant(message_id="m-a1", content=[], stop_reason="stop"),
                  "tool_results": []},
    })
    assert ok.event.tool_results == []


def test_agent_event_lifecycle_and_association_rules():
    with pytest.raises(ValidationError):
        AgentEventEnvelope(schema_version=1, session_id=1, run_id=1, message_id="m-user",
                           sequence_no=1, event=_agent_event_payload("agent_start"))
    with pytest.raises(ValidationError):
        AgentEventEnvelope(schema_version=1, session_id=1, run_id=1, message_id="m-other",
                           sequence_no=1, event=_agent_event_payload("message_start"))
    with pytest.raises(ValidationError):
        AgentEventEnvelope(schema_version=1, session_id=1, run_id=1,
                           sequence_no=1, event=_agent_event_payload("tool_execution_start"))


def test_agent_end_with_tool_result_messages():
    tool_result = make_echo_result(make_echo_call(), message_id="m-tool")
    envelope = AgentEventEnvelope(
        schema_version=1, session_id=1, run_id=1, sequence_no=9,
        event={"type": "agent_end", "messages": [make_user(), tool_result]},
    )
    assert envelope.event.messages[1].tool_call_id == "c1"


def test_parse_agent_event_rejects_unknown_type():
    with pytest.raises(ValidationError):
        parse_agent_event({"schema_version": 1, "session_id": 1, "run_id": 1,
                           "sequence_no": 1, "event": {"type": "mystery_event"}})


# ── P01 复审收尾：早期空 ID partial 与 toolcall_end 完成门禁 ──


def test_streaming_progression_empty_id_to_complete():
    # Pi ensureToolCallBlock：toolcall_start/delta 允许 id="" 的临时块；
    # ID/参数到齐后以 toolcall_end 收束；外壳在 ID 可得时才核对。
    early = {"id": "", "name": "echo", "arguments": {}}
    start_payload = {"type": "toolcall_start", "content_index": 0,
                     "partial": make_assistant(message_id="m-s", content=[{"type": "toolCall", **early}],
                                               stop_reason="pending")}
    parse_assistant_event({"schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-s",
                           "sequence_no": 1, "event": start_payload})
    delta_payload = {"type": "toolcall_delta", "content_index": 0, "delta": '{"value": "hi',
                     "partial": make_assistant(message_id="m-s", content=[{"type": "toolCall", **early}],
                                               stop_reason="pending")}
    parse_assistant_event({"schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-s",
                           "sequence_no": 2, "event": delta_payload})
    end_payload = {"type": "toolcall_end", "content_index": 0, "tool_call": make_echo_call(),
                   "partial": make_assistant(message_id="m-s", content=[make_echo_call()],
                                             stop_reason="pending")}
    parse_assistant_event({"schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-s",
                           "sequence_no": 3, "tool_call_id": "c1", "event": end_payload})


def test_toolcall_end_with_empty_id_rejected():
    empty_block = {"id": "", "name": "echo", "arguments": {}}
    with pytest.raises(ValidationError):
        parse_assistant_event({
            "schema_version": 1, "session_id": 1, "run_id": 1, "message_id": "m-s",
            "sequence_no": 1, "tool_call_id": "",
            "event": {"type": "toolcall_end", "content_index": 0,
                      "tool_call": empty_block,
                      "partial": make_assistant(message_id="m-s", content=[empty_block], stop_reason="pending")},
        })
