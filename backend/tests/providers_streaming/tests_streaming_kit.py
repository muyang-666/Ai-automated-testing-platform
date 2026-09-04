"""P02 流式测试共享合成样例（全部合成数据，零网络/凭证）。"""

from app.agents.conversation.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)

TS = 1_700_000_000_000


def make_usage(**overrides):
    base = {"input": 12, "output": 8, "cache_read": None, "cache_write": None,
            "total_tokens": 20, "cost": None}
    base.update(overrides)
    return Usage(**base)


def make_assistant(message_id="m-a", content=None, stop_reason="stop", usage=None,
                   timestamp=TS, api="chat", provider="fake", model="fake-model", **extra):
    kwargs = dict(message_id=message_id, role="assistant", timestamp=timestamp,
                  api=api, provider=provider, model=model,
                  usage=usage if usage is not None else make_usage(), stop_reason=stop_reason)
    if content is not None:
        kwargs["content"] = content
    kwargs.update(extra)
    return AssistantMessage(**kwargs)


def make_user(message_id="m-u", text="你好", timestamp=TS):
    return UserMessage(message_id=message_id, role="user", content=text, timestamp=timestamp)


def make_echo_result(tool_call_id="c1", text="hi", message_id="m-tr", is_error=False, timestamp=TS):
    return ToolResultMessage(
        message_id=message_id, role="toolResult", timestamp=timestamp,
        tool_call_id=tool_call_id, tool_name="echo",
        content=[TextContent(text=text)], is_error=is_error,
    )


def build_four_message_history():
    """user → assistant(文本+echo(c1)) → ToolResult(c1) → assistant(回复)。"""
    user = make_user()
    call = ToolCall(id="c1", name="echo", arguments={"value": "hi"})
    assistant_req = make_assistant(
        message_id="m-a-req",
        content=[TextContent(text="我来调用"), call],
        stop_reason="toolUse",
    )
    tool_result = make_echo_result("c1")
    assistant_reply = make_assistant(message_id="m-a-reply", content=[TextContent(text="结果是 hi")], stop_reason="stop")
    return user, assistant_req, tool_result, assistant_reply
