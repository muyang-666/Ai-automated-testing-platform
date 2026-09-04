"""P01 合同：合成“用户 → 工具请求 → 工具结果 → 回复”消息/事件样例。

按 Pi runLoop 的 turn 语义组织（两次模型响应 = 两个 Pi turn）：
- 第一个 Pi turn：用户消息 + 助手工具请求响应及其工具结果
  （turn_end.message = 当轮助手消息，tool_results 单列结果；
  工具结果消息在 tool_execution_end 之后、turn_end 之前有自己的
  message_start/message_end，对应 Pi emitToolResultMessage）；
- 第二个 Pi turn：最终助手回复（tool_results=[]）。
测试只验证数据构造、关键先后与关联，明确不代表真实 Loop 执行；
工具从未真实执行。
"""

import json

from app.agents.conversation.events import parse_assistant_event, parse_agent_event
from app.agents.conversation.messages import Message, parse_message
from conversation_samples import build_four_message_chain


def _chain():
    user, assistant_req, tool_result, assistant_reply = build_four_message_chain()
    return user, assistant_req, tool_result, assistant_reply


def test_four_message_chain_associations_and_roundtrip():
    user, assistant_req, tool_result, assistant_reply = _chain()

    requested_call = assistant_req.content[1]
    assert requested_call.id == "c1"
    assert tool_result.tool_call_id == requested_call.id
    assert tool_result.tool_name == requested_call.name

    raw = [m.model_dump_json() for m in (user, assistant_req, tool_result, assistant_reply)]
    parsed: list[Message] = [parse_message(json.loads(chunk)) for chunk in raw]
    assert [p.message_id for p in parsed] == [m.message_id for m in (user, assistant_req, tool_result, assistant_reply)]
    assert parsed[1].content[1].id == "c1"
    assert parsed[2].tool_call_id == "c1"
    assert parsed[3].content[0].text == "结果是 hi"


def _two_turn_event_payloads(user, assistant_req, tool_result, assistant_reply):
    """按 Pi turn 语义的事件载荷序列（顺序是契约的一部分）。"""
    return [
        {"type": "agent_start"},
        # 第一个 Pi turn：用户消息 → 助手工具请求 → 工具执行 → 工具结果消息 → turn_end
        {"type": "turn_start"},
        {"type": "message_start", "message": user},
        {"type": "message_end", "message": user},
        {"type": "message_start", "message": assistant_req},
        {"type": "message_end", "message": assistant_req},
        {"type": "tool_execution_start", "tool_call_id": "c1", "tool_name": "echo", "args": {"value": "hi"}},
        {"type": "tool_execution_end", "tool_call_id": "c1", "tool_name": "echo", "result": {"out": "hi"}, "is_error": False},
        {"type": "message_start", "message": tool_result},
        {"type": "message_end", "message": tool_result},
        {"type": "turn_end", "message": assistant_req, "tool_results": [tool_result]},
        # 第二个 Pi turn：最终助手回复（无工具）
        {"type": "turn_start"},
        {"type": "message_start", "message": assistant_reply},
        {"type": "message_end", "message": assistant_reply},
        {"type": "turn_end", "message": assistant_reply, "tool_results": []},
        {"type": "agent_end", "messages": [user, assistant_req, tool_result, assistant_reply]},
    ]


def test_two_turn_events_order_and_associations():
    user, assistant_req, tool_result, assistant_reply = _chain()
    payloads = _two_turn_event_payloads(user, assistant_req, tool_result, assistant_reply)

    parsed = []
    for index, event in enumerate(payloads, start=1):
        kind = event["type"]
        message_id = None
        tool_call_id = None
        if kind in {"message_start", "message_end"}:
            message_id = event["message"].message_id
        elif kind == "turn_end":
            message_id = event["message"].message_id
        elif kind.startswith("tool_execution_"):
            tool_call_id = event["tool_call_id"]
        envelope = parse_agent_event({
            "schema_version": 1, "session_id": 7, "run_id": 3,
            "message_id": message_id, "tool_call_id": tool_call_id,
            "sequence_no": index, "event": event,
        })
        parsed.append(envelope.event)

    def first(pred):
        return next(i for i, event in enumerate(parsed) if pred(event))

    def message_event(message_id, kind):
        return first(lambda e: e.type == kind and e.message.message_id == message_id)

    i_ts1 = first(lambda e: e.type == "turn_start")
    i_te1 = first(lambda e: e.type == "turn_end")
    i_ts2 = next(i for i, e in enumerate(parsed) if e.type == "turn_start" and i > i_te1)
    i_te2 = next(i for i, e in enumerate(parsed) if e.type == "turn_end" and i > i_ts2)

    # 期望序列：agent_start → turn1 → user(起/止) → 请求助手(起/止) → 工具执行(起/止)
    #   → tool_result(起/止) → turn_end1 → turn2 → 回复(起/止) → turn_end2 → agent_end
    seq = [
        first(lambda e: e.type == "agent_start"),
        i_ts1,
        message_event(user.message_id, "message_start"),
        message_event(user.message_id, "message_end"),
        message_event(assistant_req.message_id, "message_start"),
        message_event(assistant_req.message_id, "message_end"),
        first(lambda e: e.type == "tool_execution_start"),
        first(lambda e: e.type == "tool_execution_end"),
        message_event(tool_result.message_id, "message_start"),
        message_event(tool_result.message_id, "message_end"),
        i_te1,
        i_ts2,
        message_event(assistant_reply.message_id, "message_start"),
        message_event(assistant_reply.message_id, "message_end"),
        i_te2,
        len(parsed) - 1,  # agent_end
    ]
    assert all(seq[i] < seq[i + 1] for i in range(len(seq) - 1)), seq

    ends = [event for event in parsed if event.type == "turn_end"]
    assert ends[0].message.message_id == assistant_req.message_id
    assert [r.tool_call_id for r in ends[0].tool_results] == ["c1"]
    assert ends[1].message.message_id == assistant_reply.message_id
    assert ends[1].tool_results == []

    assert parsed[-1].type == "agent_end"
    assert [m.message_id for m in parsed[-1].messages] == [user.message_id, assistant_req.message_id,
                                                           tool_result.message_id, assistant_reply.message_id]


def test_done_event_for_final_reply():
    _, _, _, assistant_reply = _chain()
    done = parse_assistant_event({
        "schema_version": 1, "session_id": 7, "run_id": 3,
        "message_id": assistant_reply.message_id, "sequence_no": 100,
        "event": {"type": "done", "reason": "stop", "message": assistant_reply},
    })
    assert done.event.message.content[0].text == "结果是 hi"


def test_chain_sample_marks_data_only_not_execution():
    user, assistant_req, tool_result, assistant_reply = _chain()
    assert [m.role for m in (user, assistant_req, tool_result, assistant_reply)] == \
           ["user", "assistant", "toolResult", "assistant"]
    assert assistant_req.stop_reason == "toolUse"  # 工具请求不是成功结束
    assert tool_result.is_error is False
