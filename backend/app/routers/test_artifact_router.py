"""TestArtifact API（V2-P07）。API 只是 Application Service 的薄壳：

- Router 不做任何 db.add Node / 业务判断；
- 所有写操作（create/operations/undo/restore）委托 artifact_service，
  成功后 commit，失败 rollback 并按领域错误映射 HTTP；
- owner/project 权限由 Service 执行；不可读按 404（与现有 owner isolation 一致）。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.test_artifact.api import (
    AppliedOperationsResponse,
    ArtifactCreateRequest,
    ArtifactEnsureRequest,
    DiffResponse,
    OperationInput,
    OperationSubmitRequest,
    RestoreRequest,
    RevisionDetail,
    RevisionItem,
    TreeResponse,
    UndoResponse,
    ArtifactSummary,
)
from app.services.test_artifacts import artifact_service
from app.services.test_artifacts.errors import (
    RevisionConflictError,
    TestArtifactError,
    TestArtifactNotFoundError,
)

router = APIRouter(prefix="/test-artifacts", tags=["TestArtifact"])


def _http_error(err: TestArtifactError) -> HTTPException:
    code = err.error_code
    if isinstance(err, RevisionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "error_code": code,
                "message": err.message,
                "expected_revision": err.detail.get("expected_revision"),
                "current_revision": err.detail.get("current_revision"),
            },
        )
    status_map = {
        TestArtifactNotFoundError.error_code: 404,
        "artifact_permission_denied": 403,
        "test_artifact_validation_error": 400,
        "artifact_already_exists": 409,
        "test_artifact_data_error": 500,
    }
    status = status_map.get(code, 400)
    return HTTPException(status_code=status, detail=err.message)


def _to_canonical(op: OperationInput) -> dict[str, Any]:
    base: dict[str, Any] = {"operation_type": op.operation_type}
    if op.operation_type == "add_node":
        for key in ("parent_id", "node_type", "title", "content", "source_refs", "order_key"):
            value = getattr(op, key)
            if value is not None:
                base[key] = value
    elif op.operation_type == "update_node":
        base["target_node_id"] = op.target_node_id
        base["patch"] = op.patch or {}
    elif op.operation_type == "move_node":
        base["target_node_id"] = op.target_node_id
        base["new_parent_id"] = op.new_parent_id
        base["new_order_key"] = op.new_order_key
    elif op.operation_type == "delete_node":
        base["target_node_id"] = op.target_node_id
    elif op.operation_type == "restore":
        base["target_node_id"] = op.target_node_id
        base["nodes"] = op.nodes or []
    return base


def _artifact_dict(row) -> dict:
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "project_id": row.project_id,
        "title": row.title,
        "artifact_type": row.artifact_type,
        "status": row.status,
        "current_revision": row.current_revision,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _revision_dict(row) -> dict:
    return {
        "id": row.id,
        "artifact_id": row.artifact_id,
        "revision_no": row.revision_no,
        "base_revision": row.base_revision,
        "actor_type": row.actor_type,
        "actor_user_id": row.actor_user_id,
        "conversation_id": row.conversation_id,
        "run_id": row.run_id,
        "summary": row.summary,
        "created_at": row.created_at,
    }


def _operation_dict(row) -> dict:
    return {
        "op_index": row.op_index,
        "operation_type": row.operation_type,
        "target_node_id": row.target_node_id,
        "payload": row.payload_json,
        "before": row.before_json,
        "after": row.after_json,
    }


# ── Artifact ──


@router.post("", response_model=ArtifactSummary, status_code=201)
def create_artifact(payload: ArtifactCreateRequest, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        row = artifact_service.create_artifact(
            db, requester=current_user, title=payload.title,
            artifact_type=payload.artifact_type, project_id=payload.project_id,
        )
        db.commit()
    except TestArtifactError as err:
        db.rollback()
        raise _http_error(err) from err
    return _artifact_dict(row)


@router.post("/ensure-project-functional", response_model=ArtifactSummary)
def ensure_project_functional(payload: ArtifactEnsureRequest,
                             db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """P09.1：确保项目主 Functional TestArtifact（每项目唯一，并发由 DB 约束裁决）。"""
    try:
        row = artifact_service.ensure_project_functional_artifact(
            db, project_id=payload.project_id, requester=current_user,
            title=payload.title or None)
        db.commit()
    except TestArtifactError as err:
        db.rollback()
        raise _http_error(err) from err
    return _artifact_dict(row)


@router.get("", response_model=list[ArtifactSummary])
def list_artifacts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_artifact_dict(row) for row in artifact_service.list_artifacts(db, requester=current_user)]


@router.get("/{artifact_id}", response_model=ArtifactSummary)
def get_artifact(artifact_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    try:
        row = artifact_service.get_artifact(db, artifact_id=artifact_id, requester=current_user)
    except TestArtifactError as err:
        raise _http_error(err) from err
    return _artifact_dict(row)


@router.get("/{artifact_id}/tree", response_model=TreeResponse)
def get_tree(artifact_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    try:
        return artifact_service.get_tree(db, artifact_id=artifact_id, requester=current_user)
    except TestArtifactError as err:
        raise _http_error(err) from err


# ── 写：唯一入口 apply_operations ──


@router.post("/{artifact_id}/operations", response_model=AppliedOperationsResponse)
def apply_operations(artifact_id: int, payload: OperationSubmitRequest,
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # restore 是内部操作（含 arbitrary 恢复快照），只允许 undo_latest / restore_revision
    # 在 Application Service 内部生成并执行；普通 UI/API/未来 Agent Tool 不可自行提交。
    if any(op.operation_type == "restore" for op in payload.operations):
        raise HTTPException(status_code=400, detail="restore 为内部操作，请使用 undo/restore 端点")
    try:
        result = artifact_service.apply_operations(
            db,
            artifact_id=artifact_id,
            expected_revision=payload.expected_revision,
            operations=[_to_canonical(op) for op in payload.operations],
            requester=current_user,
            actor_type="user",
            actor_user_id=current_user.id,
            summary=payload.summary,
        )
        db.commit()
    except TestArtifactError as err:
        db.rollback()
        raise _http_error(err) from err
    return {
        "artifact_id": result["artifact_id"],
        "expected_revision": result["expected_revision"],
        "new_revision": result["new_revision"],
        "changed": result["changed"],
        "summary": payload.summary or "",
    }


# ── Revision / Diff ──


@router.get("/{artifact_id}/revisions", response_model=list[RevisionItem])
def list_revisions(artifact_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    try:
        rows = artifact_service.list_revisions(db, artifact_id=artifact_id, requester=current_user)
    except TestArtifactError as err:
        raise _http_error(err) from err
    return [_revision_dict(row) for row in rows]


@router.get("/{artifact_id}/revisions/{revision_no}", response_model=RevisionDetail)
def get_revision(artifact_id: int, revision_no: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    try:
        revision, operations = artifact_service.get_revision(
            db, artifact_id=artifact_id, revision_no=revision_no, requester=current_user)
    except TestArtifactError as err:
        raise _http_error(err) from err
    detail = _revision_dict(revision)
    detail["operations"] = [_operation_dict(row) for row in operations]
    return detail


@router.get("/{artifact_id}/diff", response_model=DiffResponse)
def get_diff(artifact_id: int,
             from_revision: int | None = Query(default=None, ge=0),
             to_revision: int | None = Query(default=None, ge=1),
             db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        row = artifact_service.get_artifact(db, artifact_id=artifact_id, requester=current_user)
        to = to_revision if to_revision is not None else row.current_revision
        frm = from_revision if from_revision is not None else max(0, to - 1)
        return artifact_service.get_diff(
            db, artifact_id=artifact_id, from_revision=frm, to_revision=to, requester=current_user)
    except TestArtifactError as err:
        raise _http_error(err) from err


# ── Undo / Restore（反向 Revision） ──


@router.post("/{artifact_id}/undo", response_model=UndoResponse)
def undo_latest(artifact_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    try:
        result = artifact_service.undo_latest(db, artifact_id=artifact_id, requester=current_user)
        db.commit()
    except TestArtifactError as err:
        db.rollback()
        raise _http_error(err) from err
    return result


@router.post("/{artifact_id}/restore", response_model=UndoResponse)
def restore_revision(artifact_id: int, payload: RestoreRequest,
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        result = artifact_service.restore_revision(
            db, artifact_id=artifact_id, target_revision=payload.target_revision,
            requester=current_user)
        db.commit()
    except TestArtifactError as err:
        db.rollback()
        raise _http_error(err) from err
    return result
