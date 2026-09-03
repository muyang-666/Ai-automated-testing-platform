"""Agent 平台 API 集成测试。

- TestClient + SQLite + 依赖覆盖（get_db/get_current_user）+ Fake 用户；
- 不启动真实 Worker 线程：需要推进时显式调用 Worker.run_once（Fake Gateway）；
- 覆盖 Session/Message、Run、GATE、保存全链路（幂等/冲突/回滚/source_hash）。
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.bootstrap import build_default_skill_registry, build_default_tool_registry
from app.agents.runtime.runner import AgentRunner
from app.agents.skills.case_generation.schemas import (
    AnalyzeAndPlanOutput,
    AtomicClause,
    CoveragePlanItem,
    FunctionCandidateOut,
    GenerateFunctionCandidatesOutput,
)
from app.core.database import SessionLocal
from app.models.agent_approval import AgentApproval
from app.models.agent_artifact import AgentArtifact
from app.models.agent_event import AgentEvent
from app.models.agent_message import AgentMessage
from app.models.agent_run import AgentRun
from app.models.agent_session import AgentSession
from app.models.agent_step import AgentStep
from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.models.function_case import FunctionCase
from app.models.llm_model import LLMModel
from app.models.llm_provider import LLMProvider
from app.models.llm_scene_config import LLMSceneConfig
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.role import Role
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.schemas.llm_gateway import LLMResult
from app.services import agent_approval_service, agent_artifact_service, agent_run_service
from app.workers.agent_worker import AgentWorker

PROJECT_A = 101
PROJECT_B = 202
USER_ID = 1
VIEWER_ID = 2

GATE_SCOPE = "confirm_case_generation_scope"
GATE_COVERAGE = "confirm_case_coverage_plan"
GATE_SAVE = "save_generated_case_candidates"


def test_integration_session_run_history_and_pending_approvals(client, db_session):
    session_id = _create_session(client)
    source = _seed_requirement(db_session)
    run_id = _create_run(client, session_id, source_id=source.id).json()["id"]
    assert client.get(f"/agent/sessions/{session_id}/runs").json()[0]["id"] == run_id
    assert client.get(f"/agent/runs/{run_id}/approvals").json() == []
    _switch_user(db_session, VIEWER_ID)
    assert client.get(f"/agent/sessions/{session_id}/runs").status_code == 404
    assert client.get(f"/agent/runs/{run_id}/approvals").status_code == 404
    assert client.post(f"/agent/runs/{run_id}/cancel").status_code == 404


def test_integration_save_gate_cannot_be_approved_without_saving(client, db_session):
    _seed_llm_scenes(db_session)
    run_id = _drive_to_save_gate(db_session, client, FakeGateway([
        _plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("待保存", ["REQ-001", "REQ-002"])]),
    ]))
    approvals = client.get(f"/agent/runs/{run_id}/approvals").json()
    pending = next(item for item in approvals if item["status"] == "pending")
    assert pending["action_code"] == GATE_SAVE
    response = client.post(f"/agent/approvals/{pending['id']}/resolve", json={"status": "approved", "resolution_json": {}})
    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(AgentRun, run_id).status == "waiting_approval"
    assert db_session.query(FunctionCase).count() == 0


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, provider, model, request, response_model=None):
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("FakeGateway 响应不足")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(
            content="", parsed=item, provider_name=provider.name, model_name=model.model_name,
            prompt_tokens=10, completion_tokens=20, duration_ms=1, finish_reason="stop",
        )


def _plan_output():
    return AnalyzeAndPlanOutput(
        atomic_clauses=[
            AtomicClause(clause_id="REQ-001", text="用户可正常登录", priority="P0"),
            AtomicClause(clause_id="REQ-002", text="密码错误时提示并锁定", priority="P1"),
        ],
        coverage_plan=[
            CoveragePlanItem(clause_id="REQ-001", dimension="正常场景"),
            CoveragePlanItem(clause_id="REQ-002", dimension="异常场景"),
        ],
    )


def _fn_candidate(case_name, covered, case_type="正常场景"):
    return FunctionCandidateOut(
        case_name=case_name, case_type=case_type, priority="P1",
        steps_json=["打开登录页", "提交登录"], expected_result="按预期返回",
        covered_clause_ids=covered,
    )


def _seed_users(db):
    for code in ("system_admin", "tester", "viewer"):
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(code=code, name=code, status="active"))
    db.flush()
    role_map = {r.code: r for r in db.query(Role).all()}
    if not db.query(User).filter(User.id == 99).first():
        admin = User(id=99, username="admin_seed", password_hash="x", salt="y", status="active", is_deleted=False)
        db.add(admin)
        db.flush()
        db.add(UserRole(user_id=admin.id, role_id=role_map["system_admin"].id))  # 防止 startup 提升普通用户为管理员

    if not db.query(User).filter(User.id == USER_ID).first():
        tester = User(id=USER_ID, username="api_tester", password_hash="x", salt="y", status="active", is_deleted=False)
        db.add(tester)
        db.flush()
        db.add(UserRole(user_id=tester.id, role_id=role_map["tester"].id))
    if not db.query(User).filter(User.id == VIEWER_ID).first():
        viewer = User(id=VIEWER_ID, username="api_viewer", password_hash="x", salt="y", status="active", is_deleted=False)
        db.add(viewer)
        db.flush()
        db.add(UserRole(user_id=viewer.id, role_id=role_map["viewer"].id))
    db.commit()


def _seed_project(db, project_id, name="项目"):
    if not db.query(Project).filter(Project.id == project_id).first():
        db.add(Project(id=project_id, name=name, status="active", is_deleted=False))
        db.commit()
    if not db.query(UserProjectPermission).filter(UserProjectPermission.user_id == USER_ID, UserProjectPermission.project_id == project_id).first():
        db.add(UserProjectPermission(user_id=USER_ID, project_id=project_id, can_operate=True))
        db.commit()


def _seed_llm_scenes(db):
    provider = LLMProvider(
        name="FakeProvider", provider_type="openai_compatible", base_url="https://fake.invalid/v1",
        api_key="fake-key", status="active", is_deleted=False,
    )
    db.add(provider)
    db.flush()
    model = LLMModel(
        provider_id=provider.id, model_name="fake-model", display_name="Fake",
        temperature=0.0, max_tokens=8192, timeout_seconds=60, status="active", is_deleted=False,
    )
    db.add(model)
    db.flush()
    for scene_code in ("requirement_to_function_case", "api_doc_to_api_case"):
        scene = db.query(LLMSceneConfig).filter(LLMSceneConfig.scene_code == scene_code).first()
        if scene:
            scene.model_id = model.id
            scene.enabled = True
        else:
            db.add(LLMSceneConfig(scene_code=scene_code, scene_name=scene_code, model_id=model.id, enabled=True))
    db.commit()


def _seed_requirement(db, project_id=PROJECT_A, content="用户名密码登录，密码错误 5 次锁定 30 分钟。"):
    requirement = RequirementDoc(
        project_id=project_id, title="用户登录需求", content=content,
        requirement_type="功能需求", status="confirmed", is_deleted=False,
    )
    db.add(requirement)
    db.commit()
    return requirement


def _seed_api_doc(db, project_id=PROJECT_A):
    doc = ApiDocument(
        project_id=project_id, name="登录接口文档", method="POST", url="/login",
        content="POST /login", status="active", is_deleted=False,
    )
    db.add(doc)
    db.commit()
    return doc


def _make_client(db, user_id=USER_ID):
    from app.main import app
    from app.core.database import get_db
    from app.routers.dependencies import get_current_user

    user = db.query(User).filter(User.id == user_id).one()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        with client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    _seed_users(db_session)
    _seed_project(db_session, PROJECT_A, "项目A")
    _seed_project(db_session, PROJECT_B, "项目B")
    yield from _make_client(db_session, USER_ID)


def _switch_user(db_session, user_id):
    """单 client 内切换 override 用户（双 TestClient 会互相覆盖 app 级 override）。"""
    from app.main import app
    from app.routers.dependencies import get_current_user

    user = db_session.query(User).filter(User.id == user_id).one()
    app.dependency_overrides[get_current_user] = lambda: user


def _create_session(client, project_id=PROJECT_A):
    response = client.post("/agent/sessions", json={"project_id": project_id, "title": "测试会话"})
    assert response.status_code == 200
    return response.json()["id"]


def _create_run(client, session_id, source_type="requirement", source_id=1, **extra):
    payload = {"session_id": session_id, "source_type": source_type, "source_id": source_id}
    payload.update(extra)
    return client.post("/agent/runs/case-generation", json=payload)


def _advance_worker(db, gateway):
    """显式推进（不启动真实 Worker 线程）。"""
    tool_registry = build_default_tool_registry()
    skill_registry = build_default_skill_registry(gateway_factory=lambda: gateway, tool_registry=tool_registry)

    def runtime_factory(on_step_boundary):
        return AgentRunner(skill_registry, tool_registry, on_step_boundary=on_step_boundary)

    worker = AgentWorker(
        session_factory=SessionLocal, runtime_factory=runtime_factory,
        worker_id="api-test-worker", poll_interval_seconds=0.1, stale_after_seconds=300.0,
    )
    worker.run_once()
    db.expire_all()


def _approval(db, run_id, action_code):
    return (
        db.query(AgentApproval)
        .filter(AgentApproval.agent_run_id == run_id, AgentApproval.action_code == action_code)
        .first()
    )


def _drive_to_scope_gate(db, client, gateway, source_type="requirement", source_id=None):
    if source_id is None:
        source = _seed_requirement(db) if source_type == "requirement" else _seed_api_doc(db)
        source_id = source.id
    session_id = _create_session(client)
    response = _create_run(client, session_id, source_type=source_type, source_id=source_id)
    assert response.status_code == 202
    run_id = response.json()["id"]
    _advance_worker(db, gateway)
    return run_id, session_id


# ── Session/Message ──


def test_session_create_list_detail(client, db_session):
    session_id = _create_session(client)

    detail = client.get(f"/agent/sessions/{session_id}").json()
    assert detail["id"] == session_id
    assert detail["title"] == "测试会话"
    assert detail["user_id"] == USER_ID

    listed = client.get("/agent/sessions").json()
    assert any(s["id"] == session_id for s in listed)


def test_session_owner_permission(client, db_session):
    session_id = _create_session(client)

    assert client.get(f"/agent/sessions/{session_id}").status_code == 200
    _switch_user(db_session, VIEWER_ID)
    assert client.get(f"/agent/sessions/{session_id}").status_code == 404
    assert client.post(f"/agent/sessions/{session_id}/messages", json={"content": "x"}).status_code == 404


def test_user_cannot_fake_assistant_role(client, db_session):
    session_id = _create_session(client)

    response = client.post(
        f"/agent/sessions/{session_id}/messages",
        json={"content": "帮我生成用例", "role": "assistant"},  # 尝试伪造角色（Schema 无此字段，被忽略）
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"  # 后端强制 user
    row = db_session.query(AgentMessage).one()
    assert row.role == "user"


def test_messages_ordered_and_limited(client, db_session):
    session_id = _create_session(client)
    for i in range(3):
        client.post(f"/agent/sessions/{session_id}/messages", json={"content": f"消息{i}"})

    rows = client.get(f"/agent/sessions/{session_id}/messages", params={"limit": 2}).json()

    assert len(rows) == 2
    assert [r["sequence_no"] for r in rows] == [1, 2]
    assert rows[0]["content"] == "消息0"


# ── Session 创建校验（V2.1-T08.1：修复正式环境 Agent 创建会话 500） ──


def _session_payload(project_id, source_type=None, source_id=None, title="T08 会话"):
    payload = {"project_id": project_id, "title": title}
    if source_type is not None and source_id is not None:
        payload["context_json"] = {
            "source_type": source_type,
            "source_id": source_id,
            "source_label": "来源",
        }
    return payload


def _session_rows(db):
    return db.query(AgentSession).all()


def test_session_create_valid_project_and_source(client, db_session):
    requirement = _seed_requirement(db_session)  # project_id = PROJECT_A
    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "requirement", requirement.id))

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == PROJECT_A
    assert body["context_json"]["source_id"] == requirement.id
    assert len(_session_rows(db_session)) == 1


def test_session_create_missing_project_4xx_no_new_session(client, db_session):
    response = client.post("/agent/sessions", json=_session_payload(999991))

    assert response.status_code == 404
    assert "项目" in response.json()["detail"]
    assert len(_session_rows(db_session)) == 0


def test_session_create_legacy_orphan_source_referencing_missing_project(client, db_session):
    # requirement_docs.project_id 无外键，历史可写入指向不存在项目的孤立需求；
    # 复现原故障：请求 project_id=孤立项目 → 必须稳定 4xx 且零新增会话，而不是 500 FK
    orphan = RequirementDoc(id=3033, project_id=999992, title="孤立需求", content="x",
                            status="confirmed", is_deleted=False)
    db_session.add(orphan)
    db_session.commit()

    response = client.post("/agent/sessions", json=_session_payload(999992, "requirement", orphan.id))

    assert response.status_code == 404
    assert "项目不存在或已删除" in response.json()["detail"]
    assert len(_session_rows(db_session)) == 0


def test_session_create_deleted_source_and_deleted_project(client, db_session):
    deleted = _seed_requirement(db_session)
    deleted.is_deleted = True
    db_session.commit()
    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "requirement", deleted.id))
    assert response.status_code == 404
    assert "需求不存在或已删除" in response.json()["detail"]

    project = db_session.query(Project).filter(Project.id == PROJECT_A).one()
    project.is_deleted = True
    db_session.commit()
    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A))
    assert response.status_code == 404
    assert len(_session_rows(db_session)) == 0


def test_session_create_inactive_project_400(client, db_session):
    project = db_session.query(Project).filter(Project.id == PROJECT_B).one()
    project.status = "archived"
    db_session.commit()

    response = client.post("/agent/sessions", json=_session_payload(PROJECT_B))

    assert response.status_code == 400
    assert "项目状态" in response.json()["detail"]
    assert len(_session_rows(db_session)) == 0


def test_session_create_source_belongs_to_other_project_rejected(client, db_session):
    other = _seed_requirement(db_session, project_id=PROJECT_B)

    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "requirement", other.id))

    assert response.status_code == 400
    assert "不一致" in response.json()["detail"]
    assert len(_session_rows(db_session)) == 0


def test_session_create_source_deleted_api_document(client, db_session):
    doc = _seed_api_doc(db_session)
    doc.is_deleted = True
    db_session.commit()

    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "api_document", doc.id))

    assert response.status_code == 404
    assert "接口文档不存在或已删除" in response.json()["detail"]
    assert len(_session_rows(db_session)) == 0


def test_session_create_viewer_without_write_forbidden(client, db_session):
    requirement = _seed_requirement(db_session)
    _switch_user(db_session, VIEWER_ID)

    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "requirement", requirement.id))

    assert response.status_code == 403
    assert len(_session_rows(db_session)) == 0


def test_session_create_invalid_source_shape_400(client, db_session):
    payload = _session_payload(PROJECT_A)
    payload["context_json"] = {"source_type": "scene", "source_id": 1}

    response = client.post("/agent/sessions", json=payload)

    assert response.status_code == 400
    assert len(_session_rows(db_session)) == 0


def test_session_create_invalid_then_valid_same_db_not_polluted(client, db_session):
    # 非法请求后，同一 DB 会话内后续合法请求仍成功，事务未污染
    bad = client.post("/agent/sessions", json=_session_payload(999991))
    assert bad.status_code == 404

    requirement = _seed_requirement(db_session)
    ok = client.post("/agent/sessions", json=_session_payload(PROJECT_A, "requirement", requirement.id))

    assert ok.status_code == 200
    assert len(_session_rows(db_session)) == 1


def test_session_create_no_source_still_allowed(client, db_session):
    # 无来源上下文的合法会话仍然兼容（不强制所有会话绑定需求）
    response = client.post("/agent/sessions", json=_session_payload(PROJECT_A))

    assert response.status_code == 200
    body = response.json()
    assert body["context_json"] is None
    assert len(_session_rows(db_session)) == 1


# ── Run ──


def test_create_run_202_queued_no_execution(client, db_session):
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    session_id = _create_session(client)

    response = _create_run(client, session_id, source_id=requirement.id)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["workflow_code"] == "case_generation"
    assert db_session.query(AgentStep).count() == 0  # 创建后不直接执行 Runtime


def test_idempotency_same_key_same_payload(client, db_session):
    requirement = _seed_requirement(db_session)
    session_id = _create_session(client)

    first = _create_run(client, session_id, source_id=requirement.id, idempotency_key="key-1")
    second = _create_run(client, session_id, source_id=requirement.id, idempotency_key="key-1")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert db_session.query(AgentRun).count() == 1


def test_idempotency_same_key_different_payload_409(client, db_session):
    requirement = _seed_requirement(db_session)
    session_id = _create_session(client)

    _create_run(client, session_id, source_id=requirement.id, idempotency_key="key-2")
    second = _create_run(
        client, session_id, source_id=requirement.id, idempotency_key="key-2", max_cases=5
    )

    assert second.status_code == 409


def test_source_not_in_session_project_rejected(client, db_session):
    other_project_source = _seed_requirement(db_session, project_id=PROJECT_B)
    session_id = _create_session(client, project_id=PROJECT_A)

    response = _create_run(client, session_id, source_id=other_project_source.id)

    assert response.status_code == 400
    assert "项目" in response.json()["detail"]


def test_steps_and_artifacts_masked_and_ordered(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["REQ-001", "REQ-002"])])])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)

    # 批准范围 GATE → 继续到覆盖 GATE（产生 coverage Artifact）
    scope = _approval(db_session, run_id, GATE_SCOPE)
    response = client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})
    assert response.status_code == 200
    _advance_worker(db_session, gateway)

    steps = client.get(f"/agent/runs/{run_id}/steps").json()
    assert [s["sequence_no"] for s in steps] == sorted(s["sequence_no"] for s in steps)
    assert "llm:analyze_and_plan" in [s["step_name"] for s in steps]

    artifacts = client.get(f"/agent/runs/{run_id}/artifacts").json()
    coverage = [a for a in artifacts if a["artifact_type"] == "coverage_matrix"][0]
    artifact_detail = client.get(f"/agent/artifacts/{coverage['id']}").json()
    assert artifact_detail["payload_json"]["atomic_clauses"][0]["clause_id"] == "REQ-001"


def test_cancel_behaviors(client, db_session):
    _seed_llm_scenes(db_session)
    requirement = _seed_requirement(db_session)
    session_id = _create_session(client)

    # queued → cancelled
    response = _create_run(client, session_id, source_id=requirement.id)
    queued_run_id = response.json()["id"]
    cancel = client.post(f"/agent/runs/{queued_run_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert client.post(f"/agent/runs/{queued_run_id}/cancel").status_code == 409  # 终态不可再取消

    # waiting_approval → cancelled + pending 审批级联取消
    gateway = FakeGateway([_plan_output()])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)
    assert scope.status == "pending"
    assert client.post(f"/agent/runs/{run_id}/cancel").status_code == 200
    db_session.expire_all()
    assert db_session.query(AgentRun).get(run_id).status == "cancelled"
    assert _approval(db_session, run_id, GATE_SCOPE).status == "cancelled"


# ── GATE ──


def test_approve_sets_run_queued(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["REQ-001", "REQ-002"])])])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)

    response = client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})

    assert response.status_code == 200
    db_session.expire_all()
    run = db_session.query(AgentRun).get(run_id)
    assert run.status == "queued"  # 交回 Worker 继续
    assert _approval(db_session, run_id, GATE_SCOPE).status == "approved"


def test_worker_continues_to_next_gate_after_approve(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["REQ-001", "REQ-002"])])])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)

    client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})
    _advance_worker(db_session, gateway)

    db_session.expire_all()
    run = db_session.query(AgentRun).get(run_id)
    assert run.status == "waiting_approval"
    assert _approval(db_session, run_id, GATE_COVERAGE) is not None


def test_reject_sets_cancelled_not_failed(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output()])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)

    response = client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "rejected", "resolution_json": {"rejected": True}})

    assert response.status_code == 200
    db_session.expire_all()
    run = db_session.query(AgentRun).get(run_id)
    assert run.status == "cancelled"  # 不是 failed
    events = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id, AgentEvent.event_type == "approval_rejected")
        .count()
    )
    assert events == 1


def test_scope_resolution_modification_applied(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output(), GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("A", ["REQ-001", "REQ-002"])])])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)

    client.post(
        f"/agent/approvals/{scope.id}/resolve",
        json={"status": "approved", "resolution_json": {"approved": True, "case_types": ["正常场景"], "max_cases": 1, "user_goal": "只覆盖正常场景"}},
    )
    _advance_worker(db_session, gateway)

    run = client.get(f"/agent/runs/{run_id}").json()
    state = run["output_json"]["workflow_state"]
    assert state["requested_case_types"] == ["正常场景"]
    assert state["max_cases"] == 1
    assert state["user_goal"] == "只覆盖正常场景"


def test_repeat_same_resolution_idempotent_no_duplicate_event(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output()])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)
    payload = {"status": "approved", "resolution_json": {"approved": True}}

    first = client.post(f"/agent/approvals/{scope.id}/resolve", json=payload)
    second = client.post(f"/agent/approvals/{scope.id}/resolve", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    count = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id, AgentEvent.event_type == "approval_approved")
        .count()
    )
    assert count == 1  # 幂等，不重复事件


def test_conflicting_resolution_409(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output()])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)
    scope = _approval(db_session, run_id, GATE_SCOPE)

    client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})

    response = client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "rejected", "resolution_json": {"rejected": True}})
    assert response.status_code == 409


def test_non_current_approval_cannot_advance(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([_plan_output()])
    run_id, _ = _drive_to_scope_gate(db_session, client, gateway)

    # 手工创建不属于当前 GATE 的审批（scope 阶段伪造 coverage 审批，非当前 GATE）
    bogus = agent_approval_service.request_approval(
        db_session, session_id=db_session.query(AgentRun).get(run_id).session_id,
        agent_run_id=run_id, action_code=GATE_COVERAGE,
    )
    db_session.commit()

    response = client.post(f"/agent/approvals/{bogus.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})

    assert response.status_code == 409
    assert "当前 GATE" in response.json()["detail"]


# ── 保存 ──


def _drive_to_save_gate(db, client, gateway, source_type="requirement"):
    run_id, _ = _drive_to_scope_gate(db, client, gateway, source_type=source_type)
    scope = _approval(db, run_id, GATE_SCOPE)
    client.post(f"/agent/approvals/{scope.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})
    _advance_worker(db, gateway)
    coverage = _approval(db, run_id, GATE_COVERAGE)
    assert coverage is not None
    client.post(f"/agent/approvals/{coverage.id}/resolve", json={"status": "approved", "resolution_json": {"approved": True}})
    _advance_worker(db, gateway)
    db.expire_all()
    assert db.query(AgentRun).get(run_id).status == "waiting_approval"
    return run_id


def test_save_only_selected_ids_and_backend_data(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[
            _fn_candidate("候选A", ["REQ-001"]),
            _fn_candidate("候选B", ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)

    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidate_ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]
    assert len(candidate_ids) == 2

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": [candidate_ids[0]]})

    assert response.status_code == 200
    body = response.json()
    assert body["saved_count"] == 1
    saved = db_session.query(FunctionCase).all()
    assert len(saved) == 1
    assert saved[0].case_name == "候选A"  # 数据来自 Artifact，不信任前端
    assert saved[0].project_id == PROJECT_A  # project_id 来自 Run
    assert saved[0].source == "llm"


def test_save_source_hash_conflict_409(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidate_ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    # 保存前修改来源
    requirement = db_session.query(RequirementDoc).one()
    requirement.content = "内容已改变"
    db_session.commit()

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": candidate_ids})

    assert response.status_code == 409
    assert db_session.query(FunctionCase).count() == 0  # 业务表不变


def test_save_no_write_permission_403(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidate_ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    _switch_user(db_session, VIEWER_ID)
    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": candidate_ids})

    assert response.status_code == 403
    assert db_session.query(FunctionCase).count() == 0


def test_save_artifact_ownership_mismatch_409(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidate_ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    # 篡改审批关联到另一个 Run 的 Artifact（真实 FK，但归属不一致）
    session_id = db_session.query(AgentRun).get(run_id).session_id
    session = db_session.query(AgentSession).filter(AgentSession.id == session_id).one()
    other_run = agent_run_service.create_run(
        db_session, session, "case_generation", USER_ID, session.project_id,
    )
    db_session.flush()
    other_artifact = agent_artifact_service.create_artifact(
        db_session, session.id, other_run.id, "coverage_matrix", {"clauses": []}
    )
    db_session.commit()
    save = _approval(db_session, run_id, GATE_SAVE)
    save.artifact_id = other_artifact.id
    db_session.commit()

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": candidate_ids})

    assert response.status_code == 409
    assert db_session.query(FunctionCase).count() == 0


def test_save_idempotent_same_ids(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    candidate_ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    first = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": candidate_ids})
    second = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": candidate_ids})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["saved_case_ids"] == second.json()["saved_case_ids"]
    assert db_session.query(FunctionCase).count() == 1
    saved_event_count = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id, AgentEvent.event_type == "cases_saved")
        .count()
    )
    assert saved_event_count == 1


def test_save_different_ids_409(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[
            _fn_candidate("候选A", ["REQ-001"]),
            _fn_candidate("候选B", ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": [ids[0]]})

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": [ids[1]]})

    assert response.status_code == 409
    assert db_session.query(FunctionCase).count() == 1  # 不重复写入


def test_save_rollback_on_failure(client, db_session, monkeypatch):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[
            _fn_candidate("候选A", ["REQ-001"]),
            _fn_candidate("候选B", ["REQ-002"], case_type="异常场景"),
        ]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    from app.services import agent_save_service as save_module

    real_function_case = save_module.FunctionCase
    counter = {"n": 0}

    def failing_constructor(*args, **kwargs):
        counter["n"] += 1
        if counter["n"] == 2:
            raise RuntimeError("注入保存失败")
        return real_function_case(*args, **kwargs)

    monkeypatch.setattr(save_module, "FunctionCase", failing_constructor)

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": ids})

    assert response.status_code == 500
    assert "内部错误" in response.json()["detail"]  # 不返回 traceback
    assert db_session.query(FunctionCase).count() == 0  # 整体回滚
    save = _approval(db_session, run_id, GATE_SAVE)
    assert save.status == "pending"  # 审批未决议
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    assert artifact.status == "draft"  # Artifact 未标记 saved
    assert db_session.query(AgentRun).get(run_id).status == "waiting_approval"


def test_save_success_state_transitions(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": ids})

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(AgentRun).get(run_id).status == "succeeded"
    assert db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one().status == "saved"
    save = _approval(db_session, run_id, GATE_SAVE)
    assert save.status == "approved"
    assert save.resolution_json["saved_case_ids"] == response.json()["saved_case_ids"]
    saved_event_count = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id, AgentEvent.event_type == "cases_saved")
        .count()
    )
    assert saved_event_count == 1


def test_save_api_document_source(client, db_session):
    _seed_llm_scenes(db_session)
    from app.agents.skills.case_generation.schemas import ApiCandidateOut, GenerateApiCandidatesOutput

    gateway = FakeGateway([
        _plan_output(),
        GenerateApiCandidatesOutput(candidates=[
            ApiCandidateOut(name="登录成功", method="POST", url="/login", body={"username": "valid"},
                            expected_result={"code": 200}, case_type="正常场景", covered_clause_ids=["REQ-001", "REQ-002"]),
        ]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway, source_type="api_document")
    artifact = db_session.query(AgentArtifact).filter(AgentArtifact.artifact_type == "test_case_set").one()
    ids = [c["candidate_id"] for c in artifact.payload_json["candidates"]]

    response = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": ids})

    assert response.status_code == 200
    rows = db_session.query(APICase).all()
    assert len(rows) == 1
    assert rows[0].source == "llm"
    assert rows[0].method == "POST"
    assert rows[0].body == '{"username": "valid"}'  # JSON 字符串存储
    assert db_session.query(AgentRun).get(run_id).status == "succeeded"


def test_save_empty_or_unknown_candidates_rejected(client, db_session):
    _seed_llm_scenes(db_session)
    gateway = FakeGateway([
        _plan_output(),
        GenerateFunctionCandidatesOutput(candidates=[_fn_candidate("候选A", ["REQ-001", "REQ-002"])]),
    ])
    run_id = _drive_to_save_gate(db_session, client, gateway)

    empty = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": []})
    assert empty.status_code == 422  # Pydantic 校验失败

    unknown = client.post(f"/agent/runs/{run_id}/save-candidates", json={"candidate_ids": ["CASE-999"]})
    assert unknown.status_code == 400
    assert db_session.query(FunctionCase).count() == 0
