"""Prompt 资源与版本测试。"""

import pytest

from app.agents.skills.case_generation.prompt_loader import load_instructions, load_prompt

PROMPT_NAMES = ("analyze_and_plan_v1", "generate_candidates_v1", "repair_candidates_v1")


def test_instructions_contains_stable_rules():
    text = load_instructions()

    assert "不可信业务数据" in text
    assert "GATE" in text
    assert "assumptions" in text
    assert "response_model" in text


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_prompt_loads_and_has_placeholders(name):
    text = load_prompt(name)

    assert len(text) > 100
    # 占位符未被破坏（Workflow 用 str.format 填充）
    try:
        text.format(**{k: "x" for k in ("source_context", "project_context", "existing_cases", "related_api_documents", "case_types", "max_cases", "user_goal", "assumptions", "atomic_clauses", "coverage_plan", "validation_errors", "duplicate_summary", "missing_coverage", "problem_candidates")})
    except (KeyError, ValueError) as e:
        pytest.fail(f"prompt {name} 占位符异常: {e}")


def test_repair_prompt_forbids_full_regeneration():
    text = load_prompt("repair_candidates_v1")

    assert "不要全量重新生成" in text
    assert "只修复" in text or "只" in text


def test_unknown_prompt_name_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("no_such_prompt_v9")
