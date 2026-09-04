"""V2-P04 application service for private conversation sessions and turns."""
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.agents.conversation.messages import Message, UserMessage, parse_message
from app.agents.runtime.errors import AgentError, AgentPermissionError
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
                             message_id_factory: Callable[[], str] | None = None,
                             timestamp_ms_factory: Callable[[], int] | None = None) -> ConversationTurnSubmission:
    """Atomically save user message, queued Run and the idempotency key."""
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
            if conversation_repository.find_active_conversation_run(db, session.id) is not None:
                # Another transaction may have committed between the first
                # idempotency lookup and the active-slot lookup.
                existing = conversation_repository.find_idempotent_run(db, session.id, key)
                if existing is not None:
                    return _existing_submission(db, existing, request_hash)
                raise ConversationConflict("会话已有正在处理的 Turn")

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


def persist_conversation_messages(db: Session, *, session_id: int,
                                  requester_user_id: int, run_id: int,
                                  messages: list[Message]) -> list[AgentMessage]:
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
        db.commit()
        return rows
    except Exception:
        db.rollback()
        raise


def restore_conversation_messages(db: Session, *, session_id: int,
                                  requester_user_id: int) -> list[Message]:
    _owned_conversation(db, session_id, requester_user_id, require_active=False)
    restored: list[Message] = []
    for row in conversation_repository.list_message_rows(db, session_id):
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
