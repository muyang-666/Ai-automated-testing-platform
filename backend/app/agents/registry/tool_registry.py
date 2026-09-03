"""ToolRegistry：工具定义的内存注册表。

- 本任务只建立定义和注册，不执行业务 Tool；
- tool name 唯一，未知/重复报明确错误；
- 不允许动态 import 任意路径。
"""

from dataclasses import dataclass
from typing import Any, Callable

from app.agents.runtime.errors import DuplicateToolError, UnknownToolError


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str = ""
    input_model: Any | None = None  # type[BaseModel] | None
    output_model: Any | None = None  # type[BaseModel] | None
    read_only: bool = True
    requires_approval: bool = False
    idempotent: bool = True
    required_permission: str | None = None
    handler: Callable | None = None  # 本任务不执行；测试可注入 Fake handler
    tool: Any | None = None  # AgentTool 实例（Workflow 经注册表调用其 execute）


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"工具 '{tool.name}' 已注册，不允许重复注册。")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"未知工具: '{name}'。已注册: {sorted(self._tools.keys())}")
        return tool

    def list(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda t: t.name)
