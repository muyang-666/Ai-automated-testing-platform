"""默认生产 Registry 装配（显式注册，不扫描目录、不动态 import）。

- build_default_tool_registry：注册 T05 九个只读工具（绑定真实 Tool 实例）；
- build_default_skill_registry：注册 case_generation:v1；
- import 时不启动 Worker、不调用 LLM、不访问数据库；
- 测试可注入 Fake Gateway（gateway_factory）与自定义 Registry。
"""

from app.agents.registry.skill_registry import SkillRegistry
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.agents.skills.case_generation.definition import build_case_generation_skill
from app.agents.tools.case_context_tools import (
    ListExistingCasesTool,
    ListRelatedApiDocumentsTool,
    LoadProjectModuleContextTool,
    LoadSourceContextTool,
)
from app.agents.tools.case_validation_tools import (
    ComputeCoverageMatrixTool,
    DeduplicateCasesTool,
    DryRunApiCaseCodegenTool,
    ValidateCaseBusinessRulesTool,
    ValidateCaseSchemaTool,
)

_TOOL_INSTANCES = (
    LoadSourceContextTool(),
    LoadProjectModuleContextTool(),
    ListExistingCasesTool(),
    ListRelatedApiDocumentsTool(),
    ValidateCaseSchemaTool(),
    ValidateCaseBusinessRulesTool(),
    DeduplicateCasesTool(),
    ComputeCoverageMatrixTool(),
    DryRunApiCaseCodegenTool(),
)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in _TOOL_INSTANCES:
        registry.register(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                read_only=tool.read_only,
                requires_approval=tool.requires_approval,
                input_model=tool.input_model,
                output_model=tool.output_model,
                tool=tool,
            )
        )
    return registry


def build_default_skill_registry(
    gateway_factory=None,
    tool_registry: ToolRegistry | None = None,
) -> SkillRegistry:
    registry = SkillRegistry()
    tools = tool_registry or build_default_tool_registry()
    registry.register(build_case_generation_skill(tool_registry=tools, gateway_factory=gateway_factory))
    return registry
