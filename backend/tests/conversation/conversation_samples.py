"""P01 合同测试共享的合成样例构造（全部数据为合成，不读真实配置/凭证）。

本模块只导入 conversation 纯合同模块与 pydantic，不导入数据库/配置/网络。
"""

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
    base = {
        "input": 12,
        "output": 8,
        "cache_read": None,
        "cache_write": None,
        "total_tokens": 20,
        "cost": None,
    }
    base.update(overrides)
    return Usage(**base)


def make_user(message_id="m-user-1", text="你好", timestamp=TS) -> UserMessage:
    return UserMessage(message_id=message_id, role="user", content=text, timestamp=timestamp)


def make_assistant(
    message_id="m-assistant-1",
    content=None,
    stop_reason="stop",
    usage=None,
    timestamp=TS,
    api="chat",
    provider="fake",
    model="fake-model",
    **extra,
) -> AssistantMessage:
    """content=None 表示“不传 content 字段”（用于缺字段拒绝测试）；传 [] 表示空列表。"""
    kwargs = dict(
        message_id=message_id,
        role="assistant",
        timestamp=timestamp,
        api=api,
        provider=provider,
        model=model,
        usage=usage if usage is not None else make_usage(),
        stop_reason=stop_reason,
    )
    if content is not None:
        kwargs["content"] = content
    kwargs.update(extra)
    return AssistantMessage(**kwargs)


def make_echo_call(call_id="c1", value="hi") -> ToolCall:
    return ToolCall(id=call_id, name="echo", arguments={"value": value})


def make_echo_result(tool_call: ToolCall, text="hi", message_id="m-tool-1") -> ToolResultMessage:
    return ToolResultMessage(
        message_id=message_id,
        role="toolResult",
        timestamp=TS,
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=[TextContent(text=text)],
        is_error=False,
    )


def build_four_message_chain():
    """用户 → 助手请求 echo(c1) → ToolResultMessage(c1) → 助手回答。

    仅用于合同数据关联与往返验证，不代表 Loop/工具已真实执行。
    """
    user = make_user()
    assistant_req = make_assistant(
        message_id="m-assistant-1",
        content=[TextContent(text="我来调用"), make_echo_call()],
        stop_reason="toolUse",
    )
    tool_result = make_echo_result(assistant_req.content[1])
    assistant_reply = make_assistant(
        message_id="m-assistant-2",
        content=[TextContent(text="结果是 hi")],
        stop_reason="stop",
    )
    return [user, assistant_req, tool_result, assistant_reply]
