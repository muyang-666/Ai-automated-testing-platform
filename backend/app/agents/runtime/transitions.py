"""AgentRun 合法状态转换的唯一定义。

业务代码不允许任意赋值状态，必须经 assert_can_transition 校验。

转换图：
    queued           → running / cancelled
    running          → waiting_approval / succeeded / failed / cancelled / interrupted
    waiting_approval → running / queued / succeeded / cancelled / failed
    interrupted      → queued / failed / cancelled
    succeeded / failed / cancelled → 终态，不允许再次推进
"""

from app.agents.runtime.errors import InvalidStateTransitionError
from app.schemas.agent.platform import RUN_STATUSES

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"waiting_approval", "succeeded", "failed", "cancelled", "interrupted"},
    "waiting_approval": {"running", "queued", "succeeded", "cancelled", "failed"},
    "interrupted": {"queued", "failed", "cancelled"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

# 初始化时的防御检查：任何 key 都必须是合法状态值
assert set(LEGAL_TRANSITIONS.keys()) == set(RUN_STATUSES), "状态转换表与 RUN_STATUSES 不一致"


def can_transition(current: str, target: str) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, set())


def assert_can_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise InvalidStateTransitionError(
            f"非法状态转换: {current} → {target}（合法转换见 LEGAL_TRANSITIONS）。"
        )


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
