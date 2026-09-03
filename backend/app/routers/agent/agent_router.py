"""Agent 平台 API：Session/Message/Event、Run、GATE 决议、Artifact 与保存审批。

HTTP 合同：400 业务输入不合法 / 401 未登录（依赖层）/ 403 无权限 / 404 资源不存在 /
409 状态冲突·重复不同请求·来源变化 / 422 Pydantic 校验失败 / 500 内部错误（不返回 Secret/traceback）。

权限：会话级 owner 校验；保存/写操作经 permission_service.require_project_write。
本 Router 不启动 Worker：Run 创建后保持 queued，由 Worker/Runner 显式推进。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentError, AgentPermissionError, InvalidStateTransitionError
from app.core.database import get_db
from app.models.agent.agent_approval import AgentApproval
from app.models.agent.agent_artifact import AgentArtifact
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.agent.api import (
    AgentEventResponse,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentSessionCreate,
    AgentSessionDetailResponse,
    AgentSessionResponse,
    ApprovalResolveRequest,
    ApprovalResponse,
    ArtifactResponse,
    CaseGenerationRunRequest,
    RunResponse,
    SaveCandidatesRequest,
    SaveCandidatesResponse,
    StepResponse,
)
from app.services import agent_save_service
from app.services.agent import (
    agent_approval_service,
    agent_artifact_service,
    agent_run_service,
    agent_session_service,
)
from app.services.permission_service import require_project_write

router = APIRouter(prefix="/agent", tags=["Agent Platform"])

_ERROR_STATUS = {
    "agent_permission_denied": 403,
    "agent_approval_conflict": 409,
    "agent_source_changed": 409,
    "agent_save_not_awaiting": 409,
    "agent_run_not_executable": 409,
    "agent_invalid_state_transition": 409,
    "agent_gate_conflict": 409,
    "agent_source_not_found": 404,
    "agent_project_not_found": 404,
    "agent_project_inactive": 400,
    "agent_source_mismatch": 400,
    "agent_invalid_input": 400,
    "agent_invalid_resolution": 400,
    "agent_unknown_skill": 400,
    "agent_no_valid_candidates": 400,
}


def _http_error(e: AgentError) -> HTTPException:
    status = _ERROR_STATUS.get(e.error_code, 500)
    if status == 500:
        return HTTPException(status_code=500, detail="服务内部错误")
    return HTTPException(status_code=status, detail=str(e))


_GATE_BY_PHASE = {
    "scope_gate": "confirm_case_generation_scope",
    "coverage_gate": "confirm_case_coverage_plan",
    "save_gate": "save_generated_case_candidates",
}


def _expected_gate_for_phase(workflow_state) -> str | None:
    if not isinstance(workflow_state, dict):
        return None
    return _GATE_BY_PHASE.get(workflow_state.get("phase"))


def _require_session(db: Session, session_id: int, user: User) -> AgentSession:
    try:
        return agent_session_service.get_session(db, session_id, user.id)
    except AgentPermissionError:
        raise HTTPException(status_code=404, detail="会话不存在")


def _require_readable_run(db: Session, run_id: int, user: User) -> AgentRun:
    """读取权限：会话 owner 或项目读者（admin/viewer/授权 tester）。"""
    from app.services.permission_service import can_read_project

    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    if session.user_id == user.id:
        return run
    if not can_read_project(db, user, run.project_id):
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run


# ── Session ──


@router.post("/sessions", response_model=AgentSessionResponse, summary="创建 Agent 会话")
def create_session_api(
    data: AgentSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) 项目必须存在、未删除、可用（稳定 4xx，不把 FK 抛成 500）
    try:
        agent_session_service.validate_project_for_session(db, data.project_id)
    except AgentError as e:
        raise _http_error(e)
    # 2) 按项目现有规则校验访问权限：在项目内创建/生成操作需要可操作权限
    require_project_write(db, current_user, data.project_id)
    # 3) 若携带来源上下文，核对来源存在/未删除/归属项目一致
    try:
        source_type, source_id = agent_session_service.resolve_session_source(data.context_json)
        if source_type is not None:
            agent_session_service.validate_session_source(db, data.project_id, source_type, source_id)
    except AgentError as e:
        raise _http_error(e)
    # 4) 保留外键作为最终约束：竞态等导致的引用冲突回滚后给出稳定 409，不留半写入
    try:
        session = agent_session_service.create_session(
            db, user_id=current_user.id, project_id=data.project_id,
            title=data.title, context_json=data.context_json,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="创建会话时数据引用校验失败，请刷新后重试。")
    db.commit()
    return session


@router.get("/sessions", response_model=list[AgentSessionResponse], summary="查询我的会话")
def list_sessions_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(AgentSession)
        .filter(AgentSession.user_id == current_user.id)
        .order_by(AgentSession.id.desc())
        .all()
    )
    return rows


@router.get("/sessions/{session_id}", response_model=AgentSessionDetailResponse, summary="会话详情（含消息）")
def get_session_api(
    session_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _require_session(db, session_id, current_user)
    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session.id)
        .order_by(AgentMessage.sequence_no.asc())
        .limit(limit)
        .all()
    )
    detail = AgentSessionDetailResponse.model_validate(session, from_attributes=True)
    detail.messages = messages
    return detail


@router.get("/sessions/{session_id}/messages", response_model=list[AgentMessageResponse], summary="会话消息（有序）")
def list_messages_api(
    session_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_session(db, session_id, current_user)
    return (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.sequence_no.asc())
        .limit(limit)
        .all()
    )


@router.get("/sessions/{session_id}/events", response_model=list[AgentEventResponse], summary="会话事件（有序）")
def list_events_api(
    session_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_session(db, session_id, current_user)
    return (
        db.query(AgentEvent)
        .filter(AgentEvent.session_id == session_id)
        .order_by(AgentEvent.sequence_no.asc())
        .limit(limit)
        .all()
    )


@router.post("/sessions/{session_id}/messages", response_model=AgentMessageResponse, summary="发送用户消息（可显式启动 Skill Run）")
def create_message_api(
    session_id: int,
    data: AgentMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _require_session(db, session_id, current_user)
    # role 由后端强制为 user，用户不能伪造 assistant/system/tool
    message = agent_session_service.append_message(
        db, session, role="user", content=data.content,
        content_json={"skill_code": data.skill_code} if data.skill_code else None,
    )
    db.commit()
    if data.skill_code:
        if data.source_type is None or data.source_id is None:
            raise HTTPException(status_code=400, detail="启动 Skill Run 需要 source_type 和 source_id")
        _create_case_generation_run(db, session, current_user, data)
        db.commit()
    return message


@router.get("/sessions/{session_id}/runs", response_model=list[RunResponse], summary="会话任务历史")
def list_session_runs_api(
    session_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_session(db, session_id, current_user)
    return db.query(AgentRun).filter(AgentRun.session_id == session_id).order_by(AgentRun.id.desc()).limit(limit).all()


# ── Run ──


def _build_run_input(source_type, source_id, case_types, max_cases, user_goal) -> dict:
    """构建 Run input_json：省略 None 字段，保证幂等比较口径一致。"""
    input_json = {"source_type": source_type, "source_id": source_id}
    if case_types is not None:
        input_json["case_types"] = case_types
    if max_cases is not None:
        input_json["max_cases"] = max_cases
    if user_goal is not None:
        input_json["user_goal"] = user_goal
    return input_json


def _create_case_generation_run(db: Session, session: AgentSession, user: User, data) -> AgentRun:
    try:
        return agent_run_service.create_run(
            db, session, "case_generation", user.id, session.project_id,
            input_json=_build_run_input(
                data.source_type, data.source_id, data.case_types, data.max_cases, data.user_goal
            ),
        )
    except AgentError as e:
        raise _http_error(e)


@router.post("/runs/case-generation", response_model=RunResponse, status_code=202, summary="创建用例生成 Run（不直接执行）")
def create_case_generation_run_api(
    data: CaseGenerationRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _require_session(db, data.session_id, current_user)

    # 来源必须存在且属于 Session 项目
    from app.models.api_document import ApiDocument
    from app.models.requirement_doc import RequirementDoc

    source_project_id = None
    if data.source_type == "requirement":
        source = db.query(RequirementDoc).filter(
            RequirementDoc.id == data.source_id, RequirementDoc.is_deleted == False
        ).first()
        if source is None:
            raise HTTPException(status_code=400, detail="需求文本不存在")
        source_project_id = source.project_id
    else:
        source = db.query(ApiDocument).filter(
            ApiDocument.id == data.source_id, ApiDocument.is_deleted == False
        ).first()
        if source is None:
            raise HTTPException(status_code=400, detail="接口文档不存在")
        source_project_id = source.project_id
    if source_project_id != session.project_id:
        raise HTTPException(status_code=400, detail="来源不属于会话所属项目")

    # 幂等：同 (session, workflow, idempotency_key) 复用同一 Run
    if data.idempotency_key:
        existing = (
            db.query(AgentRun)
            .filter(
                AgentRun.session_id == session.id,
                AgentRun.workflow_code == "case_generation",
                AgentRun.idempotency_key == data.idempotency_key,
            )
            .first()
        )
        if existing:
            new_hash = agent_run_service._canonical_hash(
                _build_run_input(data.source_type, data.source_id, data.case_types, data.max_cases, data.user_goal)
            )
            if existing.input_hash == new_hash:
                return existing  # 相同 payload → 返回同一 Run
            raise HTTPException(status_code=409, detail="idempotency_key 已用于不同的请求")

    run = agent_run_service.create_run(
        db, session, "case_generation", current_user.id, session.project_id,
        input_json=_build_run_input(
            data.source_type, data.source_id, data.case_types, data.max_cases, data.user_goal
        ),
        idempotency_key=data.idempotency_key,
    )
    db.commit()
    return run


@router.get("/runs/{run_id}", response_model=RunResponse, summary="查询 Run")
def get_run_api(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _require_readable_run(db, run_id, current_user)


@router.get("/runs/{run_id}/steps", response_model=list[StepResponse], summary="Run 步骤（脱敏、有序）")
def list_steps_api(
    run_id: int,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_readable_run(db, run_id, current_user)
    from app.models.agent.agent_step import AgentStep

    return (
        db.query(AgentStep)
        .filter(AgentStep.agent_run_id == run_id)
        .order_by(AgentStep.sequence_no.asc())
        .limit(limit)
        .all()
    )


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactResponse], summary="Run 产物列表")
def list_run_artifacts_api(
    run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _require_readable_run(db, run_id, current_user)
    return (
        db.query(AgentArtifact)
        .filter(AgentArtifact.agent_run_id == run_id)
        .order_by(AgentArtifact.id.asc())
        .all()
    )


@router.post("/runs/{run_id}/cancel", response_model=RunResponse, summary="取消 Run")
def cancel_run_api(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = _require_readable_run(db, run_id, current_user)
    _require_session(db, run.session_id, current_user)
    if run.status in ("succeeded", "failed", "cancelled", "interrupted"):
        raise HTTPException(status_code=409, detail=f"Run 状态为 {run.status}，不能取消")
    try:
        if run.status == "queued":
            agent_run_service.transition_status(db, run, "cancelled")
        elif run.status == "running":
            agent_run_service.transition_status(db, run, "cancelled")
        elif run.status == "waiting_approval":
            agent_run_service.transition_status(db, run, "cancelled")
            # 级联取消该 Run 的 pending 审批
            pending = db.query(AgentApproval).filter(
                AgentApproval.agent_run_id == run.id, AgentApproval.status == "pending"
            ).all()
            for approval in pending:
                agent_approval_service.cancel(db, approval, resolved_by_user_id=current_user.id)
        agent_run_service.append_event(db, run.session_id, run.id, "run_cancelled", {})
        agent_run_service.mark_finished_at(db, run)
        db.commit()
    except InvalidStateTransitionError as e:
        raise _http_error(e)
    return run


# ── GATE 决议 ──


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalResponse], summary="Run 审批列表（会话所有者）")
def list_run_approvals_api(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _require_readable_run(db, run_id, current_user)
    _require_session(db, run.session_id, current_user)
    return db.query(AgentApproval).filter(AgentApproval.agent_run_id == run_id).order_by(AgentApproval.id.asc()).all()


@router.post("/approvals/{approval_id}/resolve", response_model=ApprovalResponse, summary="解决 GATE 审批")
def resolve_approval_api(
    approval_id: int,
    data: ApprovalResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if approval is None:
        raise HTTPException(status_code=404, detail="审批不存在")
    session = db.query(AgentSession).filter(AgentSession.id == approval.session_id).first()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有该审批的权限")

    if approval.action_code == "save_generated_case_candidates" and data.status == "approved":
        raise HTTPException(status_code=409, detail="保存审批请通过 save-candidates 接口选择候选并完成保存")

    if approval.status != "pending":
        previous_status = approval.status
        previous_resolution = approval.resolution_json
        # 幂等：重复相同决议返回 200，不重复事件
        if previous_status == data.status and previous_resolution == (data.resolution_json or {}):
            return approval
        raise HTTPException(status_code=409, detail=f"审批已处理（{previous_status}）")

    run = db.query(AgentRun).filter(AgentRun.id == approval.agent_run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    if run.status != "waiting_approval":
        # 非当前 Approval 不能推进 Run
        raise HTTPException(status_code=409, detail=f"Run 状态为 {run.status}，非当前审批不能推进")

    # 审批必须是 Run 当前 GATE 对应的审批（按 workflow_state.phase 判定）
    expected_gate = _expected_gate_for_phase((run.output_json or {}).get("workflow_state"))
    if expected_gate is not None and approval.action_code != expected_gate:
        raise HTTPException(status_code=409, detail=f"审批 {approval.action_code} 不是 Run 当前 GATE（{expected_gate}）")

    try:
        if data.status == "approved":
            agent_approval_service.approve(
                db, approval, resolved_by_user_id=current_user.id,
                resolution_json=data.resolution_json or {},
            )
            # waiting_approval → queued：交回 Worker 继续执行
            agent_run_service.transition_status(db, run, "queued")
            agent_run_service.append_event(
                db, run.session_id, run.id, "approval_approved",
                {"approval_id": approval.id, "action_code": approval.action_code},
            )
        else:
            agent_approval_service.reject(
                db, approval, resolved_by_user_id=current_user.id,
                resolution_json=data.resolution_json or {},
            )
            # rejected → cancelled（不是 failed）
            agent_run_service.transition_status(db, run, "cancelled")
            agent_run_service.mark_finished_at(db, run)
            agent_run_service.append_event(
                db, run.session_id, run.id, "approval_rejected",
                {"approval_id": approval.id, "action_code": approval.action_code},
            )
        db.commit()
    except (AgentError, InvalidStateTransitionError) as e:
        db.rollback()
        raise _http_error(e)
    return approval


# ── Artifact ──


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse, summary="查询 Artifact")
def get_artifact_api(
    artifact_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    try:
        return agent_artifact_service.get_artifact(db, artifact_id, current_user.id)
    except AgentPermissionError:
        raise HTTPException(status_code=404, detail="产物不存在")


# ── 保存候选 ──


@router.post("/runs/{run_id}/save-candidates", response_model=SaveCandidatesResponse, summary="保存勾选的候选")
def save_candidates_api(
    run_id: int,
    data: SaveCandidatesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _require_readable_run(db, run_id, current_user)
    require_project_write(db, current_user, run.project_id)
    try:
        result = agent_save_service.save_candidates(db, run, data.candidate_ids, current_user.id)
    except (AgentError, InvalidStateTransitionError) as e:
        db.rollback()
        raise _http_error(e)
    except HTTPException:
        raise
    except Exception:
        # 未预期异常：回滚并返回安全 500（不返回 Secret/traceback）
        db.rollback()
        raise HTTPException(status_code=500, detail="服务内部错误")
    return result
