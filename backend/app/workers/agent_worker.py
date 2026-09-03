"""TestMind Agent Worker：最小、可测试、数据库驱动的后台执行器。

- run_once()：抢占一个 queued Run（原子条件 UPDATE）并交给 AgentRunner 推进；
- run_loop()：轮询循环，支持 stop_requested / max_iterations（测试注入）；
- recover_stale_runs()：把心跳超时的 running Run 置为 interrupted；
- 不嵌入 FastAPI startup、不自动启动、不自动重排 interrupted、不调用真实 LLM；
- 每次 run_once 都关闭数据库 Session；不把 ORM 对象跨 Session 使用；
- runtime 通过 runtime_factory(on_step_boundary) 构造，Worker 借此在每个步骤边界
  做 owner-only heartbeat（best-effort，不基于其返回分支）。
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from app.agents.runtime.errors import UnknownSkillError
from app.models.agent_run import AgentRun
from app.services import agent_run_service


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
    ):
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds 必须 > 0")
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds 必须 >= 0")
        self._session_factory = session_factory
        self._runtime_factory = runtime_factory
        self.worker_id = worker_id
        self._now = now_provider or datetime.utcnow
        self._sleeper = sleeper or time.sleep
        self.poll_interval_seconds = poll_interval_seconds
        self.stale_after_seconds = stale_after_seconds

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

        claimed = agent_run_service.claim_queued_run(db, run_id, self.worker_id, self._now())
        if not claimed:
            # 被其他 Worker 抢先（条件 UPDATE rowcount=0）
            return WorkerRunResult(action="contended", run_id=run_id)
        db.commit()  # 抢占事务结束：不在 Runtime/LLM 期间持有抢占事务

        run = db.query(AgentRun).get(run_id)
        if run is None or run.status != "running" or run.worker_id != self.worker_id:
            # 防御：抢占后状态被外部修改
            return WorkerRunResult(action="contended", run_id=run_id)

        def step_hook(current_run: AgentRun) -> None:
            # best-effort：心跳随 Runner 的 commit 一起持久化，返回值不做控制流
            agent_run_service.heartbeat(db, current_run.id, self.worker_id, self._now())

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
    from app.agents.runtime.runner import AgentRunner
    from app.core.database import SessionLocal
    from app.services.llm_gateway import LLMGateway

    # 默认生产 Registry：注册 case_generation:v1 与 T05 九个工具
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(
        gateway_factory=lambda: LLMGateway(),
        tool_registry=tool_registry,
    )
    worker_id = args.worker_id or f"cli-worker-{os.getpid()}"

    def runtime_factory(on_step_boundary):
        return AgentRunner(skill_registry, tool_registry, on_step_boundary=on_step_boundary)

    worker = AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=runtime_factory,
        worker_id=worker_id,
        poll_interval_seconds=args.poll_interval,
        stale_after_seconds=args.stale_after,
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
