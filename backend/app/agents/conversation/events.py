"""V2-P01 阶段收尾：翻译 Pi 两层事件（AssistantMessageEvent 与 AgentEvent）及应用层外壳。

- AssistantMessageEvent：助手消息流事件。start / text_start / text_delta /
  text_end / toolcall_start / toolcall_delta / toolcall_end / done / error。
  thinking_* 事件不进入当前公开/持久化合同，未知 type 一律拒绝；
  不保存隐藏思维链。done.reason 只允许 stop/length/toolUse/deferred，
  error.reason 只允许 error/aborted，且与所携带助手消息的 stop_reason 一致。
  参数分片 delta 只作为字符串保存，不补齐、不解析为可执行参数。
- AgentEvent：执行层事件。agent_start/end、turn_start/end、
  message_start/update/end、tool_execution_start/update/end。消息与工具
  结果复用 conversation.messages 类型；进度事件不进入模型历史。
- 应用层外壳：AssistantEventEnvelope / AgentEventEnvelope 携带
  schema_version、session_id、run_id、message_id、tool_call_id、sequence_no。
  Session/Run 用现有正整数 ID；消息/调用用字符串 ID。按事件类型约束
  message_id/tool_call_id，能由内层载荷核对关联的必须一致；无单一消息的
  生命周期事件允许 message_id 为空。sequence_no 只校验（正整数）不分配，
  不实现 max+1/数据库/SSE。

一致性约束（P01 集中修正）：
- 每个内部事件模型与外壳同样 strict + extra=forbid，不接受静默类型转换或
  多余字段；
- 带 content_index 的流事件要求 partial 中该索引处存在同类型内容块
  （text_* → TextContent；toolcall_* → ToolCall），toolcall_end 的完整
  ToolCall 必须与 partial 快照一致，外壳可核对 ID 一致；
- message_update 的外层消息必须是 assistant，且与嵌套
  AssistantMessageEvent 的 partial/最终消息指向同一 message_id；
- turn_end.toolResults 为必填字段（允许空列表），缺失按 Pi 视为非法。

参考来源（只读，D:\\pi 固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6）：
- packages/ai/src/types.ts：AssistantMessageEvent；
- packages/agent/src/types.ts：AgentEvent / AgentTool / AgentToolResult；
- packages/agent/src/agent-loop.ts：runLoop / streamAssistantResponse 的事件
  先后与 turn_end(toolResults) 载荷。
轻适配：Python snake_case（content_index ← contentIndex、tool_call_id ←
toolCallId、tool_results ← toolResults、assistant_message_event ←
assistantMessageEvent、partial_result ← partialResult、is_error ← isError）；
事件 type 名保留上游原值。MIT License（Copyright (c) 2025 Mario Zechner，
完整文本见 messages.py 模块头）。
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.agents.conversation.messages import (
    AssistantMessage,
    Message,
    TextContent,
    ToolCall,
    ToolResultMessage,
)

# done / error 各自允许的 reason（Pi Extract 后的子集）
DoneReason = Literal["stop", "length", "toolUse", "deferred"]
ErrorReason = Literal["error", "aborted"]

_STRICT_FORBID = ConfigDict(extra="forbid", strict=True)


def _require_block(partial: AssistantMessage, content_index: int, want_type: str) -> BaseModel:
    """流事件要求 partial.content[content_index] 存在且为期望块类型。"""
    blocks = partial.content
    if not 0 <= content_index < len(blocks):
        raise ValueError(f"content_index={content_index} 超出 partial 内容块范围")
    block = blocks[content_index]
    if getattr(block, "type", None) != want_type:
        raise ValueError(f"content_index={content_index} 指向 {getattr(block, 'type', '?')} 块，期望 {want_type}")
    return block


# ── AssistantMessageEvent（ai/types.ts）──


class AssistantStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["start"] = Field(default="start", description="事件类型，固定 start")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")


class AssistantTextStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["text_start"] = Field(default="text_start", description="事件类型，固定 text_start")
    content_index: int = Field(ge=0, description="文本内容块索引（Pi contentIndex）")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _index_matches_text_block(self):
        _require_block(self.partial, self.content_index, "text")
        return self


class AssistantTextDeltaEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["text_delta"] = Field(default="text_delta", description="事件类型，固定 text_delta")
    content_index: int = Field(ge=0, description="文本内容块索引")
    delta: str = Field(description="文本增量")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _index_matches_text_block(self):
        _require_block(self.partial, self.content_index, "text")
        return self


class AssistantTextEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["text_end"] = Field(default="text_end", description="事件类型，固定 text_end")
    content_index: int = Field(ge=0, description="文本内容块索引")
    content: str = Field(description="该文本块最终内容")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _index_matches_text_block(self):
        _require_block(self.partial, self.content_index, "text")
        return self


class AssistantToolCallStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["toolcall_start"] = Field(default="toolcall_start", description="事件类型，固定 toolcall_start")
    content_index: int = Field(ge=0, description="工具调用内容块索引")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _index_matches_tool_block(self):
        _require_block(self.partial, self.content_index, "toolCall")
        return self


class AssistantToolCallDeltaEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["toolcall_delta"] = Field(default="toolcall_delta", description="事件类型，固定 toolcall_delta")
    content_index: int = Field(ge=0, description="工具调用内容块索引")
    delta: str = Field(description="工具参数原始增量字符串；不补齐、不解析为可执行参数")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _index_matches_tool_block(self):
        _require_block(self.partial, self.content_index, "toolCall")
        return self


class AssistantToolCallEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["toolcall_end"] = Field(default="toolcall_end", description="事件类型，固定 toolcall_end")
    content_index: int = Field(ge=0, description="工具调用内容块索引")
    tool_call: ToolCall = Field(description="完整工具调用块（Pi toolCall）")
    partial: AssistantMessage = Field(description="当前 partial 助手消息")

    @model_validator(mode="after")
    def _tool_call_matches_partial_snapshot(self):
        block = _require_block(self.partial, self.content_index, "toolCall")
        if block.model_dump() != self.tool_call.model_dump():
            raise ValueError("toolcall_end 的完整 ToolCall 与 partial 中同一索引快照不一致")
        if not self.tool_call.id:
            raise ValueError("toolcall_end 必须携带有效工具调用 ID（早期空 ID 块只允许 start/delta）")
        return self


class AssistantDoneEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["done"] = Field(default="done", description="事件类型，固定 done")
    reason: DoneReason = Field(description="正常完成原因（stop/length/toolUse/deferred）")
    message: AssistantMessage = Field(description="最终助手消息")

    @model_validator(mode="after")
    def _reason_matches_message(self):
        if self.message.stop_reason != self.reason:
            raise ValueError(f"done.reason={self.reason} 与助手消息 stop_reason={self.message.stop_reason} 不一致")
        return self


class AssistantErrorEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["error"] = Field(default="error", description="事件类型，固定 error")
    reason: ErrorReason = Field(description="失败原因（error/aborted）")
    error: AssistantMessage = Field(description="携带 stop_reason=error/aborted 的助手消息")

    @model_validator(mode="after")
    def _reason_matches_message(self):
        if self.error.stop_reason != self.reason:
            raise ValueError(f"error.reason={self.reason} 与助手消息 stop_reason={self.error.stop_reason} 不一致")
        return self


AssistantMessageEvent = Annotated[
    Union[
        AssistantStartEvent,
        AssistantTextStartEvent,
        AssistantTextDeltaEvent,
        AssistantTextEndEvent,
        AssistantToolCallStartEvent,
        AssistantToolCallDeltaEvent,
        AssistantToolCallEndEvent,
        AssistantDoneEvent,
        AssistantErrorEvent,
    ],
    Field(discriminator="type"),
]


# ── AgentEvent（agent/src/types.ts）──


class AgentStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["agent_start"] = Field(default="agent_start", description="Agent 生命周期开始")


class AgentEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["agent_end"] = Field(default="agent_end", description="Agent 生命周期结束（最后一个事件）")
    messages: list[Message] = Field(description="结束时最终消息列表")


class TurnStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["turn_start"] = Field(default="turn_start", description="一次 Turn 开始（一次助手响应+其工具调用/结果）")


class TurnEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["turn_end"] = Field(default="turn_end", description="一次 Turn 结束")
    message: Message = Field(description="该 Turn 的助手消息（Pi：当轮 assistant message）")
    tool_results: list[ToolResultMessage] = Field(description="该轮工具结果（Pi toolResults，必填，可为空）")


class MessageStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["message_start"] = Field(default="message_start", description="消息生命周期开始")
    message: Message = Field(description="消息（user/assistant/toolResult）")


class MessageUpdateEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["message_update"] = Field(default="message_update", description="助手消息流式更新")
    message: Message = Field(description="当前助手消息快照")
    assistant_message_event: AssistantMessageEvent = Field(description="对应的助手消息流事件")

    @model_validator(mode="after")
    def _same_assistant_message_throughout(self):
        # Pi：message_update 只在 assistant 消息流式期间发出，外层快照与嵌套事件指向同一消息
        if self.message.role != "assistant":
            raise ValueError("message_update 只用于 assistant 消息（外层快照角色不符）")
        nested = self.assistant_message_event
        inner = getattr(nested, "partial", None) or getattr(nested, "message", None) or getattr(nested, "error", None)
        if inner is None or inner.message_id != self.message.message_id:
            raise ValueError("message_update 外层消息与嵌套事件 partial/最终消息不是同一 message_id")
        return self


class MessageEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["message_end"] = Field(default="message_end", description="消息生命周期结束")
    message: Message = Field(description="最终消息")


class ToolExecutionStartEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["tool_execution_start"] = Field(default="tool_execution_start", description="工具执行开始（非“已获授权”，仅事件通知）")
    tool_call_id: str = Field(min_length=1, description="Pi toolCallId")
    tool_name: str = Field(description="Pi toolName")
    args: Any = Field(description="Pi args（传入形状，不代表已校验/已执行）")


class ToolExecutionUpdateEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["tool_execution_update"] = Field(default="tool_execution_update", description="工具执行进度更新")
    tool_call_id: str = Field(min_length=1, description="Pi toolCallId")
    tool_name: str = Field(description="Pi toolName")
    args: Any = Field(description="Pi args")
    partial_result: Any = Field(description="Pi partialResult（部分结果，不承诺终态）")


class ToolExecutionEndEvent(BaseModel):
    model_config = _STRICT_FORBID
    type: Literal["tool_execution_end"] = Field(default="tool_execution_end", description="工具执行结束（按完成顺序发出）")
    tool_call_id: str = Field(min_length=1, description="Pi toolCallId")
    tool_name: str = Field(description="Pi toolName")
    result: Any = Field(description="Pi result")
    is_error: bool = Field(description="Pi isError")


AgentEvent = Annotated[
    Union[
        AgentStartEvent,
        AgentEndEvent,
        TurnStartEvent,
        TurnEndEvent,
        MessageStartEvent,
        MessageUpdateEvent,
        MessageEndEvent,
        ToolExecutionStartEvent,
        ToolExecutionUpdateEvent,
        ToolExecutionEndEvent,
    ],
    Field(discriminator="type"),
]


# ── 应用层事件外壳（schema_version/session/run/message/tool_call/sequence）──

_BASE_ENVELOPE_CONFIG = {"extra": "forbid", "strict": True}


def _require_message_id_of(inner_message: Message) -> str:
    """从内层消息取得 message_id 供外壳核对。"""
    return inner_message.message_id


class AssistantEventEnvelope(BaseModel):
    """AssistantMessageEvent 的应用层外壳。

    message_id 必填且必须与 partial/最终消息一致；toolcall_end 还需
    tool_call_id 与完整 ToolCall.id 一致。
    """

    model_config = ConfigDict(**_BASE_ENVELOPE_CONFIG)

    schema_version: Literal[1] = Field(default=1, description="外壳合同版本，固定 1")
    session_id: int = Field(ge=1, description="现有会话正整数 ID")
    run_id: int = Field(ge=1, description="现有 Run 正整数 ID")
    message_id: str = Field(min_length=1, description="该流指向的稳定消息 ID")
    tool_call_id: str | None = Field(default=None, description="按事件类型约束；toolcall_end 必填")
    sequence_no: int = Field(ge=1, description="会话内事件游标，只校验不分配")
    event: AssistantMessageEvent = Field(description="AssistantMessageEvent 载荷")

    @model_validator(mode="after")
    def _check_inner_associations(self):
        event = self.event
        partial = getattr(event, "partial", None)
        final = getattr(event, "message", None) or getattr(event, "error", None)
        if partial is not None and partial.message_id != self.message_id:
            raise ValueError(f"事件 partial.message_id={partial.message_id} 与外壳 message_id={self.message_id} 不一致")
        if final is not None and final.message_id != self.message_id:
            raise ValueError(f"事件最终消息 message_id={final.message_id} 与外壳 message_id={self.message_id} 不一致")
        if event.type == "toolcall_end" and event.tool_call.id != self.tool_call_id:
            raise ValueError("toolcall_end 外壳 tool_call_id 必须等于完整 ToolCall.id")
        return self


class AgentEventEnvelope(BaseModel):
    """AgentEvent 的应用层外壳。

    按事件类型约束：message_start/update/end 与 turn_end 要求 message_id 等于
    内层消息 ID；tool_execution_* 要求 tool_call_id 必填；agent_start/end、
    turn_start 等无单一消息的生命周期事件允许 message_id 为空。
    """

    model_config = ConfigDict(**_BASE_ENVELOPE_CONFIG)

    schema_version: Literal[1] = Field(default=1, description="外壳合同版本，固定 1")
    session_id: int = Field(ge=1, description="现有会话正整数 ID")
    run_id: int = Field(ge=1, description="现有 Run 正整数 ID")
    message_id: str | None = Field(default=None, description="按事件类型约束的稳定消息 ID")
    tool_call_id: str | None = Field(default=None, description="工具执行事件必填的调用 ID")
    sequence_no: int = Field(ge=1, description="会话内事件游标，只校验不分配")
    event: AgentEvent = Field(description="AgentEvent 载荷")

    @model_validator(mode="after")
    def _check_inner_associations(self):
        event = self.event
        if event.type in {"message_start", "message_update", "message_end", "turn_end"}:
            inner_id = _require_message_id_of(event.message)
            if inner_id != self.message_id:
                raise ValueError(f"事件消息 message_id={inner_id} 与外壳 message_id={self.message_id} 不一致")
        elif event.type in {"agent_start", "turn_start"}:
            if self.message_id is not None or self.tool_call_id is not None:
                raise ValueError(f"{event.type} 是无单一消息的生命周期事件，message_id/tool_call_id 应为空")
        elif event.type == "agent_end":
            # 多条最终消息，外壳不要求单一 message_id
            pass
        if event.type.startswith("tool_execution_") and event.tool_call_id != self.tool_call_id:
            raise ValueError(f"{event.type} 外壳 tool_call_id 必须等于事件 tool_call_id")
        return self


_assistant_envelope_adapter: TypeAdapter = TypeAdapter(AssistantEventEnvelope)
_agent_envelope_adapter: TypeAdapter = TypeAdapter(AgentEventEnvelope)


def parse_assistant_event(data: object) -> AssistantEventEnvelope:
    """解析 AssistantMessageEvent 外壳；未知类型/非法载荷/关联错误均拒绝。"""
    return _assistant_envelope_adapter.validate_python(data)


def parse_agent_event(data: object) -> AgentEventEnvelope:
    """解析 AgentEvent 外壳；未知类型/非法载荷/关联错误均拒绝。"""
    return _agent_envelope_adapter.validate_python(data)
