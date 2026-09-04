"""Database primitives for V2-P04 conversation persistence.

No function commits. Sequence allocation increments the session row before
reading the reserved value, so the database write lock serializes connections.
"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession


class SequenceAllocationConflict(RuntimeError):
    pass


def allocate_sequence(db: Session, session_id: int, column_name: str) -> int:
    if column_name not in {"next_message_sequence", "next_event_sequence"}:
        raise ValueError("unsupported sequence column")
    column = getattr(AgentSession, column_name)
    result = db.execute(
        update(AgentSession)
        .where(AgentSession.id == session_id)
        .values({column_name: column + 1})
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise SequenceAllocationConflict("session missing")
    next_value = db.execute(select(column).where(AgentSession.id == session_id)).scalar_one()
    return next_value - 1


def find_idempotent_run(db: Session, session_id: int, client_request_id: str) -> AgentRun | None:
    return db.execute(select(AgentRun).where(
        AgentRun.session_id == session_id,
        AgentRun.workflow_code == "conversation",
        AgentRun.idempotency_key == client_request_id,
    )).scalar_one_or_none()


def find_active_conversation_run(db: Session, session_id: int) -> AgentRun | None:
    return db.execute(select(AgentRun).where(
        AgentRun.session_id == session_id,
        AgentRun.workflow_code == "conversation",
        AgentRun.active_slot == 1,
    )).scalar_one_or_none()


def list_message_rows(db: Session, session_id: int,
                      until_sequence_no: int | None = None) -> list[AgentMessage]:
    """会话消息（按 sequence_no 升序）；可截断到某 Turn 的用户消息序号之前（含）。

    P05-E run-bounded restore：执行中的 Turn A 只能看到截至自己 user message 的历史，
    后续 follow-up（seq 更大）即使已入库也不可见。
    """
    statement = select(AgentMessage).where(AgentMessage.session_id == session_id)
    if until_sequence_no is not None:
        statement = statement.where(AgentMessage.sequence_no <= until_sequence_no)
    statement = statement.order_by(AgentMessage.sequence_no.asc())
    return list(db.execute(statement).scalars())
