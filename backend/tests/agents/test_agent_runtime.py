"""AgentRunner 测试：Fake Workflow 验证 Runtime 闭环。

- 全部 SQLite + Fake，零网络、零真实 LLM、零 sleep、零后台线程；
- 验证 ORM 持久化结果（Step/Event/Artifact/Approval 行），不只断言返回值。
"""

import pytest

from app.agents.registry import SkillDefinition, SkillRegistry, ToolDefinition, ToolRegistry
from app.agents.runtime.contracts import StepOutcome
from app.agents.runtime.runner import AgentRunner
from app.agents.runtime.errors import (
    AgentApprovalConflictError,
    RunNotExecutableError,
    UnknownSkillError,
    UnknownToolError,
)
from app.models.agent_approval import AgentApproval
from app.models.agent_artifact import AgentArtifact
from app.models.agent_event import AgentEvent
from app.models.agent_step import AgentStep
from app.models.project import Project
from app.models.user import User
from app.services import (
    agent_approval_service,
    agent_run_service,
    agent_session_service,
)


# ── Fake Workflows（只存在于测试中，不进生产注册表） ──


class FakeSuccessWorkflow:
    code = "fake_success"
    version = "1"

    def initial_state(self, input_data):
        return {"phase": 0, "input": input_data}

    def next_step(self, state):
        return {0: "step_progress", 1: "step_artifact"}.get(state.get("phase"))

    def execute_step(self, step_name, state, context):
        if step_name == "step_progress":
            return StepOutcome(
                status="continue",
                next_state={**state, "phase": 1},
                output_summary="进度步骤完成",
                emitted_events=[{"event_type": "progress", "payload_json": {"phase": 0}}],
            )
        if step_name == "step_artifact":
            return StepOutcome(
                status="succeeded",
                next_state={**state, "phase": 2},
                step_kind="tool",
                tool_name="fake_tool",
                artifacts_to_create=[
                    {"artifact_type": "test_case_set", "payload_json": {"cases": [{"name": "登录成功"}]}}
                ],
            )
        return StepOutcome(status="failed", error_code="fake_unknown_step", error_message=f"未知步骤 {step_name}")


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
            emitted_events=[{"event_type": "await_approval", "payload_json": {}}],
            approval_to_create={"action_code": "save_cases", "request_json": {"candidate_ids": ["CASE-001"]}},
        )


class FakeFailingWorkflow:
    code = "fake_failing"
    version = "1"

    def initial_state(self, input_data):
        return {}

    def next_step(self, state):
        return "step_boom"

    def execute_step(self, step_name, state, context):
        raise RuntimeError("boom 步骤异常")


class FakeEndlessWorkflow:
    code = "fake_endless"
    version = "1"

    def initial_state(self, input_data):
        return {}

    def next_step(self, state):
        return "step_loop"

    def execute_step(self, step_name, state, context):
        return StepOutcome(status="continue", output_summary="循环步骤")


# ── 构造辅助 ──


def _ensure_parents(db, user_id=1, project_id=101):
    """隔离库启用外键检查：AgentSession 引用 users/projects，须先有父行。"""
    if not db.query(User).filter(User.id == user_id).first():
        db.add(User(id=user_id, username=f"runtime_user_{user_id}", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()
    if not db.query(Project).filter(Project.id == project_id).first():
        db.add(Project(id=project_id, name="Runtime 项目", status="active", is_deleted=False))
        db.flush()


def _seed_session(db, user_id=1, project_id=101):
    _ensure_parents(db, user_id, project_id)
    session = agent_session_service.create_session(db, user_id, project_id, "测试会话")
    db.commit()
    return session


def _seed_run(db, session, workflow_code, max_steps=20, input_json=None):
    run = agent_run_service.create_run(
        db, session, workflow_code, session.user_id, session.project_id,
        input_json=input_json, max_steps=max_steps,
    )
    db.commit()
    return run


def _make_runner(skill, allowed_tools=()):
    skill_registry = SkillRegistry()
    skill_registry.register(skill)
    tool_registry = ToolRegistry()
    return AgentRunner(skill_registry, tool_registry)


def _skill(workflow, code=None, allowed_tools=()):
    return SkillDefinition(
        code=code or workflow.code,
        name=workflow.code,
        version=workflow.version,
        workflow=workflow,
        allowed_tools=tuple(allowed_tools),
    )


def _events(db, session):
    return (
        db.query(AgentEvent)
        .filter(AgentEvent.session_id == session.id)
        .order_by(AgentEvent.sequence_no.asc())
        .all()
    )


# ── 成功流程 ──


def test_success_flow_persists_steps_events_artifact(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_success", input_json={"requirement_id": 12})
    runner = _make_runner(_skill(FakeSuccessWorkflow()))

    runner.run(db_session, run)

    assert run.status == "succeeded"
    assert run.steps_used == 2
    assert run.finished_at is not None
    assert run.output_json["result"]["status"] == "succeeded"
    assert run.output_json["result"]["step_count"] == 2
    assert run.output_json["workflow_state"]["phase"] == 2  # state 已持久化

    steps = (
        db_session.query(AgentStep)
        .filter(AgentStep.agent_run_id == run.id)
        .order_by(AgentStep.sequence_no.asc())
        .all()
    )
    assert [s.sequence_no for s in steps] == [1, 2]  # sequence_no 唯一递增
    assert [s.status for s in steps] == ["succeeded", "succeeded"]
    assert steps[0].step_name == "step_progress"
    assert steps[1].step_kind == "tool"  # StepOutcome.step_kind 被记录
    assert steps[1].tool_name == "fake_tool"
    assert steps[0].output_json == {"summary": "进度步骤完成"}
    assert steps[0].duration_ms >= 0

    events = _events(db_session, session)
    seqs = [e.sequence_no for e in events]
    assert seqs == sorted(set(seqs))  # 事件序号唯一
    event_types = {e.event_type for e in events}
    assert {"run_started", "step_succeeded", "progress", "run_succeeded"} <= event_types
    assert events[0].event_type == "run_started"  # 事件有序递增

    artifact = db_session.query(AgentArtifact).one()
    assert artifact.artifact_type == "test_case_set"
    assert artifact.payload_json == {"cases": [{"name": "登录成功"}]}
    assert artifact.version == 1
    assert artifact.status == "draft"
    assert artifact.session_id == session.id
    assert artifact.agent_run_id == run.id


# ── 审批流程 ──


def test_approval_flow_waiting_and_resolve(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_approval")
    runner = _make_runner(_skill(FakeApprovalWorkflow()))

    runner.run(db_session, run)

    assert run.status == "waiting_approval"
    assert "approval_requested" in {e.event_type for e in _events(db_session, session)}

    approval = db_session.query(AgentApproval).one()
    assert approval.status == "pending"
    assert approval.action_code == "save_cases"
    assert approval.request_json == {"candidate_ids": ["CASE-001"]}

    agent_approval_service.approve(db_session, approval, resolved_by_user_id=session.user_id)
    db_session.commit()
    assert approval.status == "approved"
    assert approval.resolved_by_user_id == session.user_id
    assert approval.resolved_at is not None

    # 重复解决被拒绝
    with pytest.raises(AgentApprovalConflictError) as exc:
        agent_approval_service.reject(db_session, approval, resolved_by_user_id=session.user_id)
    assert "只有 pending" in str(exc.value)
    db_session.rollback()

    # 审批通过后再次执行：waiting_approval → running → 从持久化 state 继续 → succeeded
    runner.run(db_session, run)
    assert run.status == "succeeded"
    assert "run_resumed" in {e.event_type for e in _events(db_session, session)}


# ── 失败与预算 ──


def test_workflow_exception_marks_failed(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_failing")
    runner = _make_runner(_skill(FakeFailingWorkflow()))

    runner.run(db_session, run)

    assert run.status == "failed"
    assert run.error_code == "agent_workflow_step_failed"
    assert "boom" in run.error_message
    assert run.steps_used == 1
    steps = db_session.query(AgentStep).filter(AgentStep.agent_run_id == run.id).all()
    assert len(steps) == 1
    assert steps[0].status == "failed"
    assert steps[0].error_code == "agent_workflow_step_failed"
    event_types = {e.event_type for e in _events(db_session, session)}
    assert {"run_started", "step_failed", "run_failed"} <= event_types


def test_max_steps_exceeded_fails_with_stable_code(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_endless", max_steps=2)
    runner = _make_runner(_skill(FakeEndlessWorkflow()))

    runner.run(db_session, run)

    assert run.status == "failed"
    assert run.error_code == "agent_max_steps_exceeded"
    assert run.steps_used == 2
    assert "max_steps_exceeded" in {e.event_type for e in _events(db_session, session)}


# ── 未知 Skill / Tool ──


def test_unknown_skill_rejected(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "no_such_skill")
    runner = _make_runner(_skill(FakeSuccessWorkflow()))

    with pytest.raises(UnknownSkillError):
        runner.run(db_session, run)
    assert run.status == "queued"  # 未进入 running，未产生步骤
    assert db_session.query(AgentStep).count() == 0


def test_allowed_tools_unknown_rejected(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_success")
    runner = _make_runner(_skill(FakeSuccessWorkflow(), allowed_tools=("ghost_tool",)))

    with pytest.raises(UnknownToolError):
        runner.run(db_session, run)
    assert run.status == "queued"
    assert db_session.query(AgentStep).count() == 0


# ── cancelled / 终态 ──


def test_cancelled_run_not_executed(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_success")
    agent_run_service.transition_status(db_session, run, "cancelled")  # queued → cancelled 合法
    db_session.commit()
    runner = _make_runner(_skill(FakeSuccessWorkflow()))

    with pytest.raises(RunNotExecutableError):
        runner.run(db_session, run)
    assert db_session.query(AgentStep).count() == 0


def test_terminal_run_not_executable(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session, "fake_success")
    runner = _make_runner(_skill(FakeSuccessWorkflow()))
    runner.run(db_session, run)
    assert run.status == "succeeded"

    with pytest.raises(RunNotExecutableError):
        runner.run(db_session, run)
    assert run.status == "succeeded"  # 终态不被破坏
