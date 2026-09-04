"""Small, deterministic V2-P03 tool policy boundary.

Human approval is implemented in P09.  Until then the default policy only
allows tools that declare themselves read-only and need neither approval nor a
permission supplied by a higher application layer.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.conversation.messages import AssistantMessage, ToolCall
from app.agents.conversation.tool_validation import PreparedToolCall
from app.agents.registry.tool_registry import ToolDefinition


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    error_code: str | None = None
    arguments: dict[str, Any] | None = None
    terminate: bool = False

    @classmethod
    def allow(cls, *, arguments: dict[str, Any] | None = None) -> "ToolPolicyDecision":
        return cls(allowed=True, arguments=arguments)

    @classmethod
    def block(cls, error_code: str = "tool_policy_denied", *, terminate: bool = False) -> "ToolPolicyDecision":
        return cls(allowed=False, error_code=error_code, terminate=terminate)


@dataclass(frozen=True)
class ToolPolicyContext:
    assistant_message: AssistantMessage
    tool_call: ToolCall
    prepared: PreparedToolCall
    definition: ToolDefinition
    metadata: dict[str, Any]


class DefaultToolPolicy:
    async def evaluate(self, context: ToolPolicyContext) -> ToolPolicyDecision:
        definition = context.definition
        if definition.requires_approval:
            return ToolPolicyDecision.block("approval_required")
        if definition.required_permission:
            return ToolPolicyDecision.block("permission_required")
        if not definition.read_only:
            return ToolPolicyDecision.block("write_tool_blocked")
        return ToolPolicyDecision.allow()


async def evaluate_policy(policy: Any, context: ToolPolicyContext) -> ToolPolicyDecision:
    evaluator: Callable = getattr(policy, "evaluate", policy)
    result = evaluator(context)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ToolPolicyDecision):
        return ToolPolicyDecision.block("invalid_policy", terminate=True)
    return result
