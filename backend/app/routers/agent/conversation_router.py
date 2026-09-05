"""P06 Conversation API：创建/列表/详情/消息/Turn/取消/能力 + SSE 事件流。

HTTP 合同沿用 Agent 平台风格：401 未登录 / 403-404 越权与不存在 / 409 状态冲突 /
422 校验失败 / 503 configuration_not_ready。SSE：Bearer 由统一鉴权依赖承担，
Token 不进 URL；事件游标可断线续传（客户端带 after_sequence），DB 是唯一真相。
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentError
from app.core.database import SessionLocal, get_db
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.agent.conversation_api import (
    CancelConversationRunResponse,
    ConversationCapabilities,
    ConversationUpdateRequest,
    ConversationCreateRequest,
    ConversationEventItem,
    ConversationMessageItem,
    ConversationSnapshot,
    ConversationSummary,
    TurnSubmitRequest,
    TurnSubmitResponse,
)
from app.services.agent import conversation_service
from app.services.agent.conversation_provider import CHAT_SCENE_CODE, is_conversation_model_ready
from app.services.agent.conversation_service import (
    cancel_conversation_run,
    conversation_snapshot,
    list_conversations_for_user,
    list_events_since,
    list_messages_since,
    submit_conversation_turn,
)

router = APIRouter(prefix="/agent", tags=["Conversation Agent"])

_ERROR_STATUS = {
    "agent_permission_denied": 403,
    "agent_run_not_found": 404,
    "agent_run_not_conversation": 400,
    "agent_run_not_startable": 409,
    "agent_run_data_invalid": 409,
    "agent_session_mode_mismatch": 400,
    "conversation_conflict": 409,
    "conversation_data_invalid": 400,
    "configuration_not_ready": 503,
    "agent_invalid_state_transition": 409,
}


def _http_error(e: AgentError) -> HTTPException:
    status = _ERROR_STATUS.get(getattr(e, "error_code", "") or "", 500)
    if status == 500:
        return HTTPException(status_code=500, detail="服务内部错误")
    return HTTPException(status_code=status, detail=str(e))


def _require_conversation_run(db: Session, run_id: int, user: User):
    from app.models.agent.agent_run import AgentRun
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None or run.workflow_code != "conversation":
        raise HTTPException(status_code=404, detail="Run 不存在")
    _require_conversation(db, run.session_id, user)
    return run


def _require_conversation(db: Session, conversation_id: int, user: User) -> AgentSession:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is None or row.user_id != user.id or row.mode != "conversation":
        raise HTTPException(status_code=404, detail="Conversation 不存在")
    return row


def _message_item(row, run_errors: dict | None = None) -> dict:
    content = None
    if isinstance(row.content_json, dict):
        content = row.content_json.get("content")
    elif row.content is not None:
        content = row.content
    return {
        "id": row.id,
        "message_id": row.message_id,
        "role": row.role,
        "sequence_no": row.sequence_no,
        "timestamp_ms": row.timestamp_ms,
        "content": content,
        "run_id": row.run_id,
        "stop_reason": (row.content_json.get("stop_reason")
                        if isinstance(row.content_json, dict) else None),
        "error_code": (run_errors or {}).get(row.run_id),
    }


def _event_item(row: AgentEvent) -> dict:
    return {"sequence_no": row.sequence_no, "event_type": row.event_type,
            "run_id": row.run_id, "payload": row.payload_json,
            "created_at": row.created_at}


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
def create_conversation(payload: ConversationCreateRequest, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    try:
        session = conversation_service.create_conversation_session(
            db, requester_user_id=current_user.id, title=payload.title,
            project_id=payload.project_id)
        db.commit()
    except AgentError as e:
        raise _http_error(e)
    return ConversationSummary(id=session.id, title=session.title,
                               project_id=session.project_id, status=session.status,
                               created_at=session.created_at, updated_at=session.updated_at)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    rows = list_conversations_for_user(db, current_user.id)
    return [ConversationSummary(id=row.id, title=row.title, project_id=row.project_id,
                                status=row.status, created_at=row.created_at,
                                updated_at=row.updated_at) for row in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationSnapshot)
def get_conversation(conversation_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    _require_conversation(db, conversation_id, current_user)
    try:
        snapshot = conversation_snapshot(db, session_id=conversation_id,
                                         requester_user_id=current_user.id)
    except AgentError as e:
        raise _http_error(e)
    return ConversationSnapshot(**snapshot)


@router.get("/conversations/{conversation_id}/messages",
            response_model=list[ConversationMessageItem])
def get_messages(conversation_id: int,
                 after_sequence: int | None = Query(default=None, ge=0),
                 limit: int = Query(default=200, ge=1, le=1000),
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    _require_conversation(db, conversation_id, current_user)
    try:
        rows = list_messages_since(db, session_id=conversation_id,
                                   requester_user_id=current_user.id,
                                   after_sequence=after_sequence, limit=limit)
    except AgentError as e:
        raise _http_error(e)
    run_ids = {row.run_id for row in rows if row.run_id is not None}
    run_errors = dict(db.query(AgentRun.id, AgentRun.error_code).filter(
        AgentRun.id.in_(run_ids), AgentRun.session_id == conversation_id,
    ).all()) if run_ids else {}
    return [ConversationMessageItem(**_message_item(row, run_errors)) for row in rows]


@router.post("/conversations/{conversation_id}/turns", status_code=202,
             response_model=TurnSubmitResponse)
def submit_turn(conversation_id: int, payload: TurnSubmitRequest,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    _require_conversation(db, conversation_id, current_user)
    try:
        submission = submit_conversation_turn(
            db, session_id=conversation_id, requester_user_id=current_user.id,
            content=payload.content, client_request_id=payload.client_request_id,
            queue_mode=payload.queue_mode)
        snapshot = conversation_snapshot(db, session_id=conversation_id,
                                         requester_user_id=current_user.id)
    except AgentError as e:
        raise _http_error(e)
    return TurnSubmitResponse(
        run_id=submission.run.id,
        user_message_id=submission.user_message.id,
        replayed=submission.replayed,
        queue_state=snapshot["queue_state"],
        message_id=submission.user_message.message_id,
    )


@router.get("/conversations/{conversation_id}/events")
def stream_events(conversation_id: int,
                  after_sequence: int | None = Query(default=None, ge=0),
                  timeout_seconds: float = Query(default=30.0, ge=1, le=300),
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """SSE：DB 事件游标轮询（AgentEvent 是 Source of Truth）。

    文本增量由 Worker 聚合为 conversation_text_delta 行；tool/message/run 事件为稳定
    持久化状态；断线后带 after_sequence 重连即续传（游标保证无重复/无丢失）。
    """
    _require_conversation(db, conversation_id, current_user)
    # Release the request-scoped read transaction before returning a long-lived
    # stream.  Polling below uses a fresh short Session so MySQL REPEATABLE READ
    # can observe newly committed events.
    requester_user_id = current_user.id
    db.rollback()
    cursor = after_sequence if after_sequence is not None else 0

    def poll_events(after: int) -> list[dict]:
        with SessionLocal() as poll_db:
            rows = list_events_since(
                poll_db, session_id=conversation_id,
                requester_user_id=requester_user_id,
                after_sequence=after, limit=200,
            )
            return [_event_item(row) for row in rows]

    async def generate():
        nonlocal cursor
        deadline = time.monotonic() + timeout_seconds
        last_heartbeat = 0.0
        while time.monotonic() < deadline:
            # Run only the short DB operation in a thread. Waiting for new
            # tokens must not occupy FastAPI's shared sync request thread pool.
            events = await asyncio.to_thread(poll_events, cursor)
            for event in events:
                cursor = max(cursor, event["sequence_no"])
                yield f"event: conversation\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                last_heartbeat = now
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/conversation-runs/{run_id}/cancel",
             response_model=CancelConversationRunResponse)
def cancel_run(run_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    try:
        run = _require_conversation_run(db, run_id, current_user)
        run = cancel_conversation_run(db, run_id=run_id,
                                      requester_user_id=current_user.id)
        snapshot = conversation_snapshot(db, session_id=run.session_id,
                                         requester_user_id=current_user.id)
    except AgentError as e:
        raise _http_error(e)
    return CancelConversationRunResponse(run_id=run.id, status=run.status,
                                         queue_state=snapshot["queue_state"])


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(conversation_id: int, payload: ConversationUpdateRequest,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    _require_conversation(db, conversation_id, current_user)
    try:
        session = conversation_service.rename_conversation(
            db, session_id=conversation_id, requester_user_id=current_user.id,
            title=payload.title)
    except AgentError as e:
        raise _http_error(e)
    return ConversationSummary(id=session.id, title=session.title,
                               project_id=session.project_id, status=session.status,
                               created_at=session.created_at, updated_at=session.updated_at)


@router.get("/conversation-capabilities", response_model=ConversationCapabilities)
def conversation_capabilities(db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    del current_user  # 能力查询对所有登录用户可见（不泄漏 Secret）
    model_ready = is_conversation_model_ready(db)
    from app.agents.tools.conversation_safe_tools import build_conversation_tool_registry
    tools = [definition.name for definition in build_conversation_tool_registry().list()]
    return ConversationCapabilities(
        model_ready=model_ready,
        worker_status="unknown",  # 跨进程健康检查留 P10，不伪报 online
        tools=tools,
        supports_follow_up=True,
        supports_cancel=True,
        chat_scene=CHAT_SCENE_CODE,
    )
