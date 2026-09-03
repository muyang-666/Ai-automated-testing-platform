"""Agent 平台四个 Service 的边界测试：权限、sequence_no、状态规则、版本递增。"""

import pytest

from app.agents.runtime.errors import (
    AgentApprovalConflictError,
    AgentError,
    AgentPermissionError,
    InvalidStateTransitionError,
)
from app.models.agent.agent_approval import AgentApproval
from app.models.agent.agent_artifact import AgentArtifact
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_session import AgentSession
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.user import User
from app.services.agent import (
    agent_approval_service,
    agent_artifact_service,
    agent_run_service,
    agent_session_service,
)

USER_A = 1
USER_B = 2
PROJECT = 101


def _seed_user_and_project(db, user_id=USER_A, project_id=PROJECT, project_status="active"):
    """隔离库启用外键检查：AgentSession 引用 users/projects，须先有父行。"""
    if not db.query(User).filter(User.id == user_id).first():
        db.add(User(id=user_id, username=f"svc_user_{user_id}", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        project = Project(id=project_id, name="服务测试项目", status=project_status, is_deleted=False)
        db.add(project)
        db.flush()
    db.commit()
    return project


def _seed_session(db, user_id=USER_A, project_id=PROJECT):
    _seed_user_and_project(db, user_id=user_id, project_id=project_id)
    session = agent_session_service.create_session(db, user_id, project_id, "会话标题")
    db.commit()
    return session


def _seed_run(db, session, max_steps=20):
    run = agent_run_service.create_run(
        db, session, "fake_skill", session.user_id, session.project_id, max_steps=max_steps
    )
    db.commit()
    return run


# ── AgentSession Service ──


def test_session_create_and_owner_permission(db_session):
    session = _seed_session(db_session)

    got = agent_session_service.get_session(db_session, session.id, USER_A)
    assert got.id == session.id

    with pytest.raises(AgentPermissionError):
        agent_session_service.get_session(db_session, session.id, USER_B)


# ── AgentSession 创建校验（T08.1） ──


def test_create_session_rejects_missing_project(db_session):
    _seed_user_and_project(db_session)

    with pytest.raises(AgentError) as exc:
        agent_session_service.create_session(db_session, USER_A, 404404, "会话")
    assert exc.value.error_code == "agent_project_not_found"
    db_session.rollback()
    assert db_session.query(AgentSession).count() == 0


def test_create_session_rejects_deleted_project(db_session):
    project = _seed_user_and_project(db_session, project_status="active")
    project.is_deleted = True
    db_session.commit()

    with pytest.raises(AgentError) as exc:
        agent_session_service.create_session(db_session, USER_A, project.id, "会话")
    assert exc.value.error_code == "agent_project_not_found"
    db_session.rollback()


def test_create_session_rejects_inactive_project(db_session):
    project = _seed_user_and_project(db_session, project_status="archived")

    with pytest.raises(AgentError) as exc:
        agent_session_service.create_session(db_session, USER_A, project.id, "会话")
    assert exc.value.error_code == "agent_project_inactive"
    db_session.rollback()


def test_create_session_after_failed_attempt_still_succeeds(db_session):
    # 非法请求后事务回滚，不污染后续合法请求
    _seed_user_and_project(db_session)
    try:
        agent_session_service.create_session(db_session, USER_A, 999999, "非法会话")
    except AgentError:
        db_session.rollback()

    session = agent_session_service.create_session(db_session, USER_A, PROJECT, "合法会话")
    db_session.commit()
    assert session.project_id == PROJECT
    assert db_session.query(AgentSession).count() == 1


def test_resolve_session_source_shapes(db_session):
    assert agent_session_service.resolve_session_source(None) == (None, None)
    assert agent_session_service.resolve_session_source({}) == (None, None)
    assert agent_session_service.resolve_session_source({"source_type": None, "source_id": None}) == (None, None)

    with pytest.raises(AgentError) as exc:
        agent_session_service.resolve_session_source({"source_type": "scene", "source_id": 3})
    assert exc.value.error_code == "agent_invalid_input"
    with pytest.raises(AgentError):
        agent_session_service.resolve_session_source({"source_type": "requirement"})
    with pytest.raises(AgentError):
        agent_session_service.resolve_session_source({"source_id": 3})
    with pytest.raises(AgentError):
        agent_session_service.resolve_session_source({"source_type": "requirement", "source_id": 0})
    with pytest.raises(AgentError):
        agent_session_service.resolve_session_source({"source_type": "requirement", "source_id": "2"})


def test_validate_session_source_missing_and_mismatch(db_session):
    _seed_user_and_project(db_session)

    # 需求不存在
    with pytest.raises(AgentError) as exc:
        agent_session_service.validate_session_source(db_session, PROJECT, "requirement", 900001)
    assert exc.value.error_code == "agent_source_not_found"

    # 需求已删除
    requirement = RequirementDoc(project_id=PROJECT, title="已删需求", content="x",
                                 status="confirmed", is_deleted=True)
    db_session.add(requirement)
    db_session.flush()
    with pytest.raises(AgentError) as exc:
        agent_session_service.validate_session_source(db_session, PROJECT, "requirement", requirement.id)
    assert exc.value.error_code == "agent_source_not_found"
    db_session.rollback()

    # 需求属于其他项目 → 来源项目与请求项目不一致
    other = RequirementDoc(project_id=PROJECT + 1, title="他项目需求", content="x",
                           status="confirmed", is_deleted=False)
    db_session.add(other)
    db_session.flush()
    with pytest.raises(AgentError) as exc:
        agent_session_service.validate_session_source(db_session, PROJECT, "requirement", other.id)
    assert exc.value.error_code == "agent_source_mismatch"
    db_session.rollback()

    # 来源匹配 → 正常返回
    ok = RequirementDoc(project_id=PROJECT, title="正常需求", content="x",
                        status="confirmed", is_deleted=False)
    db_session.add(ok)
    db_session.flush()
    assert agent_session_service.validate_session_source(db_session, PROJECT, "requirement", ok.id).id == ok.id


def test_append_message_sequence_no_increments(db_session):
    session = _seed_session(db_session)

    m1 = agent_session_service.append_message(db_session, session, role="user", content="第一条")
    m2 = agent_session_service.append_message(db_session, session, role="assistant", content="第二条")
    db_session.commit()

    assert m1.sequence_no == 1
    assert m2.sequence_no == 2
    assert db_session.query(AgentMessage).count() == 2


def test_append_message_invalid_role(db_session):
    session = _seed_session(db_session)

    with pytest.raises(AgentError) as exc:
        agent_session_service.append_message(db_session, session, role="robot", content="x")
    assert exc.value.error_code == "agent_invalid_message_role"


def test_close_and_archive_rules(db_session):
    session = _seed_session(db_session)

    agent_session_service.close_session(db_session, session)
    db_session.commit()
    assert session.status == "closed"

    with pytest.raises(AgentError):  # closed 不能再次 close
        agent_session_service.close_session(db_session, session)
    db_session.rollback()

    agent_session_service.archive_session(db_session, session)  # closed → archived 合法
    db_session.commit()
    assert session.status == "archived"

    with pytest.raises(AgentError):  # archived 终态
        agent_session_service.archive_session(db_session, session)


# ── AgentRun Service ──


def test_create_run_project_mismatch(db_session):
    session = _seed_session(db_session)

    with pytest.raises(AgentError) as exc:
        agent_run_service.create_run(db_session, session, "fake_skill", USER_A, 9999)
    assert exc.value.error_code == "agent_project_mismatch"


def test_create_run_computes_input_hash(db_session):
    session = _seed_session(db_session)

    run = agent_run_service.create_run(
        db_session, session, "fake_skill", USER_A, PROJECT,
        input_json={"requirement_id": 12, "name": "登录"},
    )
    db_session.commit()

    assert run.status == "queued"
    assert run.steps_used == 0
    assert run.input_hash is not None
    assert len(run.input_hash) == 64  # sha256 hex


def test_get_run_permission(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    assert agent_run_service.get_run(db_session, run.id, USER_A).id == run.id

    with pytest.raises(AgentPermissionError):
        agent_run_service.get_run(db_session, run.id, USER_B)


def test_transition_status_rules(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    agent_run_service.transition_status(db_session, run, "running")
    db_session.commit()
    assert run.status == "running"

    with pytest.raises(InvalidStateTransitionError):
        agent_run_service.transition_status(db_session, run, "queued")  # running → queued 非法
    db_session.rollback()


def test_start_finish_step_and_counters(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    step = agent_run_service.start_step(db_session, run, step_kind="llm", step_name="生成候选")
    assert step.sequence_no == 1
    assert step.status == "running"

    agent_run_service.finish_step(
        db_session, step,
        status="succeeded",
        output_json={"summary": "完成"},
        duration_ms=120,
        provider_name="fake-provider",
        model_name="fake-model",
        prompt_tokens=10,
        completion_tokens=20,
    )
    agent_run_service.increment_counter(db_session, run, "steps_used")
    agent_run_service.increment_counter(db_session, run, "llm_calls_used")
    db_session.commit()

    assert step.status == "succeeded"
    assert step.duration_ms == 120
    assert step.provider_name == "fake-provider"
    assert run.steps_used == 1
    assert run.llm_calls_used == 1


def test_append_event_sequence_no(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    e1 = agent_run_service.append_event(db_session, session.id, run.id, "run_started")
    e2 = agent_run_service.append_event(db_session, session.id, run.id, "step_succeeded")
    db_session.commit()

    assert e1.sequence_no == 1
    assert e2.sequence_no == 2


# ── AgentArtifact Service ──


def test_artifact_create_and_permission(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    artifact = agent_artifact_service.create_artifact(
        db_session, session.id, run.id, "coverage_matrix", {"clauses": ["登录"]}
    )
    db_session.commit()

    assert artifact.version == 1
    assert artifact.status == "draft"
    assert agent_artifact_service.get_artifact(db_session, artifact.id, USER_A).id == artifact.id

    with pytest.raises(AgentPermissionError):
        agent_artifact_service.get_artifact(db_session, artifact.id, USER_B)


def test_artifact_next_version(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    artifact = agent_artifact_service.create_artifact(
        db_session, session.id, run.id, "test_case_set", {"cases": ["旧版"]}
    )
    db_session.commit()

    next_version = agent_artifact_service.create_next_version(db_session, artifact)
    db_session.commit()

    assert next_version.version == 2
    assert next_version.status == "draft"
    assert next_version.payload_json == {"cases": ["旧版"]}
    assert db_session.query(AgentArtifact).count() == 2


def test_artifact_update_status(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    artifact = agent_artifact_service.create_artifact(
        db_session, session.id, run.id, "test_case_set", {"cases": []}
    )
    db_session.commit()

    agent_artifact_service.update_status(db_session, artifact, "saved")
    db_session.commit()
    assert artifact.status == "saved"

    with pytest.raises(AgentError):
        agent_artifact_service.update_status(db_session, artifact, "not_a_status")


# ── AgentApproval Service ──


def test_approval_request_and_approve(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)

    approval = agent_approval_service.request_approval(
        db_session, session.id, run.id, "save_cases", request_json={"ids": [1]}
    )
    db_session.commit()
    assert approval.status == "pending"

    agent_approval_service.approve(db_session, approval, resolved_by_user_id=USER_A)
    db_session.commit()
    assert approval.status == "approved"
    assert approval.resolved_by_user_id == USER_A
    assert approval.resolved_at is not None


def test_approval_non_owner_cannot_resolve(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    approval = agent_approval_service.request_approval(db_session, session.id, run.id, "save_cases")
    db_session.commit()

    with pytest.raises(AgentPermissionError):
        agent_approval_service.approve(db_session, approval, resolved_by_user_id=USER_B)


def test_approval_only_pending_resolvable(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    approval = agent_approval_service.request_approval(db_session, session.id, run.id, "save_cases")
    db_session.commit()

    agent_approval_service.reject(db_session, approval, resolved_by_user_id=USER_A)
    db_session.commit()

    with pytest.raises(AgentApprovalConflictError):
        agent_approval_service.approve(db_session, approval, resolved_by_user_id=USER_A)
    assert approval.status == "rejected"


def test_approval_expire(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    approval = agent_approval_service.request_approval(db_session, session.id, run.id, "save_cases")
    db_session.commit()

    agent_approval_service.expire(db_session, approval)
    db_session.commit()
    assert approval.status == "expired"

    with pytest.raises(AgentApprovalConflictError):
        agent_approval_service.expire(db_session, approval)


def test_approval_access_permission(db_session):
    session = _seed_session(db_session)
    run = _seed_run(db_session, session)
    approval = agent_approval_service.request_approval(db_session, session.id, run.id, "save_cases")
    db_session.commit()

    with pytest.raises(AgentPermissionError):
        agent_approval_service.get_approval(db_session, approval.id, USER_B)
    assert agent_approval_service.get_approval(db_session, approval.id, USER_A).id == approval.id
    assert db_session.query(AgentApproval).count() == 1
