"""AgentRun / AgentStep / AgentEvent 数据访问 Service。

- 状态转换一律经 transitions.assert_can_transition，不允许任意赋值；
- 归属校验：Run 仅 requester 本人（或会话 owner）可见；
- 事务边界：Service 只 add/flush 不 commit，由 Runner 每步 commit；
- sequence_no 生成方式为 max+1，并发限制已登记开发记录。
"""

import hashlib
import json
from datetime import datetime

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.agents.runtime.transitions import assert_can_transition
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_run import AgentRun
from app.models.agent.agent_session import AgentSession
from app.models.agent.agent_step import AgentStep
from app.schemas.agent.platform import RUN_STATUSES, STEP_KINDS, STEP_STATUSES


def create_run(
    db: Session,
    session: AgentSession,
    workflow_code: str,
    requester_user_id: int,
    project_id: int,
    input_json: dict | None = None,
    workflow_version: str | None = None,
    idempotency_key: str | None = None,
    max_steps: int = 20,
) -> AgentRun:
    """创建 queued Run；project_id 必须与所属会话一致。"""
    if project_id != session.project_id:
        raise AgentError(
            f"Run 归属项目 {project_id} 与会话归属项目 {session.project_id} 不一致。",
            error_code="agent_project_mismatch",
        )
    if max_steps < 1:
        raise AgentError("max_steps 必须 >= 1", error_code="agent_invalid_max_steps")
    run = AgentRun(
        session_id=session.id,
        project_id=project_id,
        requester_user_id=requester_user_id,
        workflow_code=workflow_code,
        workflow_version=workflow_version,
        status="queued",
        input_json=input_json,
        input_hash=_canonical_hash(input_json),
        idempotency_key=idempotency_key,
        max_steps=max_steps,
        steps_used=0,
        llm_calls_used=0,
        tool_calls_used=0,
        prompt_tokens=0,
        completion_tokens=0,
    )
    db.add(run)
    db.flush()
    return run


def get_run(db: Session, run_id: int, requester_user_id: int) -> AgentRun:
    """按 ID 获取；仅 requester 本人或会话 owner 可见。"""
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise AgentPermissionError(f"Run {run_id} 不存在或无权访问。")
    if run.requester_user_id != requester_user_id:
        session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
        if not session or session.user_id != requester_user_id:
            raise AgentPermissionError(f"用户 {requester_user_id} 无权访问 Run {run_id}。")
    return run


def transition_status(db: Session, run: AgentRun, target: str) -> AgentRun:
    """集中状态转换入口；非法转换抛 InvalidStateTransitionError。"""
    assert_can_transition(run.status, target)
    run.status = target
    db.flush()
    return run


def start_step(
    db: Session,
    run: AgentRun,
    step_kind: str,
    step_name: str,
    tool_name: str | None = None,
    sequence_no: int | None = None,
) -> AgentStep:
    """创建 running 步骤；默认 sequence_no = Run 内已有序号最大值 + 1。"""
    if step_kind not in STEP_KINDS:
        raise AgentError(f"非法步骤类型: {step_kind}", error_code="agent_invalid_step_kind")
    if sequence_no is None:
        max_no = (
            db.query(AgentStep.sequence_no)
            .filter(AgentStep.agent_run_id == run.id)
            .order_by(AgentStep.sequence_no.desc())
            .first()
        )
        sequence_no = (max_no[0] + 1) if max_no else 1
    step = AgentStep(
        agent_run_id=run.id,
        sequence_no=sequence_no,
        step_kind=step_kind,
        step_name=step_name,
        tool_name=tool_name,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(step)
    db.flush()
    return step


def finish_step(
    db: Session,
    step: AgentStep,
    status: str = "succeeded",
    output_json: dict | None = None,
    duration_ms: int | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentStep:
    if status not in STEP_STATUSES:
        raise AgentError(f"非法步骤状态: {status}", error_code="agent_invalid_step_status")
    step.status = status
    step.finished_at = datetime.utcnow()
    if output_json is not None:
        step.output_json = output_json
    if duration_ms is not None:
        step.duration_ms = duration_ms
    if provider_name is not None:
        step.provider_name = provider_name
    if model_name is not None:
        step.model_name = model_name
    if prompt_tokens is not None:
        step.prompt_tokens = prompt_tokens
    if completion_tokens is not None:
        step.completion_tokens = completion_tokens
    if error_code is not None:
        step.error_code = error_code
    if error_message is not None:
        step.error_message = error_message
    db.flush()
    return step


def increment_counter(db: Session, run: AgentRun, field: str, amount: int = 1) -> AgentRun:
    allowed = {"steps_used", "llm_calls_used", "tool_calls_used", "prompt_tokens", "completion_tokens"}
    if field not in allowed:
        raise AgentError(f"非法计数器字段: {field}", error_code="agent_invalid_counter")
    setattr(run, field, getattr(run, field) + amount)
    db.flush()
    return run


def append_event(
    db: Session,
    session_id: int,
    run_id: int | None,
    event_type: str,
    payload_json: dict | None = None,
) -> AgentEvent:
    """追加事件；sequence_no 取会话内最大值 +1。"""
    max_no = (
        db.query(AgentEvent.sequence_no)
        .filter(AgentEvent.session_id == session_id)
        .order_by(AgentEvent.sequence_no.desc())
        .first()
    )
    sequence_no = (max_no[0] + 1) if max_no else 1
    event = AgentEvent(
        session_id=session_id,
        run_id=run_id,
        event_type=event_type,
        sequence_no=sequence_no,
        payload_json=payload_json,
    )
    db.add(event)
    db.flush()
    return event


def save_output_json(db: Session, run: AgentRun, output_json: dict) -> AgentRun:
    run.output_json = output_json
    db.flush()
    return run


def mark_finished_at(db: Session, run: AgentRun, now: datetime | None = None) -> AgentRun:
    run.finished_at = now or datetime.utcnow()
    db.flush()
    return run


def _canonical_hash(input_json: dict | None) -> str | None:
    if input_json is None:
        return None
    canonical = json.dumps(input_json, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Worker 原子操作（条件 UPDATE，SQLite/MySQL 兼容，不使用 SKIP LOCKED） ──

STALE_ERROR_CODE = "agent_worker_heartbeat_timeout"


def next_queued_run_id(db: Session) -> int | None:
    """最早进入 queued 的 Run ID；无任务返回 None。"""
    row = (
        db.query(AgentRun.id)
        .filter(AgentRun.status == "queued")
        .order_by(AgentRun.id.asc())
        .first()
    )
    return row[0] if row else None


def claim_queued_run(db: Session, run_id: int, worker_id: str, now: datetime) -> bool:
    """原子抢占：只有 status='queued' 的行会被更新。

    条件 UPDATE 保证两个 Worker 看到同一候选时只有一个成功（rowcount==1）。
    抢占成功后调用方应立即 commit，释放抢占事务，再进入 Runtime。
    只能抢占 queued；cancelled/waiting_approval/终态不会被抢占。
    """
    result = db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == "queued")
        .values(
            status="running",
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(AgentRun.started_at, now),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def heartbeat(db: Session, run_id: int, worker_id: str, now: datetime) -> int:
    """Owner-only 心跳：仅 owner Worker 且 status='running' 时更新。

    返回 rowcount。注意：MySQL 在更新值与当前值完全相同时 rowcount 可能为 0，
    因此调用方不得基于返回值做控制流分支（best-effort 语义）。
    """
    result = db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == "running", AgentRun.worker_id == worker_id)
        .values(heartbeat_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def find_stale_run_ids(db: Session, stale_before: datetime, limit: int = 50) -> list[int]:
    """找出心跳超时的 running Run。

    条件：status='running' AND (heartbeat_at < stale_before
         OR (heartbeat_at IS NULL AND started_at < stale_before))
    waiting_approval / 终态不参与扫描。
    """
    rows = (
        db.query(AgentRun.id)
        .filter(
            AgentRun.status == "running",
            or_(
                AgentRun.heartbeat_at < stale_before,
                and_(AgentRun.heartbeat_at.is_(None), AgentRun.started_at < stale_before),
            ),
        )
        .order_by(AgentRun.id.asc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows]


def mark_interrupted(
    db: Session,
    run_id: int,
    error_code: str,
    error_message: str,
    now: datetime,
) -> bool:
    """stale running → interrupted（条件 UPDATE，避免与并发恢复竞争）。

    保留 worker_id 供排查（统一策略：不清理）；不自动重排 queued。
    """
    result = db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == "running")
        .values(
            status="interrupted",
            error_code=error_code,
            error_message=error_message,
            finished_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


assert set(RUN_STATUSES) == {"queued", "running", "waiting_approval", "succeeded", "failed", "cancelled", "interrupted"}
