"""AgentSession 数据访问 Service。

权限规则（本任务范围）：会话仅 owner 本人可见/操作；admin 绕过留给 T07 Router 层。
事务边界：Service 只 add/flush 不 commit，由调用方（Runner 或测试）控制。
sequence_no 生成方式为 max+1，并发限制已登记开发记录（T04B 前单进程同步使用）。
"""

from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_session import AgentSession
from app.models.api_document import ApiDocument
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.schemas.agent.platform import MESSAGE_ROLES, MESSAGE_TYPES, SESSION_STATUSES

_SOURCE_LABELS = {"requirement": "需求", "api_document": "接口文档"}


def validate_project_for_session(db: Session, project_id: int) -> Project:
    """创建会话前校验项目存在、未删除且处于可用状态。

    外键会作为最终约束保留；这里把“项目不可用”翻译成稳定、可理解的 AgentError，
    避免把 FK IntegrityError 直接暴露成 500。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None or project.is_deleted:
        raise AgentError(
            "项目不存在或已删除，无法创建会话。请先确认所选项目有效。",
            error_code="agent_project_not_found",
        )
    if project.status != "active":
        raise AgentError(
            f"项目状态为“{project.status}”，无法创建会话。请选择状态为 active 的项目。",
            error_code="agent_project_inactive",
        )
    return project


def resolve_session_source(context_json: dict | None) -> tuple[str | None, int | None]:
    """从会话上下文中解析来源类型/ID。

    - 无来源上下文（含 None / 空 dict / 两者均为 None）返回 (None, None)，会话仍合法；
    - 来源形状非法（类型不支持 / source_id 非正整数）抛 agent_invalid_input。
    """
    if not context_json:
        return None, None
    source_type = context_json.get("source_type")
    source_id = context_json.get("source_id")
    if source_type is None and source_id is None:
        return None, None
    if source_type not in _SOURCE_LABELS:
        raise AgentError(f"会话来源类型不合法：{source_type!r}", error_code="agent_invalid_input")
    if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id <= 0:
        raise AgentError("会话来源 ID 不合法，必须是正整数", error_code="agent_invalid_input")
    return source_type, source_id


def validate_session_source(db: Session, project_id: int, source_type: str, source_id: int):
    """来源必须存在、未删除，且其归属项目与请求项目一致（以服务端查询为准）。

    冲突明确拒绝，不静默换项目。无来源上下文的会话不进入本校验。
    """
    label = _SOURCE_LABELS[source_type]
    if source_type == "requirement":
        source = db.query(RequirementDoc).filter(RequirementDoc.id == source_id).first()
    else:
        source = db.query(ApiDocument).filter(ApiDocument.id == source_id).first()
    if source is None or source.is_deleted:
        raise AgentError(
            f"引用的{label}不存在或已删除，无法创建会话。请返回来源页面重新选择后再试。",
            error_code="agent_source_not_found",
        )
    if source.project_id != project_id:
        raise AgentError(
            f"该{label}属于项目 {source.project_id}，与所选项目 {project_id} 不一致，无法创建会话。",
            error_code="agent_source_mismatch",
        )
    return source


def create_session(
    db: Session,
    user_id: int,
    project_id: int,
    title: str,
    context_json: dict | None = None,
    current_skill_code: str | None = None,
    agent_version: str | None = None,
) -> AgentSession:
    validate_project_for_session(db, project_id)
    session = AgentSession(
        project_id=project_id,
        user_id=user_id,
        title=title,
        status="active",
        current_skill_code=current_skill_code,
        agent_version=agent_version,
        context_json=context_json,
    )
    db.add(session)
    db.flush()
    return session


def get_session(db: Session, session_id: int, requester_user_id: int) -> AgentSession:
    """按会话 ID 获取；仅会话 owner 本人可见，否则拒绝。"""
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if not session:
        raise AgentPermissionError(f"会话 {session_id} 不存在或无权访问。")
    if session.user_id != requester_user_id:
        raise AgentPermissionError(f"用户 {requester_user_id} 无权访问会话 {session_id}。")
    return session


def append_message(
    db: Session,
    session: AgentSession,
    role: str,
    content: str | None = None,
    message_type: str = "text",
    content_json: dict | None = None,
    run_id: int | None = None,
    sequence_no: int | None = None,
) -> AgentMessage:
    if role not in MESSAGE_ROLES:
        raise AgentError(f"非法消息角色: {role}", error_code="agent_invalid_message_role")
    if message_type not in MESSAGE_TYPES:
        raise AgentError(f"非法消息类型: {message_type}", error_code="agent_invalid_message_type")
    if sequence_no is None:
        max_no = (
            db.query(AgentMessage.sequence_no)
            .filter(AgentMessage.session_id == session.id)
            .order_by(AgentMessage.sequence_no.desc())
            .first()
        )
        sequence_no = (max_no[0] + 1) if max_no else 1
    message = AgentMessage(
        session_id=session.id,
        run_id=run_id,
        role=role,
        message_type=message_type,
        content=content,
        content_json=content_json,
        sequence_no=sequence_no,
    )
    db.add(message)
    db.flush()
    return message


def close_session(db: Session, session: AgentSession) -> AgentSession:
    """active → closed。"""
    _require_session_status(session, {"active"}, "close")
    session.status = "closed"
    db.flush()
    return session


def archive_session(db: Session, session: AgentSession) -> AgentSession:
    """active/closed → archived。"""
    _require_session_status(session, {"active", "closed"}, "archive")
    session.status = "archived"
    db.flush()
    return session


def _require_session_status(session: AgentSession, allowed: set[str], action: str) -> None:
    if session.status not in allowed:
        raise AgentError(
            f"会话状态为 {session.status}，不允许执行 {action}（要求 {sorted(allowed)}）。",
            error_code="agent_session_status_conflict",
        )


assert set(SESSION_STATUSES) == {"active", "closed", "archived"}
