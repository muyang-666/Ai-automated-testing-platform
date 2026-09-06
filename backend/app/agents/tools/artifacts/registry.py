from pydantic import BaseModel, ConfigDict, Field

from app.agents.conversation.messages import TextContent
from app.agents.conversation.tool_executor import ToolExecutionResult, ToolReportedError
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.agents.skills.catalog import default_skill_catalog
from app.agents.tools.artifacts import handlers
from app.agents.tools.artifacts.schemas import (
    AddNodeInput, BatchInput, CoverageInput, DeleteNodeInput, DuplicateInput, EmptyInput,
    MoveNodeInput, OutlineInput, QualityInput, ReadNodesInput, RecentDiffInput,
    RequirementInput, SearchInput, UpdateNodeInput,
)


class LoadSkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(pattern=r"^[a-z0-9-]{1,64}$")


def _load_skill(arguments, runtime):
    del runtime
    try:
        skill = default_skill_catalog().load(arguments["name"])
    except KeyError:
        payload = {"status": "error", "error_code": "unknown_skill",
                   "message": "Requested Skill is not registered.", "retryable": False}
        raise ToolReportedError("unknown_skill", ToolExecutionResult(
            content=[TextContent(text="Requested Skill is not registered.")], details=payload,
        )) from None
    payload = {"status": "ok", "summary": f"Loaded Skill {skill.name}", "data": {
        "name": skill.name, "version": skill.version, "sha256": skill.sha256,
        "content": skill.content,
    }}
    return ToolExecutionResult(content=[TextContent(text=skill.content)], details=payload)


def register_artifact_tools(registry: ToolRegistry) -> None:
    definitions = [
        ("load_skill", "Load an allowlisted domain Skill by registered name.", LoadSkillInput, True, _load_skill),
        ("get_current_artifact", "Read metadata for the trusted current TestArtifact; never returns the full tree.", EmptyInput, True, handlers.get_current_artifact),
        ("read_artifact_outline", "Read a bounded lightweight outline of the current Artifact.", OutlineInput, True, handlers.read_artifact_outline),
        ("read_artifact_nodes", "Read up to 20 current Artifact nodes by stable node IDs.", ReadNodesInput, True, handlers.read_artifact_nodes),
        ("search_artifact", "Search the current Artifact by keyword, node type, or exact tag.", SearchInput, True, handlers.search_artifact),
        ("get_artifact_diff", "Read recent machine-readable changes for resolving references such as 'the second one'.", RecentDiffInput, True, handlers.get_artifact_diff),
        ("read_requirement", "Read only a requirement already bound to the current Artifact or Conversation.", RequirementInput, True, handlers.read_requirement),
        ("add_artifact_node", "Add one node through the TestArtifact application service. Requires expected_revision.", AddNodeInput, False, handlers.add_artifact_node),
        ("update_artifact_node", "Patch one node only. Requires expected_revision.", UpdateNodeInput, False, handlers.update_artifact_node),
        ("delete_artifact_node", "Delete one node/subtree after policy checks its impact. Requires expected_revision.", DeleteNodeInput, False, handlers.delete_artifact_node),
        ("move_artifact_node", "Move one node through shared tree-integrity rules. Requires expected_revision.", MoveNodeInput, False, handlers.move_artifact_node),
        ("batch_apply_artifact_operations", "Apply up to 10 related incremental edits as one Revision.", BatchInput, False, handlers.batch_apply_artifact_operations),
        ("validate_test_artifact", "Diagnose structural/test-case issues without modifying the Artifact.", QualityInput, True, handlers.validate_test_artifact),
        ("find_duplicate_cases", "Find deterministic duplicate candidates without modifying the Artifact.", DuplicateInput, True, handlers.find_duplicate_cases),
        ("analyze_test_coverage", "Report rule-based coverage dimensions and gaps without modifying the Artifact.", CoverageInput, True, handlers.analyze_test_coverage),
    ]
    for name, description, schema, read_only, handler in definitions:
        registry.register(ToolDefinition(name=name, description=description, input_model=schema,
            read_only=read_only, idempotent=read_only, handler=handler))
