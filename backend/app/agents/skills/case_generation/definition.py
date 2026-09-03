"""case_generation Skill 定义（Python 显式注册，不使用 skill.yaml）。"""

from app.agents.registry.skill_registry import SkillDefinition
from app.agents.skills.case_generation.workflow import (
    SKILL_CODE,
    SKILL_VERSION,
    CaseGenerationWorkflow,
)

# 严格限定为 T05 的九个只读工具
ALLOWED_TOOL_NAMES = (
    "load_source_context",
    "load_project_module_context",
    "list_existing_cases",
    "list_related_api_documents",
    "validate_case_schema",
    "validate_case_business_rules",
    "deduplicate_cases",
    "compute_coverage_matrix",
    "dry_run_api_case_codegen",
)


def build_case_generation_skill(tool_registry, gateway_factory=None) -> SkillDefinition:
    """构造 SkillDefinition；workflow_factory 在每次 Run 时创建独立 Workflow 实例。"""

    def workflow_factory():
        return CaseGenerationWorkflow(
            tool_registry=tool_registry,
            llm_gateway=gateway_factory() if gateway_factory is not None else None,
        )

    return SkillDefinition(
        code=SKILL_CODE,
        name="用例生成",
        version=SKILL_VERSION,
        description=(
            "根据需求文本或接口文档，拆解原子条款、规划覆盖、生成并校验候选用例，"
            "经范围确认与覆盖计划确认两个 GATE 后产出覆盖矩阵与用例集 Artifact，"
            "最终创建保存审批（保存动作由后续任务执行）。"
        ),
        workflow_factory=workflow_factory,
        required_context=("source_type", "source_id"),
        allowed_tools=ALLOWED_TOOL_NAMES,
        default_max_steps=30,
    )
