"""P06 Conversation 安全工具白名单（不暴露 legacy 业务工具）。

可用集恒等于：registry ∩ conversation whitelist ∩ user permission ∩ Tool Policy。
首期只有无副作用只读工具（calculator），供对话链路与验收测试使用。
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.agents.skills.catalog import skill_system_summary
from app.agents.tools.artifacts.registry import register_artifact_tools


class CalculatorInput(BaseModel):
    operation: Literal["add", "subtract", "multiply", "divide"]
    left: str
    right: str


def _calculate(arguments, runtime):
    left, right = Decimal(arguments["left"]), Decimal(arguments["right"])
    operations = {
        "add": lambda: left + right,
        "subtract": lambda: left - right,
        "multiply": lambda: left * right,
        "divide": lambda: left / right,
    }
    return str(operations[arguments["operation"]]())


def build_conversation_tool_registry() -> ToolRegistry:
    """Conversation whitelist: calculator + P08 Skill/Artifact tools."""
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="calculator",
        description="四位整数/十进制加减乘除计算器（不使用 eval）。",
        input_model=CalculatorInput,
        read_only=True,
        idempotent=True,
        handler=_calculate,
    ))
    register_artifact_tools(registry)
    return registry


def build_conversation_system_prompt() -> str:
    return (
        "你是可靠的测试设计协作助手。由你根据用户意图选择工具；修改已有节点前先读取相关节点，"
        "只做满足请求的最小增量修改。Quality 工具只诊断。工具调用只是提案，权限与写入由系统裁决。\n\n"
        + skill_system_summary()
    )
