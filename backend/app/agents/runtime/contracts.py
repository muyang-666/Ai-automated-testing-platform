"""Runtime 数据合同：RuntimeContext、StepOutcome、WorkflowResult 与 AgentWorkflow Protocol。

- Workflow 一次只执行一个可持久化步骤；
- Workflow 不直接 commit 数据库事务、不直接操作 Agent ORM 对象；
- StepOutcome 不含模型隐藏思维链。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal, Protocol, runtime_checkable

StepStatus = Literal["continue", "waiting_approval", "succeeded", "failed", "cancelled"]


@dataclass
class RuntimeContext:
    """Runner 提供给 Workflow 的受控上下文。"""

    run_id: int
    session_id: int
    project_id: int
    requester_user_id: int
    db: Any  # SQLAlchemy Session
    skill: Any  # SkillDefinition
    tool_registry: Any  # ToolRegistry
    llm_gateway: Any | None = None  # 本任务为 None 或 Fake，不调用真实 LLM
    run: Any | None = None  # 当前 AgentRun ORM 对象（预算计数查询用），可空
    now: Callable[[], datetime] = field(default_factory=lambda: datetime.utcnow)


@dataclass
class StepOutcome:
    """一个 Workflow 步骤的执行结果。"""

    status: StepStatus
    next_state: dict | None = None  # 不提供则保持原 state
    output_summary: str | None = None
    emitted_events: list[dict] = field(default_factory=list)  # [{event_type, payload_json}]
    artifacts_to_create: list[dict] = field(default_factory=list)  # [{artifact_type, payload_json, source_refs_json?}]
    approval_to_create: dict | None = None  # {action_code, request_json?, artifact_id?, expires_at?}
    error_code: str | None = None
    error_message: str | None = None
    step_kind: str = "validation"  # llm/tool/validation/approval，写入 AgentStep
    tool_name: str | None = None
    invocations: list[dict] = field(default_factory=list)
    # 调用轨迹（由 Runner 落为独立 AgentStep，Workflow 不直接写表）：
    # {kind: "llm"|"tool", name, tool_name?, status?, input_summary?, output_summary?,
    #  provider_name?, model_name?, prompt_tokens?, completion_tokens?,
    #  duration_ms?, error_code?, error_message?}


@dataclass
class WorkflowResult:
    """Run 结束时的汇总（写入 run.output_json["result"]）。"""

    final_status: str
    step_count: int
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class AgentWorkflow(Protocol):
    """由 Skill 提供的工作流协议。"""

    code: str
    version: str

    def initial_state(self, input_data: dict) -> dict:
        ...

    def next_step(self, state: dict) -> str | None:
        """返回下一个要执行的步骤名；None 表示没有更多步骤（成功结束）。"""

    def execute_step(
        self,
        step_name: str,
        state: dict,
        context: RuntimeContext,
    ) -> StepOutcome:
        ...
