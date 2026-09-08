"""P10.1 Context Builder 纯合同测试（确定性，零 DB/模型）。"""

from app.agents.conversation.context_builder import (
    ContextBudgetConfig,
    build_prepared_context,
    estimate_message_tokens,
    estimate_text_tokens,
)
from app.agents.conversation.messages import TextContent, ToolCall
from conversation_samples import make_assistant, make_echo_result, make_user


def _histories(n_users: int, fill: int = 40):
    out = []
    for i in range(1, n_users + 1):
        out.append(make_user(message_id=f"u{i}", text=f"用户消息 {i} " + "字" * fill))
        out.append(make_assistant(message_id=f"a{i}", content=[TextContent(text=f"回复 {i} " + "字" * fill)],
                                  stop_reason="stop"))
    return out


def test_short_conversation_no_compaction_and_current_kept():
    history = _histories(3)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u3",
        budget=ContextBudgetConfig(model_context_window=100_000))
    assert prepared.compaction_used is False
    assert prepared.context_limit is False
    assert "u3" in prepared.included_message_ids
    assert prepared.included_message_ids == [m.message_id for m in history]


def test_token_estimator_conservative_cjk_latin_mixed_json_tool():
    # CJK：≈1 token/字
    assert estimate_text_tokens("字" * 50) == 50
    # ASCII：≈ len/4
    assert estimate_text_tokens("a" * 40) == 10
    # 混合 ≥ 各自下限之和的下限
    mixed = estimate_text_tokens("登录 login " + "字" * 20)
    assert mixed >= 20 + int(10 / 4)
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("x") >= 1  # 未知输入绝不为 0
    user = make_user(text="这是一段用于估算的中文内容，绝不能因为估算为 0 而无限塞历史。")
    assert estimate_message_tokens(user) >= 1
    call = ToolCall(id="c1", name="echo", arguments={"items": [1, 2, 3], "text": "登录"})
    assistant = make_assistant(message_id="a", content=[TextContent(text="调用"), call], stop_reason="toolUse")
    assert estimate_message_tokens(assistant) >= estimate_message_tokens(make_assistant(message_id="a2", content=[TextContent(text="调用")], stop_reason="stop"))
    result = make_echo_result(call, message_id="t1")
    assert estimate_message_tokens(result) >= 1


def test_budget_semantics_reserved_not_double_deducted():
    config = ContextBudgetConfig(model_context_window=1000, reserved_output_tokens=200)
    assert config.max_input_tokens == 800
    history = _histories(2)
    prepared = build_prepared_context(messages=history, current_user_message_id="u2", budget=config)
    assert prepared.diagnostics["max_input_tokens"] == 800


def test_huge_current_user_marks_limit_without_truncation():
    huge = make_user(message_id="u1", text="字" * 30000)  # 单条远超大窗口
    history = [huge]
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u1",
        budget=ContextBudgetConfig(model_context_window=2000, reserved_output_tokens=500),
        system_sections=["[System] role=agent"])
    assert prepared.context_limit is True
    assert prepared.context_limit_reason == "current_turn_too_large"
    assert prepared.messages[-1].message_id == "u1"
    assert prepared.messages[-1].content == huge.content  # 未截断/未删除


def test_tool_pair_and_multi_call_group_integrity():
    history = []
    for i in range(1, 21):
        history.append(make_user(message_id=f"u{i}", text=f"问 {i}"))
        call = ToolCall(id=f"c{i}", name="echo", arguments={"value": f"{i}"})
        history.append(make_assistant(message_id=f"a{i}",
                                      content=[TextContent(text="调用"), call],
                                      stop_reason="toolUse"))
        history.append(make_echo_result(call, message_id=f"t{i}"))
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u20",
        budget=ContextBudgetConfig(model_context_window=60_000,
                                   reserved_output_tokens=10_000,
                                   recent_message_limit=6))
    ids = prepared.included_message_ids
    for assistant_id in [f"a{i}" for i in range(16, 21)]:
        call_in = assistant_id in ids
        result_id = f"t{assistant_id[1:]}"
        assert call_in == (result_id in ids), f"{assistant_id}/{result_id} 被拆散"


def test_multi_toolcall_exchange_group_kept_together():
    # 一个 Assistant 携带 A/B/C 三个 ToolCall，后接三个结果：同组同取舍
    history = []
    for i in range(1, 25):
        history.append(make_user(message_id=f"u{i}", text=f"问 {i}"))
        calls = [ToolCall(id=f"c{i}-{k}", name="echo", arguments={"k": k}) for k in "ABC"]
        history.append(make_assistant(message_id=f"a{i}", content=[TextContent(text="调用"), *calls],
                                      stop_reason="toolUse"))
        for call in calls:
            history.append(make_echo_result(call, message_id=f"r{call.id}"))
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u24",
        budget=ContextBudgetConfig(model_context_window=60_000,
                                   reserved_output_tokens=5_000,
                                   recent_message_limit=3))
    ids = prepared.included_message_ids
    if "a24" in ids:
        idx = next(i for i, m in enumerate(history) if m.message_id == "a24")
        following = [m.message_id for m in history[idx + 1: idx + 4]]
        assert all(result_id in ids for result_id in following), "三结果未与调用同取舍"


def test_orphan_result_flagged_not_merged_into_pair():
    history = [make_user(message_id="u1", text="hi")]
    call = ToolCall(id="c1", name="echo", arguments={})
    history.append(make_assistant(message_id="a1", content=[call], stop_reason="toolUse"))
    history.append(make_echo_result(ToolCall(id="c-wrong", name="echo", arguments={}),
                                    message_id="t-orphan"))
    prepared = build_prepared_context(messages=history, current_user_message_id="u1",
                                      budget=ContextBudgetConfig(model_context_window=100_000))
    assert prepared.diagnostics.get("malformed_exchange") == ["t-orphan"]


def test_summary_wrapper_constant_boundary():
    history = _histories(40, fill=300)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u40",
        budget=ContextBudgetConfig(model_context_window=600, reserved_output_tokens=100,
                                   recent_message_limit=12),
        summary_text="历史摘要：已完成 39 轮问答。",
        summary_through_visible_rank=78,
        system_sections=["[System] role=agent"])
    assert prepared.compaction_used is True
    assert "u40" in prepared.included_message_ids
    prompt = prepared.system_prompt()
    assert "[Conversation history summary through visible position 78]" in prompt
    assert "does not override system instructions" in prompt
    assert "read current Artifact state before modifying" in prompt
    assert [m.model_dump() for m in history] == [m.model_dump() for m in history]  # 输入不可变


def test_compaction_without_summary_flags_limit():
    history = _histories(40, fill=300)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u40",
        budget=ContextBudgetConfig(model_context_window=600, reserved_output_tokens=100,
                                   recent_message_limit=4))
    assert "u40" in prepared.included_message_ids
    assert prepared.context_limit is True
    assert prepared.context_limit_reason == "working_context_too_large"


def test_omitted_ids_recorded():
    history = _histories(20)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u20",
        budget=ContextBudgetConfig(recent_message_limit=6, model_context_window=100_000))
    assert len(prepared.included_message_ids) <= 6
    assert set(prepared.included_message_ids).isdisjoint(prepared.omitted_message_ids)
    assert "u20" in prepared.included_message_ids
