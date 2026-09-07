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
    """构造 user/assistant(text) 交替历史（无工具）。"""
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
        budget=ContextBudgetConfig(context_token_budget=100_000))
    assert prepared.compaction_used is False
    assert prepared.context_limit is False
    assert "u3" in prepared.included_message_ids
    assert prepared.included_message_ids == [m.message_id for m in history]  # 全量进入


def test_tool_pair_integrity_when_window_cuts_between_pair():
    # 构造 30 个工具交换对，把窗口打到只够保留尾部（含最后一对）
    history = []
    for i in range(1, 31):
        history.append(make_user(message_id=f"u{i}", text=f"问 {i}"))
        call = ToolCall(id=f"c{i}", name="echo", arguments={"value": f"{i}"})
        history.append(make_assistant(message_id=f"a{i}",
                                      content=[TextContent(text="调用"), call],
                                      stop_reason="toolUse"))
        history.append(make_echo_result(call, message_id=f"t{i}"))
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u30",
        budget=ContextBudgetConfig(context_token_budget=60_000,
                                   reserved_output_tokens=10_000,
                                   recent_message_limit=6))
    ids = prepared.included_message_ids
    # 如果 a30(含 c30) 保留，则 t30 必须同组保留；如果被裁，二者都不在
    if "a30" in ids:
        assert "t30" in ids
    # 组内不拆散：任何保留 assistant 的工具调用，其结果消息也保留（或双双省略）
    for assistant_id in [f"a{i}" for i in range(26, 31)]:
        call_in = assistant_id in ids
        result_id = f"t{assistant_id[1:]}"
        assert call_in == (result_id in ids), f"{assistant_id}/{result_id} 被拆散"


def test_compaction_over_budget_uses_summary_and_preserves_messages():
    history = _histories(40, fill=300)  # 40 对长消息（触发预算压缩）
    before_texts = [m.model_dump() for m in history]
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u40",
        budget=ContextBudgetConfig(context_token_budget=600, reserved_output_tokens=100,
                                   recent_message_limit=12),
        summary_text="历史摘要：已完成 39 轮问答。",
        summary_through_sequence=78,
        system_sections=["[System] role=agent"])
    assert prepared.compaction_used is True
    assert prepared.summary_text is not None
    assert prepared.estimated_tokens <= 600
    assert "u40" in prepared.included_message_ids  # current turn 保留
    # 持久化消息未被修改/删除（pure 输入不可变）
    assert [m.model_dump() for m in history] == before_texts
    assert "39" in prepared.system_prompt()  # summary 块进入 system 侧


def test_summary_fallback_flag_without_summary():
    # 无 summary 且超预算：保留当前组并标记 context_limit 由调用方决策
    history = _histories(40, fill=300)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u40",
        budget=ContextBudgetConfig(context_token_budget=300, reserved_output_tokens=100,
                                   recent_message_limit=4))
    assert "u40" in prepared.included_message_ids
    assert prepared.context_limit is True


def test_token_estimation_unknown_is_conservative_not_zero():
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("你好") >= 1
    msg = make_user(text="这是一段用于估算的中文内容，绝不能因为估算为 0 而无限塞历史。")
    assert estimate_message_tokens(msg) >= 1


def test_omitted_ids_recorded():
    history = _histories(20)
    prepared = build_prepared_context(
        messages=history, current_user_message_id="u20",
        budget=ContextBudgetConfig(recent_message_limit=6, context_token_budget=100_000))
    assert len(prepared.included_message_ids) <= 6
    assert set(prepared.included_message_ids).isdisjoint(prepared.omitted_message_ids)
    assert "u20" in prepared.included_message_ids
