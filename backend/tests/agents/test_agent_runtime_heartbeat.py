"""Runner on_step_boundary 回调测试：Heartbeat 接入点且不破坏 T04A 合同。"""

from app.agents.registry import SkillDefinition, SkillRegistry, ToolRegistry
from app.agents.runtime.contracts import StepOutcome
from app.agents.runtime.runner import AgentRunner
from app.models.project import Project
from app.models.user import User
from app.services.agent import agent_run_service, agent_session_service


class HookProbeWorkflow:
    code = "hook_probe"
    version = "1"

    def initial_state(self, input_data):
        return {"phase": 0}

    def next_step(self, state):
        return {0: "step_one", 1: "step_two"}.get(state.get("phase"))

    def execute_step(self, step_name, state, context):
        return StepOutcome(status="continue", next_state={**state, "phase": state["phase"] + 1})


def _seed(db):
    # 隔离库启用外键检查：AgentSession 引用 users/projects，须先有父行
    if not db.query(User).filter(User.id == 1).first():
        db.add(User(id=1, username="hook_user", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()
    if not db.query(Project).filter(Project.id == 101).first():
        db.add(Project(id=101, name="Hook 项目", status="active", is_deleted=False))
        db.flush()
    session = agent_session_service.create_session(db, 1, 101, "hook 测试会话")
    run = agent_run_service.create_run(db, session, "hook_probe", 1, 101)
    db.commit()
    return run


def _registry():
    registry = SkillRegistry()
    registry.register(SkillDefinition(code="hook_probe", name="hook_probe", workflow=HookProbeWorkflow()))
    return registry


def test_on_step_boundary_called_after_each_step(db_session):
    run = _seed(db_session)
    calls = []

    def hook(current_run):
        calls.append((current_run.id, current_run.steps_used))

    runner = AgentRunner(_registry(), ToolRegistry(), on_step_boundary=hook)
    runner.run(db_session, run)

    assert run.status == "succeeded"
    # 每个步骤边界回调一次，且回调时 steps_used 已自增
    assert calls == [(run.id, 1), (run.id, 2)]


def test_default_no_hook_keeps_t04a_behavior(db_session):
    run = _seed(db_session)

    runner = AgentRunner(_registry(), ToolRegistry())  # 不传 hook
    runner.run(db_session, run)

    assert run.status == "succeeded"
    assert run.steps_used == 2
