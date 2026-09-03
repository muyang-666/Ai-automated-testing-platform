"""case_generation Workflow 单元测试（输入校验、条款规范化、脱敏、resolution 校验）。"""

import pytest

from app.agents.registry import ToolRegistry
from app.agents.runtime.errors import AgentError
from app.agents.skills.case_generation.schemas import (
    AnalyzeAndPlanOutput,
    AtomicClause,
    CoveragePlanItem,
    CoverageResolution,
    ScopeResolution,
)
from app.agents.skills.case_generation.workflow import (
    CaseGenerationWorkflow,
    _parse_resolution,
    _validate_input,
    redact,
)


def _workflow():
    return CaseGenerationWorkflow(tool_registry=ToolRegistry())


# ── 输入合同校验 ──


def test_input_valid():
    data = _validate_input(
        {"source_type": "requirement", "source_id": 12, "case_types": ["正常场景", "正常场景", "异常场景"], "max_cases": 30, "user_goal": "重点覆盖账号锁定"}
    )
    assert data["case_types"] == ["正常场景", "异常场景"]  # 去重
    assert data["max_cases"] == 30


def test_input_invalid_source_type():
    with pytest.raises(AgentError) as exc:
        _validate_input({"source_type": "scene", "source_id": 1})
    assert exc.value.error_code == "agent_invalid_input"


def test_input_invalid_case_types():
    with pytest.raises(AgentError):
        _validate_input({"source_type": "requirement", "source_id": 1, "case_types": []})
    with pytest.raises(AgentError):
        _validate_input({"source_type": "requirement", "source_id": 1, "case_types": ["冒烟场景"]})


def test_input_invalid_max_cases():
    with pytest.raises(AgentError):
        _validate_input({"source_type": "requirement", "source_id": 1, "max_cases": 0})
    with pytest.raises(AgentError):
        _validate_input({"source_type": "requirement", "source_id": 1, "max_cases": 51})


def test_input_user_goal_too_long():
    with pytest.raises(AgentError):
        _validate_input({"source_type": "requirement", "source_id": 1, "user_goal": "x" * 501})


# ── 条款规范化（程序化去重与格式校验） ──


def test_normalize_clauses_dedupe_and_format():
    workflow = _workflow()
    items = [
        AtomicClause(clause_id="REQ-001", text="登录成功"),
        AtomicClause(clause_id="非法中文ID", text="密码错误"),
        AtomicClause(clause_id="REQ-001", text="重复条款"),
    ]

    clauses, warnings = workflow._normalize_clauses(items)

    # 非法格式被替换为 REQ-001 后与既有 REQ-001 去重合并，最终 1 条
    assert [c.clause_id for c in clauses] == ["REQ-001"]
    assert len(clauses) == 1
    assert any("重复" in w for w in warnings)


def test_normalize_plan_drops_unknown_clause_refs():
    workflow = _workflow()
    items = [
        CoveragePlanItem(clause_id="REQ-001", dimension="正常场景"),
        CoveragePlanItem(clause_id="REQ-999", dimension="正常场景"),
        CoveragePlanItem(clause_id="REQ-001", dimension="正常场景"),  # 重复对
    ]

    result = workflow._normalize_plan(items, {"REQ-001"})

    assert len(result) == 1
    assert result[0].clause_id == "REQ-001"


# ── 脱敏 ──


def test_redact_secret_keys_recursive():
    payload = {
        "headers": {"Authorization": "Bearer sk-secret-123", "Content-Type": "application/json"},
        "body": {"password": "correct", "nested": [{"X-Token": "tok-456"}]},
        "public": "可见",
    }

    result = redact(payload)

    assert result["headers"]["Authorization"] == "***"
    assert result["headers"]["Content-Type"] == "application/json"
    assert result["body"]["password"] == "***"
    assert result["body"]["nested"][0]["X-Token"] == "***"
    assert result["public"] == "可见"
    assert payload["headers"]["Authorization"] == "Bearer sk-secret-123"  # 不修改原对象


# ── GATE resolution 校验 ──


def test_parse_resolution_valid():
    resolution = _parse_resolution({"approved": True, "case_types": ["正常场景"]}, ScopeResolution)
    assert resolution.approved is True
    assert resolution.case_types == ["正常场景"]


def test_parse_resolution_invalid_type():
    with pytest.raises(AgentError) as exc:
        _parse_resolution({"max_cases": "不是数字"}, ScopeResolution)
    assert exc.value.error_code == "agent_invalid_resolution"


def test_coverage_resolution_plan_validated():
    resolution = _parse_resolution(
        {"approved": True, "coverage_plan": [{"clause_id": "REQ-001", "dimension": "正常场景"}]},
        CoverageResolution,
    )
    assert len(resolution.coverage_plan) == 1


def test_initial_state_valid():
    workflow = _workflow()
    state = workflow.initial_state({"source_type": "api_document", "source_id": 3})
    assert state["source_type"] == "api_document"
    assert state["phase"] == "load_source"
    assert state["schema_version"] == 1
