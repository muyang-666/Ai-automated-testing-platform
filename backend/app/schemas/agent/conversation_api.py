"""P06 Conversation API Schemas（最小、无 Secret）。

消息结构保留结构化 content（含 ToolCall/ToolResult 关联），不是拼接字符串。
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=200)
    project_id: int | None = None


class ConversationSummary(BaseModel):
    id: int
    title: str
    project_id: int | None
    status: str
    created_at: Any = None
    updated_at: Any = None


class ConversationSnapshot(BaseModel):
    conversation: ConversationSummary
    active_run: dict | None = None
    latest_run: dict | None = None
    queue_state: str = "idle"
    head_status: str | None = None
    queued_follow_ups: int = 0
    latest_event_sequence: int = 0
    latest_message_sequence: int = 0


class TurnSubmitRequest(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(min_length=1, max_length=8000)
    client_request_id: str = Field(min_length=1, max_length=128)
    queue_mode: Literal["reject", "follow_up"] = "follow_up"


class TurnSubmitResponse(BaseModel):
    run_id: int
    user_message_id: int
    replayed: bool
    queue_state: str
    message_id: str | None = None


class ConversationMessageItem(BaseModel):
    id: int
    message_id: str | None
    role: str
    sequence_no: int
    timestamp_ms: int | None = None
    content: list[dict] | str | None = None  # 结构化内容块（model_dump），保 ToolCall/ToolResult
    run_id: int | None = None
    stop_reason: str | None = None
    error_code: str | None = None


class ConversationEventItem(BaseModel):
    sequence_no: int
    event_type: str
    payload: dict | None = None
    created_at: Any = None


class CancelConversationRunRequest(BaseModel):
    model_config = {"extra": "forbid"}


class CancelConversationRunResponse(BaseModel):
    run_id: int
    status: str
    queue_state: str


class ConversationCapabilities(BaseModel):
    model_ready: bool
    worker_status: Literal["online", "unknown"] = "unknown"
    tools: list[str] = []
    supports_follow_up: bool = True
    supports_cancel: bool = True
    chat_scene: str = "agent_chat"
