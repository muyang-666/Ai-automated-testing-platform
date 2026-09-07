"""Database primitives for V2-P04 conversation persistence.

No function commits. Sequence allocation increments the session row before
reading the reserved value, so the database write lock serializes connections.
"""
from sqlalchemy import and_, or_, select, update
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


def list_run_visible_message_rows(db: Session, session_id: int,
                                  until_sequence_no: int) -> list[AgentMessage]:
    """run-bounded 可见消息（P10.1-B3：owner 边界下推到 SQL，不在 Python 过滤未来消息）。

    可见集合 = 逻辑序前缀 { owner user sequence <= until_sequence_no }：
    - user 行按自身 sequence_no 归属（<= until 才可见）；
    - assistant/toolResult 行按所属 Run 的 user_message_id 归属：Run 的用户
      消息 seq <= until 的 Run 产出的行全部可见——即使其物理 sequence_no 大于
      until（例如 Turn A 执行期间入队的 B/C 用户消息先落库、A 的助手消息后落库：
      对 B 而言 A 的助手行物理 seq 更大，但 owner=A 的 user seq <= until_B，可见）。

    返回按 (owner user sequence, sequence_no) 逻辑序升序排列的行；调用方把
    该序的位置（1-based rank）作为摘要 marker/增量选择的逻辑键。
    """
    # 1) 会话内 user 行中 seq <= until 的部分（其 id 集合定义可见 Run 边界）
    user_rows = db.execute(
        select(AgentMessage.id, AgentMessage.sequence_no).where(
            AgentMessage.session_id == session_id,
            AgentMessage.role == "user",
            AgentMessage.sequence_no <= until_sequence_no,
        )
    ).all()
    if not user_rows:
        return []
    user_seq_by_id = {row_id: seq for row_id, seq in user_rows}
    visible_user_ids = set(user_seq_by_id)
    # 2) 这些用户行所属的 Run
    run_rows = db.execute(
        select(AgentRun.id, AgentRun.user_message_id).where(
            AgentRun.session_id == session_id,
            AgentRun.user_message_id.in_(visible_user_ids),
        )
    ).all()
    user_seq_by_run_id = {
        run_id: user_seq_by_id[user_message_id]
        for run_id, user_message_id in run_rows if user_message_id in user_seq_by_id}
    # 3) SQL 侧取回可见行：user 行（id ∈ visible）∪ 上述 Run 产出的非 user 行
    rows = db.execute(
        select(AgentMessage).where(
            AgentMessage.session_id == session_id,
            or_(
                and_(AgentMessage.role == "user", AgentMessage.id.in_(visible_user_ids)),
                and_(AgentMessage.role != "user", AgentMessage.run_id.in_(user_seq_by_run_id)),
            ),
        )
    ).scalars().all()
    ordered = sorted(
        rows,
        key=lambda row: (user_seq_by_id.get(row.id, user_seq_by_run_id.get(row.run_id, row.sequence_no)),
                         row.sequence_no),
    )
    return list(ordered)
