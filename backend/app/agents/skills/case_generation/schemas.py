"""case_generation Skill 的 Pydantic Schema。

包含 Workflow State、LLM 结构化输出与 GATE resolution（不可信输入）合同。
State 序列化后存于 AgentRun.output_json["workflow_state"]，恢复时经 model_validate 校验。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

STATE_SCHEMA_VERSION = 1

ALLOWED_CASE_TYPES = ("正常场景", "异常场景", "边界场景", "业务规则场景", "其他")
MAX_CASES_LIMIT = 50
USER_GOAL_MAX_LEN = 500
CANDIDATE_ID_PATTERN = "CASE-{index:03d}"


# ── LLM 结构化输出 ──


class AtomicClause(BaseModel):
    clause_id: str = Field(..., description="原子条款 ID（模型建议，程序去重与格式校验）")
    text: str = Field(..., description="条款内容")
    priority: str = Field(default="P1", description="P0/P1/P2")
    source_ref: Optional[str] = Field(default=None, description="来源引用，可空")


class CoveragePlanItem(BaseModel):
    clause_id: str
    dimension: str = Field(..., description="覆盖维度：正常/异常/边界/业务规则场景")


class AnalyzeAndPlanOutput(BaseModel):
    atomic_clauses: list[AtomicClause]
    coverage_plan: list[CoveragePlanItem]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FunctionCandidateOut(BaseModel):
    candidate_id: Optional[str] = None  # 后端分配；repair 时用于替换既有候选
    case_code: Optional[str] = None
    case_name: str
    case_type: str = "正常场景"
    priority: str = "P1"
    precondition: Optional[str] = None
    steps_json: list[str] = Field(default_factory=list)
    test_data_json: dict[str, Any] = Field(default_factory=dict)
    expected_result: str = ""
    remark: Optional[str] = None
    covered_clause_ids: list[str] = Field(default_factory=list)


class ApiCandidateOut(BaseModel):
    candidate_id: Optional[str] = None
    name: str
    description: str = ""
    method: str = "GET"
    url: str = ""
    headers: dict[str, Any] = Field(default_factory=dict)
    body: Optional[Any] = None
    expected_result: Optional[Any] = None
    case_type: str = "正常场景"
    priority: str = "P1"
    remark: str = ""
    covered_clause_ids: list[str] = Field(default_factory=list)


class GenerateFunctionCandidatesOutput(BaseModel):
    candidates: list[FunctionCandidateOut]


class GenerateApiCandidatesOutput(BaseModel):
    candidates: list[ApiCandidateOut]


class RepairFunctionOutput(BaseModel):
    repaired: list[FunctionCandidateOut]


class RepairApiOutput(BaseModel):
    repaired: list[ApiCandidateOut]


# ── 候选 State ──


class CandidateState(BaseModel):
    candidate_id: str
    revision: int = 1
    case: dict[str, Any] = Field(default_factory=dict)
    covered_clause_ids: list[str] = Field(default_factory=list)
    dry_run_ok: Optional[bool] = None
    dry_run_reason: str = ""


# ── GATE resolution（不可信输入，必须校验） ──


class ScopeResolution(BaseModel):
    approved: bool = False
    rejected: bool = False
    case_types: Optional[list[str]] = None
    max_cases: Optional[int] = None
    user_goal: Optional[str] = None


class CoverageResolution(BaseModel):
    approved: bool = False
    rejected: bool = False
    coverage_plan: Optional[list[CoveragePlanItem]] = None


class SaveResolution(BaseModel):
    approved: bool = False
    rejected: bool = False


# ── Workflow State ──


class CaseGenerationState(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    schema_version: int = STATE_SCHEMA_VERSION
    source_type: Literal["requirement", "api_document"]
    source_id: int
    project_id: Optional[int] = None  # 首个步骤从 RuntimeContext 同步（Run.project_id 为准）
    requester_user_id: Optional[int] = None
    requested_case_types: list[str]
    max_cases: int
    user_goal: str

    phase: str = "load_source"
    next_candidate_index: int = 0

    source_hash: Optional[str] = None
    source_context: dict[str, Any] = Field(default_factory=dict)
    project_context: dict[str, Any] = Field(default_factory=dict)
    existing_cases: list[dict[str, Any]] = Field(default_factory=list)
    related_api_documents: list[dict[str, Any]] = Field(default_factory=list)
    atomic_clauses: list[AtomicClause] = Field(default_factory=list)
    coverage_plan: list[CoveragePlanItem] = Field(default_factory=list)
    candidates: list[CandidateState] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_relations: list[dict[str, Any]] = Field(default_factory=list)
    coverage_matrix: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repair_round: int = 0
    model_metadata: dict[str, Any] = Field(default_factory=dict)

    scope_approval_id: Optional[int] = None
    coverage_approval_id: Optional[int] = None
    save_approval_id: Optional[int] = None
    coverage_artifact_id: Optional[int] = None
    coverage_artifact_version: int = 1
    case_set_artifact_id: Optional[int] = None
    case_set_artifact_version: int = 1
