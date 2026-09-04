"""Agent 平台共享常量与 Schema。

status/枚举取值在本文件集中定义，模型注释与后续 Service/Router 均引用这里，
避免 magic string 散落各处。本任务只定义数据合同，不实现任何 Service/Router。
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ── 集中状态/枚举定义 ──

SESSION_STATUSES = ("active", "closed", "archived")
MESSAGE_ROLES = ("user", "assistant", "toolResult", "system", "tool")
SESSION_MODES = ("legacy_workflow", "conversation")
MESSAGE_TYPES = ("text", "status", "gate", "artifact_ref", "error")
RUN_STATUSES = (
    "queued",
    "running",
    "waiting_approval",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
)
STEP_KINDS = ("llm", "tool", "validation", "approval")
STEP_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
ARTIFACT_STATUSES = ("draft", "reviewing", "approved", "saved", "rejected")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "cancelled")

SessionStatus = Literal["active", "closed", "archived"]
MessageRole = Literal["user", "assistant", "toolResult", "system", "tool"]
SessionMode = Literal["legacy_workflow", "conversation"]
MessageType = Literal["text", "status", "gate", "artifact_ref", "error"]
RunStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
]
StepKind = Literal["llm", "tool", "validation", "approval"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
ArtifactStatus = Literal["draft", "reviewing", "approved", "saved", "rejected"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]


class AgentBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


# ── AgentSession ──


class AgentSessionCreate(AgentBase):
    project_id: Optional[int] = Field(default=None, description="可选项目ID；conversation 可空")
    user_id: int = Field(..., description="会话所属用户ID")
    mode: SessionMode = Field(default="legacy_workflow", description="会话模式")
    title: str = Field(..., max_length=200, description="会话标题")
    status: SessionStatus = Field(default="active", description="状态：active/closed/archived")
    current_skill_code: Optional[str] = Field(default=None, max_length=100, description="当前选中的 Skill 编码")
    agent_version: Optional[str] = Field(default=None, max_length=50, description="当前 Agent 版本")
    context_json: Optional[dict[str, Any]] = Field(default=None, description="会话业务上下文JSON")


class AgentSessionResponse(AgentSessionCreate):
    id: int
    last_activity_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── AgentMessage ──


class AgentMessageCreate(AgentBase):
    session_id: int = Field(..., description="所属会话ID")
    run_id: Optional[int] = Field(default=None, description="关联 Run ID，可空")
    message_id: Optional[str] = Field(default=None, max_length=64, description="P01 稳定消息ID；旧消息可空")
    schema_version: int = Field(default=1, ge=1, description="消息合同版本")
    timestamp_ms: Optional[int] = Field(default=None, ge=0, description="Unix 毫秒时间戳")
    role: MessageRole = Field(..., description="角色：user/assistant/system/tool")
    message_type: MessageType = Field(default="text", description="类型：text/status/gate/artifact_ref/error")
    content: Optional[str] = Field(default=None, description="消息文本内容")
    content_json: Optional[dict[str, Any]] = Field(default=None, description="结构化内容JSON")
    sequence_no: int = Field(..., description="会话内消息序号")


class AgentMessageResponse(AgentMessageCreate):
    id: int
    created_at: Optional[datetime] = None


# ── AgentEvent ──


class AgentEventCreate(AgentBase):
    session_id: int = Field(..., description="所属会话ID")
    run_id: Optional[int] = Field(default=None, description="关联 Run ID，可空")
    event_type: str = Field(..., max_length=50, description="事件类型")
    sequence_no: int = Field(..., description="会话内事件序号")
    payload_json: Optional[dict[str, Any]] = Field(default=None, description="事件负载，只保存脱敏摘要")


class AgentEventResponse(AgentEventCreate):
    id: int
    created_at: Optional[datetime] = None


# ── AgentRun ──


class AgentRunCreate(AgentBase):
    session_id: int = Field(..., description="所属会话ID")
    project_id: Optional[int] = Field(default=None, description="可选项目ID；conversation 可空")
    requester_user_id: int = Field(..., description="发起用户ID")
    workflow_code: str = Field(..., max_length=100, description="Workflow 编码，如 case_generation")
    workflow_version: Optional[str] = Field(default=None, max_length=50, description="Workflow 版本")
    status: RunStatus = Field(default="queued", description="运行状态")
    current_step: Optional[str] = Field(default=None, max_length=100, description="当前步骤")
    input_json: Optional[dict[str, Any]] = Field(default=None, description="任务输入JSON")
    output_json: Optional[dict[str, Any]] = Field(default=None, description="任务输出JSON")
    input_hash: Optional[str] = Field(default=None, max_length=64, description="输入内容哈希")
    idempotency_key: Optional[str] = Field(default=None, max_length=128, description="幂等键，可空")
    user_message_id: Optional[int] = Field(default=None, description="conversation 首条用户消息ID")
    model_snapshot_json: Optional[dict[str, Any]] = Field(default=None, description="模型快照，只存非敏感信息")
    prompt_version: Optional[str] = Field(default=None, max_length=50, description="Prompt 版本")
    max_steps: int = Field(default=20, ge=1, description="最大步骤数")
    error_code: Optional[str] = Field(default=None, max_length=50, description="错误码")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    worker_id: Optional[str] = Field(default=None, max_length=64, description="执行 Worker 标识")


class AgentRunResponse(AgentRunCreate):
    id: int
    steps_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    heartbeat_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── AgentStep ──


class AgentStepCreate(AgentBase):
    agent_run_id: int = Field(..., description="所属 Run ID")
    sequence_no: int = Field(..., description="Run 内步骤序号")
    step_kind: StepKind = Field(..., description="步骤类型：llm/tool/validation/approval")
    step_name: str = Field(..., max_length=100, description="步骤名称")
    tool_name: Optional[str] = Field(default=None, max_length=100, description="工具名称")
    status: StepStatus = Field(default="pending", description="步骤状态")
    input_json: Optional[dict[str, Any]] = Field(default=None, description="输入JSON，只保存脱敏摘要")
    output_json: Optional[dict[str, Any]] = Field(default=None, description="输出JSON，只保存脱敏摘要")
    provider_name: Optional[str] = Field(default=None, max_length=100, description="模型供应商名称")
    model_name: Optional[str] = Field(default=None, max_length=100, description="模型名称")
    prompt_tokens: Optional[int] = Field(default=None, ge=0, description="提示词 token 数")
    completion_tokens: Optional[int] = Field(default=None, ge=0, description="补全 token 数")
    duration_ms: Optional[int] = Field(default=None, ge=0, description="耗时(毫秒)")
    error_code: Optional[str] = Field(default=None, max_length=50, description="错误码")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class AgentStepResponse(AgentStepCreate):
    id: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ── AgentArtifact ──


class AgentArtifactCreate(AgentBase):
    session_id: int = Field(..., description="所属会话ID")
    agent_run_id: int = Field(..., description="产生该产物的 Run ID")
    artifact_type: str = Field(..., max_length=50, description="产物类型：coverage_matrix/test_case_set 等")
    version: int = Field(default=1, ge=1, description="产物版本号")
    status: ArtifactStatus = Field(default="draft", description="产物状态")
    payload_json: dict[str, Any] = Field(..., description="结构化业务成果JSON")
    source_refs_json: Optional[dict[str, Any]] = Field(default=None, description="来源引用JSON")
    source_hash: Optional[str] = Field(default=None, max_length=64, description="来源内容哈希")
    created_by_user_id: Optional[int] = Field(default=None, description="创建者用户ID，可空")


class AgentArtifactResponse(AgentArtifactCreate):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── AgentApproval ──


class AgentApprovalCreate(AgentBase):
    session_id: int = Field(..., description="所属会话ID")
    agent_run_id: int = Field(..., description="所属 Run ID")
    artifact_id: Optional[int] = Field(default=None, description="关联产物ID，可空")
    action_code: str = Field(..., max_length=100, description="审批动作编码，如 save_selected_candidates")
    status: ApprovalStatus = Field(default="pending", description="审批状态")
    request_json: Optional[dict[str, Any]] = Field(default=None, description="审批请求JSON，只保存脱敏摘要")
    resolution_json: Optional[dict[str, Any]] = Field(default=None, description="审批结果JSON")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间，可空")
    resolved_at: Optional[datetime] = Field(default=None, description="处理时间，可空")
    resolved_by_user_id: Optional[int] = Field(default=None, description="处理人用户ID，可空")


class AgentApprovalResponse(AgentApprovalCreate):
    id: int
    requested_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
