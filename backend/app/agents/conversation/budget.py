"""Hard logical limits for the pure V2-P03 agent loop.

Provider retries use P02 ``AttemptBudget``.  This module counts logical model
calls, proposed tool calls and turns.  Keeping the two levels separate avoids
mistaking a transport retry for a new reasoning turn.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass


_MESSAGES = {
    "max_turns": "Agent 已达到最大轮次",
    "max_model_calls": "Agent 已达到最大模型调用次数",
    "max_tool_calls": "Agent 已达到最大工具调用次数",
    "deadline_exceeded": "Agent 已超过总执行截止时间",
}


class AgentLimitError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(_MESSAGES.get(error_code, "Agent 执行预算已耗尽"))


@dataclass(frozen=True)
class AgentLoopLimits:
    max_turns: int = 8
    max_model_calls: int = 8
    max_tool_calls: int = 16
    deadline: float | None = None  # time.monotonic() domain

    def __post_init__(self) -> None:
        for value in (self.max_turns, self.max_model_calls, self.max_tool_calls):
            if type(value) is not int or value < 1:
                raise ValueError("Agent Loop 限额必须是正整数")
        if self.deadline is not None and (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, (int, float))
            or not math.isfinite(float(self.deadline))
        ):
            raise ValueError("deadline 必须是有限 monotonic 时间或 None")


@dataclass
class AgentLoopBudget:
    limits: AgentLoopLimits
    turns: int = 0
    model_calls: int = 0
    tool_calls: int = 0

    def check_deadline(self) -> None:
        if self.limits.deadline is not None and time.monotonic() >= self.limits.deadline:
            raise AgentLimitError("deadline_exceeded")

    def begin_turn(self) -> None:
        self.check_deadline()
        if self.turns >= self.limits.max_turns:
            raise AgentLimitError("max_turns")
        self.turns += 1

    def begin_model_call(self) -> None:
        self.check_deadline()
        if self.model_calls >= self.limits.max_model_calls:
            raise AgentLimitError("max_model_calls")
        self.model_calls += 1

    def begin_model_turn(self) -> None:
        """Atomically reserve one turn and its model call before events start."""
        self.check_deadline()
        if self.turns >= self.limits.max_turns:
            raise AgentLimitError("max_turns")
        if self.model_calls >= self.limits.max_model_calls:
            raise AgentLimitError("max_model_calls")
        self.turns += 1
        self.model_calls += 1

    def reserve_tool_batch(self, count: int) -> None:
        self.check_deadline()
        if type(count) is not int or count < 0:
            raise ValueError("工具调用计数必须是非负整数")
        if self.tool_calls + count > self.limits.max_tool_calls:
            raise AgentLimitError("max_tool_calls")
        self.tool_calls += count
