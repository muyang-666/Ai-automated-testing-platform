"""case_generation 端到端集成测试。

- 全部 SQLite + Fake Gateway（按调用顺序回放结构化输出）+ 虚构需求/接口文档；
- 零网络、零真实 LLM、零业务表写入、零 pytest 执行；
- 覆盖三个 GATE、修复循环（0–2 轮 / 最多 4 次 LLM）、轨迹与计数、来源变化、取消。
"""

import pytest

from app.agents.bootstrap import build_default_skill_registry, build_default_tool_registry
from app.agents.runtime.errors import RunNotExecutableError
from app.agents.runtime.runner import AgentRunner
from app.agents.skills.case_generation.schemas import (
    AnalyzeAndPlanOutput,
    ApiCandidateOut,
    AtomicClause,
    CoveragePlanItem,
    FunctionCandidateOut,
    GenerateApiCandidatesOutput,
    GenerateFunctionCandidatesOutput,
    RepairApiOutput,
    RepairFunctionOutput,
)
from app.exceptions.llm_errors import LLMOutputValidationError
from app.models.agent_approval import AgentApproval
from app.models.agent_artifact import AgentArtifact
from app.models.agent_step import AgentStep
from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.models.llm_model import LLMModel
from app.models.llm_provider import LLMProvider
from app.models.llm_scene_config import LLMSceneConfig
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.role import Role
from app.models.test_module import TestModule as ModuleModel
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.schemas.llm_gateway import LLMResult
from app.services import (
    agent_approval_service,
    agent_run_service,
    agent_session_service,
)
from app.workers.agent_worker import AgentWorker

PROJECT_ID = 101
USER_ID = 1
SECRET_AUTH = "Bearer sk-secret-123"
SECRET_TOKEN = "tok-456"

GATE_SCOPE = "confirm_case_generation_scope"
GATE_COVERAGE = "confirm_case_coverage_plan"
GATE_SAVE = "save_generated_case_candidates"


class FakeGateway:
    """按调用顺序回放响应；响应为结构化输出对象或异常。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, provider, model, request, response_model=None):
        self.calls.append({"provider_name": provider.name, "model_name": model.model_name, "request": request})
        if not self.responses:
            raise AssertionError("FakeGateway 响应不足")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(
            content="",
            parsed=item,
            provider_name=provider.name,
            model_name=model.model_name,
            prompt_tokens=10,
            completion_tokens=20,
            duration_ms=1,
            finish_reason="stop",
        )


def _plan_output():
    return AnalyzeAndPlanOutput(
        atomic_clauses=[
            AtomicClause(clause_id="REQ-001", text="用户可正常登录", priority="P0"),
            AtomicClause(clause_id="REQ-002", text="密码错误时给出提示并锁定", priority="P1"),
        ],
        coverage_plan=[
            CoveragePlanItem(clause_id="REQ-001", dimension="正常场景"),
            CoveragePlanItem(clause_id="REQ-002", dimension="异常场景"),
        ],
        assumptions=["密码规则未明确，假设为 8 位以上"],
        warnings=[],
    )


def _fn_candidate(case_name, steps, expected, covered, case_type="正常场景"):
    return FunctionCandidateOut(
        case_name=case_name,
        case_type=case_type,
        priority="P1",
        steps_json=steps,
        expected_result=expected,
        covered_clause_ids=covered,
    )


def _api_candidate(name, body, expected, covered, case_type="正常场景", method="POST", url="/login"):
    return ApiCandidateOut(
        name=name,
        method=method,
        url=url,
        headers={"Content-Type": "application/json"},
        body=body,
        expected_result=expected,
        case_type=case_type,
        priority="P1",
        covered_clause_ids=covered,
    )


def _seed_base(db):
    db.add(Project(id=PROJECT_ID, name="登录项目", status="active", is_deleted=False))
    for code in ("tester",):
        db.add(Role(code=code, name=code, status="active"))
    db.flush()
    user = User(id=USER_ID, username="tester1", password_hash="x", salt="y", status="active", is_deleted=False)
    db.add(user)
    db.flush()
    tester_role = db.query(Role).filter(Role.code == "tester").one()
    db.add(UserRole(user_id=user.id, role_id=tester_role.id))
    db.add(UserProjectPermission(user_id=user.id, project_id=PROJECT_ID, can_operate=True))
    db.commit()


def _seed_llm_scenes(db):
    provider = LLMProvider(
        name="FakeProvider", provider_type="openai_compatible", base_url="https://fake.invalid/v1",
        api_key="fake-key", status="active", is_deleted=False,
    )
    db.add(provider)
    db.flush()
    model = LLMModel(
        provider_id=provider.id, model_name="fake-model", display_name="Fake",
        temperature=0.0, max_tokens=8192, timeout_seconds=60, status="active", is_deleted=False,
    )
    db.add(model)
    db.flush()
    for scene_code in ("requirement_to_function_case", "api_doc_to_api_case"):
        db.add(LLMSceneConfig(scene_code=scene_code, scene_name=scene_code, model_id=model.id, enabled=True))
    db.commit()


def _seed_requirement(db, content="用户名密码登录，密码错误 5 次锁定 30 分钟。"):
    module = ModuleModel(project_id=PROJECT_ID, name="登录模块")
    db.add(module)
    db.flush()
    requirement = RequirementDoc(
        project_id=PROJECT_ID, module_id=module.id, title="用户登录需求",
        content=content, requirement_type="功能需求", status="confirmed", is_deleted=False,
    )
    db.add(requirement)
    db.commit()
    return requirement


def _seed_api_doc(db):
    module = ModuleModel(project_id=PROJECT_ID, name="登录模块")
    db.add(module)
    db.flush()
    doc = ApiDocument(
        project_id=PROJECT_ID, module_id=module.id, name="登录接口文档", method="POST",
        url="/login", content="POST /login",
        headers_json={"Authorization": SECRET_AUTH, "X-Token": SECRET_TOKEN},
        status="active", is_deleted=False,
    )
    db.add(doc)
    db.commit()
    return doc


def _make_runner(fake_gateway):
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(gateway_factory=lambda: fake_gateway, tool_registry=tool_registry)
    return AgentRunner(skill_registry, tool_registry)


def _make_run(db, source_type, source_id, input_json=None):
    session = agent_session_service.create_session(db, USER_ID, PROJECT_ID, "集成测试会话")
    db.commit()
    run = agent_run_service.create_run(
        db, session, "case_generation", USER_ID, PROJECT_ID,
        input_json=input_json or {"source_type": source_type, "source_id": source_id},
        max_steps=30,
    )
    db.commit()
    return session, run


def _approval(db, run_id, action_code):
    return (
        db.query(AgentApproval)
        .filter(AgentApproval.agent_run_id == run_id, AgentApproval.action_code == action_code)
        .first()
    )


def _approve(db, approval, resolution=None):
    agent_approval_service.approve(
        db, approval, resolved_by_user_id=USER_ID,
        resolution_json=resolution or {"approved": True},
    )
    db.commit()


def _state(db, run):
    return (run.output_json or {}).get("workflow_state", {})


def _step_names(db, run):
    return [s.step_name for s in db.query(AgentStep).filter(AgentStep.agent_run_id == run.id).order_by(AgentStep.sequence_no.asc()).all()]


# ── Requirement happy path ──


def test_requirement_happy_path(db_session, monkeypatch):
    import app.utils.file_writer as file_writer
    monkeypatch.setattr(file_writer, "save_test_code_to_file", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应写文件")))

    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[
            _fn_candidate("登录成功", ["打开登录页", "登录"], "跳转首页", ["REQ-001"]),
            _fn_candidate("密码错误锁定", ["打开登录页", "输错密码"], "提示错误并锁定", ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    # GATE 1：范围确认
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    scope = _approval(db_session, run.id, GATE_SCOPE)
    assert scope is not None and scope.status == "pending"
    assert gateway.calls == []  # GATE 前不调用 LLM
    _approve(db_session, scope)

    # GATE 2：覆盖计划确认
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    coverage = _approval(db_session, run.id, GATE_COVERAGE)
    assert coverage is not None
    assert gateway.calls and len(gateway.calls) == 1  # analyze 已执行
    coverage_artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "coverage_matrix").one()
    assert coverage_artifact.id == coverage.artifact_id  # GATE 关联正确的 coverage Artifact
    _approve(db_session, coverage)

    # 生成 + 校验 + 覆盖 + GATE 3：保存审批
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    save = _approval(db_session, run.id, GATE_SAVE)
    assert save is not None
    case_set = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    assert save.artifact_id == case_set.id
    assert case_set.payload_json["candidates"][0]["candidate_id"] == "CASE-001"
    assert case_set.payload_json["coverage_summary"]["uncovered_count"] == 0
    assert case_set.status == "draft"  # 不直接 saved
    assert gateway.calls and len(gateway.calls) == 2  # analyze + generate

    # 批准保存 → 成功结束（保存动作留 T07）
    _approve(db_session, save)
    runner.run(db_session, run)
    assert run.status == "succeeded"
    assert run.llm_calls_used == 2
    assert run.tool_calls_used > 0
    assert run.prompt_tokens == 20
    names = _step_names(db_session, run)
    assert "llm:analyze_and_plan" in names
    assert "llm:generate_candidates" in names
    assert "load_source_context" in names
    assert "deduplicate_cases" in names


# ── ApiDocument happy path ──


def test_api_document_happy_path(db_session, monkeypatch):
    import app.utils.file_writer as file_writer
    monkeypatch.setattr(file_writer, "save_test_code_to_file", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应写文件")))

    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    doc = _seed_api_doc(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateApiCandidatesOutput(candidates=[
            _api_candidate("登录成功", {"username": "valid", "password": "correct"}, {"code": 200}, ["REQ-001"]),
            _api_candidate("密码错误", {"username": "valid", "password": "wrong"}, {"code": 401}, ["REQ-002"], case_type="异常场景"),
            _api_candidate("密码缺失", {"username": "valid"}, {"code": 400}, ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "api_document", doc.id)
    before = db_session.query(APICase).count()

    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    _approve(db_session, _approval(db_session, run.id, GATE_SAVE))
    runner.run(db_session, run)

    assert run.status == "succeeded"
    case_set = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidates = case_set.payload_json["candidates"]
    assert len(candidates) == 3  # 同 method+url 的三个场景全部保留
    names = _step_names(db_session, run)
    assert "dry_run_api_case_codegen" in names  # API dry-run 被调用
    assert "llm:analyze_and_plan" in names
    assert db_session.query(APICase).count() == before  # 不写业务表
    # Artifact/State 不含来源 Secret 明文
    state = _state(db_session, run)
    assert SECRET_AUTH not in str(state["source_context"])
    assert SECRET_TOKEN not in str(case_set.payload_json)


# ── GATE 行为 ──


def test_scope_gate_pending_does_not_continue(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output()])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    first = _approval(db_session, run.id, GATE_SCOPE)

    runner.run(db_session, run)  # 未审批，重新执行
    assert run.status == "waiting_approval"
    assert db_session.query(AgentApproval).count() == 1  # 不重复创建
    assert _approval(db_session, run.id, GATE_SCOPE).id == first.id
    assert gateway.calls == []  # 不继续调用 LLM


def test_scope_resolution_modifies_request(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["s"], "e", ["REQ-001"])])])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(
        db_session, _approval(db_session, run.id, GATE_SCOPE),
        resolution={"approved": True, "case_types": ["正常场景"], "max_cases": 1, "user_goal": "只覆盖正常场景"},
    )
    runner.run(db_session, run)

    state = _state(db_session, run)
    assert state["requested_case_types"] == ["正常场景"]
    assert state["max_cases"] == 1
    assert state["user_goal"] == "只覆盖正常场景"
    assert run.status == "waiting_approval"  # 到达覆盖 GATE


def test_scope_rejected_terminates(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output()])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    agent_approval_service.reject(
        db_session, _approval(db_session, run.id, GATE_SCOPE),
        resolved_by_user_id=USER_ID, resolution_json={"rejected": True},
    )
    db_session.commit()

    runner.run(db_session, run)
    assert run.status == "cancelled"  # rejected → cancelled（T07 语义，不是 failed）
    assert run.error_code == "agent_gate_rejected"
    assert gateway.calls == []


def test_coverage_rejected_terminates(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output()])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    agent_approval_service.reject(
        db_session, _approval(db_session, run.id, GATE_COVERAGE),
        resolved_by_user_id=USER_ID, resolution_json={"rejected": True},
    )
    db_session.commit()

    runner.run(db_session, run)
    assert run.status == "cancelled"  # rejected → cancelled
    assert run.error_code == "agent_gate_rejected"
    assert len(gateway.calls) == 1  # 仅 analyze 被执行


def test_coverage_resolution_plan_modification(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["s"], "e", ["REQ-001", "REQ-002"], case_type="异常场景")])])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(
        db_session, _approval(db_session, run.id, GATE_COVERAGE),
        resolution={"approved": True, "coverage_plan": [{"clause_id": "REQ-002", "dimension": "异常场景"}]},
    )
    runner.run(db_session, run)

    state = _state(db_session, run)
    assert [p["clause_id"] for p in state["coverage_plan"]] == ["REQ-002"]
    assert run.status == "waiting_approval"  # 到达保存 GATE


# ── LLM / 校验 / 修复 ──


def test_fake_gateway_output_validation_failure(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([LLMOutputValidationError("模型输出未通过 Schema 校验: x")])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)

    assert run.status == "failed"  # Gateway 错误直接失败，不重试
    assert "Schema 校验" in run.error_message
    assert run.llm_calls_used == 0  # 调用失败未计入成功调用


def test_duplicate_filtered_with_record(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    doc = _seed_api_doc(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateApiCandidatesOutput(candidates=[
            _api_candidate("登录成功", {"username": "valid"}, {"code": 200}, ["REQ-001"]),
            _api_candidate("密码错误", {"username": "valid", "password": "wrong"}, {"code": 401}, ["REQ-002"], case_type="异常场景"),
            _api_candidate("重复场景", {"username": "valid"}, {"code": 200}, ["REQ-001"]),  # 与第一条指纹相同
        ]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "api_document", doc.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    assert run.status == "waiting_approval"
    state = _state(db_session, run)
    assert len(state["candidates"]) == 2  # 3 条中去掉 1 条重复
    assert len(state["duplicate_relations"]) == 1
    assert any("去重丢弃候选" in w for w in state["warnings"])


def test_missing_coverage_triggers_one_repair(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("登录成功", ["s"], "e", ["REQ-001"])]),  # 缺 REQ-002
        RepairFunctionOutput(repaired=[_fn_candidate("锁定边界补充", ["输错5次"], "锁定", ["REQ-002"], case_type="异常场景")]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    assert run.status == "waiting_approval"
    state = _state(db_session, run)
    assert state["repair_round"] == 1
    assert len(state["candidates"]) == 2
    assert [c["candidate_id"] for c in state["candidates"]] == ["CASE-001", "CASE-002"]
    assert state["coverage_matrix"]["uncovered_count"] == 0
    assert len(gateway.calls) == 3  # analyze + generate + repair
    assert run.llm_calls_used == 3


def test_repair_replaces_candidate_keeps_id_revision(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    doc = _seed_api_doc(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateApiCandidatesOutput(candidates=[
            _api_candidate("坏候选", {"username": "valid"}, {"code": 200}, ["REQ-001"], method=""),
        ]),
        RepairApiOutput(repaired=[
            ApiCandidateOut(candidate_id="CASE-001", name="坏候选-已修复", method="POST", url="/login",
                            body={"username": "valid"}, expected_result={"code": 200},
                            case_type="正常场景", covered_clause_ids=["REQ-001"]),
            _api_candidate("密码错误锁定", {"username": "valid", "password": "wrong"}, {"code": 401}, ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "api_document", doc.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    assert run.status == "waiting_approval"  # dry-run 失败触发 repair 后到达保存 GATE
    state = _state(db_session, run)
    assert state["repair_round"] == 1
    candidate = state["candidates"][0]
    assert candidate["candidate_id"] == "CASE-001"
    assert candidate["revision"] == 2  # 被替换候选记录 revision
    assert candidate["case"]["method"] == "POST"
    assert candidate["dry_run_ok"] is True


def test_repair_capped_at_two_rounds_four_llm_calls(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    still_missing = RepairFunctionOutput(repaired=[_fn_candidate("仍缺锁定", ["s"], "e", ["REQ-001"])])
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("登录成功", ["s"], "e", ["REQ-001"])]),
        still_missing,
        still_missing,
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    assert run.status == "waiting_approval"
    state = _state(db_session, run)
    assert state["repair_round"] == 2  # 最多 2 轮
    assert len(gateway.calls) == 4  # LLM 最多 4 次
    assert run.llm_calls_used == 4
    assert any("达到修正上限" in w for w in state["warnings"])
    assert state["coverage_matrix"]["uncovered_count"] == 1  # 不伪造成功覆盖


def test_max_cases_truncation_with_warning(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[
            _fn_candidate("A", ["s"], "e", ["REQ-001"]),
            _fn_candidate("B", ["s"], "e", ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE), resolution={"approved": True, "max_cases": 1})
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    state = _state(db_session, run)
    assert len(state["candidates"]) == 1
    assert any("截断" in w for w in state["warnings"])


def test_zero_candidates_failed(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    assert run.status == "failed"
    assert run.error_code == "agent_no_valid_candidates"


def test_source_changed_warning(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["s"], "e", ["REQ-001", "REQ-002"])]),
    ])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    _approve(db_session, _approval(db_session, run.id, GATE_SCOPE))
    runner.run(db_session, run)
    # 覆盖 GATE 期间修改来源
    requirement.content = "完全不同的需求内容"
    db_session.commit()
    _approve(db_session, _approval(db_session, run.id, GATE_COVERAGE))
    runner.run(db_session, run)

    state = _state(db_session, run)
    assert any(w.startswith("source_changed") for w in state["warnings"])
    assert run.status == "waiting_approval"


def test_cancel_stops_further_calls(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output()])
    runner = _make_runner(gateway)
    _, run = _make_run(db_session, "requirement", requirement.id)

    runner.run(db_session, run)
    assert run.status == "waiting_approval"
    agent_run_service.transition_status(db_session, run, "cancelled")  # waiting_approval → cancelled 合法
    db_session.commit()

    with pytest.raises(RunNotExecutableError):
        runner.run(db_session, run)
    assert gateway.calls == []  # 取消后不再调用 LLM


# ── Worker 从默认 Registry 找到 case_generation ──


def test_worker_executes_case_generation_from_default_registry(db_session):
    _seed_base(db_session)
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    gateway = FakeGateway([_plan_output()])
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(gateway_factory=lambda: gateway, tool_registry=tool_registry)

    def runtime_factory(on_step_boundary):
        return AgentRunner(skill_registry, tool_registry, on_step_boundary=on_step_boundary)

    from app.core.database import SessionLocal

    worker = AgentWorker(
        session_factory=SessionLocal,  # Worker 会自行关闭 Session，不使用 fixture 会话
        runtime_factory=runtime_factory,
        worker_id="worker-t6",
        poll_interval_seconds=0.1,
        stale_after_seconds=300.0,
    )
    session = agent_session_service.create_session(db_session, USER_ID, PROJECT_ID, "worker 会话")
    db_session.commit()
    run = agent_run_service.create_run(
        db_session, session, "case_generation", USER_ID, PROJECT_ID,
        input_json={"source_type": "requirement", "source_id": requirement.id}, max_steps=30,
    )
    db_session.commit()

    result = worker.run_once()

    assert result.action == "completed"
    db_session.expire_all()  # Worker 使用独立 Session，刷新后断言
    assert run.status == "waiting_approval"
    assert _approval(db_session, run.id, GATE_SCOPE) is not None
    assert run.worker_id == "worker-t6"
