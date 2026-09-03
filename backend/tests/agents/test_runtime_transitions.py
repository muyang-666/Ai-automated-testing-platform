"""Run 状态转换表测试：合法转换、非法转换、终态。"""

import pytest

from app.agents.runtime.errors import InvalidStateTransitionError
from app.agents.runtime.transitions import (
    TERMINAL_STATUSES,
    assert_can_transition,
    can_transition,
    is_terminal,
)

LEGAL_PAIRS = [
    ("queued", "running"),
    ("queued", "cancelled"),
    ("running", "waiting_approval"),
    ("running", "succeeded"),
    ("running", "failed"),
    ("running", "cancelled"),
    ("running", "interrupted"),
    ("waiting_approval", "running"),
    ("waiting_approval", "queued"),  # T07：GATE 批准后交回 Worker
    ("waiting_approval", "succeeded"),  # T07：保存成功直接完成 Run
    ("waiting_approval", "cancelled"),
    ("waiting_approval", "failed"),
    ("interrupted", "queued"),
    ("interrupted", "failed"),
    ("interrupted", "cancelled"),
]

ILLEGAL_PAIRS = [
    ("queued", "succeeded"),
    ("queued", "failed"),
    ("queued", "queued"),
    ("running", "queued"),
    ("running", "running"),
    ("waiting_approval", "interrupted"),
    ("interrupted", "succeeded"),
    ("interrupted", "running"),
    ("succeeded", "running"),
    ("succeeded", "failed"),
    ("failed", "running"),
    ("failed", "cancelled"),
    ("cancelled", "queued"),
    ("cancelled", "succeeded"),
]


@pytest.mark.parametrize("current,target", LEGAL_PAIRS)
def test_legal_transitions(current, target):
    assert can_transition(current, target) is True
    assert_can_transition(current, target)  # 不抛异常


@pytest.mark.parametrize("current,target", ILLEGAL_PAIRS)
def test_illegal_transitions(current, target):
    assert can_transition(current, target) is False
    with pytest.raises(InvalidStateTransitionError) as exc:
        assert_can_transition(current, target)
    assert f"{current} → {target}" in str(exc.value)


def test_terminal_statuses():
    assert TERMINAL_STATUSES == {"succeeded", "failed", "cancelled"}
    assert is_terminal("succeeded") is True
    assert is_terminal("running") is False
