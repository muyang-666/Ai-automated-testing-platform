"""case_validation_tools 测试：Schema/业务规则/去重/覆盖矩阵/dry-run 零副作用。"""

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.case_validation_tools import (
    ComputeCoverageMatrixTool,
    DeduplicateCasesTool,
    DryRunApiCaseCodegenTool,
    ValidateCaseBusinessRulesTool,
    ValidateCaseSchemaTool,
)
from app.models.api_case import APICase


def _ctx(db, user_id=1):
    return ToolContext(user_id=user_id, db=db)


def _fn_case(**overrides):
    case = {
        "case_name": "登录成功",
        "case_type": "正常场景",
        "priority": "P0",
        "steps_json": ["步骤1"],
        "expected_result": "登录成功",
    }
    case.update(overrides)
    return case


def _api_case(**overrides):
    case = {
        "name": "登录接口-正常登录",
        "method": "POST",
        "url": "https://api.example.com/v1/login",
        "headers": {"Content-Type": "application/json"},
        "body": {"username": "u1"},
        "expected_result": {"status": 200},
        "case_type": "正常场景",
        "priority": "P0",
    }
    case.update(overrides)
    return case


# ── validate_case_schema ──


def test_schema_tool_mixed_results(db_session):
    tool = ValidateCaseSchemaTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(case_kind="function", candidates=[_fn_case(), {"case_name": 123}]),
    )

    assert result.results[0].valid is True
    assert result.results[1].valid is False
    assert any("case_name" in e for e in result.results[1].errors)


def test_schema_tool_api_kind(db_session):
    tool = ValidateCaseSchemaTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(case_kind="api", candidates=[_api_case(), _api_case(headers=[1])]),
    )

    assert result.results[0].valid is True
    assert result.results[1].valid is False
    assert any("headers" in e for e in result.results[1].errors)


# ── validate_case_business_rules ──


def test_business_rules_tool(db_session):
    tool = ValidateCaseBusinessRulesTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(
            case_kind="function",
            candidates=[_fn_case(), _fn_case(case_name="", steps_json=[])],
        ),
    )

    assert result.results[0].valid is True
    assert result.results[1].valid is False
    assert any("缺少 case_name" in e for e in result.results[1].errors)


# ── deduplicate_cases ──


def test_deduplicate_tool(db_session):
    tool = DeduplicateCasesTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(
            case_kind="function",
            candidates=[_fn_case(), _fn_case(case_name=" 登录成功 "), _fn_case(case_name="密码错误")],
        ),
    )

    assert result.keep_indexes == [0, 2]
    assert len(result.duplicates) == 1
    assert result.duplicates[0].first_position == 0
    assert result.duplicates[0].duplicate_position == 1


def test_deduplicate_tool_with_summary_fingerprint(db_session):
    """已有用例以 list_existing_cases 摘要形态（仅 dedup_fingerprint）参与去重。"""
    from app.agents.validators.case_validators import case_fingerprint

    existing_summary = [
        {
            "id": 1,
            "name": "登录接口用例",
            "method": "POST",
            "url": "https://api.example.com/v1/login",
            "dedup_fingerprint": case_fingerprint("api", _api_case()),
        }
    ]
    tool = DeduplicateCasesTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(case_kind="api", candidates=[_api_case()], existing=existing_summary),
    )

    assert result.keep_indexes == []
    assert result.duplicates[0].first_origin == "existing"
    assert result.duplicates[0].duplicate_origin == "candidate"


# ── compute_coverage_matrix ──


def test_coverage_tool(db_session):
    tool = ComputeCoverageMatrixTool()
    result = tool.execute(
        _ctx(db_session),
        tool.input_model(
            clauses=[{"clause_id": "REQ-001", "text": "A"}, {"clause_id": "REQ-002", "text": "B"}],
            candidates=[
                {"candidate_id": "CASE-001", "name": "A", "covered_clause_ids": ["REQ-001"]},
            ],
        ),
    )

    assert result.covered_count == 1
    assert result.uncovered_count == 1
    assert result.uncovered_clause_ids == ["REQ-002"]
    assert result.matrix[0]["covered_by"] == ["CASE-001"]


# ── dry_run_api_case_codegen ──


def test_dry_run_valid_candidate(db_session):
    tool = DryRunApiCaseCodegenTool()

    result = tool.execute(_ctx(db_session), tool.input_model(candidate=_api_case()))

    assert result.ok is True
    assert result.reason == ""
    assert "httpx.request(" in result.generated_code
    assert "def test_case_0" in result.generated_code


def test_dry_run_missing_url_fails(db_session):
    tool = DryRunApiCaseCodegenTool()

    result = tool.execute(_ctx(db_session), tool.input_model(candidate=_api_case(url="")))

    assert result.ok is False
    assert result.reason != ""


def test_dry_run_unsupported_method_fails(db_session):
    tool = DryRunApiCaseCodegenTool()

    result = tool.execute(_ctx(db_session), tool.input_model(candidate=_api_case(method="FOO")))

    assert result.ok is False
    assert "暂不支持请求方法" in result.reason


def test_dry_run_zero_side_effects(db_session, monkeypatch):
    before = db_session.query(APICase).count()

    # 若 dry-run 误调用文件写入，测试直接失败
    import app.utils.file_writer as file_writer

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run 不应写入测试文件")

    monkeypatch.setattr(file_writer, "save_test_code_to_file", fail_if_called)

    tool = DryRunApiCaseCodegenTool()
    tool.execute(_ctx(db_session), tool.input_model(candidate=_api_case()))
    tool.execute(_ctx(db_session), tool.input_model(candidate=_api_case(name="第二次调用")))
    db_session.commit()

    after = db_session.query(APICase).count()
    assert after == before  # 数据库无新增用例行
