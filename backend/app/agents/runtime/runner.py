"""AgentRunner：同步、有界本地循环的 Runtime。

职责（本任务范围）：
- 按显式 skill_code 从 SkillRegistry 获取 Skill；
- 校验 allowed_tools 是否全部已注册；
- queued / waiting_approval → running，初始化并持久化 workflow state；
- 循环执行 next_step/execute_step，每步写 AgentStep、AgentEvent；
- 应用 StepOutcome：state 持久化、事件、Artifact、Approval；
- 处理 succeeded / failed / waiting_approval / max_steps / cancelled。

明确不做：while True Worker、数据库轮询、多进程锁、heartbeat、自动恢复、
Tool Call 执行、真实 LLM 调用（llm_gateway 仅传入 RuntimeContext，本任务不调用）。

事务边界：每执行一个步骤 commit 一次；Workflow 抛异常时先 rollback 再落 failed 记录。
"""

import time
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.agents.registry.skill_registry import SkillRegistry
from app.agents.registry.tool_registry import ToolRegistry
from app.agents.runtime.contracts import RuntimeContext, StepOutcome, WorkflowResult
from app.agents.runtime.errors import (
    AgentError,
    MaxStepsExceededError,
    RunNotExecutableError,
    UnknownToolError,
)
from app.agents.runtime.transitions import TERMINAL_STATUSES, assert_can_transition
from app.models.agent.agent_run import AgentRun
from app.services.agent import agent_approval_service, agent_artifact_service, agent_run_service

_STATE_KEY = "workflow_state"
_RESULT_KEY = "result"


class AgentRunner:
    def __init__(
        self,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        llm_gateway=None,
        now=None,
        on_step_boundary: Callable[[AgentRun], None] | None = None,
    ):
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._llm_gateway = llm_gateway  # 本任务不调用，仅注入上下文
        self._now = now or datetime.utcnow
        # 可选步骤边界回调（默认 None，保持 T04A 行为）。Worker 用它做 heartbeat；
        # 回调随 Runner 的下一次 commit 一起持久化，不自己 commit。
        self._on_step_boundary = on_step_boundary

    # ── 对外入口：有界本地推进直到终止状态 ──

    def run(self, db: Session, run: AgentRun, input_data: dict | None = None) -> AgentRun:
        """推进 Run 直到 succeeded / failed / waiting_approval（或预算耗尽）。

        可重复调用：waiting_approval 审批通过后再次调用会从持久化 state 继续。
        """
        self._ensure_executable(run)
        skill = self._skill_registry.get(run.workflow_code)
        workflow = self._resolve_workflow(skill)
        self._check_allowed_tools(skill)
        context = RuntimeContext(
            run_id=run.id,
            session_id=run.session_id,
            project_id=run.project_id,
            requester_user_id=run.requester_user_id,
            db=db,
            skill=skill,
            tool_registry=self._tool_registry,
            llm_gateway=self._llm_gateway,
            run=run,
            now=self._now,
        )

        if run.status == "queued":
            agent_run_service.transition_status(db, run, "running")
            run.started_at = self._now()
            agent_run_service.append_event(db, run.session_id, run.id, "run_started")
            db.commit()
        elif run.status == "waiting_approval":
            # 审批通过后的恢复执行：waiting_approval → running
            agent_run_service.transition_status(db, run, "running")
            agent_run_service.append_event(db, run.session_id, run.id, "run_resumed")
            db.commit()
        # status == "running"：已被 Worker 抢占，直接从持久化 state 继续

        state = self._load_state(run) or workflow.initial_state(
            input_data if input_data is not None else (run.input_json or {})
        )

        while True:
            if run.status == "cancelled":
                # 执行前检查取消（T04B 之前只支持外部置为 cancelled 后拒绝执行）
                raise RunNotExecutableError(f"Run {run.id} 已取消，不允许继续执行。")
            if run.steps_used >= run.max_steps:
                self._fail_budget(db, run)
                db.commit()
                return run

            step_name = workflow.next_step(state)
            if step_name is None:
                self._succeed(db, run, state)
                db.commit()
                return run

            started = time.monotonic()
            try:
                outcome = workflow.execute_step(step_name, state, context)
            except Exception as e:  # Workflow 步骤异常 → Step failed + Run failed
                db.rollback()
                self._fail_step_exception(db, run, step_name, e)
                db.commit()
                return run
            duration_ms = int((time.monotonic() - started) * 1000)

            if outcome.next_state is not None:
                state = outcome.next_state
            self._save_state(db, run, state)
            self._record_step(db, run, step_name, outcome, duration_ms)
            # 步骤序号 = 记录前 steps_used + 1，因此先记录步骤再自增计数
            agent_run_service.increment_counter(db, run, "steps_used")
            self._record_invocations(db, run, outcome)
            if self._on_step_boundary is not None:
                self._on_step_boundary(run)

            for event in outcome.emitted_events:
                agent_run_service.append_event(
                    db, run.session_id, run.id,
                    event.get("event_type") or "workflow_event",
                    event.get("payload_json"),
                )
            for artifact_spec in outcome.artifacts_to_create:
                agent_artifact_service.create_artifact(
                    db,
                    session_id=run.session_id,
                    agent_run_id=run.id,
                    artifact_type=artifact_spec.get("artifact_type") or "unknown",
                    payload_json=artifact_spec.get("payload_json") or {},
                    source_refs_json=artifact_spec.get("source_refs_json"),
                    created_by_user_id=run.requester_user_id,
                )

            if outcome.status == "failed":
                agent_run_service.transition_status(db, run, "failed")
                run.error_code = outcome.error_code or "agent_workflow_failed"
                run.error_message = outcome.error_message
                agent_run_service.append_event(
                    db, run.session_id, run.id, "run_failed",
                    {"error_code": run.error_code, "error_message": run.error_message},
                )
                self._finalize(db, run, state)
                db.commit()
                return run
            if outcome.status == "cancelled":
                # GATE 被拒绝等取消语义：running/waiting_approval → cancelled
                agent_run_service.transition_status(db, run, "cancelled")
                run.error_code = outcome.error_code or "agent_run_cancelled"
                run.error_message = outcome.error_message
                agent_run_service.append_event(
                    db, run.session_id, run.id, "run_cancelled",
                    {"error_code": run.error_code, "error_message": run.error_message},
                )
                self._finalize(db, run, state)
                db.commit()
                return run
            if outcome.status == "waiting_approval":
                approval = None
                if outcome.approval_to_create:
                    approval = agent_approval_service.request_approval(
                        db,
                        session_id=run.session_id,
                        agent_run_id=run.id,
                        action_code=outcome.approval_to_create.get("action_code") or "unknown_action",
                        request_json=outcome.approval_to_create.get("request_json"),
                        artifact_id=outcome.approval_to_create.get("artifact_id"),
                        expires_at=outcome.approval_to_create.get("expires_at"),
                    )
                agent_run_service.transition_status(db, run, "waiting_approval")
                agent_run_service.append_event(
                    db, run.session_id, run.id, "approval_requested",
                    {
                        "action_code": outcome.approval_to_create.get("action_code") if outcome.approval_to_create else None,
                        "approval_id": approval.id if approval else None,
                    },
                )
                db.commit()
                return run
            if outcome.status == "succeeded":
                self._succeed(db, run, state)
                db.commit()
                return run
            # continue → 继续循环
            db.commit()

    # ── 内部步骤 ──

    def _ensure_executable(self, run: AgentRun) -> None:
        if run.status in TERMINAL_STATUSES:
            raise RunNotExecutableError(
                f"Run {run.id} 处于终态 {run.status}，不允许再次执行。"
            )
        if run.status not in {"queued", "waiting_approval", "running"}:
            raise AgentError(
                f"Run {run.id} 状态 {run.status} 不支持当前 Runner 启动"
                f"（需要 queued/waiting_approval/running）。",
                error_code="agent_run_not_startable",
            )

    def _resolve_workflow(self, skill):
        workflow = skill.workflow
        if workflow is None and skill.workflow_factory is not None:
            workflow = skill.workflow_factory()
        if workflow is None:
            raise AgentError(
                f"Skill '{skill.code}' 未绑定 workflow。", error_code="agent_skill_no_workflow"
            )
        return workflow

    def _check_allowed_tools(self, skill) -> None:
        for tool_name in skill.allowed_tools:
            self._tool_registry.get(tool_name)  # 未知工具 → UnknownToolError

    def _load_state(self, run: AgentRun) -> dict | None:
        output = run.output_json or {}
        state = output.get(_STATE_KEY)
        return state if isinstance(state, dict) else None

    def _save_state(self, db: Session, run: AgentRun, state: dict) -> None:
        output = dict(run.output_json or {})
        output[_STATE_KEY] = state
        agent_run_service.save_output_json(db, run, output)

    def _record_step(
        self,
        db: Session,
        run: AgentRun,
        step_name: str,
        outcome: StepOutcome,
        duration_ms: int,
    ) -> None:
        step = agent_run_service.start_step(
            db, run, outcome.step_kind, step_name, tool_name=outcome.tool_name
        )
        step_output = {}
        if outcome.output_summary:
            step_output["summary"] = outcome.output_summary
        agent_run_service.finish_step(
            db,
            step,
            status="succeeded",
            output_json=step_output or None,
            duration_ms=duration_ms,
            error_code=outcome.error_code,
            error_message=outcome.error_message,
        )
        agent_run_service.append_event(
            db, run.session_id, run.id, "step_succeeded", {"step_name": step_name}
        )

    def _record_invocations(self, db: Session, run: AgentRun, outcome: StepOutcome) -> None:
        """把 Tool/LLM 调用轨迹落为独立可观察 AgentStep，并累计预算计数。"""
        for invocation in outcome.invocations:
            kind = invocation.get("kind") or "validation"
            step_kind = "llm" if kind == "llm" else ("tool" if kind == "tool" else "validation")
            step = agent_run_service.start_step(
                db, run, step_kind, invocation.get("name") or "invocation",
                tool_name=invocation.get("tool_name"),
            )
            summary = {}
            if invocation.get("input_summary") is not None:
                summary["input_summary"] = invocation["input_summary"]
            if invocation.get("output_summary") is not None:
                summary["output_summary"] = invocation["output_summary"]
            agent_run_service.finish_step(
                db, step,
                status=invocation.get("status", "succeeded"),
                output_json=summary or None,
                duration_ms=invocation.get("duration_ms"),
                provider_name=invocation.get("provider_name"),
                model_name=invocation.get("model_name"),
                prompt_tokens=invocation.get("prompt_tokens"),
                completion_tokens=invocation.get("completion_tokens"),
                error_code=invocation.get("error_code"),
                error_message=invocation.get("error_message"),
            )
            if step_kind == "llm":
                agent_run_service.increment_counter(db, run, "llm_calls_used")
                if invocation.get("prompt_tokens") is not None:
                    agent_run_service.increment_counter(db, run, "prompt_tokens", invocation["prompt_tokens"])
                if invocation.get("completion_tokens") is not None:
                    agent_run_service.increment_counter(db, run, "completion_tokens", invocation["completion_tokens"])
            elif step_kind == "tool":
                agent_run_service.increment_counter(db, run, "tool_calls_used")

    def _fail_step_exception(self, db: Session, run: AgentRun, step_name: str, e: Exception) -> None:
        step = agent_run_service.start_step(db, run, "validation", step_name)
        # 若 LLM/Provider 层抛出的异常携带诊断信息（如空响应的 finish_reason/request_id），
        # 一并落库，避免“模型无返回”等失败变成无法排查的黑盒。
        provider_name = getattr(e, "provider_name", None)
        model_name = getattr(e, "model_name", None)
        diag = {}
        if getattr(e, "finish_reason", None) is not None:
            diag["finish_reason"] = e.finish_reason
        if getattr(e, "request_id", None):
            diag["request_id"] = e.request_id
        if getattr(e, "error_code", None):
            diag["llm_error_code"] = e.error_code
        agent_run_service.finish_step(
            db,
            step,
            status="failed",
            error_code="agent_workflow_step_failed",
            error_message=(str(e) or type(e).__name__)[:500],
            provider_name=provider_name,
            model_name=model_name,
            output_json=diag or None,
        )
        agent_run_service.increment_counter(db, run, "steps_used")
        agent_run_service.transition_status(db, run, "failed")
        run.error_code = "agent_workflow_step_failed"
        run.error_message = (str(e) or type(e).__name__)[:500]
        agent_run_service.append_event(
            db, run.session_id, run.id, "step_failed",
            {"step_name": step_name, "error_code": run.error_code},
        )
        agent_run_service.append_event(
            db, run.session_id, run.id, "run_failed",
            {"error_code": run.error_code, "error_message": run.error_message},
        )
        self._finalize(db, run, self._load_state(run) or {})

    def _fail_budget(self, db: Session, run: AgentRun) -> None:
        """max_steps 超限 → failed + 稳定 error_code。"""
        agent_run_service.transition_status(db, run, "failed")
        run.error_code = MaxStepsExceededError.error_code
        run.error_message = f"达到最大步骤数 {run.max_steps}，Run 终止。"
        agent_run_service.append_event(
            db, run.session_id, run.id, "max_steps_exceeded",
            {"max_steps": run.max_steps, "steps_used": run.steps_used},
        )
        agent_run_service.append_event(
            db, run.session_id, run.id, "run_failed",
            {"error_code": run.error_code, "error_message": run.error_message},
        )
        self._finalize(db, run, self._load_state(run) or {})

    def _succeed(self, db: Session, run: AgentRun, state: dict) -> None:
        agent_run_service.transition_status(db, run, "succeeded")
        self._save_state(db, run, state)
        agent_run_service.append_event(db, run.session_id, run.id, "run_succeeded")
        self._finalize(db, run, state)

    def _finalize(self, db: Session, run: AgentRun, state: dict) -> None:
        output = dict(run.output_json or {})
        output[_STATE_KEY] = state
        output[_RESULT_KEY] = {
            "status": run.status,
            "step_count": run.steps_used,
            "error_code": run.error_code,
            "error_message": run.error_message,
        }
        agent_run_service.save_output_json(db, run, output)
        agent_run_service.mark_finished_at(db, run, self._now())
