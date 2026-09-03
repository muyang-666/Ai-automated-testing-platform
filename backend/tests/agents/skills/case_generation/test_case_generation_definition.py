"""case_generation SkillDefinition 与 bootstrap 注册测试。"""

import pytest

from app.agents.bootstrap import build_default_skill_registry, build_default_tool_registry
from app.agents.registry import SkillDefinition, SkillRegistry, ToolDefinition, ToolRegistry
from app.agents.runtime.errors import DuplicateSkillError
from app.agents.skills.case_generation.definition import (
    ALLOWED_TOOL_NAMES,
    build_case_generation_skill,
)
from app.agents.skills.case_generation.workflow import (
    SKILL_CODE,
    SKILL_VERSION,
    CaseGenerationWorkflow,
)

EXPECTED_TOOLS = {
    "load_source_context",
    "load_project_module_context",
    "list_existing_cases",
    "list_related_api_documents",
    "validate_case_schema",
    "validate_case_business_rules",
    "deduplicate_cases",
    "compute_coverage_matrix",
    "dry_run_api_case_codegen",
}


def test_skill_definition_fields():
    tools = build_default_tool_registry()
    skill = build_case_generation_skill(tool_registry=tools)

    assert isinstance(skill, SkillDefinition)
    assert skill.code == SKILL_CODE
    assert skill.version == SKILL_VERSION
    assert skill.name == "用例生成"
    assert skill.required_context == ("source_type", "source_id")
    assert set(skill.allowed_tools) == EXPECTED_TOOLS  # 严格限定为 T05 九个工具
    assert skill.default_max_steps == 30
    assert skill.workflow_factory is not None


def test_workflow_factory_creates_workflow_with_gateway():
    tools = build_default_tool_registry()
    fake_gateway = object()

    skill = build_case_generation_skill(tool_registry=tools, gateway_factory=lambda: fake_gateway)
    workflow = skill.workflow_factory()

    assert isinstance(workflow, CaseGenerationWorkflow)
    assert workflow.code == SKILL_CODE
    assert workflow.version == SKILL_VERSION
    assert workflow._llm_gateway is fake_gateway


def test_bootstrap_registers_skill_and_tools():
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(tool_registry=tool_registry)

    assert skill_registry.get(SKILL_CODE).code == SKILL_CODE
    for name in EXPECTED_TOOLS:
        definition = tool_registry.get(name)
        assert isinstance(definition, ToolDefinition)
        assert definition.tool is not None  # 绑定真实 Tool 实例
        assert definition.read_only is True


def test_duplicate_registration_contract():
    registry = SkillRegistry()
    tools = build_default_tool_registry()
    registry.register(build_case_generation_skill(tool_registry=tools))

    with pytest.raises(DuplicateSkillError):
        registry.register(build_case_generation_skill(tool_registry=tools))


def test_import_does_not_trigger_worker_or_llm():
    # import 时不启动 Worker、不调用 LLM、不访问数据库：本测试仅导入即通过
    import app.agents.bootstrap  # noqa: F401
    import app.agents.skills.case_generation.workflow  # noqa: F401
