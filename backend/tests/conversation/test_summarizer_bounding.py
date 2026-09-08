"""审计 #2 纯测试：Summarizer 输入渲染与覆盖边界（zero over-claim）。

规则：
- 渲染绝不整条丢弃 Message（超大 Tool payload 只做单条内部缩写，并保留
  tool_name/id/is_error/长度省略等语义标记）；
- 超预算时按完整 exchange 组从最新端裁减（不切散 assistant+toolResult 对），
  marker 只能推进到模型实际收到的最后一条消息；
- 单条消息必能装下（任意输入至少覆盖第一个完整组）。
"""

import pytest

from app.agents.conversation.context_builder import _split_into_exchange_units
from app.agents.conversation.messages import (
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from app.agents.conversation.summarizer import (
    render_summarizer_input,
    summarizer_coverable_messages,
)
from tests.conversation.conversation_samples import (
    make_assistant,
    make_echo_result,
    make_user,
)

TS = 1_700_000_000_000


def _result(tool_call, text="ok", message_id="tr-1", is_error=False) -> ToolResultMessage:
    return ToolResultMessage(message_id=message_id, role="toolResult", timestamp=TS,
                             tool_call_id=tool_call.id, tool_name=tool_call.name,
                             content=[TextContent(text=text)], is_error=is_error)


def _call(call_id="c1", name="echo") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments={"payload": "x" * 4000})


def test_render_never_drops_messages_and_marks_huge_payloads():
    messages = [
        make_user(message_id="u1", text="请检查登录模块 " + "字" * 2000),
        make_assistant(message_id="a1", content=[TextContent(text="查一下"), _call("c1")],
                       stop_reason="toolUse"),
        _result(_call("c1"), text="字" * 5000, message_id="r1"),
        make_assistant(message_id="a2", content=[TextContent(text="完成")]),
    ]
    rendered = render_summarizer_input(existing_summary=None, messages=messages)
    # 每条消息都有结构化表示：角色/工具语义标记存在
    assert "user: 请检查登录模块" in rendered
    assert "[toolCall name=echo id=c1" in rendered
    assert "toolResult tool=echo id=c1 is_error=False" in rendered
    assert "assistant: 完成" in rendered
    # 大型正文被缩写但带明确省略标记（消息/结果“存在”语义不丢）
    assert "省略" in rendered
    # 缩写生效：渲染长度远小于原始正文总长（7000+ 字符）
    raw_total = 2000 + 5000 + 8
    assert len(rendered) < raw_total // 2


def test_coverable_prefix_trims_whole_exchange_groups_only():
    """超预算裁减不得切散 exchange 组，chunk 必须是原序列的完整组前缀。"""
    messages = []
    for i in range(1, 21):
        messages.append(make_user(message_id=f"u{i}", text=f"问 {i} " + "字" * 40))
        if i % 3 == 0:
            calls = [_call(f"c{i}-a"), _call(f"c{i}-b")]
            messages.append(make_assistant(message_id=f"a{i}", content=[TextContent(text="查"), *calls],
                                           stop_reason="toolUse"))
            messages.append(_result(calls[0], text="字" * 30, message_id=f"r{i}-a"))
            messages.append(_result(calls[1], text="字" * 30, message_id=f"r{i}-b"))
        else:
            messages.append(make_assistant(message_id=f"a{i}",
                                           content=[TextContent(text="答 " + "字" * 40)]))

    chunk = summarizer_coverable_messages(messages, max_chars=1500)
    assert chunk, "必须至少覆盖第一个完整组"
    # chunk == 前 K 个完整组（按原序展平）——与"逐组模拟渲染装到放不下"等价
    units, _ = _split_into_exchange_units(messages)
    flattened_prefix = []
    for unit in units:
        candidate = flattened_prefix + unit
        if len(render_summarizer_input(existing_summary=None, messages=candidate)) > 1500 + 5:
            break
        flattened_prefix = candidate
    assert [m.message_id for m in chunk] == [m.message_id for m in flattened_prefix]
    # 多调用组完整性：工具调用与其结果要么同进要么同出
    chunk_ids = [m.message_id for m in chunk]
    for i in range(3, 21, 3):
        in_chunk = [mid for mid in chunk_ids if mid in {f"r{i}-a", f"r{i}-b"}]
        assert len(in_chunk) in (0, 2), f"exchange 组被切散: {in_chunk}"
    # 渲染总量在预算内
    rendered = render_summarizer_input(existing_summary=None, messages=chunk)
    assert len(rendered) <= 1500 + 5


def test_coverable_guarantees_at_least_one_complete_unit():
    messages = [
        make_user(message_id="u1", text="字" * 300),
        make_assistant(message_id="a1", content=[TextContent(text="字" * 300)]),
    ]
    chunk = summarizer_coverable_messages(messages, max_chars=10)
    assert [m.message_id for m in chunk] == ["u1"]


def test_coverable_empty_input():
    assert summarizer_coverable_messages([], max_chars=1000) == []


def test_render_budget_consistency_with_coverable():
    """coverable 的度量与 render_summarizer_input 完全一致（同一渲染规则）。"""
    messages = [make_user(message_id=f"u{i}", text="测 " + "字" * 60) for i in range(1, 60)]
    chunk = summarizer_coverable_messages(messages, max_chars=2500)
    rendered = render_summarizer_input(existing_summary=None, messages=chunk)
    assert len(rendered) <= 2500 + 5
    full = render_summarizer_input(existing_summary=None, messages=messages)
    assert len(full) > 2500
