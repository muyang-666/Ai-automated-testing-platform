"""ToolRegistry 测试：定义/注册/查询/唯一性/未知错误。"""

import pytest

from app.agents.registry import ToolDefinition, ToolRegistry
from app.agents.runtime.errors import DuplicateToolError, UnknownToolError


def _tool(name="fake_tool"):
    return ToolDefinition(name=name, description="测试工具", read_only=True)


def test_register_and_get():
    registry = ToolRegistry()
    tool = _tool("list_cases")
    registry.register(tool)
    registry.register(_tool("compute_matrix"))

    assert registry.get("list_cases") is tool
    assert [t.name for t in registry.list()] == ["compute_matrix", "list_cases"]


def test_duplicate_name_rejected():
    registry = ToolRegistry()
    registry.register(_tool("save_cases"))

    with pytest.raises(DuplicateToolError) as exc:
        registry.register(_tool("save_cases"))
    assert "save_cases" in str(exc.value)
    assert exc.value.error_code == "agent_duplicate_tool"


def test_unknown_tool_error():
    registry = ToolRegistry()

    with pytest.raises(UnknownToolError) as exc:
        registry.get("ghost_tool")
    assert "ghost_tool" in str(exc.value)
    assert exc.value.error_code == "agent_unknown_tool"


def test_tool_definition_fields():
    tool = ToolDefinition(
        name="save_cases",
        description="保存候选",
        read_only=False,
        requires_approval=True,
        idempotent=True,
        required_permission="project_write",
        handler=lambda: None,
    )

    assert tool.read_only is False
    assert tool.requires_approval is True
    assert tool.idempotent is True
    assert tool.required_permission == "project_write"
    assert callable(tool.handler)
