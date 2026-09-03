"""用例生成校验/去重/覆盖/dry-run 工具（全部只读、无副作用）。

- validate_case_schema：结构/类型校验（Pydantic 输入/输出）；
- validate_case_business_rules：取值/枚举/必填语义校验；
- deduplicate_cases：确定性指纹去重（候选之间、候选与已有用例）；
- compute_coverage_matrix：条款覆盖矩阵（确定性聚合）；
- dry_run_api_case_codegen：复用 ai_service 的纯内存规则生成函数检查候选
  是否可生成合法 pytest 代码。零副作用：构造瞬态 APICase（不 add/不 commit），
  绝不调用 save_generated_code_result / generate_case_test_code_by_rule
  （这两个函数会写数据库与 tests_generated 文件）。
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.tools.base import ToolContext
from app.agents.validators.case_validators import (
    compute_coverage,
    find_duplicates,
    validate_api_case_business,
    validate_api_case_schema,
    validate_function_case_business,
    validate_function_case_schema,
)
from app.models.api_case import APICase
from app.services import ai_service


def _json_dumps(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


# ── validate_case_schema ──


class ValidateCaseSchemaInput(BaseModel):
    case_kind: Literal["function", "api"]
    candidates: list[dict[str, Any]] = Field(..., description="候选列表")


class CaseValidationItem(BaseModel):
    index: int
    valid: bool
    errors: list[str] = Field(default_factory=list)


class ValidateCaseSchemaOutput(BaseModel):
    results: list[CaseValidationItem] = Field(default_factory=list)


class ValidateCaseSchemaTool:
    name = "validate_case_schema"
    description = "校验候选的 Schema 结构（类型），不修改任何数据"
    read_only = True
    requires_approval = False
    input_model = ValidateCaseSchemaInput
    output_model = ValidateCaseSchemaOutput

    def execute(self, context: ToolContext, payload: ValidateCaseSchemaInput) -> ValidateCaseSchemaOutput:
        validator = (
            validate_function_case_schema if payload.case_kind == "function" else validate_api_case_schema
        )
        results = []
        for index, candidate in enumerate(payload.candidates):
            errors = validator(candidate)
            results.append(CaseValidationItem(index=index, valid=not errors, errors=errors))
        return ValidateCaseSchemaOutput(results=results)


# ── validate_case_business_rules ──


class ValidateCaseBusinessRulesInput(BaseModel):
    case_kind: Literal["function", "api"]
    candidates: list[dict[str, Any]] = Field(..., description="候选列表")


class ValidateCaseBusinessRulesOutput(BaseModel):
    results: list[CaseValidationItem] = Field(default_factory=list)


class ValidateCaseBusinessRulesTool:
    name = "validate_case_business_rules"
    description = "校验候选的业务规则（必填/枚举/取值），不修改任何数据"
    read_only = True
    requires_approval = False
    input_model = ValidateCaseBusinessRulesInput
    output_model = ValidateCaseBusinessRulesOutput

    def execute(self, context: ToolContext, payload: ValidateCaseBusinessRulesInput) -> ValidateCaseBusinessRulesOutput:
        validator = (
            validate_function_case_business if payload.case_kind == "function" else validate_api_case_business
        )
        results = []
        for index, candidate in enumerate(payload.candidates):
            errors = validator(candidate)
            results.append(CaseValidationItem(index=index, valid=not errors, errors=errors))
        return ValidateCaseBusinessRulesOutput(results=results)


# ── deduplicate_cases ──


class DeduplicateCasesInput(BaseModel):
    case_kind: Literal["function", "api"]
    candidates: list[dict[str, Any]] = Field(..., description="候选列表")
    existing: list[dict[str, Any]] = Field(default_factory=list, description="已有用例摘要（可选）")


class DuplicateRelation(BaseModel):
    fingerprint: str
    first_position: int
    first_origin: str
    duplicate_position: int
    duplicate_origin: str


class DeduplicateCasesOutput(BaseModel):
    keep_indexes: list[int] = Field(default_factory=list, description="保留的候选下标（每组首个出现）")
    duplicates: list[DuplicateRelation] = Field(default_factory=list)


class DeduplicateCasesTool:
    name = "deduplicate_cases"
    description = "按确定性指纹去重（function: 名称；api: method+url），无副作用"
    read_only = True
    requires_approval = False
    input_model = DeduplicateCasesInput
    output_model = DeduplicateCasesOutput

    def execute(self, context: ToolContext, payload: DeduplicateCasesInput) -> DeduplicateCasesOutput:
        keep_indexes, duplicates = find_duplicates(payload.case_kind, payload.candidates, payload.existing)
        return DeduplicateCasesOutput(
            keep_indexes=keep_indexes,
            duplicates=[DuplicateRelation(**d) for d in duplicates],
        )


# ── compute_coverage_matrix ──


class ComputeCoverageMatrixInput(BaseModel):
    clauses: list[dict[str, Any]] = Field(..., description="原子条款：[{clause_id, text}]")
    candidates: list[dict[str, Any]] = Field(..., description="候选：[{candidate_id, name, covered_clause_ids}]")


class ComputeCoverageMatrixOutput(BaseModel):
    matrix: list[dict[str, Any]] = Field(default_factory=list)
    covered_count: int = 0
    uncovered_count: int = 0
    uncovered_clause_ids: list[str] = Field(default_factory=list)
    unknown_refs: list[dict[str, Any]] = Field(default_factory=list, description="引用不存在条款的候选")


class ComputeCoverageMatrixTool:
    name = "compute_coverage_matrix"
    description = "按条款聚合候选覆盖（确定性代码计算，不采用模型自报覆盖率）"
    read_only = True
    requires_approval = False
    input_model = ComputeCoverageMatrixInput
    output_model = ComputeCoverageMatrixOutput

    def execute(self, context: ToolContext, payload: ComputeCoverageMatrixInput) -> ComputeCoverageMatrixOutput:
        result = compute_coverage(payload.clauses, payload.candidates)
        return ComputeCoverageMatrixOutput(**result)


# ── dry_run_api_case_codegen ──


class DryRunApiCaseCodegenInput(BaseModel):
    candidate: dict[str, Any] = Field(..., description="接口用例候选（method/url/headers/body/expected_result）")


class DryRunApiCaseCodegenOutput(BaseModel):
    ok: bool = Field(..., description="候选是否可生成合法 pytest 代码")
    reason: str = Field(default="", description="失败原因（通过时为空）")
    generated_code: str | None = Field(default=None, description="预览代码（通过时返回）")


class DryRunApiCaseCodegenTool:
    name = "dry_run_api_case_codegen"
    description = (
        "内存中复用 ai_service 确定性规则生成，检查候选是否可生成合法 pytest 代码。"
        "零副作用：不写数据库、不写文件、不发送请求。"
    )
    read_only = True
    requires_approval = False
    input_model = DryRunApiCaseCodegenInput
    output_model = DryRunApiCaseCodegenOutput

    def execute(self, context: ToolContext, payload: DryRunApiCaseCodegenInput) -> DryRunApiCaseCodegenOutput:
        candidate = payload.candidate
        # 瞬态对象：不 add 到 Session、不 commit、不写 generated_test_code
        transient = APICase(
            id=0,
            name=candidate.get("name") or "dry-run-candidate",
            description=candidate.get("description") or "",
            method=str(candidate.get("method") or "GET").upper(),
            url=candidate.get("url") or "",
            headers=_json_dumps(candidate.get("headers")),
            body=_json_dumps(candidate.get("body")),
            expected_result=_json_dumps(candidate.get("expected_result")),
            case_type=candidate.get("case_type") or "正常场景",
            priority=candidate.get("priority") or "P1",
        )
        try:
            ctx = ai_service.build_case_context(transient)
            ai_service.validate_rule_generation_input(transient, ctx)  # 失败抛 ValueError
            code = ai_service.generate_mock_test_code(transient)
            ok, reason = ai_service.validate_generated_code_rules_with_reason(code, transient)
            return DryRunApiCaseCodegenOutput(
                ok=ok,
                reason="" if ok else reason,
                generated_code=code if ok else None,
            )
        except ValueError as e:
            return DryRunApiCaseCodegenOutput(ok=False, reason=str(e), generated_code=None)
