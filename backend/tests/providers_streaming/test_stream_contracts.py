"""V2-P02：流式合同 DTO 与请求转换纯函数测试（零网络）。"""

import pytest

from app.agents.providers.streaming import (
    AttemptBudget,
    ProviderSnapshot,
    StreamContext,
    StreamError,
    StreamRequest,
    to_anthropic_system_messages_and_tools,
    to_openai_messages_and_tools,
)
from app.agents.conversation.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from tests_streaming_kit import build_four_message_history, make_assistant, make_echo_result, make_usage, make_user


def test_provider_snapshot_redacts_api_key():
    snap = ProviderSnapshot(provider_type="openai_compatible", name="p", base_url="u", api_key="sk-topsecret",
                            model_name="m")
    assert "sk-topsecret" not in repr(snap)
    assert "sk-topsecret" not in str(snap.safe_dict())


def test_conversion_openai_user_text():
    req = StreamRequest(messages=[UserMessage(message_id="u", role="user", content="你好", timestamp=1)])
    messages, _tools = to_openai_messages_and_tools(req)
    assert messages == [{"role": "user", "content": "你好"}]


@pytest.mark.parametrize("reason", ["error", "aborted"])
def test_empty_failure_record_is_not_sent_as_an_assistant_reply(reason):
    failed = make_assistant(content=[], stop_reason=reason)
    history = [make_user(text="previous question"), failed, make_user(message_id="u2", text="next question")]
    messages, _ = to_openai_messages_and_tools(StreamRequest(messages=history))
    assert [message["role"] for message in messages] == ["user", "user"]
    _, messages, _ = to_anthropic_system_messages_and_tools(StreamRequest(messages=history))
    assert [message["role"] for message in messages] == ["user", "user"]
    assert failed.content == []  # original audit record remains unchanged


def test_skipping_failure_does_not_hide_missing_tool_results():
    call = make_assistant(content=[ToolCall(id="c1", name="echo", arguments={})], stop_reason="toolUse")
    failed = make_assistant(content=[], stop_reason="error")
    with pytest.raises(StreamError, match="工具结果"):
        to_openai_messages_and_tools(StreamRequest(messages=[call, failed, make_user()]))


def test_conversion_openai_four_message_history_preserves_tool_request():
    user, assistant_req, tool_result, assistant_reply = build_four_message_history()
    messages, _ = to_openai_messages_and_tools(
        StreamRequest(messages=[user, assistant_req, tool_result, assistant_reply]))
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_calls = messages[1]["tool_calls"]
    assert tool_calls[0]["id"] == "c1"
    assert tool_calls[0]["function"]["name"] == "echo"
    assert messages[2]["tool_call_id"] == "c1"
    assert messages[2]["content"] == "hi"
    assert messages[3]["content"] == "结果是 hi"


def test_conversion_openai_rejects_mismatched_tool_result():
    user, assistant_req, tool_result, assistant_reply = build_four_message_history()
    bad = ToolResultMessage(message_id="b", role="toolResult", timestamp=1,
                            tool_call_id="c-wrong", tool_name="echo",
                            content=[TextContent(text="x")], is_error=False)
    with pytest.raises(StreamError) as exc:
        to_openai_messages_and_tools(StreamRequest(messages=[assistant_req, bad]))
    assert exc.value.error_code == "mismatched_tool_result"


def test_conversion_anthropic_four_message_history_keeps_tool_use_and_groups_result():
    user, assistant_req, tool_result, assistant_reply = build_four_message_history()
    system, messages, _ = to_anthropic_system_messages_and_tools(
        StreamRequest(system_prompt="系统策略", messages=[user, assistant_req, tool_result, assistant_reply]))
    assert system == "系统策略"
    roles = [m["role"] for m in messages]
    # user → assistant(tool_use) → user(tool_result) → assistant(final)
    assert roles == ["user", "assistant", "user", "assistant"]
    assistant_blocks = messages[1]["content"]
    assert any(block["type"] == "tool_use" and block["id"] == "c1" for block in assistant_blocks)
    result_msg = messages[2]
    tool_results = [c for c in result_msg["content"] if c["type"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_use_id"] == "c1"
    assert tool_results[0]["is_error"] is False
    # tool_result 不进 system
    assert "tool_result" not in system


def test_conversion_anthropic_rejects_tool_result_without_prior_call():
    orphan = make_echo_result("c-orphan")
    with pytest.raises(StreamError) as exc:
        to_anthropic_system_messages_and_tools(
            StreamRequest(messages=[UserMessage(message_id="u", role="user", content="hi", timestamp=1), orphan]))
    assert exc.value.error_code == "mismatched_tool_result"


def test_budget_and_context_minimal():
    budget = AttemptBudget(limit=2)
    assert budget.try_acquire() is True
    assert budget.try_acquire() is True
    assert budget.try_acquire() is False
    ctx = StreamContext(message_id="m", timestamp=123)
    assert ctx.message_id == "m" and ctx.timestamp == 123
    assert make_usage().total_tokens == 20


def test_history_rejects_intervening_user_and_duplicate_tool_result():
    call = make_assistant(content=[ToolCall(id="c1", name="echo", arguments={})], stop_reason="toolUse")
    interrupted = StreamRequest(messages=[call, make_user(), make_echo_result("c1")])
    with pytest.raises(StreamError) as exc:
        to_anthropic_system_messages_and_tools(interrupted)
    assert exc.value.error_code == "mismatched_tool_result"

    duplicate = StreamRequest(messages=[call, make_echo_result("c1"), make_echo_result("c1")])
    with pytest.raises(StreamError) as exc:
        to_anthropic_system_messages_and_tools(duplicate)
    assert exc.value.error_code == "mismatched_tool_result"
