"""V2-P05-B ConversationRunner：把持久化 conversation AgentRun 桥接到 run_agent_loop。

职责（生产执行适配器）：
- 校验 run / session / owner 与 conversation 模式；
- restore 持久化 Messages（复用 P04 conversation_service，不重写 ORM→Domain 转换）；
- 构造 AgentLoopContext / AgentLoopConfig 并注入 Provider(Gateway) / ToolRegistry / Policy；
- 调用 P03 `run_agent_loop()` —— 它是唯一 Agent 控制循环，本模块不复制 while 循环；
- 只持久化本轮新产生的 Message（增量策略见 _persist_new_messages 注释）；
- 持久化 Run 生命周期事件（复用既有 DB event_type：run_started/run_succeeded/run_failed/run_cancelled）；
- 按服务层原语推进 Run 终态（transition_status / mark_finished_at / save_output_json），不裸改 status。

不负责：Worker claim / lease / heartbeat / fencing / follow-up（P05-C/D）；Workflow phase /
next_step / execute_step / CaseGenerationWorkflow；Artifact / coverage / dedup / Test Design Skill；
SSE。禁止本模块 → AgentRunner 或 → CaseGenerationWorkflow 的任何复用路径。

事务边界：模型网络等待期间不持有数据库写事务——
1) start 事务（running + run_started 事件，短事务立即 commit）；
2) restore 只读后立即 rollback 释放读事务；
3) 网络等待（run_agent_loop）期间无任何 DB 事务；
4) 收尾：ownership 行锁下把消息、message_committed 事件与终态一次 commit。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.context_builder import ContextBudgetConfig
from app.agents.conversation.loop import AgentLoopConfig, AgentLoopContext, AgentLoopResult, run_agent_loop
from app.agents.conversation.messages import Message, UserMessage
from app.agents.conversation.summarizer import ConversationSummarizer, ProviderConversationSummarizer
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot, StreamLimits
from app.agents.registry.tool_registry import ToolRegistry
from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.services.agent import agent_run_service, conversation_service
from app.services.agent.conversation_context_service import (
    ConversationContextLimitError,
    ConversationContextPreparer,
    PreparedRunContext,
)

# 与 legacy AgentRunner 使用的既有 DB AgentEvent event_type 保持一致，不新造事件名。
EVENT_RUN_STARTED = "run_started"
EVENT_RUN_SUCCEEDED = "run_succeeded"
EVENT_RUN_FAILED = "run_failed"
EVENT_RUN_CANCELLED = "run_cancelled"

_DEFAULT_SYSTEM_PROMPT = "你是一个可靠的测试助手，请根据对话上下文直接回答或调用受控工具。"


@dataclass(frozen=True)
class ConversationRunOutcome:
    status: Literal["succeeded", "failed", "cancelled"]
    model_calls: int = 0
    tool_calls: int = 0
    turns: int = 0
    error_code: str | None = None
    error_type: str | None = None  # 仅异常类型名（不含消息内容），供诊断/审计
    run_finalized: bool = True  # False = 旧 ownership/已终态，未改动任何 Run 生命周期状态
    persisted_message_ids: tuple[str, ...] = ()
    # 本轮 AgentLoop 产生的事件快照（供测试与未来 SSE 通道；本轮不落库为逐条事件行）
    loop_events: tuple[Any, ...] = ()


@dataclass
class ConversationRunner:
    """把 queued/running 的 conversation AgentRun 执行到终态。

    依赖全部由构造注入，不从全局状态猜测：gateway 提供 async
    `.stream(snapshot, request, *, context, control, limits)`；snapshot 描述本轮要用的
    Provider；tool_registry 是本轮允许的受控工具集合。身份永不来自模型——
    执行身份取 run.requester_user_id 并要求与会话 owner 一致。
    """

    gateway: Any
    snapshot: ProviderSnapshot
    tool_registry: ToolRegistry
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    limits: AgentLoopLimits = field(default_factory=AgentLoopLimits)
    provider_attempt_budget: AttemptBudget = field(default_factory=lambda: AttemptBudget(limit=24))
    stream_limits: StreamLimits = field(default_factory=StreamLimits)
    policy: Any = None
    event_persister: Callable[[Any], None] | None = None  # P06：安全执行事件落库（Worker 注入）
    application_context_factory: Callable[..., Any] | None = None
    id_factory: Callable[[], str] = field(default_factory=lambda: lambda: uuid.uuid4().hex)
    timestamp_factory: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time() * 1000))
    # P10.1-B3：上下文预算与 Summarizer。summarizer_factory 为空时默认构造
    # ProviderConversationSummarizer（复用同一 gateway/snapshot；Worker 每 Run
    # 注入 snapshot 后再调用，因此工厂在调用时解析，不在构造时绑定）。
    context_budget: ContextBudgetConfig | None = None
    summarizer_factory: Callable[[], ConversationSummarizer] | None = None

    # ------------------------------------------------------------------ 主入口

    async def run(self, db: Session, run_id: int,
                  cancel_event: asyncio.Event | None = None, *,
                  worker_id: str | None = None,
                  execution_token: int | None = None) -> ConversationRunOutcome:
        """执行一个 conversation Run 到终态。Worker claim/lease 不在本模块。

        P05-D fencing：提供 worker_id + execution_token 时（Worker 生产路径），
        在每次关键写（消息持久化/终态/事件）前先做 ownership 断言；丢失/已被
        外部终结时不再提交任何 Run 状态（run_finalized=False）。
        """
        run, session_id, actor_user_id = self._validate_run(db, run_id)
        await self._start_run(db, run)

        loop_events: list[Any] = []
        try:
            # P08.2/P08.3：Runner 只使用 Run 上的可信快照（submit 时固化），
            # 不读取可变的 Session focus/context —— 会话焦点只影响未来新 Turn。
            run_context = conversation_service.artifact_context_from_run(run)
            workspace_context = conversation_service.workspace_context_from_run(run)
            artifact_id = run_context.get("artifact_id")
            # project 亦以快照为准（快照缺失时回退 run.project_id，兼容迁移前的旧行）
            project_id = run_context.get("project_id") or run.project_id
            requirement_id = run_context.get("requirement_id")

            if cancel_event is not None and cancel_event.is_set():
                # 模型请求前已取消：不发起任何 Provider/Summarizer 调用
                return self._finalize_canceled(db, run, cancel_event,
                                               worker_id=worker_id,
                                               execution_token=execution_token)

            # P10.1-B3：上下文准备（bounded history → 需要时一次增量压缩 →
            # PreparedContext）。Runner 不再把完整 transcript 直接交 AgentLoop；
            # 上下文准备不修改任何历史 Message 行。
            workspace_hint = ""
            if any(value is not None for value in workspace_context.values()):
                workspace_hint = (
                    "\n\nCurrent test workspace (UI selection hint, not permission):\n"
                    f"- selected module node id: {workspace_context.get('selected_module_id') or 'none'}\n"
                    f"- selected test case node id: {workspace_context.get('selected_case_id') or 'none'}\n"
                    f"- current view: {workspace_context.get('current_view') or 'none'}\n"
                    "Use these IDs only to resolve references such as 这里/这个模块/这个用例. "
                    "Always read current Artifact nodes with tools before changing them."
                )
            base_sections = [self.system_prompt] + ([workspace_hint] if workspace_hint else [])
            prepared = await self._prepare_run_context(
                db, run, actor_user_id, base_sections,
                worker_id=worker_id, execution_token=execution_token,
                cancel_event=cancel_event,
            )
            if prepared is None:
                # 准备期间（含 Summarizer 模型等待）已被取消/终结/失去 ownership：
                # 取消走合成 canceled 终态；否则按终态/失去 ownership 无写入退出。
                if cancel_event is not None and cancel_event.is_set():
                    return self._finalize_canceled(db, run, cancel_event,
                                                   worker_id=worker_id,
                                                   execution_token=execution_token)
                state = self._execution_state(db, run.id, worker_id, execution_token)
                if state == "terminal":
                    return self._no_write_outcome_for_terminal(db, run.id)
                return ConversationRunOutcome(status="failed", error_code="ownership_lost",
                                              run_finalized=False)
            if cancel_event is not None and cancel_event.is_set():
                return self._finalize_canceled(db, run, cancel_event,
                                               worker_id=worker_id,
                                               execution_token=execution_token)
            # context 事件（压缩/预算观测）在进入网络等待前用短事务落库（fenced）
            self._persist_context_events(db, run, prepared,
                                         worker_id=worker_id,
                                         execution_token=execution_token)

            application_context = (self.application_context_factory(
                user_id=actor_user_id, conversation_id=session_id, run_id=run_id,
                artifact_id=artifact_id,
                project_id=project_id,
                requirement_id=requirement_id,
                selected_module_id=workspace_context.get("selected_module_id"),
                selected_case_id=workspace_context.get("selected_case_id"),
                current_view=workspace_context.get("current_view"),
                worker_id=worker_id, execution_token=execution_token,
            ) if self.application_context_factory is not None else None)

            context = AgentLoopContext(
                system_prompt=prepared.prepared.system_prompt(),
                messages=prepared.prepared.messages,
                tool_registry=self.tool_registry,
                metadata={"user_id": actor_user_id, "conversation_id": session_id,
                          "project_id": project_id,
                          "artifact_id": artifact_id,
                          "requirement_id": requirement_id,
                          "selected_module_id": workspace_context.get("selected_module_id"),
                          "selected_case_id": workspace_context.get("selected_case_id"),
                          "current_view": workspace_context.get("current_view"),
                          "run_id": run_id,
                          "permissions": sorted(getattr(application_context, "permissions", ()))},
                application_context=application_context,
            )
            config = self._build_config(loop_events, cancel_event)
            result = await run_agent_loop(prompts=[], context=context, config=config)
        except ConversationContextLimitError as exc:
            # 无法在预算内构造合法上下文：Run=context_limit（不调用主 Agent Provider）
            state = self._execution_state(db, run.id, worker_id, execution_token)
            if state == "terminal":
                return self._no_write_outcome_for_terminal(db, run.id)
            if state == "lost":
                return ConversationRunOutcome(status="failed", error_code="ownership_lost",
                                              error_type="context_limit",
                                              run_finalized=False)
            return self._fail_run(db, run, error_code="context_limit",
                                  error_type="context_limit",
                                  extra_event=("context_limit", exc.event_payload()))
        except Exception as exc:
            # 执行异常：先复核 ownership/终态（旧 Worker 不得在丢失后落 failed），
            # 仍持有 ownership 才标记 failed（best-effort），不向上抛。
            state = self._execution_state(db, run.id, worker_id, execution_token)
            if state == "terminal":
                return self._no_write_outcome_for_terminal(db, run.id)
            if state == "lost":
                return ConversationRunOutcome(status="failed", error_code="ownership_lost",
                                              error_type=type(exc).__name__,
                                              run_finalized=False)
            return self._fail_run(db, run, error_code="runner_execution_error",
                                  error_type=type(exc).__name__)

        state = self._execution_state(db, run.id, worker_id, execution_token)
        if state == "terminal":
            # 已被外部终结（如用户 cancel 已置 status=cancelled 并写过事件）：不再写
            return self._no_write_outcome_for_terminal(db, run.id)
        if state == "lost":
            return ConversationRunOutcome(
                status="failed", error_code="ownership_lost",
                model_calls=result.model_calls, tool_calls=result.tool_calls,
                turns=result.turns, run_finalized=False)
        try:
            return self._finalize_run(
                db, run, result, loop_events,
                worker_id=worker_id, execution_token=execution_token,
            )
        except AgentError as exc:
            if getattr(exc, "error_code", None) != "agent_ownership_lost":
                raise
            db.rollback()
            state = self._execution_state(db, run.id, worker_id, execution_token)
            if state == "terminal":
                return self._no_write_outcome_for_terminal(db, run.id)
            return ConversationRunOutcome(
                status="failed", error_code="ownership_lost",
                model_calls=result.model_calls, tool_calls=result.tool_calls,
                turns=result.turns, run_finalized=False,
            )

    @staticmethod
    def _execution_state(db: Session, run_id: int, worker_id: str | None,
                         execution_token: int | None) -> str:
        """'ok'（可继续写） | 'terminal'（已被外部终结） | 'lost'（ownership 被替换）。

        用标量 SELECT（不走 ORM 身份映射）读取最新已提交状态，避免 Worker 会话
        中缓存的旧 ownership 让过期执行者误判自己仍持有执行权。
        """
        row = db.execute(
            select(AgentRun.status, AgentRun.worker_id, AgentRun.execution_token)
            .where(AgentRun.id == run_id)
        ).first()
        if row is None or row.status != "running":
            return "terminal"
        if worker_id is None or execution_token is None:
            return "ok"  # 非 Worker 直调（测试/未来入口）不做 fencing
        if row.worker_id != worker_id or row.execution_token != execution_token:
            return "lost"
        return "ok"

    @staticmethod
    def _no_write_outcome_for_terminal(db: Session, run_id: int) -> ConversationRunOutcome:
        status = db.execute(
            select(AgentRun.status).where(AgentRun.id == run_id)
        ).scalar_one_or_none()
        if status == "cancelled":
            return ConversationRunOutcome(status="cancelled", error_code="canceled",
                                          run_finalized=False)
        if status == "succeeded":
            return ConversationRunOutcome(status="succeeded", run_finalized=False)
        return ConversationRunOutcome(status="failed", error_code="already_terminal",
                                      run_finalized=False)

    # ------------------------------------------------------------------ 校验

    def _validate_run(self, db: Session, run_id: int) -> tuple[AgentRun, int, int]:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run is None:
            raise AgentError(f"Run {run_id} 不存在", error_code="agent_run_not_found")
        if run.workflow_code != "conversation":
            raise AgentError("ConversationRunner 只能执行 conversation Run",
                             error_code="agent_run_not_conversation")
        if run.user_message_id is None:
            raise AgentError("conversation Run 缺少首条用户消息关联",
                             error_code="agent_run_data_invalid")
        session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
        if session is None or session.mode != "conversation":
            raise AgentError("Run 所属会话不是 conversation 模式",
                             error_code="agent_session_mode_mismatch")
        if run.status not in {"queued", "running"}:
            raise AgentError(f"Run 状态 {run.status} 不可启动",
                             error_code="agent_run_not_startable")
        actor_user_id = run.requester_user_id
        if session.user_id != actor_user_id:
            raise AgentPermissionError("Run 发起人不是会话 owner")
        return run, session.id, actor_user_id

    # ------------------------------------------------------------------ 执行阶段

    async def _start_run(self, db: Session, run: AgentRun) -> None:
        """短事务：queued→running + run_started 事件；提交后释放事务再进入网络等待。"""
        if run.status == "queued":
            agent_run_service.transition_status(db, run, "running")
        if run.started_at is None:
            run.started_at = datetime.utcnow()
        agent_run_service.append_event(db, run.session_id, run.id, EVENT_RUN_STARTED)
        db.commit()

    async def _prepare_run_context(self, db: Session, run: AgentRun, actor_user_id: int,
                                   system_sections: list[str], *,
                                   worker_id: str | None,
                                   execution_token: int | None,
                                   cancel_event: asyncio.Event | None) -> PreparedRunContext | None:
        """上下文准备：bounded history → 压缩(≤1 次) → PreparedContext。

        事务边界（spec #10/#32）：读事务在本方法内释放；Summarizer 模型调用与
        Agent Provider 网络等待期间无悬挂 DB 事务；summary 写入为独立短事务。
        返回 None = 准备期间 Run 已被取消/终结/失去 ownership（调用方不再写状态）。
        """
        if self.summarizer_factory is not None:
            summarizer = self.summarizer_factory()
        else:
            summarizer = ProviderConversationSummarizer(
                gateway=self.gateway, snapshot=self.snapshot,
                stream_limits=self.stream_limits,
                id_factory=self.id_factory)
        preparer = ConversationContextPreparer(summarizer=summarizer,
                                               budget=self.context_budget)
        try:
            prepared = await preparer.prepare(
                db, run, requester_user_id=actor_user_id,
                system_sections=system_sections,
                cancel_event=cancel_event,
                deadline=self.limits.deadline,
            )
        except ConversationContextLimitError:
            # 取消优先于失败：压缩因取消中断而走到 context_limit 时按取消处理
            if cancel_event is not None and cancel_event.is_set():
                db.rollback()
                return None
            raise
        except Exception as exc:
            raise AgentError(
                f"上下文准备失败（原始异常类型：{type(exc).__name__}）",
                error_code="context_preparation_error") from exc
        # 上下文准备跨 Summarizer 模型等待：结束后复核 ownership/终态，
        # 避免把过期执行者的摘要/事件写入 DB。
        if cancel_event is not None and cancel_event.is_set():
            db.rollback()
            return None
        state = self._execution_state(db, run.id, worker_id, execution_token)
        db.rollback()  # 释放 ownership 复核产生的隐式读事务
        if state != "ok":
            return None
        return prepared

    def _persist_context_events(self, db: Session, run: AgentRun,
                                prepared: PreparedRunContext, *,
                                worker_id: str | None,
                                execution_token: int | None) -> None:
        """context_prepared / context_compacted 观测事件（fenced 短事务）。

        只在真正使用压缩上下文时落库（summary_text 非空）；事件 payload 只含
        预算/计数/usage 等脱敏元数据，绝不含 summary 文本或完整上下文。
        这些事件是 Agent runtime observability，不能被 artifact realtime bridge
        识别为 Artifact Revision Event（前端只按精确 event_type 匹配后者）。
        """
        ctx = prepared.prepared
        if not ctx.summary_text:
            return
        if worker_id is not None and execution_token is not None:
            agent_run_service.assert_execution_ownership(
                db, run.id, worker_id, execution_token)
        prepared_payload = {
            "estimated_input_tokens": ctx.estimated_tokens,
            "max_input_tokens": (self.context_budget or ContextBudgetConfig()).max_input_tokens,
            "summary_used": bool(ctx.summary_text),
            "summary_through_visible_rank": ctx.diagnostics.get("summary_through_visible_rank"),
            "summary_through_message_id": (ctx.diagnostics.get("summary_covered_message_id")
                                           or ctx.diagnostics.get("existing_summary_through_message_id")),
            "recent_message_count": len(ctx.included_message_ids),
            "omitted_message_count": len(ctx.omitted_message_ids),
            "summary_refresh_failed": bool(prepared.summary_refresh_failed),
        }
        agent_run_service.append_event(db, run.session_id, run.id,
                                       "context_prepared", prepared_payload)
        if prepared.summary_refreshed:
            diag = prepared.diagnostics
            compacted_payload = {
                "old_through_visible_rank": diag.get("existing_summary_through_visible_rank"),
                "old_through_message_id": diag.get("existing_summary_through_message_id"),
                "new_through_visible_rank": diag.get("summary_covered_visible_rank"),
                "new_through_message_id": diag.get("summary_covered_message_id"),
                "source_message_count": diag.get("summary_covered_visible_rank"),
                "estimated_summary_tokens": diag.get("summary_estimated_tokens"),
                "provider": diag.get("summary_provider"),
                "model": diag.get("summary_model"),
            }
            usage = {key[len("summary_"):]: value for key, value in diag.items()
                     if key.startswith("summary_") and key not in {
                         "summary_provider", "summary_model", "summary_estimated_tokens",
                         "summary_source_message_count", "summary_covered_visible_rank",
                         "summary_covered_message_id"}}
            if usage:
                compacted_payload["usage"] = usage
            agent_run_service.append_event(db, run.session_id, run.id,
                                           "context_compacted", compacted_payload)
        db.commit()  # 短事务：进入主 Provider 网络等待前立即结束

    def _finalize_canceled(self, db: Session, run: AgentRun,
                           cancel_event: asyncio.Event, *,
                           worker_id: str | None,
                           execution_token: int | None) -> ConversationRunOutcome:
        """模型调用前取消：合成 canceled 结果走既有 finalize 路径（含 fencing）。"""
        synthetic = AgentLoopResult(
            status="aborted", messages=[], new_messages=[], turns=0,
            model_calls=0, tool_calls=0, error_code="canceled")
        try:
            return self._finalize_run(db, run, synthetic, [],
                                      worker_id=worker_id, execution_token=execution_token)
        except AgentError as exc:
            if getattr(exc, "error_code", None) != "agent_ownership_lost":
                raise
            db.rollback()
            state = self._execution_state(db, run.id, worker_id, execution_token)
            if state == "terminal":
                return self._no_write_outcome_for_terminal(db, run.id)
            return ConversationRunOutcome(
                status="failed", error_code="ownership_lost",
                model_calls=0, tool_calls=0, turns=0, run_finalized=False,
            )

    def _build_config(self, loop_events: list[Any],
                      cancel_event: asyncio.Event | None) -> AgentLoopConfig:
        def event_sink(event: Any) -> None:
            loop_events.append(event)
            if self.event_persister is not None:
                self.event_persister(event)

        return AgentLoopConfig(
            gateway=self.gateway,
            snapshot=self.snapshot,
            event_sink=event_sink,  # 内存收集 + Worker 注入的持久化通道
            cancel_event=cancel_event or asyncio.Event(),
            limits=self.limits,
            provider_attempt_budget=self.provider_attempt_budget,
            stream_limits=self.stream_limits,
            policy=self.policy,
            id_factory=self.id_factory,
            timestamp_factory=self.timestamp_factory,
        )

    # ------------------------------------------------------------------ 收尾

    def _finalize_run(self, db: Session, run: AgentRun, result: Any,
                      loop_events: list[Any], *, worker_id: str | None,
                      execution_token: int | None) -> ConversationRunOutcome:
        # Lock and verify ownership in the same transaction that writes the
        # final messages/events/status.  This closes the former check-then-write
        # race between _execution_state() and two separate commits.
        if worker_id is not None and execution_token is not None:
            agent_run_service.assert_execution_ownership(
                db, run.id, worker_id, execution_token,
            )
        self._persist_new_messages(db, run, result)
        self._record_usage(db, run, result)
        terminal, error_code = self._map_terminal(result)
        self._apply_terminal(db, run, terminal, error_code)
        return ConversationRunOutcome(
            status=terminal,
            model_calls=result.model_calls,
            tool_calls=result.tool_calls,
            turns=result.turns,
            error_code=error_code,
            persisted_message_ids=tuple(
                message.message_id for message in result.new_messages
                if not isinstance(message, UserMessage)),
            loop_events=tuple(loop_events),
        )

    def _persist_new_messages(self, db: Session, run: AgentRun, result: Any) -> None:
        """增量持久化策略（显式判定，不以 DB 唯一约束作为主要去重）：

        1) 本模块以 prompts=[] 调用 run_agent_loop：历史消息（含当前 Turn 的用户消息）
           已在提交阶段入库并只进入 context.messages；result.new_messages 只含本轮
           AgentLoop 新生成的 assistant/toolResult 消息，因此不会整段重写历史；
        2) 仍显式过滤 UserMessage（persist 合同禁止重复写入用户首消息）；
        3) 仍按 message_id 排除任何已持久化消息（双保险）；随后一次性写入。
        """
        if not result.new_messages:
            return
        existing_ids = {row.message_id for row in db.query(AgentMessage).filter(
            AgentMessage.session_id == run.session_id,
            AgentMessage.message_id.isnot(None),
        ).all()}
        fresh: list[Message] = []
        for message in result.new_messages:
            if isinstance(message, UserMessage):
                continue  # 用户首消息由 submit_conversation_turn 同事务写入
            if message.message_id in existing_ids:
                continue  # 已持久化；理论上 new_messages 不含历史，此处为显式保险
            fresh.append(message)
        if fresh:
            # Runner uses one transaction for messages + committed events +
            # terminal state.  This event is therefore never visible before
            # its AgentMessage row exists.
            conversation_service.persist_conversation_messages(
                db, session_id=run.session_id, requester_user_id=run.requester_user_id,
                run_id=run.id, messages=fresh, commit=False)
            for message in fresh:
                agent_run_service.append_event(
                    db, run.session_id, run.id, "conversation_message_committed",
                    {
                        "message_id": message.message_id,
                        "role": message.role,
                        "stop_reason": getattr(message, "stop_reason", None),
                    },
                )

    def _record_usage(self, db: Session, run: AgentRun, result: Any) -> None:
        if result.model_calls:
            agent_run_service.increment_counter(db, run, "llm_calls_used", result.model_calls)
        if result.tool_calls:
            agent_run_service.increment_counter(db, run, "tool_calls_used", result.tool_calls)
        agent_run_service.save_output_json(db, run, {
            "turns": result.turns,
            "model_calls": result.model_calls,
            "tool_calls": result.tool_calls,
            "error_code": result.error_code,
        })

    @staticmethod
    def _map_terminal(result: Any) -> tuple[Literal["succeeded", "failed", "cancelled"], str | None]:
        """AgentLoopResult.status → Run 终态。

        completed→succeeded；aborted+canceled→cancelled；其余（error / 非取消 aborted /
        limit / stopped / waiting）→ failed。stopped（工具显式终止）与 waiting（审批等待）
        在 conversation 本轮没有产品路径，统一按 failed 落账，Deferred 见开发记录。
        """
        status = result.status
        error_code = result.error_code
        if status == "completed":
            return "succeeded", None
        if status == "aborted" and error_code == "canceled":
            return "cancelled", error_code
        if status == "aborted":
            return "failed", error_code or "aborted"
        if status == "error":
            return "failed", error_code or "model_error"
        if status == "limit":
            return "failed", error_code or "limit_exceeded"
        if status == "stopped":
            return "failed", error_code or "stopped"
        if status == "waiting":
            return "failed", error_code or "waiting_not_supported"
        return "failed", "unknown_loop_status"

    def _apply_terminal(self, db: Session, run: AgentRun,
                        terminal: Literal["succeeded", "failed", "cancelled"],
                        error_code: str | None) -> None:
        agent_run_service.transition_status(db, run, terminal)
        if terminal == "failed":
            run.error_code = error_code
            run.error_message = "Agent Loop 执行失败（错误码见 error_code/事件记录）"
        elif terminal == "cancelled":
            run.error_code = error_code
        agent_run_service.mark_finished_at(db, run)
        event_type = {
            "succeeded": EVENT_RUN_SUCCEEDED,
            "failed": EVENT_RUN_FAILED,
            "cancelled": EVENT_RUN_CANCELLED,
        }[terminal]
        agent_run_service.append_event(
            db, run.session_id, run.id, event_type,
            payload_json={"error_code": error_code} if error_code else None)
        db.commit()

    def _fail_run(self, db: Session, run: AgentRun, *, error_code: str,
                  error_type: str,
                  extra_event: tuple[str, dict] | None = None) -> ConversationRunOutcome:
        """恢复/执行阶段异常：不落伪消息，best-effort 推进到 failed 并记录事件。

        extra_event：(event_type, payload) 与 run_failed 同事务落库（如
        context_limit 事件），保证失败事件与终态原子可见。
        """
        try:
            db.rollback()
            agent_run_service.save_output_json(db, run, {
                "turns": 0, "model_calls": 0, "tool_calls": 0, "error_code": error_code,
            })
            if extra_event is not None:
                agent_run_service.append_event(db, run.session_id, run.id,
                                               extra_event[0], extra_event[1])
            self._apply_terminal(db, run, "failed", error_code)
        except Exception:
            db.rollback()
            raise AgentError("Runner 失败收尾失败（原始异常类型："
                             f"{error_type}）", error_code="runner_finalize_error") from None
        return ConversationRunOutcome(
            status="failed", error_code=error_code, error_type=error_type,
            model_calls=0, tool_calls=0, turns=0,
        )
