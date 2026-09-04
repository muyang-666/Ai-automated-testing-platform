"""Agent 平台 API 的请求/响应 Schema。"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Session ──


class AgentSessionCreate(BaseModel):
    project_id: int = Field(..., description="所属项目ID")
    title: str = Field(..., min_length=1, max_length=200, description="会话标题")
    context_json: Optional[dict[str, Any]] = Field(default=None, description="业务上下文，可空")


class AgentSessionResponse(AgentResponseBase):
    id: int
    project_id: Optional[int]
    user_id: int
    mode: str = "legacy_workflow"
    title: str
    status: str
    current_skill_code: Optional[str] = None
    agent_version: Optional[str] = None
    context_json: Optional[dict[str, Any]] = None
    last_activity_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AgentMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000, description="消息内容")
    skill_code: Optional[str] = Field(default=None, description="显式启动的 Skill 编码，如 case_generation")
    source_type: Optional[Literal["requirement", "api_document"]] = Field(default=None, description="来源类型（启动 Run 时需要）")
    source_id: Optional[int] = Field(default=None, description="来源 ID（启动 Run 时需要）")
    case_types: Optional[list[str]] = Field(default=None, description="请求覆盖的用例类型")
    max_cases: Optional[int] = Field(default=None, ge=1, le=50, description="最大候选数")
    user_goal: Optional[str] = Field(default=None, max_length=500, description="补充目标")


class AgentMessageResponse(AgentResponseBase):
    id: int
    session_id: int
    run_id: Optional[int] = None
    message_id: Optional[str] = None
    schema_version: int = 1
    timestamp_ms: Optional[int] = None
    role: str
    message_type: str
    content: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    sequence_no: int
    created_at: Optional[datetime] = None


class AgentEventResponse(AgentResponseBase):
    id: int
    session_id: int
    run_id: Optional[int] = None
    event_type: str
    sequence_no: int
    payload_json: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None


class AgentSessionDetailResponse(AgentSessionResponse):
    messages: list[AgentMessageResponse] = Field(default_factory=list)


# ── Run ──


class CaseGenerationRunRequest(BaseModel):
    session_id: int = Field(..., description="所属会话ID")
    source_type: Literal["requirement", "api_document"] = Field(..., description="来源类型")
    source_id: int = Field(..., ge=1, description="来源 ID")
    case_types: Optional[list[str]] = Field(default=None, description="请求覆盖的用例类型")
    max_cases: Optional[int] = Field(default=None, ge=1, le=50, description="最大候选数")
    user_goal: Optional[str] = Field(default=None, max_length=500, description="补充目标")
    idempotency_key: Optional[str] = Field(default=None, max_length=128, description="幂等键")


class RunResponse(AgentResponseBase):
    id: int
    session_id: int
    project_id: Optional[int]
    requester_user_id: int
    workflow_code: str
    workflow_version: Optional[str] = None
    status: str
    current_step: Optional[str] = None
    input_json: Optional[dict[str, Any]] = None
    output_json: Optional[dict[str, Any]] = None
    input_hash: Optional[str] = None
    user_message_id: Optional[int] = None
    max_steps: int
    steps_used: int
    llm_calls_used: int
    tool_calls_used: int
    prompt_tokens: int
    completion_tokens: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class StepResponse(AgentResponseBase):
    id: int
    sequence_no: int
    step_kind: str
    step_name: str
    tool_name: Optional[str] = None
    status: str
    output_json: Optional[dict[str, Any]] = None  # 只含脱敏摘要
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ArtifactResponse(AgentResponseBase):
    id: int
    session_id: int
    agent_run_id: int
    artifact_type: str
    version: int
    status: str
    payload_json: dict[str, Any]
    source_refs_json: Optional[dict[str, Any]] = None
    source_hash: Optional[str] = None
    created_at: Optional[datetime] = None


# ── Approval ──


class ApprovalResolveRequest(BaseModel):
    status: Literal["approved", "rejected"] = Field(..., description="决议状态")
    resolution_json: Optional[dict[str, Any]] = Field(default=None, description="决议内容（不可信，后端校验）")


class ApprovalResponse(AgentResponseBase):
    id: int
    session_id: int
    agent_run_id: int
    artifact_id: Optional[int] = None
    action_code: str
    status: str
    request_json: Optional[dict[str, Any]] = None
    resolution_json: Optional[dict[str, Any]] = None
    requested_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: Optional[int] = None


# ── 保存候选 ──


class SaveCandidatesRequest(BaseModel):
    candidate_ids: list[str] = Field(..., min_length=1, max_length=200, description="要保存的候选 ID 列表")


class SaveCandidatesResponse(BaseModel):
    run_id: int
    saved_count: int
    saved_case_ids: list[int] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
