"""P06 Conversation 安全工具白名单（不暴露 legacy 业务工具）。

可用集恒等于：registry ∩ conversation whitelist ∩ user permission ∩ Tool Policy。
首期只有无副作用只读工具（calculator），供对话链路与验收测试使用。
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry


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
    """Conversation 模型的可见工具集合（安全、只读、无副作用）。"""
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="calculator",
        description="四位整数/十进制加减乘除计算器（不使用 eval）。",
        input_model=CalculatorInput,
        read_only=True,
        idempotent=True,
        handler=_calculate,
    ))
    return registry
