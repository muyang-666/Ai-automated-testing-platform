"""Agent Runtime 统一错误。

- 每个错误带稳定 error_code（可持久化到 AgentRun.error_code）；
- 消息只包含用户可读信息。
"""


class AgentError(Exception):
    """Agent 平台错误基类。"""

    error_code: str = "agent_error"

    def __init__(self, message: str, *, error_code: str | None = None):
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code


class UnknownSkillError(AgentError):
    error_code = "agent_unknown_skill"


class DuplicateSkillError(AgentError):
    error_code = "agent_duplicate_skill"


class UnknownToolError(AgentError):
    error_code = "agent_unknown_tool"


class DuplicateToolError(AgentError):
    error_code = "agent_duplicate_tool"


class InvalidStateTransitionError(AgentError):
    error_code = "agent_invalid_state_transition"


class RunNotExecutableError(AgentError):
    """Run 处于终态或已取消时再次执行。"""

    error_code = "agent_run_not_executable"


class MaxStepsExceededError(AgentError):
    error_code = "agent_max_steps_exceeded"


class WorkflowStepError(AgentError):
    error_code = "agent_workflow_step_failed"


class AgentPermissionError(AgentError):
    error_code = "agent_permission_denied"


class AgentApprovalConflictError(AgentError):
    error_code = "agent_approval_conflict"
