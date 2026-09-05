"""V2-P04 application service for private conversation sessions and turns."""
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.agents.conversation.messages import Message, UserMessage, parse_message
from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.services.agent import agent_run_service, agent_session_service, conversation_repository


class ConversationConflict(AgentError):
    error_code = "conversation_conflict"


class ConversationDataError(AgentError):
    error_code = "conversation_data_invalid"


@dataclass(frozen=True)
class ConversationTurnSubmission:
    run: AgentRun
    user_message: AgentMessage
    replayed: bool


def create_conversation_session(db: Session, *, requester_user_id: int, title: str,
                                project_id: int | None = None,
                                context_json: dict | None = None) -> AgentSession:
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ConversationDataError("会话标题无效")
    if project_id is not None:
        agent_session_service.validate_project_for_session(db, project_id)
    session = AgentSession(project_id=project_id, user_id=requester_user_id,
        mode="conversation", title=title.strip(), status="active",
        context_json=context_json, next_message_sequence=1, next_event_sequence=1)
    db.add(session)
    db.flush()
    return session


def _owned_conversation(db: Session, session_id: int, requester_user_id: int,
                        *, require_active: bool = True) -> AgentSession:
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if session is None or session.user_id != requester_user_id:
        raise AgentPermissionError("会话不存在或无权访问")
    if session.mode != "conversation":
        raise ConversationConflict("该会话不是 conversation 模式")
    if require_active and session.status != "active":
        raise ConversationConflict("会话当前不可提交新消息")
    return session


def _request_hash(content: str) -> str:
    return agent_run_service._canonical_hash({"content": content})


def _existing_submission(db: Session, run: AgentRun, request_hash: str) -> ConversationTurnSubmission:
    if run.input_hash != request_hash:
        raise ConversationConflict("client_request_id 已用于不同请求")
    if run.user_message_id is None:
        raise ConversationDataError("幂等记录缺少用户消息关联")
    message = db.query(AgentMessage).filter(
        AgentMessage.id == run.user_message_id,
        AgentMessage.session_id == run.session_id,
    ).first()
    if message is None:
        raise ConversationDataError("幂等记录关联的用户消息不存在")
    return ConversationTurnSubmission(run=run, user_message=message, replayed=True)


def submit_conversation_turn(db: Session, *, session_id: int, requester_user_id: int,
                             content: str, client_request_id: str,
                             queue_mode: str = "reject",
                             message_id_factory: Callable[[], str] | None = None,
                             timestamp_ms_factory: Callable[[], int] | None = None) -> ConversationTurnSubmission:
    """Atomically save user message, queued Run and the idempotency key.

    queue_mode（P05-E）：
    - reject（默认，P04 语义）：会话已有活跃 Turn 时抛 conversation_conflict；
    - follow_up：活跃 Turn 存在时把新消息保存为 queued follow-up
      （UserMessage + AgentRun，active_slot=NULL），等当前 head 终态后由
      promote_next_conversation_run 原子提升。
    幂等合同不变：同 key 同内容 → replay；同 key 不同内容 → conflict。
    """
    if queue_mode not in {"reject", "follow_up"}:
        raise ConversationDataError("queue_mode 必须是 reject 或 follow_up")
    if not isinstance(content, str) or not content.strip() or len(content) > 8000:
        raise ConversationDataError("消息内容无效")
    if not isinstance(client_request_id, str) or not client_request_id.strip() or len(client_request_id) > 128:
        raise ConversationDataError("client_request_id 无效")
    key, request_hash = client_request_id.strip(), _request_hash(content)
    make_id = message_id_factory or (lambda: uuid.uuid4().hex)
    make_timestamp = timestamp_ms_factory or (lambda: int(time.time() * 1000))

    for attempt in range(3):
        try:
            session = _owned_conversation(db, session_id, requester_user_id)
            existing = conversation_repository.find_idempotent_run(db, session.id, key)
            if existing is not None:
                return _existing_submission(db, existing, request_hash)
            active = conversation_repository.find_active_conversation_run(db, session.id)
            if active is not None:
                # Another transaction may have committed between the first
                # idempotency lookup and the active-slot lookup.
                existing = conversation_repository.find_idempotent_run(db, session.id, key)
                if existing is not None:
                    return _existing_submission(db, existing, request_hash)
                if queue_mode == "reject":
                    raise ConversationConflict("会话已有正在处理的 Turn")
                # follow_up：head 运行期间入队，active_slot 留空，等待原子提升
                return _persist_follow_up(db, session, requester_user_id, content, key,
                                          request_hash, make_id, make_timestamp)

            message = UserMessage(message_id=make_id(), timestamp=make_timestamp(),
                                  role="user", content=content)
            sequence = conversation_repository.allocate_sequence(db, session.id, "next_message_sequence")
            row = AgentMessage(session_id=session.id, run_id=None,
                message_id=message.message_id, schema_version=message.schema_version,
                timestamp_ms=message.timestamp, role=message.role, message_type="text",
                content=content, content_json=message.model_dump(mode="json"), sequence_no=sequence)
            db.add(row)
            db.flush()
            run = agent_run_service.create_run(db, session, "conversation", requester_user_id,
                session.project_id, input_json={"content": content}, idempotency_key=key,
                user_message_id=row.id, active_slot=1)
            row.run_id = run.id
            db.flush()
            db.commit()
            return ConversationTurnSubmission(run=run, user_message=row, replayed=False)
        except ConversationConflict:
            db.rollback()
            raise
        except (IntegrityError, OperationalError):
            db.rollback()
            existing = conversation_repository.find_idempotent_run(db, session_id, key)
            if existing is not None:
                return _existing_submission(db, existing, request_hash)
            if conversation_repository.find_active_conversation_run(db, session_id) is not None:
                raise ConversationConflict("会话已有正在处理的 Turn")
            if attempt == 2:
                raise ConversationConflict("并发提交冲突，请重试")
        except Exception:
            db.rollback()
            raise
    raise ConversationConflict("并发提交冲突，请重试")  # pragma: no cover


def _persist_follow_up(db: Session, session: AgentSession, requester_user_id: int,
                       content: str, key: str, request_hash: str,
                       make_id: Callable[[], str],
                       make_timestamp: Callable[[], int]) -> ConversationTurnSubmission:
    """follow_up 路径：UserMessage + queued Run（active_slot=NULL）同事务落库。"""
    message = UserMessage(message_id=make_id(), timestamp=make_timestamp(),
                          role="user", content=content)
    sequence = conversation_repository.allocate_sequence(db, session.id, "next_message_sequence")
    row = AgentMessage(session_id=session.id, run_id=None,
        message_id=message.message_id, schema_version=message.schema_version,
        timestamp_ms=message.timestamp, role=message.role, message_type="text",
        content=content, content_json=message.model_dump(mode="json"), sequence_no=sequence)
    db.add(row)
    db.flush()
    run = agent_run_service.create_run(db, session, "conversation", requester_user_id,
        session.project_id, input_json={"content": content}, idempotency_key=key,
        user_message_id=row.id, active_slot=None)  # queued follow-up：不可执行
    row.run_id = run.id
    db.flush()
    db.commit()
    return ConversationTurnSubmission(run=run, user_message=row, replayed=False)


def promote_next_conversation_run(db: Session, session_id: int) -> int | None:
    """原子提升最早 queued follow-up 为可执行 head（active_slot: NULL → 1）。

    并发裁决：UQ(session_id, active_slot) 保证同会话最多一个 active_slot=1；
    两个并发 promotion 命中同候选时只有先到者满足 active_slot IS NULL 条件；
    命中不同候选时后到者触发唯一约束 → 回滚返回 None（调用方可重试）。
    """
    # Pause 语义：最新一个已终结的 head 若为 failed/interrupted，后续 follow-up
    # 不提升（pause），等 P06 UI 向用户解释；succeeded/cancelled 则继续。
    latest_terminal = db.execute(
        select(AgentRun.status)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.workflow_code == "conversation",
            AgentRun.status.in_(["succeeded", "failed", "cancelled", "interrupted"]),
        )
        .order_by(AgentRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_terminal in {"failed", "interrupted"}:
        return None

    candidate = db.execute(
        select(AgentRun.id)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.workflow_code == "conversation",
            AgentRun.status == "queued",
            AgentRun.active_slot.is_(None),
        )
        .order_by(AgentRun.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if candidate is None:
        return None
    try:
        result = db.execute(
            update(AgentRun)
            .where(AgentRun.id == candidate,
                   AgentRun.status == "queued",
                   AgentRun.active_slot.is_(None))
            .values(active_slot=1)
            .execution_options(synchronize_session=False)
        )
        return candidate if result.rowcount == 1 else None
    except IntegrityError:
        db.rollback()
        return None




# ─────────────────────────── P06 snapshot / read helpers ───────────────────────────

def list_conversations_for_user(db: Session, requester_user_id: int) -> list[AgentSession]:
    return list(db.query(AgentSession).filter(
        AgentSession.user_id == requester_user_id,
        AgentSession.mode == "conversation",
    ).order_by(AgentSession.id.desc()).all())


def conversation_snapshot(db: Session, *, session_id: int,
                          requester_user_id: int) -> dict:
    """P06 会话快照：元数据 + 当前 run + queue 状态 + 最新游标。不带消息正文。"""
    from sqlalchemy import func as sa_func
    session = _owned_conversation(db, session_id, requester_user_id, require_active=False)
    head = db.execute(
        select(AgentRun).where(
            AgentRun.session_id == session.id,
            AgentRun.workflow_code == "conversation",
            AgentRun.active_slot == 1,
        ).order_by(AgentRun.id.desc())
    ).scalar_one_or_none()
    latest_run = db.execute(
        select(AgentRun).where(
            AgentRun.session_id == session.id,
            AgentRun.workflow_code == "conversation",
        ).order_by(AgentRun.id.desc()).limit(1)
    ).scalar_one_or_none()
    queue = conversation_queue_state(db, session.id)
    latest_event = db.execute(
        select(sa_func.max(AgentEvent.sequence_no)).where(
            AgentEvent.session_id == session.id)).scalar_one_or_none() or 0
    latest_message = db.execute(
        select(sa_func.max(AgentMessage.sequence_no)).where(
            AgentMessage.session_id == session.id)).scalar_one_or_none() or 0
    return {
        "conversation": {
            "id": session.id,
            "title": session.title,
            "project_id": session.project_id,
            "status": session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        },
        "active_run": ({
            "id": head.id, "status": head.status, "workflow_code": head.workflow_code,
            "error_code": head.error_code,
        } if head is not None else None),
        "latest_run": ({
            "id": latest_run.id,
            "status": latest_run.status,
            "error_code": latest_run.error_code,
        } if latest_run is not None else None),
        "queue_state": queue["state"],
        "head_status": queue["head_status"],
        "queued_follow_ups": queue["queued_follow_ups"],
        "latest_event_sequence": int(latest_event),
        "latest_message_sequence": int(latest_message),
    }


def list_messages_since(db: Session, *, session_id: int, requester_user_id: int,
                        after_sequence: int | None = None,
                        limit: int = 200) -> list[AgentMessage]:
    """按 sequence_no 升序的消息分页（P06 前端/恢复用）。"""
    _owned_conversation(db, session_id, requester_user_id, require_active=False)
    statement = db.query(AgentMessage).filter(AgentMessage.session_id == session_id)
    if after_sequence is not None:
        statement = statement.filter(AgentMessage.sequence_no > after_sequence)
    return list(statement.order_by(AgentMessage.sequence_no.asc()).limit(limit).all())


def list_events_since(db: Session, *, session_id: int, requester_user_id: int,
                      after_sequence: int | None = None,
                      limit: int = 500) -> list[AgentEvent]:
    _owned_conversation(db, session_id, requester_user_id, require_active=False)
    statement = db.query(AgentEvent).filter(AgentEvent.session_id == session_id)
    if after_sequence is not None:
        statement = statement.filter(AgentEvent.sequence_no > after_sequence)
    return list(statement.order_by(AgentEvent.sequence_no.asc()).limit(limit).all())

def cancel_conversation_run(db: Session, *, run_id: int,
                            requester_user_id: int) -> AgentRun:
    """P06 conversation 取消（单一应用边界，含原子 promote）。

    语义：
    - head（active_slot=1，queued 或 running）→ cancelled + run_cancelled 事件
      + 同事务 promote 下一个 queued follow-up（queued head 在 Worker claim 前
      被取消时，B 不会永远留在 NULL slot）；
    - queued follow-up（active_slot=NULL）→ 仅取消自身，不触发 promote
      （当前 head A 若仍在，不得错误提升 C）；
    - 非 conversation Run / 非 owner / 已终态 → 相应错误。
    """
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        raise AgentError(f"Run {run_id} 不存在", error_code="agent_run_not_found")
    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session is None or session.user_id != requester_user_id:
        raise AgentPermissionError("会话不存在或无权访问")
    if run.workflow_code != "conversation":
        raise AgentError("该接口只支持 conversation Run", error_code="agent_run_not_conversation")
    if run.status in {"succeeded", "failed", "cancelled", "interrupted"}:
        raise AgentError("Run 已终态，无需取消", error_code="agent_run_not_startable")
    was_head = run.active_slot == 1
    agent_run_service.transition_status(db, run, "cancelled")
    agent_run_service.append_event(db, run.session_id, run.id, "run_cancelled", {})
    if was_head:
        promote_next_conversation_run(db, run.session_id)
    db.commit()
    return run

def conversation_queue_state(db: Session, session_id: int) -> dict:
    """派生队列状态（P06 前端展示用，不新增 DB status）。

    state：executable（head 可执行/执行中）/ paused（最近 head 失败或中断且仍有
    follow-up）/ idle（无 head）；另给 head_status 与 queued_follow_ups 计数。
    """
    from sqlalchemy import func as sa_func
    head = db.execute(
        select(AgentRun).where(
            AgentRun.session_id == session_id,
            AgentRun.workflow_code == "conversation",
            AgentRun.active_slot == 1,
        )
    ).scalar_one_or_none()
    queued_follow_ups = db.execute(
        select(sa_func.count()).select_from(AgentRun).where(
            AgentRun.session_id == session_id,
            AgentRun.workflow_code == "conversation",
            AgentRun.status == "queued",
            AgentRun.active_slot.is_(None),
        )
    ).scalar_one() or 0
    latest_terminal = db.execute(
        select(AgentRun.status)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.workflow_code == "conversation",
            AgentRun.status.in_(["succeeded", "failed", "cancelled", "interrupted"]),
        )
        .order_by(AgentRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if head is None:
        # 无 head：最新终结的 head 失败/中断且有 follow-up → paused；否则 idle
        state = ("paused" if latest_terminal in {"failed", "interrupted"}
                 and queued_follow_ups else "idle")
        return {"state": state, "head_status": latest_terminal,
                "queued_follow_ups": queued_follow_ups}
    if head.status in {"failed", "interrupted"}:
        state = "paused" if queued_follow_ups else "idle"
    else:
        state = "executable"
    return {"state": state, "head_status": head.status,
            "queued_follow_ups": queued_follow_ups}


def persist_conversation_messages(db: Session, *, session_id: int,
                                  requester_user_id: int, run_id: int,
                                  messages: list[Message],
                                  commit: bool = True) -> list[AgentMessage]:
    """Persist assistant/tool messages.

    ``commit=False`` lets ConversationRunner include messages, committed
    events and the Run terminal transition in one fenced transaction.  Other
    application callers keep the historical self-committing behaviour.
    """
    session = _owned_conversation(db, session_id, requester_user_id)
    run = db.query(AgentRun).filter(AgentRun.id == run_id,
                                    AgentRun.session_id == session.id).first()
    if run is None or run.workflow_code != "conversation":
        raise ConversationConflict("Run 不属于该 conversation 会话")
    rows: list[AgentMessage] = []
    try:
        for message in messages:
            if isinstance(message, UserMessage):
                raise ConversationDataError("该入口不重复写入用户首消息")
            sequence = conversation_repository.allocate_sequence(db, session.id, "next_message_sequence")
            row = AgentMessage(session_id=session.id, run_id=run.id,
                message_id=message.message_id, schema_version=message.schema_version,
                timestamp_ms=message.timestamp, role=message.role, message_type="text",
                content="".join(getattr(block, "text", "") for block in message.content) or None,
                content_json=message.model_dump(mode="json"), sequence_no=sequence)
            db.add(row)
            db.flush()
            rows.append(row)
        if commit:
            db.commit()
        return rows
    except Exception:
        db.rollback()
        raise


def restore_conversation_messages(db: Session, *, session_id: int,
                                  requester_user_id: int,
                                  until_sequence_no: int | None = None) -> list[Message]:
    """恢复历史消息（P05-E run-bounded）。

    默认（until_sequence_no=None）：按 sequence_no 全量升序（P04 语义）。
    提供 until_sequence_no 时：当前 Run 只能看到"自己 Turn 及其之前 Turn"产出的
    消息——每条消息按其所属 Turn 的用户消息序号（owner sequence）归组，只保留
    owner <= until 的行，并按 (owner, sequence_no) 逻辑排序。这样 A 执行期间
    已入库的 B/C 用户消息（seq 更大）不会泄漏给 A，而 A 的助手消息即使晚于
    B/C 的用户消息落库（seq 更大），也因其 owner(1) <= A 的直到序号而被 A 看到。
    """
    _owned_conversation(db, session_id, requester_user_id, require_active=False)
    rows = conversation_repository.list_message_rows(db, session_id)
    if until_sequence_no is not None:
        rows = _visible_rows_by_turn(db, session_id, rows, until_sequence_no)
    restored: list[Message] = []
    for row in rows:
        if not isinstance(row.content_json, dict):
            raise ConversationDataError("会话消息缺少版本化内容")
        try:
            message = parse_message(row.content_json)
        except Exception:
            raise ConversationDataError("会话消息合同无效") from None
        if row.message_id != message.message_id or row.schema_version != message.schema_version:
            raise ConversationDataError("会话消息标识或版本不一致")
        restored.append(message)
    return restored


def _visible_rows_by_turn(db: Session, session_id: int, rows: list,
                          until_sequence_no: int) -> list:
    """按消息所属 Turn（user message sequence）过滤并逻辑排序（见 restore 注释）。"""
    user_seq_by_row_id = {row.id: row.sequence_no for row in rows if row.role == "user"}
    run_ids = {row.run_id for row in rows if row.run_id is not None}
    user_seq_by_run_id: dict[int, int] = {}
    if run_ids:
        run_rows = db.execute(
            select(AgentRun.id, AgentRun.user_message_id).where(AgentRun.id.in_(run_ids))
        ).all()
        msg_rows = db.execute(
            select(AgentMessage.id, AgentMessage.sequence_no).where(
                AgentMessage.id.in_([row.user_message_id for row in run_rows
                                     if row.user_message_id is not None]))
        ).all()
        seq_by_message_id = {row_id: seq for row_id, seq in msg_rows}
        user_seq_by_run_id = {run_id: seq_by_message_id[user_message_id]
                              for run_id, user_message_id in run_rows
                              if user_message_id in seq_by_message_id}
    visible = []
    for row in rows:
        if row.role == "user":
            owner = user_seq_by_row_id.get(row.id, row.sequence_no)
        else:
            owner = user_seq_by_run_id.get(row.run_id)
            if owner is None:
                continue  # 孤儿/旧数据：不进入 run-bounded 上下文
        if owner <= until_sequence_no:
            visible.append((owner, row.sequence_no, row))
    visible.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in visible]
