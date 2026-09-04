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
4) 收尾：persist_conversation_messages 自带提交，随后事件/终态在同一收尾 commit 完成。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

from sqlalchemy.orm import Session

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.loop import AgentLoopConfig, AgentLoopContext, run_agent_loop
from app.agents.conversation.messages import Message, UserMessage
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot, StreamLimits
from app.agents.registry.tool_registry import ToolRegistry
from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.services.agent import agent_run_service, conversation_service

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
    id_factory: Callable[[], str] = field(default_factory=lambda: lambda: uuid.uuid4().hex)
    timestamp_factory: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time() * 1000))

    # ------------------------------------------------------------------ 主入口

    async def run(self, db: Session, run_id: int,
                  cancel_event: asyncio.Event | None = None) -> ConversationRunOutcome:
        """执行一个 conversation Run 到终态。Worker claim/lease 不在本模块。"""
        run, session_id, actor_user_id = self._validate_run(db, run_id)
        await self._start_run(db, run)

        loop_events: list[Any] = []
        try:
            restored = self._restore(db, session_id, actor_user_id, run)
            self._assert_history_ends_with_current_user_message(db, run, restored)

            context = AgentLoopContext(
                system_prompt=self.system_prompt,
                messages=restored,
                tool_registry=self.tool_registry,
                metadata={"conversation_id": session_id, "run_id": run.id},
                application_context=None,
            )
            config = self._build_config(loop_events, cancel_event)
            result = await run_agent_loop(prompts=[], context=context, config=config)
        except Exception as exc:
            # 恢复/执行阶段失败：不产生伪助手消息；标记 failed（best-effort），不向上抛。
            return self._fail_run(db, run, error_code="runner_execution_error",
                                  error_type=type(exc).__name__)

        return self._finalize_run(db, run, result, loop_events)

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

    def _restore(self, db: Session, session_id: int, actor_user_id: int,
                 run: AgentRun) -> list[Message]:
        restored = conversation_service.restore_conversation_messages(
            db, session_id=session_id, requester_user_id=actor_user_id)
        # restore 是只读查询；立即结束读事务，确保模型等待期间无悬挂 DB 事务。
        db.rollback()
        return restored

    def _assert_history_ends_with_current_user_message(self, db: Session, run: AgentRun,
                                                       restored: list[Message]) -> None:
        user_row = db.query(AgentMessage).filter(AgentMessage.id == run.user_message_id).first()
        if user_row is None or user_row.message_id is None:
            raise AgentError("首条用户消息记录缺失", error_code="agent_run_data_invalid")
        if not restored or restored[-1].message_id != user_row.message_id:
            raise AgentError("恢复的历史未以当前 Turn 用户消息结尾",
                             error_code="agent_run_data_invalid")

    def _build_config(self, loop_events: list[Any],
                      cancel_event: asyncio.Event | None) -> AgentLoopConfig:
        return AgentLoopConfig(
            gateway=self.gateway,
            snapshot=self.snapshot,
            event_sink=loop_events.append,  # EventSink：本轮内存收集，未来由 SSE 通道替换
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
                      loop_events: list[Any]) -> ConversationRunOutcome:
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
            # persist_conversation_messages 内部完成自己的提交事务
            conversation_service.persist_conversation_messages(
                db, session_id=run.session_id, requester_user_id=run.requester_user_id,
                run_id=run.id, messages=fresh)

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
                  error_type: str) -> ConversationRunOutcome:
        """恢复/执行阶段异常：不落伪消息，best-effort 推进到 failed 并记录事件。"""
        try:
            db.rollback()
            agent_run_service.save_output_json(db, run, {
                "turns": 0, "model_calls": 0, "tool_calls": 0, "error_code": error_code,
            })
            self._apply_terminal(db, run, "failed", error_code)
        except Exception:
            db.rollback()
            raise AgentError("Runner 失败收尾失败（原始异常类型："
                             f"{error_type}）", error_code="runner_finalize_error") from None
        return ConversationRunOutcome(
            status="failed", error_code=error_code,
            model_calls=0, tool_calls=0, turns=0,
        )
