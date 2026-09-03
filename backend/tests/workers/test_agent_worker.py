"""AgentWorker 测试：原子抢占、Heartbeat、stale 恢复、循环与 CLI。

- 不启动真实线程/进程：用两个独立 SQLAlchemy Session 模拟竞争；
- FakeClock / fake sleeper 注入，零真实 sleep、零网络、固定 worker_id；
- 全部 SQLite（conftest 内存库 + SessionLocal）。
"""

from datetime import datetime, timedelta

import pytest

from app.agents.registry import SkillDefinition, SkillRegistry, ToolRegistry
from app.agents.runtime.contracts import StepOutcome
from app.agents.runtime.runner import AgentRunner
from app.core.database import SessionLocal
from app.models.agent_approval import AgentApproval
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.project import Project
from app.models.user import User
from app.services import agent_run_service, agent_session_service
from app.workers.agent_worker import AgentWorker

WORKER_A = "worker-a"
WORKER_B = "worker-b"


# ── 时间与 Session 注入 ──


class FakeClock:
    def __init__(self, start=None):
        self.t = start or datetime(2026, 1, 1, 0, 0, 0)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t = self.t + timedelta(seconds=seconds)


class TrackingFactory:
    """统计创建的 Session，用于断言全部被关闭。"""

    def __init__(self, factory):
        self._factory = factory
        self.created = []

    def __call__(self):
        session = self._factory()
        self.created.append(session)
        return session


# ── Fake Workflows（只存在于测试） ──


class FakeSuccessWorkflow:
    code = "fake_success"
    version = "1"

    def initial_state(self, input_data):
        return {"phase": 0}

    def next_step(self, state):
        return {0: "step_one", 1: "step_two"}.get(state.get("phase"))

    def execute_step(self, step_name, state, context):
        if step_name == "step_two":
            return StepOutcome(status="succeeded", next_state={**state, "phase": 2})
        return StepOutcome(status="continue", next_state={**state, "phase": 1})


class FakeApprovalWorkflow:
    code = "fake_approval"
    version = "1"

    def initial_state(self, input_data):
        return {"phase": 0}

    def next_step(self, state):
        return "step_request" if state.get("phase") == 0 else None

    def execute_step(self, step_name, state, context):
        return StepOutcome(
            status="waiting_approval",
            next_state={"phase": 1},
            approval_to_create={"action_code": "save_cases", "request_json": {}},
        )


class FakeBrokenNextStepWorkflow:
    """next_step 抛异常：Runner 不捕获的 Runtime 异常路径。"""

    code = "fake_broken_next"
    version = "1"

    def initial_state(self, input_data):
        return {}

    def next_step(self, state):
        raise RuntimeError("next_step 爆炸")

    def execute_step(self, step_name, state, context):
        return StepOutcome(status="continue")


# ── 构造辅助 ──


def _registry(code="fake_success"):
    registry = SkillRegistry()
    workflow = {
        "fake_success": FakeSuccessWorkflow,
        "fake_approval": FakeApprovalWorkflow,
        "fake_broken_next": FakeBrokenNextStepWorkflow,
    }[code]()
    registry.register(SkillDefinition(code=code, name=code, workflow=workflow))
    return registry


def _runtime_factory(registry):
    def factory(on_step_boundary):
        return AgentRunner(registry, ToolRegistry(), on_step_boundary=on_step_boundary)

    return factory


def _make_worker(
    session_factory=SessionLocal,
    registry=None,
    worker_id=WORKER_A,
    clock=None,
    sleeper=None,
    poll_interval=0.1,
    stale_after=300.0,
):
    return AgentWorker(
        session_factory=session_factory,
        runtime_factory=_runtime_factory(registry or _registry()),
        worker_id=worker_id,
        now_provider=clock or FakeClock(),
        sleeper=sleeper,
        poll_interval_seconds=poll_interval,
        stale_after_seconds=stale_after,
    )


def _ensure_parents(db, user_id=1, project_id=101):
    """隔离库启用外键检查：AgentSession 引用 users/projects，须先有父行。"""
    if not db.query(User).filter(User.id == user_id).first():
        db.add(User(id=user_id, username=f"worker_user_{user_id}", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()
    if not db.query(Project).filter(Project.id == project_id).first():
        db.add(Project(id=project_id, name="Worker 项目", status="active", is_deleted=False))
        db.flush()


def _seed_session(db, user_id=1, project_id=101):
    _ensure_parents(db, user_id, project_id)
    session = agent_session_service.create_session(db, user_id, project_id, "Worker 测试会话")
    db.commit()
    return session


def _seed_queued_run(db, session, code="fake_success", max_steps=20):
    run = agent_run_service.create_run(
        db, session, code, session.user_id, session.project_id, max_steps=max_steps
    )
    db.commit()
    return run


# ── 抢占 ──


def test_run_once_idle_when_no_tasks(db_session):
    worker = _make_worker()

    result = worker.run_once()

    assert result.action == "idle"
    assert result.run_id is None


def test_claim_and_execute_to_succeeded(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    worker = _make_worker(clock=clock)

    result = worker.run_once()

    assert result.action == "completed"
    assert result.final_status == "succeeded"
    assert run.status == "succeeded"
    assert run.worker_id == WORKER_A
    assert run.started_at == clock()
    assert run.heartbeat_at == clock()  # 抢占即写心跳，步骤边界续写
    assert run.steps_used == 2
    assert db_session.query(AgentStep).filter(AgentStep.agent_run_id == run.id).count() == 2


def test_second_worker_claim_rowcount_zero(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    db2 = SessionLocal()
    try:
        clock = FakeClock()
        # Worker A 抢占成功
        assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is True
        db_session.commit()
        # Worker B 对同一候选条件更新 → rowcount 0
        assert agent_run_service.claim_queued_run(db2, run.id, WORKER_B, clock()) is False
        db2.rollback()

        refreshed = db_session.query(AgentRun).get(run.id)
        assert refreshed.status == "running"
        assert refreshed.worker_id == WORKER_A
    finally:
        db2.close()


@pytest.mark.parametrize("target_status", ["cancelled", "waiting_approval", "succeeded", "failed"])
def test_non_queued_status_not_claimable(db_session, target_status):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    agent_run_service.transition_status(db_session, run, "running")
    if target_status != "cancelled":
        agent_run_service.transition_status(db_session, run, target_status)
    else:
        agent_run_service.transition_status(db_session, run, "cancelled")
    db_session.commit()

    clock = FakeClock()
    assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is False
    worker = _make_worker(clock=clock)
    assert worker.run_once().action == "idle"  # 没有 queued 任务
    assert run.status == target_status  # 状态未被改动


# ── Heartbeat ──


def test_heartbeat_owner_only(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is True
    db_session.commit()

    clock.advance(5)
    assert agent_run_service.heartbeat(db_session, run.id, WORKER_A, clock()) == 1
    assert agent_run_service.heartbeat(db_session, run.id, WORKER_B, clock()) == 0  # 非 owner 不能更新
    db_session.commit()

    refreshed = db_session.query(AgentRun).get(run.id)
    assert refreshed.heartbeat_at == clock()


def test_heartbeat_only_when_running(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    agent_run_service.transition_status(db_session, run, "running")
    agent_run_service.transition_status(db_session, run, "succeeded")
    db_session.commit()

    assert agent_run_service.heartbeat(db_session, run.id, WORKER_A, FakeClock()()) == 0


# ── Worker 执行结果 ──


def test_waiting_approval_stops_worker(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session, code="fake_approval")
    worker = _make_worker(registry=_registry("fake_approval"))

    result = worker.run_once()

    assert result.action == "completed"
    assert result.final_status == "waiting_approval"
    assert run.status == "waiting_approval"
    assert run.steps_used == 1
    approval = db_session.query(AgentApproval).one()
    assert approval.status == "pending"
    # 不会被再次抢占
    assert worker.run_once().action == "idle"


def test_unknown_workflow_marks_failed(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session, code="ghost_skill")
    worker = _make_worker()

    result = worker.run_once()

    assert result.action == "failed"
    assert run.status == "failed"
    assert run.error_code == "agent_unknown_workflow"
    assert run.finished_at is not None


def test_next_step_exception_no_permanent_running(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session, code="fake_broken_next")
    worker = _make_worker(registry=_registry("fake_broken_next"))

    result = worker.run_once()

    assert result.action == "failed"
    assert run.status == "failed"
    assert run.error_code == "agent_runtime_error"
    assert "next_step" in run.error_message


# ── stale 恢复 ──


def test_stale_running_interrupted(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is True
    db_session.commit()

    clock.advance(301)  # stale_after=300
    worker = _make_worker(clock=clock, stale_after=300.0)

    assert worker.recover_stale_runs() == 1

    refreshed = db_session.query(AgentRun).get(run.id)
    assert refreshed.status == "interrupted"
    assert refreshed.error_code == "agent_worker_heartbeat_timeout"
    assert refreshed.worker_id == WORKER_A  # 统一保留 worker_id 供排查
    assert refreshed.finished_at == clock()


def test_fresh_running_not_touched(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is True
    db_session.commit()

    clock.advance(60)  # 未超 stale_after
    worker = _make_worker(clock=clock, stale_after=300.0)

    assert worker.recover_stale_runs() == 0
    assert db_session.query(AgentRun).get(run.id).status == "running"


def test_stale_with_null_heartbeat_and_old_started_at(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    agent_run_service.transition_status(db_session, run, "running")
    run.started_at = clock() - timedelta(seconds=3600)  # heartbeat 为 NULL
    db_session.commit()

    worker = _make_worker(clock=clock, stale_after=300.0)
    assert worker.recover_stale_runs() == 1
    assert db_session.query(AgentRun).get(run.id).status == "interrupted"


def test_waiting_approval_not_stale_recovered(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session, code="fake_approval")
    clock = FakeClock()
    worker = _make_worker(registry=_registry("fake_approval"), clock=clock, stale_after=300.0)
    worker.run_once()
    assert run.status == "waiting_approval"

    clock.advance(1000)
    assert worker.recover_stale_runs() == 0
    assert db_session.query(AgentRun).get(run.id).status == "waiting_approval"


def test_interrupted_not_auto_requeued(db_session):
    session = _seed_session(db_session)
    run = _seed_queued_run(db_session, session)
    clock = FakeClock()
    assert agent_run_service.claim_queued_run(db_session, run.id, WORKER_A, clock()) is True
    db_session.commit()
    clock.advance(301)
    worker = _make_worker(clock=clock, stale_after=300.0)
    assert worker.recover_stale_runs() == 1

    assert agent_run_service.next_queued_run_id(db_session) is None  # 不重排
    assert worker.run_once().action == "idle"
    assert db_session.query(AgentRun).get(run.id).status == "interrupted"


# ── 循环与资源 ──


def test_run_loop_bounded_with_sleeper(db_session):
    sleeps = []
    worker = _make_worker(sleeper=sleeps.append, poll_interval=0.25)

    worker.run_loop(max_iterations=2)

    assert sleeps == [0.25]  # 最后一次迭代后不再 sleep


def test_run_loop_stop_requested(db_session):
    calls = {"count": 0}

    def stop_requested():
        return calls["count"] >= 1

    def sleeper(_seconds):
        calls["count"] += 1

    worker = _make_worker(sleeper=sleeper)
    worker.run_loop(stop_requested=stop_requested)

    assert calls["count"] == 1  # 睡过一次后停止


def test_run_loop_keyboard_interrupt_graceful(db_session):
    def sleeper(_seconds):
        raise KeyboardInterrupt

    worker = _make_worker(sleeper=sleeper)
    worker.run_loop()  # 不抛异常，正常退出


def test_sessions_closed(db_session):
    factory = TrackingFactory(SessionLocal)
    worker = _make_worker(session_factory=factory)

    worker.run_once()  # idle 路径
    session = _seed_session(db_session)
    _seed_queued_run(db_session, session)
    worker.run_once()  # 执行路径

    assert len(factory.created) == 2
    # SQLAlchemy 2.0 的 is_active 在 close 后仍为 True，用 in_transaction 判断
    assert all(not s.in_transaction() for s in factory.created)


def test_constructor_validation():
    with pytest.raises(ValueError):
        _make_worker(poll_interval=0)
    with pytest.raises(ValueError):
        _make_worker(stale_after=-1)


# ── CLI ──


def test_cli_once_idle(capsys, db_session):
    from app.workers.agent_worker import main

    main(["--once"])  # Registry 为空 → 安全 idle

    assert "idle" in capsys.readouterr().out


def test_cli_invalid_poll_interval():
    from app.workers.agent_worker import main

    with pytest.raises(SystemExit):
        main(["--once", "--poll-interval", "-1"])
    with pytest.raises(SystemExit):
        main(["--once", "--stale-after", "-5"])
