"""TestMind Agent Worker：最小、可测试、数据库驱动的后台执行器。

- run_once()：抢占一个 queued Run（原子条件 UPDATE，conversation 与 legacy 统一）
  并按 workflow_code 分发：conversation → ConversationRunner，其余 → AgentRunner；
- run_loop()：轮询循环，支持 stop_requested / max_iterations（测试注入）；
- recover_stale_runs()：把心跳超时的 running Run 置为 interrupted；
- 不嵌入 FastAPI startup、不自动启动、不自动重排 interrupted、不调用真实 LLM；
- 每次 run_once 都关闭数据库 Session；不把 ORM 对象跨 Session 使用；
- legacy runtime 通过 runtime_factory(on_step_boundary) 构造，Worker 借此在每个
  步骤边界做 owner-only heartbeat（best-effort，不基于其返回分支）；
- conversation runner 通过 conversation_runner_factory 构造（P05-C；heartbeat 属
  P05-D，本阶段 conversation 不提供 step 边界心跳）。
"""

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from app.agents.runtime.errors import AgentError, UnknownSkillError
from app.models.agent.agent_run import AgentRun
from app.services.agent import agent_run_service, conversation_service


@dataclass
class WorkerRunResult:
    action: str  # idle / contended / completed / failed
    run_id: int | None = None
    final_status: str | None = None


class AgentWorker:
    def __init__(
        self,
        session_factory: Callable,
        runtime_factory: Callable[[Callable | None], object],
        worker_id: str,
        now_provider: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        poll_interval_seconds: float = 1.0,
        stale_after_seconds: float = 300.0,
        conversation_runner_factory: Callable[[], Any] | None = None,
        conversation_snapshot_factory: Callable[[], Any] | None = None,
        heartbeat_interval_seconds: float | None = None,
        heartbeat_failure_limit: int = 1,
    ):
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds 必须 > 0")
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds 必须 >= 0")
        if heartbeat_interval_seconds is None:
            from app.core.config import settings
            heartbeat_interval_seconds = settings.AGENT_HEARTBEAT_INTERVAL_SECONDS
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds 必须 > 0")
        self._session_factory = session_factory
        self._runtime_factory = runtime_factory
        self._conversation_runner_factory = conversation_runner_factory
        self._conversation_snapshot_factory = conversation_snapshot_factory
        self.worker_id = worker_id
        self._now = now_provider or datetime.utcnow
        self._sleeper = sleeper or time.sleep
        self.poll_interval_seconds = poll_interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.heartbeat_failure_limit = max(1, heartbeat_failure_limit)

    # ── 单次处理 ──

    def run_once(self) -> WorkerRunResult:
        """无任务时正常返回 idle，不抛异常；每个 Session 都在 finally 中关闭。"""
        db = self._session_factory()
        try:
            return self._run_once(db)
        finally:
            db.close()

    def _run_once(self, db) -> WorkerRunResult:
        run_id = agent_run_service.next_queued_run_id(db)
        if run_id is None:
            return WorkerRunResult(action="idle")

        execution_token = agent_run_service.claim_queued_run(
            db, run_id, self.worker_id, self._now())
        if execution_token is None:
            # 被其他 Worker 抢先（条件 UPDATE rowcount=0）
            return WorkerRunResult(action="contended", run_id=run_id)
        db.commit()  # 抢占事务结束：不在 Runtime/LLM 期间持有抢占事务

        run = db.query(AgentRun).get(run_id)
        if run is None or run.status != "running" or run.worker_id != self.worker_id:
            # 防御：抢占后状态被外部修改
            return WorkerRunResult(action="contended", run_id=run_id)

        # P05-C/D dispatch：conversation → ConversationRunner；其余 → legacy AgentRunner
        if run.workflow_code == "conversation":
            result = self._run_conversation(db, run_id, execution_token, run.session_id)
            self._promote_conversation_queue_after_terminal(db, run_id)
            return result

        def step_hook(current_run: AgentRun) -> None:
            # best-effort fenced 心跳：随 Runner 的 commit 一起持久化，
            # 仅当 status='running' 且 worker_id/execution_token 匹配时生效
            agent_run_service.heartbeat(db, current_run.id, self.worker_id,
                                        self._now(), execution_token=execution_token)

        runner = self._runtime_factory(step_hook)
        try:
            runner.run(db, run)
        except UnknownSkillError as e:
            # 未知 workflow_code/version 不能永久 running
            db.rollback()
            self._mark_failed(db, run_id, "agent_unknown_workflow", str(e))
            return WorkerRunResult(action="failed", run_id=run_id, final_status="failed")
        except Exception as e:
            # Runtime 异常：先回滚失败事务，再用新事务记录 failed
            db.rollback()
            fresh = db.query(AgentRun).get(run_id)
            if fresh is not None and fresh.status == "running":
                self._mark_failed(db, run_id, "agent_runtime_error", (str(e) or type(e).__name__)[:500])
            return WorkerRunResult(action="failed", run_id=run_id, final_status="failed")

        fresh = db.query(AgentRun).get(run_id)
        return WorkerRunResult(
            action="completed",
            run_id=run_id,
            final_status=fresh.status if fresh else None,
        )

    def _run_conversation(self, db, run_id: int, execution_token: int,
                          session_id: int) -> WorkerRunResult:
        """conversation Run：ConversationRunner.run()（async）执行并自行 finalize。

        P05-D：执行期间并行运行 ownership control loop（fenced heartbeat +
        cancel 观察 + ownership lost 检测），ownership 丢失或收到取消时置
        cancel_event 让 AgentLoop 尽快停止。control heartbeat 使用独立 Session、
        每次 tick 短事务，不持有长事务；Runner 网络等待期间不碰 DB（P05-C 保持）。
        Runner 内部把执行期异常收敛为 failed outcome；Worker 只兜底 Runner 之外
        的 unexpected exception，且仅在 Run 仍为 running 时标记 failed（单一 ownership）。
        """
        if self._conversation_runner_factory is None:
            db.rollback()
            self._mark_failed(db, run_id, "agent_unknown_workflow", "未配置 conversation runner")
            return WorkerRunResult(action="failed", run_id=run_id, final_status="failed")
        try:
            asyncio.run(self._run_conversation_async(db, run_id, execution_token, session_id))
        except AgentError as e:
            db.rollback()
            fresh = db.query(AgentRun).get(run_id)
            if fresh is not None and fresh.status == "running":
                error_code = getattr(e, "error_code", None) or "agent_runtime_error"
                message = ("Agent 对话模型尚未配置，请在模型管理中绑定 Agent 对话场景。"
                           if error_code == "configuration_not_ready"
                           else "Agent 执行失败，请查看错误码。")
                self._mark_failed(db, run_id, error_code, message)
            return WorkerRunResult(action="failed", run_id=run_id, final_status="failed")
        except Exception as e:
            db.rollback()
            fresh = db.query(AgentRun).get(run_id)
            if fresh is not None and fresh.status == "running":
                self._mark_failed(db, run_id, "agent_runtime_error",
                                  (str(e) or type(e).__name__)[:500])
            return WorkerRunResult(action="failed", run_id=run_id, final_status="failed")
        fresh = db.query(AgentRun).get(run_id)
        return WorkerRunResult(
            action="completed",
            run_id=run_id,
            final_status=fresh.status if fresh else None,
        )

    async def _run_conversation_async(self, db, run_id: int, execution_token: int,
                                      session_id: int) -> None:
        """runner task + ownership control task 同 loop 并发；runner 结束即停 control。

        P06：runner 事件经 ConversationEventPersister 落库（独立 Session、短事务、
        文本增量聚合），SSE 以 DB 事件行为 Source of Truth；run 结束后 flush 收尾。
        """
        cancel_event = asyncio.Event()
        runner = self._conversation_runner_factory()
        if self._conversation_snapshot_factory is not None:
            runner.snapshot = self._conversation_snapshot_factory()
        from app.workers.conversation_event_persister import ConversationEventPersister
        persister = ConversationEventPersister(
            self._session_factory, session_id=session_id, run_id=run_id,
            worker_id=self.worker_id, execution_token=execution_token)
        runner.event_persister = persister
        runner_task = asyncio.create_task(
            runner.run(db, run_id, cancel_event=cancel_event,
                       worker_id=self.worker_id, execution_token=execution_token))
        control_task = asyncio.create_task(self._ownership_control(run_id, execution_token,
                                                                   cancel_event))
        try:
            await asyncio.wait({runner_task}, return_when=asyncio.FIRST_COMPLETED)
            runner_task.result()  # runner 内部异常上抛给 _run_conversation 的统一边界
            persister.flush()  # 收尾：把未刷出的文本增量落库
        finally:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass

    async def _ownership_control(self, run_id: int, execution_token: int,
                                 cancel_event: asyncio.Event) -> None:
        """每个 tick：fenced heartbeat → 区分 cancel / ownership lost / 已终态。

        一次 heartbeat 异常即安全中止（不吞异常、不做复杂 retry）：执行安全不确定时
        停止当前执行，避免假装 ownership 仍正常。
        """
        consecutive_heartbeat_failures = 0
        while True:
            if cancel_event.is_set():
                return
            try:
                state = self._ownership_probe(run_id, execution_token)
            except Exception:
                consecutive_heartbeat_failures += 1
                if consecutive_heartbeat_failures >= self.heartbeat_failure_limit:
                    cancel_event.set()
                    return
                await asyncio.sleep(self.heartbeat_interval_seconds)
                continue
            consecutive_heartbeat_failures = 0
            if state == "ok":
                pass
            elif state == "cancelled":
                cancel_event.set()  # 用户取消（DB 已终态 + run_cancelled 事件由取消方写入）
                return
            elif state in {"lost", "finalized"}:
                cancel_event.set()  # ownership lost：让 AgentLoop 尽快停止
                return
            await asyncio.sleep(self.heartbeat_interval_seconds)

    def _ownership_probe(self, run_id: int, execution_token: int) -> str:
        """独立 Session 的 fenced heartbeat；rowcount=0 时 SELECT 复核原因。"""
        session = self._session_factory()
        try:
            updated = agent_run_service.heartbeat(
                session, run_id, self.worker_id, self._now(),
                execution_token=execution_token)
            if updated == 1:
                session.commit()
                return "ok"
            session.rollback()
            run = session.query(AgentRun).get(run_id)
            if run is None:
                return "finalized"
            if run.status == "cancelled":
                return "cancelled"
            if run.status in {"succeeded", "failed", "interrupted"}:
                return "finalized"
            # 仍 running：MySQL 在心跳值不变时 rowcount 可能为 0，需重新匹配
            # worker/token 判定——三者仍匹配视为 ownership 有效（preflight B）。
            if run.worker_id == self.worker_id and run.execution_token == execution_token:
                session.commit()  # 以复核结果作为本 tick 的 heartbeat 续期
                return "ok"
            return "lost"  # running 但 worker/token 不匹配 → ownership 被替换
        finally:
            session.close()

    def _promote_conversation_queue_after_terminal(self, db, run_id: int) -> None:
        """P05-E：conversation head 终态后推进队列。

        succeeded / cancelled → promote 下一个 queued follow-up（原子、跳过
        cancelled 的 follow-up）；failed / interrupted → pause（不 promote），
        P06 前端用 conversation_queue_state 展示 paused。
        """
        run = db.query(AgentRun).get(run_id)
        if run is None or run.workflow_code != "conversation":
            return
        if run.status not in {"succeeded", "cancelled"}:
            return  # failed/interrupted = pause queue
        if conversation_service.promote_next_conversation_run(db, run.session_id) is not None:
            db.commit()

    def _mark_failed(self, db, run_id: int, error_code: str, message: str) -> None:
        run = db.query(AgentRun).get(run_id)
        if run is None or run.status != "running":
            return  # 终态/waiting_approval 是合法停止点，不覆盖
        agent_run_service.transition_status(db, run, "failed")
        run.error_code = error_code
        run.error_message = (message or "")[:500]
        agent_run_service.append_event(
            db, run.session_id, run.id, "run_failed",
            {"error_code": error_code, "error_message": run.error_message},
        )
        agent_run_service.mark_finished_at(db, run, self._now())
        db.commit()

    # ── 轮询循环 ──

    def run_loop(
        self,
        stop_requested: Callable[[], bool] | None = None,
        max_iterations: int | None = None,
    ) -> None:
        """有界轮询循环。测试注入 fake sleeper 与 max_iterations，禁止无限循环。"""
        iterations = 0
        try:
            while True:
                if stop_requested is not None and stop_requested():
                    break
                if max_iterations is not None and iterations >= max_iterations:
                    break
                self.run_once()
                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    break
                self._sleeper(self.poll_interval_seconds)
        except KeyboardInterrupt:
            return  # Ctrl+C 正常退出

    # ── stale 恢复 ──

    def recover_stale_runs(self, limit: int = 50) -> int:
        """把心跳超时的 running Run 置为 interrupted。

        - 不自动重排 queued、不重新执行可能已有副作用的步骤；
        - waiting_approval / 终态不参与扫描；
        - 保留 worker_id 供排查（统一策略）。
        """
        db = self._session_factory()
        try:
            now = self._now()
            stale_before = now - timedelta(seconds=self.stale_after_seconds)
            run_ids = agent_run_service.find_stale_run_ids(db, stale_before, limit=limit)
            count = 0
            for run_id in run_ids:
                if agent_run_service.mark_interrupted(
                    db,
                    run_id,
                    agent_run_service.STALE_ERROR_CODE,
                    f"Worker 心跳超时（超过 {self.stale_after_seconds} 秒），任务被中断。",
                    now,
                    stale_before=stale_before,
                ):
                    run = db.query(AgentRun).get(run_id)
                    if run:
                        agent_run_service.append_event(
                            db, run.session_id, run.id, "run_interrupted",
                            {"error_code": agent_run_service.STALE_ERROR_CODE},
                        )
                        count += 1
            db.commit()
            return count
        finally:
            db.close()


def main(argv=None) -> None:
    """Worker CLI 入口：python -m app.workers.agent_worker --once 等。

    当前没有生产 Skill：Registry 为空时 Worker 安全 idle，不注册 Fake。
    """
    import argparse

    parser = argparse.ArgumentParser(description="TestMind Agent Worker（单进程同步执行器）")
    parser.add_argument("--once", action="store_true", help="最多处理一个任务后退出")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="轮询间隔秒数，必须 > 0")
    parser.add_argument("--stale-after", type=float, default=300.0, help="心跳超时秒数，必须 >= 0")
    parser.add_argument("--worker-id", type=str, default=None, help="Worker 标识，默认 cli-worker-<pid>")
    args = parser.parse_args(argv)

    if args.poll_interval <= 0:
        raise SystemExit("--poll-interval 必须 > 0")
    if args.stale_after < 0:
        raise SystemExit("--stale-after 必须 >= 0")

    from app.agents.bootstrap import build_default_skill_registry, build_default_tool_registry
    from app.agents.conversation.runner import ConversationRunner
    from app.agents.providers.streaming import ProviderSnapshot
    from app.agents.runtime.runner import AgentRunner
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.services.llm.llm_gateway import LLMGateway

    # 默认生产 Registry：注册 case_generation:v1 与 T05 九个工具
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(
        gateway_factory=lambda: LLMGateway(),
        tool_registry=tool_registry,
    )
    worker_id = args.worker_id or f"cli-worker-{os.getpid()}"

    def runtime_factory(on_step_boundary):
        return AgentRunner(skill_registry, tool_registry, on_step_boundary=on_step_boundary)

    # conversation 执行依赖（P06 收敛）：统一 LLMGateway + 配置中心 agent_chat 场景快照
    # （按 Run 解析）；工具白名单只暴露 conversation_safe_tools，不暴露 legacy 业务工具。
    from app.agents.tools.conversation_safe_tools import build_conversation_tool_registry
    from app.services.agent.conversation_provider import resolve_conversation_snapshot
    conversation_gateway = LLMGateway()
    conversation_tools = build_conversation_tool_registry()

    def conversation_snapshot_factory():
        db = SessionLocal()
        try:
            return resolve_conversation_snapshot(db)
        finally:
            db.close()

    def conversation_runner_factory():
        return ConversationRunner(
            gateway=conversation_gateway,
            snapshot=None,  # 每个 Run 执行前由 worker 经 conversation_snapshot_factory 注入
            tool_registry=conversation_tools,
        )

    worker = AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=runtime_factory,
        worker_id=worker_id,
        poll_interval_seconds=args.poll_interval,
        stale_after_seconds=args.stale_after,
        conversation_runner_factory=conversation_runner_factory,
        conversation_snapshot_factory=conversation_snapshot_factory,
    )

    recovered = worker.recover_stale_runs()
    if recovered:
        print(f"已中断 {recovered} 个心跳超时任务")

    if args.once:
        result = worker.run_once()
        print(result.action)
    else:
        print(
            f"Worker {worker_id} 启动（poll-interval={args.poll_interval}s, "
            f"stale-after={args.stale_after}s），Ctrl+C 退出"
        )
        worker.run_loop()


if __name__ == "__main__":
    main()
