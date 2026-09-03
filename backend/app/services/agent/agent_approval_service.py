"""AgentApproval 数据访问 Service。

- 只有 pending 的审批可以被解决（approve/reject/cancel/expire）；
- resolved_by_user_id 必须与审批所属会话 owner 一致；
- 本任务不执行被批准的业务动作（保存/重跑等留给 T05/T07）；
- 事务边界：Service 只 add/flush 不 commit，由调用方控制。
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentApprovalConflictError, AgentPermissionError
from app.models.agent.agent_approval import AgentApproval
from app.models.agent.agent_session import AgentSession
from app.schemas.agent.platform import APPROVAL_STATUSES


def request_approval(
    db: Session,
    session_id: int,
    agent_run_id: int,
    action_code: str,
    request_json: dict | None = None,
    artifact_id: int | None = None,
    expires_at: datetime | None = None,
) -> AgentApproval:
    approval = AgentApproval(
        session_id=session_id,
        agent_run_id=agent_run_id,
        artifact_id=artifact_id,
        action_code=action_code,
        status="pending",
        request_json=request_json,
        expires_at=expires_at,
    )
    db.add(approval)
    db.flush()
    return approval


def get_approval(db: Session, approval_id: int, requester_user_id: int) -> AgentApproval:
    approval = db.query(AgentApproval).filter(AgentApproval.id == approval_id).first()
    if not approval:
        raise AgentPermissionError(f"审批 {approval_id} 不存在或无权访问。")
    _require_session_owner(db, approval.session_id, requester_user_id, f"审批 {approval_id}")
    return approval


def find_approval_by_action(db: Session, run_id: int, action_code: str) -> AgentApproval | None:
    """按 (run_id, action_code) 查询现有审批；GATE 恢复时用于避免重复创建。"""
    return (
        db.query(AgentApproval)
        .filter(AgentApproval.agent_run_id == run_id, AgentApproval.action_code == action_code)
        .order_by(AgentApproval.id.asc())
        .first()
    )


def resolve_approval(
    db: Session,
    approval: AgentApproval,
    status: str,
    resolved_by_user_id: int,
    resolution_json: dict | None = None,
) -> AgentApproval:
    """解决审批；仅 pending 可解决，解决人必须与会话 owner 一致。"""
    if status not in APPROVAL_STATUSES or status == "pending":
        raise AgentApprovalConflictError(f"非法审批状态: {status}")
    if approval.status != "pending":
        raise AgentApprovalConflictError(
            f"审批 {approval.id} 当前状态为 {approval.status}，只有 pending 可以被解决。"
        )
    _require_session_owner(db, approval.session_id, resolved_by_user_id, f"审批 {approval.id}")
    approval.status = status
    approval.resolved_at = datetime.utcnow()
    approval.resolved_by_user_id = resolved_by_user_id
    approval.resolution_json = resolution_json
    db.flush()
    return approval


def approve(db: Session, approval: AgentApproval, resolved_by_user_id: int, resolution_json: dict | None = None) -> AgentApproval:
    return resolve_approval(db, approval, "approved", resolved_by_user_id, resolution_json)


def reject(db: Session, approval: AgentApproval, resolved_by_user_id: int, resolution_json: dict | None = None) -> AgentApproval:
    return resolve_approval(db, approval, "rejected", resolved_by_user_id, resolution_json)


def cancel(db: Session, approval: AgentApproval, resolved_by_user_id: int, resolution_json: dict | None = None) -> AgentApproval:
    return resolve_approval(db, approval, "cancelled", resolved_by_user_id, resolution_json)


def expire(db: Session, approval: AgentApproval, resolution_json: dict | None = None) -> AgentApproval:
    """过期处理不需要人工解决人（系统动作），但同样只能作用于 pending。"""
    if approval.status != "pending":
        raise AgentApprovalConflictError(
            f"审批 {approval.id} 当前状态为 {approval.status}，只有 pending 可以被解决。"
        )
    approval.status = "expired"
    approval.resolved_at = datetime.utcnow()
    approval.resolution_json = resolution_json
    db.flush()
    return approval


def _require_session_owner(db: Session, session_id: int, user_id: int, subject: str) -> None:
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if not session or session.user_id != user_id:
        raise AgentPermissionError(f"用户 {user_id} 无权处理 {subject}（非会话 owner）。")
