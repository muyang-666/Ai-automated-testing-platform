"""Agent 平台七张表的模型测试。

运行在 conftest 提供的内存 SQLite 上（每条测试重建全部表）。
只验证数据模型行为，不涉及 Runtime/Service/Router。
"""

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.agent.agent_approval import AgentApproval
from app.models.agent.agent_artifact import AgentArtifact
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.agent.agent_step import AgentStep
from app.models.project import Project
from app.models.user import User
from app.schemas.agent.platform import (
    APPROVAL_STATUSES,
    ARTIFACT_STATUSES,
    RUN_STATUSES,
    SESSION_STATUSES,
    STEP_STATUSES,
)

AGENT_TABLE_NAMES = {
    "agent_sessions",
    "agent_messages",
    "agent_events",
    "agent_runs",
    "agent_steps",
    "agent_artifacts",
    "agent_approvals",
}


def _seed_chain(db):
    """构造 User→Project→Session→Run 基础外键链。"""
    user = User(username="agent_user_1", password_hash="x", salt="y", status="active", is_deleted=False)
    project = Project(name="Agent项目", status="active", is_deleted=False)
    db.add_all([user, project])
    db.flush()
    agent_session = AgentSession(project_id=project.id, user_id=user.id, title="登录需求用例生成会话")
    db.add(agent_session)
    db.flush()
    run = AgentRun(
        session_id=agent_session.id,
        project_id=project.id,
        requester_user_id=user.id,
        workflow_code="case_generation",
    )
    db.add(run)
    db.flush()
    return user, project, agent_session, run


# ── 七张表可在 SQLite 创建 ──


def test_agent_tables_created(db_session):
    names = set(inspect(db_session.get_bind()).get_table_names())
    assert AGENT_TABLE_NAMES <= names


# ── 必填字段约束 ──


def test_required_fields_enforced(db_session):
    with pytest.raises(IntegrityError):
        db_session.add(AgentSession(project_id=1))  # 缺 user_id、title
        db_session.flush()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(AgentMessage(session_id=1, role="user"))  # 缺 sequence_no
        db_session.flush()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(AgentRun(session_id=1, project_id=1, requester_user_id=1))  # 缺 workflow_code
        db_session.flush()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(AgentArtifact(session_id=1, agent_run_id=1, artifact_type="test_case_set"))  # 缺 payload_json
        db_session.flush()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(AgentApproval(session_id=1, agent_run_id=1))  # 缺 action_code
        db_session.flush()
    db_session.rollback()


# ── status 默认值 ──


def test_status_defaults(db_session):
    _, _, agent_session, run = _seed_chain(db_session)
    step = AgentStep(agent_run_id=run.id, sequence_no=1, step_kind="llm", step_name="生成候选")
    artifact = AgentArtifact(
        session_id=agent_session.id, agent_run_id=run.id, artifact_type="test_case_set", payload_json={"cases": []}
    )
    approval = AgentApproval(session_id=agent_session.id, agent_run_id=run.id, action_code="save_selected_candidates")
    db_session.add_all([step, artifact, approval])
    db_session.commit()

    assert agent_session.status == "active" and agent_session.status in SESSION_STATUSES
    assert run.status == "queued" and run.status in RUN_STATUSES
    assert step.status == "pending" and step.status in STEP_STATUSES
    assert artifact.status == "draft" and artifact.status in ARTIFACT_STATUSES
    assert approval.status == "pending" and approval.status in APPROVAL_STATUSES
    assert run.max_steps == 20
    assert run.steps_used == 0
    assert run.llm_calls_used == 0
    assert run.tool_calls_used == 0
    assert run.prompt_tokens == 0
    assert run.completion_tokens == 0
    assert artifact.version == 1
    assert approval.requested_at is not None  # server_default 生效


# ── JSON 字段往返 ──


def test_json_roundtrip(db_session):
    _, _, agent_session, run = _seed_chain(db_session)
    context = {"source_type": "requirement", "requirement_id": 12}
    agent_session.context_json = context
    run.input_json = {"case_types": ["正常场景", "异常场景"], "max_cases": 30}
    run.output_json = {"candidates": [{"candidate_id": "CASE-001", "case_name": "登录成功"}]}
    run.model_snapshot_json = {"provider": "fake-provider", "model": "fake-model"}
    db_session.commit()
    db_session.expire_all()

    loaded_session = db_session.query(AgentSession).filter(AgentSession.id == agent_session.id).one()
    assert loaded_session.context_json == context
    loaded_run = db_session.query(AgentRun).filter(AgentRun.id == run.id).one()
    assert loaded_run.input_json["case_types"] == ["正常场景", "异常场景"]
    assert loaded_run.output_json["candidates"][0]["candidate_id"] == "CASE-001"
    assert loaded_run.model_snapshot_json["model"] == "fake-model"


# ── Session/Run/Artifact/Approval 外键关联 ──


def test_fk_association_chain(db_session):
    _, _, agent_session, run = _seed_chain(db_session)
    message = AgentMessage(session_id=agent_session.id, run_id=run.id, role="user", sequence_no=1, content="生成登录用例")
    event = AgentEvent(session_id=agent_session.id, run_id=run.id, event_type="phase_started", sequence_no=1)
    step = AgentStep(agent_run_id=run.id, sequence_no=1, step_kind="tool", step_name="查询已有用例", tool_name="list_existing_cases")
    artifact = AgentArtifact(
        session_id=agent_session.id, agent_run_id=run.id, artifact_type="coverage_matrix", payload_json={"clauses": []}
    )
    approval = AgentApproval(session_id=agent_session.id, agent_run_id=run.id, action_code="save_selected_candidates")
    db_session.add_all([message, event, step, artifact, approval])
    db_session.commit()
    db_session.expire_all()

    assert db_session.query(AgentMessage).filter(AgentMessage.session_id == agent_session.id).count() == 1
    assert db_session.query(AgentEvent).filter(AgentEvent.run_id == run.id).count() == 1
    assert db_session.query(AgentStep).filter(AgentStep.agent_run_id == run.id).count() == 1
    artifact_row = db_session.query(AgentArtifact).one()
    approval_row = db_session.query(AgentApproval).one()
    assert artifact_row.session_id == agent_session.id and artifact_row.agent_run_id == run.id
    assert approval_row.session_id == agent_session.id and approval_row.agent_run_id == run.id


# ── sequence_no 唯一约束 ──


def test_message_sequence_no_unique(db_session):
    _, _, agent_session, _ = _seed_chain(db_session)
    db_session.add(AgentMessage(session_id=agent_session.id, role="user", sequence_no=1))
    db_session.flush()
    db_session.add(AgentMessage(session_id=agent_session.id, role="assistant", sequence_no=1))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_event_sequence_no_unique(db_session):
    _, _, agent_session, _ = _seed_chain(db_session)
    db_session.add(AgentEvent(session_id=agent_session.id, event_type="skill_selected", sequence_no=1))
    db_session.flush()
    db_session.add(AgentEvent(session_id=agent_session.id, event_type="phase_started", sequence_no=1))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_step_sequence_no_unique(db_session):
    _, _, _, run = _seed_chain(db_session)
    db_session.add(AgentStep(agent_run_id=run.id, sequence_no=1, step_kind="llm", step_name="步骤A"))
    db_session.flush()
    db_session.add(AgentStep(agent_run_id=run.id, sequence_no=1, step_kind="tool", step_name="步骤B"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ── idempotency 唯一约束 ──


def test_idempotency_key_unique(db_session):
    _, project, agent_session, _ = _seed_chain(db_session)
    db_session.add(AgentRun(session_id=agent_session.id, project_id=project.id, requester_user_id=1, workflow_code="case_generation", idempotency_key="req-1001"))
    db_session.flush()
    db_session.add(AgentRun(session_id=agent_session.id, project_id=project.id, requester_user_id=1, workflow_code="case_generation", idempotency_key="req-1001"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_idempotency_key_null_not_unique(db_session):
    _, project, agent_session, _ = _seed_chain(db_session)
    db_session.add(AgentRun(session_id=agent_session.id, project_id=project.id, requester_user_id=1, workflow_code="case_generation"))
    db_session.add(AgentRun(session_id=agent_session.id, project_id=project.id, requester_user_id=1, workflow_code="case_generation"))
    db_session.flush()  # key 为 NULL 时不参与唯一性，不抛异常


# ── 删除行为：RESTRICT（需要开启 SQLite 外键强制） ──


def test_delete_restrict_with_fk_enforcement(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fk_enforced.db'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        user = User(username="fk_user", password_hash="x", salt="y", status="active", is_deleted=False)
        project = Project(name="FK项目", status="active", is_deleted=False)
        session.add_all([user, project])
        session.flush()
        agent_session = AgentSession(project_id=project.id, user_id=user.id, title="会话")
        session.add(agent_session)
        session.flush()
        session.add(AgentMessage(session_id=agent_session.id, role="user", sequence_no=1))
        session.commit()

        # 会话下存在消息，RESTRICT 阻止删除会话
        with pytest.raises(IntegrityError):
            session.delete(agent_session)
            session.flush()
        session.rollback()

        # 删除用户同样被 Agent 会话 RESTRICT 阻止
        with pytest.raises(IntegrityError):
            session.delete(user)
            session.flush()
        session.rollback()
    finally:
        session.close()
        engine.dispose()
