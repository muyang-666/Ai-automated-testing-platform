"""case_generation Workflow：受控状态机，一次只执行一个可持久化步骤。

状态图：
    load_source → load_project_context → load_existing_cases
    → scope_gate（GATE 1：确认范围）
    → analyze_and_plan（LLM #1）
    → create_coverage_artifact → coverage_gate（GATE 2：确认覆盖计划）
    → generate_candidates（LLM #2）
    → validate_candidates → deduplicate → compute_coverage
    → api_dry_run（仅 api_document）
    → repair_decision（LLM #3/#4，最多 2 轮）
    → finalize_artifacts → save_gate（GATE 3：保存审批）
    → done（succeeded，保存动作留 T07）

约束：
- 每次 Tool/LLM 调用经 StepOutcome.invocations 记录为可观察 AgentStep；
- LLM 最多 4 次（analyze/generate/repair×2），T06 不在 Workflow 内额外重试；
- GATE 恢复先查现有 Approval（find_approval_by_action），绝不重复创建；
- resolution_json 不可信，一律 Pydantic 校验；
- State 可序列化（不存 Session/Gateway/Registry/Pydantic class/Secret）；
- Secret 键递归脱敏后才进入 State/Artifact；
- 不写业务用例表；保存候选由 T07 的审批动作执行。
"""

import json
import time
from typing import Any

from app.agents.runtime.contracts import RuntimeContext, StepOutcome
from app.agents.runtime.errors import AgentError
from app.agents.skills.case_generation.prompt_loader import load_instructions, load_prompt
from app.agents.skills.case_generation.schemas import (
    ALLOWED_CASE_TYPES,
    AnalyzeAndPlanOutput,
    ApiCandidateOut,
    CandidateState,
    CaseGenerationState,
    CoveragePlanItem,
    CoverageResolution,
    FunctionCandidateOut,
    GenerateApiCandidatesOutput,
    GenerateFunctionCandidatesOutput,
    MAX_CASES_LIMIT,
    RepairApiOutput,
    RepairFunctionOutput,
    SaveResolution,
    ScopeResolution,
    USER_GOAL_MAX_LEN,
)
from app.agents.tools.base import ToolContext
from app.agents.tools.case_context_tools import (
    ListExistingCasesInput,
    ListExistingCasesTool,
    ListRelatedApiDocumentsInput,
    ListRelatedApiDocumentsTool,
    LoadProjectModuleContextInput,
    LoadProjectModuleContextTool,
    LoadSourceContextInput,
    LoadSourceContextTool,
)
from app.agents.tools.case_validation_tools import (
    ComputeCoverageMatrixInput,
    ComputeCoverageMatrixTool,
    DeduplicateCasesInput,
    DeduplicateCasesTool,
    DryRunApiCaseCodegenInput,
    DryRunApiCaseCodegenTool,
    ValidateCaseBusinessRulesInput,
    ValidateCaseBusinessRulesTool,
    ValidateCaseSchemaInput,
    ValidateCaseSchemaTool,
)
from app.exceptions.llm_errors import LLMError
from app.schemas.llm.llm_gateway import LLMMessage, LLMRequest
from app.services.agent import agent_approval_service, agent_artifact_service
from app.services.llm.llm_client_service import _apply_prompt_template, get_model_config_by_scene

SKILL_CODE = "case_generation"
SKILL_VERSION = "v1"

PROMPT_VERSION_ANALYZE = "analyze_and_plan_v1"
PROMPT_VERSION_GENERATE = "generate_candidates_v1"
PROMPT_VERSION_REPAIR = "repair_candidates_v1"

GATE_SCOPE = "confirm_case_generation_scope"
GATE_COVERAGE = "confirm_case_coverage_plan"
GATE_SAVE = "save_generated_case_candidates"

SCENE_BY_SOURCE = {
    "requirement": "requirement_to_function_case",
    "api_document": "api_doc_to_api_case",
}

MAX_LLM_CALLS = 4
MAX_REPAIR_ROUNDS = 2
LLM_MAX_TOKENS = 8192

_INSENSITIVE_KEYS = {
    "authorization", "token", "access_token", "refresh_token",
    "password", "secret", "api_key", "cookie", "x-auth-token", "x-token",
}


def redact(value: Any) -> Any:
    """递归脱敏：敏感键的值替换为 ***（不修改原对象）。"""
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _INSENSITIVE_KEYS else redact(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _safe_summary(value: Any, limit: int) -> str:
    """脱敏后的 JSON 摘要（截断），用于 invocation 记录。"""
    return json.dumps(redact(value), ensure_ascii=False, default=str)[:limit]


def _validate_input(input_data: dict) -> dict:
    source_type = input_data.get("source_type")
    if source_type not in ("requirement", "api_document"):
        raise AgentError(f"非法 source_type: {source_type}", error_code="agent_invalid_input")
    source_id = input_data.get("source_id")
    if not isinstance(source_id, int) or source_id <= 0:
        raise AgentError("source_id 必须为正整数", error_code="agent_invalid_input")

    case_types = input_data.get("case_types") if input_data.get("case_types") is not None else ["正常场景", "异常场景", "边界场景"]
    if not isinstance(case_types, list) or not case_types:
        raise AgentError("case_types 不能为空", error_code="agent_invalid_input")
    deduped = list(dict.fromkeys(case_types))
    invalid = [item for item in deduped if item not in ALLOWED_CASE_TYPES]
    if invalid:
        raise AgentError(f"非法 case_types: {invalid}", error_code="agent_invalid_input")

    max_cases = input_data.get("max_cases")
    if max_cases is None:
        max_cases = 30
    if not isinstance(max_cases, int) or not (1 <= max_cases <= MAX_CASES_LIMIT):
        raise AgentError(f"max_cases 必须在 1-{MAX_CASES_LIMIT} 之间", error_code="agent_invalid_input")

    user_goal = input_data.get("user_goal")
    if user_goal is None:
        user_goal = ""
    if not isinstance(user_goal, str) or len(user_goal) > USER_GOAL_MAX_LEN:
        raise AgentError(f"user_goal 长度不能超过 {USER_GOAL_MAX_LEN}", error_code="agent_invalid_input")

    return {
        "source_type": source_type,
        "source_id": source_id,
        "case_types": deduped,
        "max_cases": max_cases,
        "user_goal": user_goal,
    }


def _parse_resolution(resolution_json: dict | None, model_cls):
    try:
        return model_cls.model_validate(resolution_json or {})
    except Exception as e:
        raise AgentError(f"GATE 决议非法: {e}", error_code="agent_invalid_resolution") from e


class CaseGenerationWorkflow:
    code = SKILL_CODE
    version = SKILL_VERSION

    def __init__(self, tool_registry, llm_gateway=None):
        self._tool_registry = tool_registry
        self._llm_gateway = llm_gateway

    # ── Protocol ──

    def initial_state(self, input_data: dict) -> dict:
        data = _validate_input(input_data)
        return CaseGenerationState(
            source_type=data["source_type"],
            source_id=data["source_id"],
            requested_case_types=data["case_types"],
            max_cases=data["max_cases"],
            user_goal=data["user_goal"],
        ).model_dump()

    def next_step(self, state: dict) -> str | None:
        current = CaseGenerationState.model_validate(state)
        if current.phase == "done":
            return None
        return current.phase

    def execute_step(self, step_name: str, state: dict, context: RuntimeContext) -> StepOutcome:
        current = CaseGenerationState.model_validate(state)
        if current.project_id is None:
            current.project_id = context.project_id
        if current.requester_user_id is None:
            current.requester_user_id = context.requester_user_id
        handler = getattr(self, f"_step_{step_name}", None)
        if handler is None:
            return StepOutcome(
                status="failed",
                error_code="agent_unknown_step",
                error_message=f"未知步骤 {step_name}",
                next_state=current.model_dump(),
            )
        return handler(current, context)

    # ── 辅助 ──

    @staticmethod
    def _tool_context(context: RuntimeContext) -> ToolContext:
        return ToolContext(
            user_id=context.requester_user_id,
            db=context.db,
            run_id=context.run_id,
            session_id=context.session_id,
            project_id=context.project_id,
        )

    def _run_tool(self, tool_name: str, context: RuntimeContext, payload) -> tuple[Any, dict]:
        definition = self._tool_registry.get(tool_name)  # 经注册表调用，不绕过
        tool = definition.tool
        if tool is None:
            raise AgentError(f"工具 {tool_name} 未绑定执行实例", error_code="agent_tool_unavailable")
        started = time.monotonic()
        output = tool.execute(self._tool_context(context), payload)
        duration_ms = int((time.monotonic() - started) * 1000)
        invocation = {
            "kind": "tool",
            "name": tool_name,
            "tool_name": tool_name,
            "status": "succeeded",
            "input_summary": _safe_summary(payload.model_dump(), 1000),
            "output_summary": _safe_summary(output.model_dump(), 2000),
            "duration_ms": duration_ms,
        }
        return output, invocation

    @staticmethod
    def _continue(current: CaseGenerationState, **kwargs) -> StepOutcome:
        kwargs.setdefault("status", "continue")
        kwargs.setdefault("next_state", current.model_dump())
        return StepOutcome(**kwargs)

    @staticmethod
    def _failed(current: CaseGenerationState, error_code: str, message: str) -> StepOutcome:
        return StepOutcome(
            status="failed",
            error_code=error_code,
            error_message=message,
            next_state=current.model_dump(),
        )

    @staticmethod
    def _cancelled(current: CaseGenerationState, error_code: str, message: str) -> StepOutcome:
        """GATE 被拒绝等取消语义：Run 进入 cancelled（不是 failed）。"""
        return StepOutcome(
            status="cancelled",
            error_code=error_code,
            error_message=message,
            next_state=current.model_dump(),
        )

    @staticmethod
    def _find_approval(context: RuntimeContext, action_code: str):
        return agent_approval_service.find_approval_by_action(context.db, context.run_id, action_code)

    def _llm_calls_used(self, context: RuntimeContext) -> int:
        run = getattr(context, "run", None)
        return int(run.llm_calls_used) if run is not None else 0

    def _call_llm(self, current, context, call_name: str, prompt_version: str, user_content: str, response_model):
        if self._llm_gateway is None:
            raise AgentError("LLM Gateway 未注入，无法执行模型调用", error_code="agent_llm_gateway_missing")
        scene_code = SCENE_BY_SOURCE[current.source_type]
        config = get_model_config_by_scene(context.db, scene_code)  # 配置不可用 → LLMConfigurationError
        provider, model, scene_config = config["provider"], config["model"], config["scene_config"]
        final_user = _apply_prompt_template(scene_config.prompt_template, user_content)
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=load_instructions()),
                LLMMessage(role="user", content=final_user),
            ],
            response_mode="pydantic",
            temperature=0.0,
            max_tokens=LLM_MAX_TOKENS,
            timeout_seconds=float(model.timeout_seconds),
        )
        started = time.monotonic()
        result = self._llm_gateway.complete(provider, model, request, response_model=response_model)
        duration_ms = int((time.monotonic() - started) * 1000)
        invocation = {
            "kind": "llm",
            "name": f"llm:{call_name}",
            "status": "succeeded",
            "input_summary": {
                "scene_code": scene_code,
                "prompt_version": prompt_version,
                "user_content_chars": len(final_user),
            },
            "output_summary": {"finish_reason": result.finish_reason},
            "provider_name": result.provider_name,
            "model_name": result.model_name,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "duration_ms": duration_ms,
        }
        current.model_metadata = {"provider_name": result.provider_name, "model_name": result.model_name}
        return result.parsed, invocation

    @staticmethod
    def _normalize_clauses(items: list) -> tuple[list, list[str]]:
        """程序化 clause_id 去重与格式校验；非法格式替换为 REQ-NNN。"""
        import re

        seen: dict[str, Any] = {}
        warnings: list[str] = []
        counter = 0
        for item in items:
            if not (item.text or "").strip():
                warnings.append("存在空文本条款，已丢弃")
                continue
            clause_id = str(item.clause_id or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", clause_id):
                counter += 1
                clause_id = f"REQ-{counter:03d}"
            if clause_id in seen:
                warnings.append(f"clause_id 重复: {clause_id}，已合并")
                continue
            seen[clause_id] = item.model_copy(update={"clause_id": clause_id})
        clauses = list(seen.values())
        # 顺序稳定：按首次出现顺序
        return clauses, warnings

    def _normalize_plan(self, items: list, clause_ids: set) -> list:
        result = []
        seen_pairs = set()
        for item in items:
            if item.clause_id not in clause_ids:
                continue
            pair = (item.clause_id, item.dimension)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            result.append(item)
        return result

    # ── 各步骤 ──

    def _step_load_source(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        output, invocation = self._run_tool(
            "load_source_context", context,
            LoadSourceContextInput(source_type=current.source_type, source_id=current.source_id),
        )
        if not output.found:
            return self._failed(current, "agent_source_not_found", "来源不存在或已删除")
        source = output.source
        if source.get("project_id") != context.project_id:
            return self._failed(
                current, "agent_project_mismatch",
                f"来源归属项目 {source.get('project_id')} 与 Run 归属项目 {context.project_id} 不一致",
            )
        current.source_context = redact(source)
        current.source_hash = output.source_hash
        current.phase = "load_project_context"
        return self._continue(current, invocations=[invocation])

    def _step_load_project_context(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        output, invocation = self._run_tool(
            "load_project_module_context", context,
            LoadProjectModuleContextInput(
                project_id=current.project_id,
                module_id=current.source_context.get("module_id"),
            ),
        )
        current.project_context = redact(output.model_dump())
        if output.module_mismatch:
            current.warnings.append("来源所属模块与项目不一致")
        current.phase = "load_existing_cases"
        return self._continue(current, invocations=[invocation])

    def _step_load_existing_cases(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        invocations = []
        case_kind = "function" if current.source_type == "requirement" else "api"
        existing_input = ListExistingCasesInput(
            project_id=current.project_id,
            case_kind=case_kind,
            requirement_id=current.source_id if current.source_type == "requirement" else None,
            limit=100,
        )
        existing_out, existing_inv = self._run_tool("list_existing_cases", context, existing_input)
        invocations.append(existing_inv)
        current.existing_cases = existing_out.cases

        docs_out, docs_inv = self._run_tool(
            "list_related_api_documents", context,
            ListRelatedApiDocumentsInput(project_id=current.project_id, limit=50),
        )
        invocations.append(docs_inv)
        current.related_api_documents = docs_out.documents

        current.phase = "scope_gate"
        return self._continue(current, invocations=invocations)

    def _step_scope_gate(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        approval = self._find_approval(context, GATE_SCOPE)
        if approval is None:
            # 首次进入：创建 pending Approval（Runner 负责落库与 waiting_approval）
            return StepOutcome(
                status="waiting_approval",
                next_state=current.model_dump(),
                approval_to_create={
                    "action_code": GATE_SCOPE,
                    "request_json": {
                        "source": {
                            "type": current.source_type,
                            "id": current.source_id,
                            "title_or_name": current.source_context.get("title")
                            or current.source_context.get("name"),
                            "project_id": current.project_id,
                            "module_id": current.source_context.get("module_id"),
                        },
                        "case_types": current.requested_case_types,
                        "max_cases": current.max_cases,
                        "user_goal": current.user_goal,
                        "warnings": current.warnings,
                    },
                },
                emitted_events=[{"event_type": "scope_gate_requested", "payload_json": {}}],
            )
        current.scope_approval_id = approval.id
        if approval.status == "pending":
            return StepOutcome(status="waiting_approval", next_state=current.model_dump())
        if approval.status == "rejected":
            return self._cancelled(current, "agent_gate_rejected", "范围确认被拒绝，Run 取消")
        if approval.status != "approved":
            return self._failed(current, "agent_gate_conflict", f"范围审批状态异常: {approval.status}")

        resolution = _parse_resolution(approval.resolution_json, ScopeResolution)
        if resolution.case_types is not None:
            if not resolution.case_types or any(t not in ALLOWED_CASE_TYPES for t in resolution.case_types):
                return self._failed(current, "agent_invalid_resolution", "决议中的 case_types 非法")
            current.requested_case_types = list(dict.fromkeys(resolution.case_types))
        if resolution.max_cases is not None:
            if not (1 <= resolution.max_cases <= MAX_CASES_LIMIT):
                return self._failed(current, "agent_invalid_resolution", "决议中的 max_cases 非法")
            current.max_cases = resolution.max_cases
        if resolution.user_goal is not None:
            if len(resolution.user_goal) > USER_GOAL_MAX_LEN:
                return self._failed(current, "agent_invalid_resolution", "决议中的 user_goal 过长")
            current.user_goal = resolution.user_goal
        current.phase = "analyze_and_plan"
        return self._continue(
            current,
            emitted_events=[{"event_type": "scope_gate_approved", "payload_json": {"approval_id": approval.id}}],
        )

    def _step_analyze_and_plan(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        user_content = load_prompt(PROMPT_VERSION_ANALYZE).format(
            source_context=json.dumps(current.source_context, ensure_ascii=False),
            project_context=json.dumps(current.project_context, ensure_ascii=False),
            existing_cases=json.dumps(current.existing_cases, ensure_ascii=False)[:8000],
            related_api_documents=json.dumps(current.related_api_documents, ensure_ascii=False)[:4000],
            case_types=", ".join(current.requested_case_types),
            max_cases=current.max_cases,
            user_goal=current.user_goal,
        )
        parsed, invocation = self._call_llm(
            current, context, "analyze_and_plan", PROMPT_VERSION_ANALYZE, user_content, AnalyzeAndPlanOutput
        )
        clauses, clause_warnings = self._normalize_clauses(parsed.atomic_clauses)
        if not clauses:
            return self._failed(current, "agent_no_clauses", "模型未输出有效原子条款")
        current.atomic_clauses = clauses
        current.warnings.extend(clause_warnings)
        current.coverage_plan = self._normalize_plan(parsed.coverage_plan, {c.clause_id for c in clauses})
        current.assumptions = parsed.assumptions
        current.warnings.extend(parsed.warnings)
        current.phase = "create_coverage_artifact"
        invocation["output_summary"] = {
            "clauses": len(clauses),
            "plan_items": len(current.coverage_plan),
            "finish_reason": invocation["output_summary"].get("finish_reason"),
        }
        return self._continue(current, invocations=[invocation])

    def _step_create_coverage_artifact(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        artifact = agent_artifact_service.create_artifact(
            context.db,
            session_id=context.session_id,
            agent_run_id=context.run_id,
            artifact_type="coverage_matrix",
            payload_json={
                "atomic_clauses": [c.model_dump() for c in current.atomic_clauses],
                "coverage_plan": [p.model_dump() for p in current.coverage_plan],
                "matrix": [],
                "missing": [],
                "assumptions": current.assumptions,
                "warnings": current.warnings,
                "source_hash": current.source_hash,
                "prompt_version": PROMPT_VERSION_ANALYZE,
            },
            created_by_user_id=current.requester_user_id,
        )
        current.coverage_artifact_id = artifact.id
        current.coverage_artifact_version = artifact.version
        current.phase = "coverage_gate"
        return self._continue(
            current,
            emitted_events=[
                {"event_type": "artifact_created", "payload_json": {"artifact_id": artifact.id, "artifact_type": "coverage_matrix"}}
            ],
        )

    def _step_coverage_gate(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        approval = self._find_approval(context, GATE_COVERAGE)
        if approval is None:
            return StepOutcome(
                status="waiting_approval",
                next_state=current.model_dump(),
                approval_to_create={
                    "action_code": GATE_COVERAGE,
                    "artifact_id": current.coverage_artifact_id,
                    "request_json": {
                        "artifact_id": current.coverage_artifact_id,
                        "clause_count": len(current.atomic_clauses),
                        "plan_count": len(current.coverage_plan),
                        "assumptions": current.assumptions,
                        "warnings": current.warnings,
                    },
                },
                emitted_events=[{"event_type": "coverage_gate_requested", "payload_json": {}}],
            )
        current.coverage_approval_id = approval.id
        if approval.status == "pending":
            return StepOutcome(status="waiting_approval", next_state=current.model_dump())
        if approval.status == "rejected":
            return self._cancelled(current, "agent_gate_rejected", "覆盖计划被拒绝，Run 取消")
        if approval.status != "approved":
            return self._failed(current, "agent_gate_conflict", f"覆盖计划审批状态异常: {approval.status}")

        resolution = _parse_resolution(approval.resolution_json, CoverageResolution)
        if resolution.coverage_plan is not None:
            # 受控修改：修改内容必须重新通过校验（clause 引用 + 去重）
            clause_ids = {c.clause_id for c in current.atomic_clauses}
            new_plan = self._normalize_plan(resolution.coverage_plan, clause_ids)
            if len(new_plan) != len(resolution.coverage_plan):
                return self._failed(current, "agent_invalid_resolution", "决议中的 coverage_plan 含非法条款引用")
            current.coverage_plan = new_plan
        current.phase = "generate_candidates"
        return self._continue(
            current,
            emitted_events=[{"event_type": "coverage_gate_approved", "payload_json": {"approval_id": approval.id}}],
        )

    def _step_generate_candidates(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        user_content = load_prompt(PROMPT_VERSION_GENERATE).format(
            atomic_clauses=json.dumps([c.model_dump() for c in current.atomic_clauses], ensure_ascii=False),
            coverage_plan=json.dumps([p.model_dump() for p in current.coverage_plan], ensure_ascii=False),
            existing_cases=json.dumps(current.existing_cases, ensure_ascii=False)[:8000],
            case_types=", ".join(current.requested_case_types),
            max_cases=current.max_cases,
            user_goal=current.user_goal,
            assumptions=json.dumps(current.assumptions, ensure_ascii=False),
        )
        if current.source_type == "requirement":
            response_model = GenerateFunctionCandidatesOutput
        else:
            response_model = GenerateApiCandidatesOutput
        parsed, invocation = self._call_llm(
            current, context, "generate_candidates", PROMPT_VERSION_GENERATE, user_content, response_model
        )

        clause_ids = {c.clause_id for c in current.atomic_clauses}
        new_candidates: list[CandidateState] = []
        truncated = False
        for item in parsed.candidates:
            payload = item.model_dump(exclude={"candidate_id"})
            unknown_refs = [cid for cid in item.covered_clause_ids if cid not in clause_ids]
            if unknown_refs:
                current.warnings.append(f"候选引用了未知 clause_id: {unknown_refs}")
            covered = [cid for cid in item.covered_clause_ids if cid in clause_ids]
            if len(new_candidates) >= current.max_cases:
                truncated = True
                break
            current.next_candidate_index += 1
            candidate_id = f"CASE-{current.next_candidate_index:03d}"
            new_candidates.append(
                CandidateState(candidate_id=candidate_id, case=payload, covered_clause_ids=covered)
            )
        if truncated:
            current.warnings.append(f"模型返回候选超过 max_cases={current.max_cases}，已程序强制截断")
        if not new_candidates:
            return self._failed(current, "agent_no_valid_candidates", "模型未生成任何候选")
        current.candidates = new_candidates
        current.phase = "validate_candidates"
        invocation["output_summary"] = {"candidates": len(new_candidates), "finish_reason": invocation["output_summary"].get("finish_reason")}
        return self._continue(current, invocations=[invocation])

    def _step_validate_candidates(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        case_kind = "function" if current.source_type == "requirement" else "api"
        invocations = []
        schema_out, schema_inv = self._run_tool(
            "validate_case_schema", context,
            ValidateCaseSchemaInput(case_kind=case_kind, candidates=[c.case for c in current.candidates]),
        )
        invocations.append(schema_inv)
        business_out, business_inv = self._run_tool(
            "validate_case_business_rules", context,
            ValidateCaseBusinessRulesInput(case_kind=case_kind, candidates=[c.case for c in current.candidates]),
        )
        invocations.append(business_inv)

        errors: list[dict] = []
        kept: list[CandidateState] = []
        for candidate, schema_item, business_item in zip(current.candidates, schema_out.results, business_out.results):
            item_errors = list(schema_item.errors) + list(business_item.errors)
            if item_errors:
                errors.append({"candidate_id": candidate.candidate_id, "errors": item_errors})
            else:
                kept.append(candidate)
        current.validation_errors = errors
        current.candidates = kept
        current.phase = "deduplicate"
        return self._continue(
            current,
            invocations=invocations,
            emitted_events=[{"event_type": "candidates_validated", "payload_json": {"valid": len(kept), "invalid": len(errors)}}],
        )

    def _step_deduplicate(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        case_kind = "function" if current.source_type == "requirement" else "api"
        output, invocation = self._run_tool(
            "deduplicate_cases", context,
            DeduplicateCasesInput(
                case_kind=case_kind,
                candidates=[c.case for c in current.candidates],
                existing=current.existing_cases,
            ),
        )
        keep = set(output.keep_indexes)
        dropped = [c.candidate_id for i, c in enumerate(current.candidates) if i not in keep]
        current.candidates = [c for i, c in enumerate(current.candidates) if i in keep]
        current.duplicate_relations = [d.model_dump() for d in output.duplicates]
        if dropped:
            current.warnings.append(f"去重丢弃候选: {dropped}")
        current.phase = "compute_coverage"
        return self._continue(
            current,
            invocations=[invocation],
            emitted_events=[{"event_type": "candidates_deduplicated", "payload_json": {"dropped": dropped}}],
        )

    def _step_compute_coverage(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        output, invocation = self._run_tool(
            "compute_coverage_matrix", context,
            ComputeCoverageMatrixInput(
                clauses=[{"clause_id": c.clause_id, "text": c.text} for c in current.atomic_clauses],
                candidates=[
                    {"candidate_id": c.candidate_id, "name": c.candidate_id, "covered_clause_ids": c.covered_clause_ids}
                    for c in current.candidates
                ],
            ),
        )
        current.coverage_matrix = output.model_dump()
        if output.unknown_refs:
            current.warnings.append(f"未知条款引用: {output.unknown_refs}")
        current.phase = "api_dry_run" if current.source_type == "api_document" else "repair_decision"
        return self._continue(current, invocations=[invocation])

    def _step_api_dry_run(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        invocations = []
        failures = []
        for candidate in current.candidates:
            output, invocation = self._run_tool(
                "dry_run_api_case_codegen", context,
                DryRunApiCaseCodegenInput(candidate=candidate.case),
            )
            invocations.append(invocation)
            candidate.dry_run_ok = output.ok
            candidate.dry_run_reason = output.reason
            if not output.ok:
                failures.append(candidate.candidate_id)
                current.validation_errors.append(
                    {"candidate_id": candidate.candidate_id, "errors": [f"dry_run: {output.reason}"]}
                )
        if failures:
            current.warnings.append(f"API dry-run 失败候选: {failures}")
        current.phase = "repair_decision"
        return self._continue(current, invocations=invocations)

    def _step_repair_decision(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        missing = current.coverage_matrix.get("uncovered_clause_ids") or []
        has_errors = bool(current.validation_errors)
        dry_failures = [c.candidate_id for c in current.candidates if c.dry_run_ok is False]
        no_candidates = not current.candidates
        need_repair = has_errors or bool(missing) or bool(dry_failures) or no_candidates

        if not need_repair:
            current.phase = "finalize_artifacts"
            return self._continue(current)

        if no_candidates and not (has_errors or missing or dry_failures):
            return self._failed(current, "agent_no_valid_candidates", "没有有效候选，Run 终止")

        if current.repair_round >= MAX_REPAIR_ROUNDS or self._llm_calls_used(context) >= MAX_LLM_CALLS:
            if current.candidates:
                current.warnings.append(
                    f"达到修正上限（repair_round={current.repair_round}，llm_calls={self._llm_calls_used(context)}），"
                    f"仍有缺口/错误，保留有效候选并如实记录（不伪造成功覆盖）"
                )
                current.phase = "finalize_artifacts"
                return self._continue(current)
            return self._failed(current, "agent_no_valid_candidates", "达到修正上限且无有效候选，Run 终止")

        problem_candidates = [
            {"candidate_id": c.candidate_id, "case": c.case, "covered_clause_ids": c.covered_clause_ids, "dry_run_reason": c.dry_run_reason}
            for c in current.candidates
            if c.dry_run_ok is False
        ]
        user_content = load_prompt(PROMPT_VERSION_REPAIR).format(
            atomic_clauses=json.dumps([c.model_dump() for c in current.atomic_clauses], ensure_ascii=False),
            validation_errors=json.dumps(current.validation_errors, ensure_ascii=False)[:4000],
            duplicate_summary=json.dumps(current.duplicate_relations, ensure_ascii=False)[:2000],
            missing_coverage=json.dumps(missing, ensure_ascii=False),
            problem_candidates=json.dumps(problem_candidates, ensure_ascii=False)[:8000],
            case_types=", ".join(current.requested_case_types),
            max_cases=current.max_cases,
            user_goal=current.user_goal,
        )
        if current.source_type == "requirement":
            response_model = RepairFunctionOutput
        else:
            response_model = RepairApiOutput
        parsed, invocation = self._call_llm(
            current, context, "repair_candidates", PROMPT_VERSION_REPAIR, user_content, response_model
        )

        clause_ids = {c.clause_id for c in current.atomic_clauses}
        by_id = {c.candidate_id: c for c in current.candidates}
        for item in parsed.repaired:
            payload = item.model_dump(exclude={"candidate_id"})
            covered = [cid for cid in item.covered_clause_ids if cid in clause_ids]
            unknown = [cid for cid in item.covered_clause_ids if cid not in clause_ids]
            if unknown:
                current.warnings.append(f"修正候选引用了未知 clause_id: {unknown}")
            if item.candidate_id and item.candidate_id in by_id:
                existing = by_id[item.candidate_id]
                existing.case = payload
                existing.covered_clause_ids = covered
                existing.revision += 1
                existing.dry_run_ok = None
                existing.dry_run_reason = ""
            elif len(current.candidates) < current.max_cases:
                current.next_candidate_index += 1
                current.candidates.append(
                    CandidateState(
                        candidate_id=f"CASE-{current.next_candidate_index:03d}",
                        case=payload,
                        covered_clause_ids=covered,
                    )
                )
            else:
                current.warnings.append(f"达到 max_cases={current.max_cases}，跳过新增修正候选")
        current.repair_round += 1
        current.phase = "validate_candidates"
        invocation["output_summary"] = {"repaired": len(parsed.repaired), "finish_reason": invocation["output_summary"].get("finish_reason")}
        return self._continue(
            current,
            invocations=[invocation],
            emitted_events=[{"event_type": "repair_started", "payload_json": {"repair_round": current.repair_round}}],
        )

    def _step_finalize_artifacts(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        invocations = []
        # 来源变化检测：重新读取来源哈希并比较（不自动重新生成）
        source_out, source_inv = self._run_tool(
            "load_source_context", context,
            LoadSourceContextInput(source_type=current.source_type, source_id=current.source_id),
        )
        invocations.append(source_inv)
        if not source_out.found or source_out.source_hash != current.source_hash:
            # 来源已变化：记录警告，不自动重新生成；T07 保存前必须再次强制比较
            current.warnings.append("source_changed: 来源内容已变化，保存前需重新确认")

        # 覆盖矩阵 Artifact：回填 matrix/missing
        if current.coverage_artifact_id is not None:
            artifact = agent_artifact_service.get_artifact(
                context.db, current.coverage_artifact_id, current.requester_user_id
            )
            agent_artifact_service.update_payload(
                context.db, artifact,
                {
                    "atomic_clauses": [c.model_dump() for c in current.atomic_clauses],
                    "coverage_plan": [p.model_dump() for p in current.coverage_plan],
                    "matrix": current.coverage_matrix.get("matrix", []),
                    "missing": current.coverage_matrix.get("uncovered_clause_ids", []),
                    "assumptions": current.assumptions,
                    "warnings": current.warnings,
                    "source_hash": current.source_hash,
                    "prompt_version": PROMPT_VERSION_ANALYZE,
                },
            )

        case_set_payload = {
            "source_type": current.source_type,
            "source_id": current.source_id,
            "source_hash": current.source_hash,
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "revision": c.revision,
                    "case": c.case,
                    "covered_clause_ids": c.covered_clause_ids,
                    "dry_run_ok": c.dry_run_ok,
                }
                for c in current.candidates
            ],
            "validation_summary": {"error_count": len(current.validation_errors), "details": current.validation_errors},
            "duplicate_summary": current.duplicate_relations,
            "coverage_summary": {
                "covered_count": current.coverage_matrix.get("covered_count", 0),
                "uncovered_count": current.coverage_matrix.get("uncovered_count", 0),
                "uncovered_clause_ids": current.coverage_matrix.get("uncovered_clause_ids", []),
            },
            "repair_round": current.repair_round,
            "warnings": current.warnings,
            "model_metadata": current.model_metadata,
        }
        if current.case_set_artifact_id is None:
            artifact = agent_artifact_service.create_artifact(
                context.db,
                session_id=context.session_id,
                agent_run_id=context.run_id,
                artifact_type="test_case_set",
                payload_json=case_set_payload,
                created_by_user_id=current.requester_user_id,
            )
        else:
            existing_artifact = agent_artifact_service.get_artifact(
                context.db, current.case_set_artifact_id, current.requester_user_id
            )
            artifact = agent_artifact_service.create_next_version(context.db, existing_artifact)
            agent_artifact_service.update_payload(context.db, artifact, case_set_payload)
        current.case_set_artifact_id = artifact.id
        current.case_set_artifact_version = artifact.version
        current.phase = "save_gate"
        return self._continue(
            current,
            invocations=invocations,
            emitted_events=[
                {"event_type": "artifact_created", "payload_json": {"artifact_id": artifact.id, "artifact_type": "test_case_set"}}
            ],
        )

    def _step_save_gate(self, current: CaseGenerationState, context: RuntimeContext) -> StepOutcome:
        approval = self._find_approval(context, GATE_SAVE)
        if approval is None:
            return StepOutcome(
                status="waiting_approval",
                next_state=current.model_dump(),
                approval_to_create={
                    "action_code": GATE_SAVE,
                    "artifact_id": current.case_set_artifact_id,
                    "request_json": {
                        "artifact_id": current.case_set_artifact_id,
                        "candidate_count": len(current.candidates),
                        "warnings": current.warnings,
                    },
                },
                emitted_events=[{"event_type": "save_gate_requested", "payload_json": {}}],
            )
        current.save_approval_id = approval.id
        if approval.status == "pending":
            return StepOutcome(status="waiting_approval", next_state=current.model_dump())
        if approval.status == "rejected":
            return self._cancelled(current, "agent_gate_rejected", "保存审批被拒绝，Run 取消")
        if approval.status != "approved":
            return self._failed(current, "agent_gate_conflict", f"保存审批状态异常: {approval.status}")
        # 保存动作由 T07 执行；approved 后 Workflow 正常结束
        current.phase = "done"
        return self._continue(
            current,
            emitted_events=[{"event_type": "save_gate_approved", "payload_json": {"approval_id": approval.id}}],
        )
