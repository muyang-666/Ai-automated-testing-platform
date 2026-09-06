"""TestArtifact Application Service（V2-P07）。

唯一写入口：Router / UI / 未来 Agent Tool 必须全部经过这里的写方法
（create_artifact / apply_operations / undo_latest / restore_revision），
禁止路由或工具直接 db.add Node。

不变式（均由 Service 在事务内保证）：
  - 每个 Artifact 恰好一个 root；root parent 恒为 NULL；root 不可 delete/move；
  - parent 存在、同 artifact、存活；禁止跨 artifact；禁止环；
  - 删除 = 逻辑删除（deleted_revision），tree/API 默认隐藏；
  - 每次逻辑写 = 一个 Revision（线性递增）；
  - 乐观并发：写携带 expected_revision；最终由条件 UPDATE
    (WHERE current_revision = expected) 在数据库事务层裁决；冲突 → RevisionConflictError(409)。
任何一步失败 → 调用方 rollback（本服务不 commit）。
"""

import json

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.requirement_doc import RequirementDoc
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.test_artifact.artifact_operation import ArtifactOperation
from app.models.test_artifact.artifact_revision import ArtifactRevision
from app.models.test_artifact.test_artifact import TestArtifact
from app.schemas.test_artifact.content import validate_node_content, validate_source_refs
from app.services.permission_service import can_operate_project, can_read_project
from app.services.test_artifacts import diff as diff_mod
from app.services.test_artifacts import repository as repo
from app.services.test_artifacts.domain import (
    ACTOR_TYPE_USER,
    NODE_TYPE_ROOT,
    NODE_TYPE_MODULE,
    NODE_TYPE_TEST_CASE,
    OP_ADD_NODE,
    OP_DELETE_NODE,
    OP_MOVE_NODE,
    OP_RESTORE,
    OP_UPDATE_NODE,
    SERVER_CONTROLLED_FIELDS,
    WRITABLE_NODE_FIELDS,
)
from app.services.test_artifacts.errors import (
    RevisionConflictError,
    TestArtifactDataError,
    TestArtifactNotFoundError,
    TestArtifactPermissionError,
    TestArtifactValidationError,
)

NODE_TYPES = ("root", "module", "test_case")

# Primary Functional Artifact 语义：每项目一份 test_design（P09.1）
FUNCTIONAL_ARTIFACT_TYPE = "test_design"
DEFAULT_MODULE_TITLE = "默认模块"

_ALLOWED_KEYS = {
    OP_ADD_NODE: {"operation_type", "parent_id", "node_type", "title", "content", "source_refs", "order_key", "ref"},
    OP_UPDATE_NODE: {"operation_type", "target_node_id", "patch"},
    OP_MOVE_NODE: {"operation_type", "target_node_id", "new_parent_id", "new_order_key"},
    OP_DELETE_NODE: {"operation_type", "target_node_id"},
    OP_RESTORE: {"operation_type", "target_node_id", "nodes"},
}


# ── 权限 ──


def _readable(db: Session, artifact: TestArtifact, requester) -> bool:
    if artifact.owner_user_id == requester.id:
        return True
    if artifact.project_id is not None:
        return can_read_project(db, requester, artifact.project_id)
    return False


def _writable(db: Session, artifact: TestArtifact, requester) -> bool:
    if artifact.owner_user_id == requester.id:
        return True
    if artifact.project_id is not None:
        return can_operate_project(db, requester, artifact.project_id)
    return False


def _load_readable(db: Session, artifact_id: int, requester) -> TestArtifact:
    artifact = repo.get_artifact(db, artifact_id)
    if artifact is None or not _readable(db, artifact, requester):
        # 与现有 owner isolation 一致：不可读按不存在处理（404）
        raise TestArtifactNotFoundError("Test Artifact 不存在")
    return artifact


def _load_writable(db: Session, artifact_id: int, requester) -> TestArtifact:
    artifact = repo.get_artifact(db, artifact_id)
    if artifact is None or not _readable(db, artifact, requester):
        raise TestArtifactNotFoundError("Test Artifact 不存在")
    if not _writable(db, artifact, requester):
        raise TestArtifactPermissionError("没有该 Artifact 的写入权限")
    return artifact


# ── 节点快照 / 工具 ──


def node_snapshot(node: ArtifactNode) -> dict:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "title": node.title,
        "content": node.content_json,
        "source_refs": node.source_refs_json,
        "parent_id": node.parent_id,
        "order_key": node.order_key,
    }


def _validate_request_keys(op_type: str, request: dict) -> None:
    extras = set(request.keys()) - _ALLOWED_KEYS[op_type]
    if extras:
        raise TestArtifactValidationError(f"operation 含不允许的字段: {sorted(extras)}")


def _validated_content(node_type: str, raw):
    """content schema 校验失败 → 领域校验错误（而非裸 ValueError/pydantic 错）。"""
    try:
        return validate_node_content(node_type, raw)
    except ValueError as exc:
        raise TestArtifactValidationError(str(exc)) from None


def _validated_refs(raw):
    try:
        return validate_source_refs(raw)
    except ValueError as exc:
        raise TestArtifactValidationError(str(exc)) from None


# SourceRef = provenance metadata，不等于 Requirement 读取授权（P08.1）。
# requirement/requirement_doc 类型的引用写入时，服务端必须再次验证目标
# Requirement 属于当前 Artifact 的 project scope；projectless Artifact 仅凭
# 模型写入 source_id 不能获得任何项目 Requirement 的读取能力。
_REQUIREMENT_SOURCE_TYPES = ("requirement", "requirement_doc")


def _validated_node_refs(db: Session, artifact: TestArtifact, raw, *, enforce_requirement: bool = True):
    """解析并校验节点 source_refs。

    enforce_requirement=False 用于 internal undo/restore：允许恢复历史 provenance，
    即使 Requirement 后来 soft-delete / unavailable（SourceRef=provenance，
    SourceRef≠当前能力）；read_requirement 对已删除 Requirement 仍然拒绝。
    """
    refs = _validated_refs(raw)
    if not refs:
        return refs
    requirement_refs = [ref for ref in refs if ref["source_type"] in _REQUIREMENT_SOURCE_TYPES]
    if not requirement_refs or not enforce_requirement:
        return refs
    scope = artifact.project_id
    if scope is None:
        raise TestArtifactValidationError(
            "未绑定项目的 Artifact 不能引用 Requirement（SourceRef 不授予读取权限）")
    for ref in requirement_refs:
        try:
            requirement_id = int(ref["source_id"])
        except (TypeError, ValueError):
            raise TestArtifactValidationError(
                "requirement 类型引用的 source_id 必须是数字 Requirement ID") from None
        row = db.get(RequirementDoc, requirement_id)
        if row is None or row.project_id != scope or row.is_deleted:
            raise TestArtifactValidationError(
                "引用的 Requirement 不存在、不属于当前 Artifact 项目或已删除")
    return refs


def _require_visible_node(db: Session, artifact: TestArtifact, node_id: int | None, *, what: str) -> ArtifactNode:
    node = repo.get_node(db, node_id) if node_id is not None else None
    if node is None or node.artifact_id != artifact.id or node.deleted_revision is not None:
        raise TestArtifactValidationError(f"{what} 不存在、已删除或不属于该 Artifact")
    return node


def _require_parent(db: Session, artifact: TestArtifact, parent_id: int | None, *,
                    restoring_ids: set[int] | None = None, what: str = "父节点") -> ArtifactNode | None:
    """共享 parent Tree Integrity（add/move/restore 同规则，防三套规则漂移）。

    - parent_id=None → 返回 None（root 专用，由调用方结合 root 规则判断）；
    - parent 必须存在、同 artifact；
    - parent 必须存活（deleted_revision IS NULL），或在 restoring_ids 中（本批正在恢复）；
    - test_case 永远不能作父节点。
    """
    if parent_id is None:
        return None
    parent = repo.get_node(db, parent_id)
    if parent is None or parent.artifact_id != artifact.id:
        raise TestArtifactValidationError(f"{what} 不存在或不属于该 Artifact")
    if parent.deleted_revision is not None and not (restoring_ids and parent.id in restoring_ids):
        raise TestArtifactValidationError(f"{what} 已删除，不能作为父节点")
    if parent.node_type == NODE_TYPE_TEST_CASE:
        raise TestArtifactValidationError("test_case 节点不能作为父节点")
    return parent


def _descendant_ids(db: Session, artifact: TestArtifact, node_id: int) -> list[int]:
    """当前可见树中以 node 为根的子孙节点 id（不含 node 自身）。"""
    rows = repo.list_visible_nodes(db, artifact.id)
    children: dict[int | None, list[int]] = {}
    for row in rows:
        children.setdefault(row.parent_id, []).append(row.id)
    result: list[int] = []
    stack = list(children.get(node_id, []))
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(children.get(current, []))
    return result


def _next_order_key(db: Session, artifact_id: int, parent_id: int | None,
                    exclude_node_id: int | None = None) -> int:
    query = (
        select(func.max(ArtifactNode.order_key))
        .where(ArtifactNode.artifact_id == artifact_id,
               ArtifactNode.deleted_revision.is_(None),
               ArtifactNode.parent_id.is_(None) if parent_id is None
               else ArtifactNode.parent_id == parent_id)
    )
    if exclude_node_id is not None:
        query = query.where(ArtifactNode.id != exclude_node_id)
    current = db.execute(query).scalar()
    return (current if current is not None else 0) + 1


def _ensure_root_available(db: Session, artifact: TestArtifact) -> None:
    if artifact.root_node_id is not None:
        root = repo.get_node(db, artifact.root_node_id)
        if root is not None and root.deleted_revision is None:
            raise TestArtifactValidationError("该 Artifact 已存在 root，不能重复添加")


# ── Operation 应用（单条） ──


def _apply_add(db: Session, artifact: TestArtifact, new_no: int, request: dict,
               actor_user_id: int | None) -> dict:
    node_type = request.get("node_type")
    if node_type not in NODE_TYPES:
        raise TestArtifactValidationError(f"未知 node_type: {node_type}")
    parent_id = request.get("parent_id")
    title = request.get("title") or ""
    content = _validated_content(node_type, request.get("content"))
    source_refs = _validated_node_refs(db, artifact, request.get("source_refs"))
    order_key = request.get("order_key")

    if node_type == "root":
        if parent_id is not None:
            raise TestArtifactValidationError("root 节点的 parent_id 必须为空")
        _ensure_root_available(db, artifact)
        parent_row = None
    else:
        if parent_id is None:
            raise TestArtifactValidationError("非 root 节点必须提供 parent_id")
        parent_row = _require_parent(db, artifact, parent_id)
        # P09.1 Domain invariant：module 只能挂在 root/module 下；test_case 只能挂在 module 下
        if node_type == NODE_TYPE_TEST_CASE:
            if parent_row is None or parent_row.node_type != NODE_TYPE_MODULE:
                raise TestArtifactValidationError("test_case 必须属于 module")
        elif parent_row is None or parent_row.node_type not in (NODE_TYPE_ROOT, NODE_TYPE_MODULE):
            raise TestArtifactValidationError("module 只能挂在 root 或其他 module 下")
    if order_key is not None and order_key < 0:
        raise TestArtifactValidationError("order_key 不能为负数")

    node = ArtifactNode(
        artifact_id=artifact.id,
        parent_id=parent_row.id if parent_row is not None else None,
        node_type=node_type,
        order_key=_next_order_key(db, artifact.id, parent_row.id if parent_row else None) if order_key is None else order_key,
        title=title,
        content_json=content,
        source_refs_json=source_refs,
        created_revision=new_no,
        deleted_revision=None,
        created_by=actor_user_id,
    )
    db.add(node)
    db.flush()
    if node_type == "root" and artifact.root_node_id is None:
        artifact.root_node_id = node.id
    return {"target_node_id": node.id, "payload": request, "before": None, "after": node_snapshot(node)}


def _apply_update(db: Session, artifact: TestArtifact, request: dict, *,
                enforce_requirement: bool = True) -> dict:
    node = _require_visible_node(db, artifact, request.get("target_node_id"), what="节点")
    patch = request.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise TestArtifactValidationError("update_node 必须提供非空 patch")
    for key, value in patch.items():
        if key in SERVER_CONTROLLED_FIELDS:
            raise TestArtifactValidationError(f"服务端控制字段不可被客户端 patch: {key}")
        if key not in WRITABLE_NODE_FIELDS:
            raise TestArtifactValidationError(f"不可 patch 的字段: {key}")
        if value is None:
            raise TestArtifactValidationError(
                f"patch.{key} 不能为 null（null 不代表清空；source_refs=[] 表示清空）")
    before = node_snapshot(node)
    if "title" in patch:
        value = patch["title"]
        if not isinstance(value, str) or not value:
            raise TestArtifactValidationError("title 必须为非空字符串")
        node.title = value
    if "content" in patch:
        node.content_json = _validated_content(node.node_type, patch["content"])
    if "source_refs" in patch:
        node.source_refs_json = _validated_node_refs(db, artifact, patch["source_refs"], enforce_requirement=enforce_requirement)
    db.flush()
    return {"target_node_id": node.id, "payload": {"patch": patch}, "before": before, "after": node_snapshot(node)}


def _apply_move(db: Session, artifact: TestArtifact, request: dict) -> dict:
    node = _require_visible_node(db, artifact, request.get("target_node_id"), what="节点")
    if node.node_type == "root":
        raise TestArtifactValidationError("root 节点不可移动")
    new_parent_id = request.get("new_parent_id")
    if new_parent_id is None:
        raise TestArtifactValidationError("move_node 必须提供 new_parent_id")
    new_parent = _require_parent(db, artifact, new_parent_id, what="目标父节点")
    if new_parent is None:  # move 不允许悬空（root 专属 None）
        raise TestArtifactValidationError("move_node 必须提供 new_parent_id")
    if node.node_type == NODE_TYPE_TEST_CASE and new_parent.node_type != NODE_TYPE_MODULE:
        raise TestArtifactValidationError("test_case 只能移动到 module 下")
    if node.node_type == NODE_TYPE_MODULE and new_parent.node_type not in (NODE_TYPE_ROOT, NODE_TYPE_MODULE):
        raise TestArtifactValidationError("module 只能移动到 root 或其他 module 下")
    if new_parent_id == node.id or new_parent_id in _descendant_ids(db, artifact, node.id):
        raise TestArtifactValidationError("不能移动到自身或其子孙节点下（会形成环）")

    before = {"parent_id": node.parent_id, "order_key": node.order_key}
    new_order = request.get("new_order_key")
    node.parent_id = new_parent.id
    node.order_key = (
        _next_order_key(db, artifact.id, new_parent.id, exclude_node_id=node.id)
        if new_order is None else new_order
    )
    db.flush()
    after = {"parent_id": node.parent_id, "order_key": node.order_key}
    return {
        "target_node_id": node.id,
        "payload": {"new_parent_id": new_parent.id, "new_order_key": node.order_key},
        "before": before,
        "after": after,
    }


def _apply_delete(db: Session, artifact: TestArtifact, new_no: int, request: dict) -> dict:
    node = _require_visible_node(db, artifact, request.get("target_node_id"), what="节点")
    if node.node_type == "root":
        raise TestArtifactValidationError("root 节点不可删除")
    descendants = _descendant_ids(db, artifact, node.id)
    affected = [node.id] + descendants
    rows = db.execute(
        select(ArtifactNode).where(ArtifactNode.id.in_(affected))
    ).scalars().all()
    for row in rows:
        row.deleted_revision = new_no
    db.flush()
    return {
        "target_node_id": node.id,
        "payload": {"affected_node_ids": affected, "descendant_count": len(descendants)},
        "before": node_snapshot(node),
        "after": None,
    }


def _apply_restore(db: Session, artifact: TestArtifact, request: dict, *,
                       enforce_requirement: bool = True) -> dict:
    """撤销一次删除：恢复先前逻辑删除的子树（target + 快照列表）。

    nodes 为服务端生成的恢复快照（含 id/parent/order/title/content/source_refs）。
    """
    target_id = request.get("target_node_id")
    raw_nodes = request.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise TestArtifactValidationError("restore 需要非空 nodes 快照列表")
    ids = [int(item["id"]) for item in raw_nodes if isinstance(item, dict) and item.get("id") is not None]
    if target_id is None or target_id not in ids:
        raise TestArtifactValidationError("restore 的 target_node_id 必须位于 nodes 中")
    rows = db.execute(
        select(ArtifactNode).where(ArtifactNode.id.in_(ids),
                                   ArtifactNode.artifact_id == artifact.id)
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(set(ids)):
        raise TestArtifactValidationError("restore 存在不属于该 Artifact 的节点")
    visible_ids = {r.id for r in repo.list_visible_nodes(db, artifact.id)}
    restored_ids: set[int] = set()
    for snap_id in ids:
        if snap_id in visible_ids:
            raise TestArtifactValidationError(f"节点 {snap_id} 不是已删除节点，不能重复恢复")
        restored_ids.add(snap_id)
    # ── 完整 Tree Integrity（与 add/move 共用 _require_parent 规则） ──
    # parent 存在/同 artifact/（存活 或 本批恢复中）；test_case 不可为父；root 规则；
    # 禁止 self-parent；恢复快照内 parent 链不得成环。
    snap_by_id = {int(item["id"]): item for item in raw_nodes if isinstance(item, dict) and item.get("id") is not None}
    if set(snap_by_id) != set(ids):
        raise TestArtifactValidationError("restore 快照必须覆盖全部待恢复节点")
    for snap_id in ids:
        row = by_id[snap_id]
        if row.node_type == NODE_TYPE_ROOT:
            raise TestArtifactValidationError("root 节点不可通过 restore 恢复（数据异常）")
    allowed_parent_ids = restored_ids | visible_ids
    for snap_id in ids:
        snap = snap_by_id[snap_id]
        parent = snap.get("parent_id")
        row = by_id[snap_id]
        if parent is None:
            if row.node_type != NODE_TYPE_ROOT:
                raise TestArtifactValidationError("非 root 节点的 restore 快照必须有父节点")
            continue
        if parent not in allowed_parent_ids:
            raise TestArtifactValidationError("restore 父节点不存在/已删除/跨 Artifact")
        if parent == snap_id:
            raise TestArtifactValidationError("restore 节点不能以自身为父节点")
        parent_row = repo.get_node(db, parent)
        if parent_row is None or parent_row.artifact_id != artifact.id:
            raise TestArtifactValidationError("restore 父节点不存在或不属于该 Artifact")
        if row.node_type == NODE_TYPE_TEST_CASE and parent_row.node_type != NODE_TYPE_MODULE:
            raise TestArtifactValidationError("test_case 只能恢复到 module 下")
        if row.node_type == NODE_TYPE_MODULE and parent_row.node_type not in (
                NODE_TYPE_ROOT, NODE_TYPE_MODULE):
            raise TestArtifactValidationError("module 只能恢复到 root 或其他 module 下")
        if not isinstance(snap.get("title"), str):
            raise TestArtifactValidationError("restore 快照缺少合法 title")
        _validated_content(row.node_type, snap.get("content"))  # 防御：快照内容必须匹配节点类型
    # 环检测：仅沿“本批恢复节点”的 parent 链行走，重入即环（A→B→A）
    parent_of: dict[int, int | None] = {sid: snap_by_id[sid].get("parent_id") for sid in ids}
    for start in ids:
        seen: set[int] = set()
        cursor: int | None = start
        while cursor is not None and cursor in parent_of:
            if cursor in seen:
                raise TestArtifactValidationError("restore 快照的 parent 链形成环")
            seen.add(cursor)
            cursor = parent_of[cursor]
    # 先解除删除标记（全部），再按快照回填字段
    for row in by_id.values():
        row.deleted_revision = None
    db.flush()
    restored_by_id = {r.id: r for r in db.execute(
        select(ArtifactNode).where(ArtifactNode.id.in_(ids))
    ).scalars().all()}
    for snap in raw_nodes:
        row = restored_by_id[int(snap["id"])]
        row.parent_id = snap.get("parent_id")
        row.order_key = snap.get("order_key", row.order_key)
        row.title = snap.get("title", row.title)
        row.content_json = _validated_content(row.node_type, snap.get("content"))
        row.source_refs_json = _validated_node_refs(db, artifact, snap.get("source_refs"), enforce_requirement=enforce_requirement)
    db.flush()
    after = [node_snapshot(restored_by_id[sid]) for sid in ids]
    return {"target_node_id": target_id, "payload": {"affected_node_ids": ids}, "before": None, "after": after}


# ── 主写入口 ──

_ACTOR_TYPE_VALUES = ("user", "agent", "system")


def apply_operations(db: Session, *, artifact_id: int, expected_revision: int,
                     operations: list[dict], requester, actor_type: str = ACTOR_TYPE_USER,
                     actor_user_id: int | None = None, conversation_id: int | None = None,
                     run_id: int | None = None, summary: str | None = None,
                     enforce_requirement_live: bool = True) -> dict:
    """在一个事务内应用一个 operation batch 并产生恰好一个 Revision。

    失败即抛错（由调用方 rollback）；成功返回 {artifact_id, expected_revision,
    new_revision, changed, revision_id}，commit 由调用方（Router/测试）负责。
    """
    if actor_type not in _ACTOR_TYPE_VALUES:
        raise TestArtifactValidationError(f"未知 actor_type: {actor_type}")
    artifact = _load_writable(db, artifact_id, requester)
    if not isinstance(operations, list) or not operations:
        raise TestArtifactValidationError("operations 不能为空")

    # 快速失败：expected 已过期（友好信息）；DB 层仍以条件 UPDATE 为最终裁决
    if artifact.current_revision != expected_revision:
        raise RevisionConflictError(expected_revision, artifact.current_revision)

    new_no = artifact.current_revision + 1
    revision = ArtifactRevision(
        artifact_id=artifact.id,
        revision_no=new_no,
        base_revision=artifact.current_revision,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        summary=(summary or "").strip()[:500],
    )
    db.add(revision)
    db.flush()

    # P09.1：调用方未指定 module 时（test_case.parent == root），同批自动落入
    # 一级「默认模块」——只产生一个 Revision，不创建 root 下裸 Case。
    # 并发：唯一约束不可用于"按 title 唯一"（普通重名合法），因此靠 revision
    # 条件写裁决：两方都看不见默认模块时各自创建，仅一方提交成功；失败方由
    # 上层（如 save 产品线）重试后命中既有默认模块。
    work_operations = list(operations)
    implicit_default_ops: list[dict] = []
    rewrite_root_case: list[tuple[int, str | int]] = []
    for index, request in enumerate(work_operations):
        if request.get("operation_type") != OP_ADD_NODE:
            continue
        if request.get("node_type") != NODE_TYPE_TEST_CASE:
            continue
        if request.get("parent_id") != artifact.root_node_id:
            continue
        existing_default = db.execute(
            select(ArtifactNode.id).where(
                ArtifactNode.artifact_id == artifact.id,
                ArtifactNode.parent_id == artifact.root_node_id,
                ArtifactNode.node_type == NODE_TYPE_MODULE,
                ArtifactNode.title == DEFAULT_MODULE_TITLE,
                ArtifactNode.deleted_revision.is_(None),
            ).limit(1)
        ).scalar_one_or_none()
        if existing_default is not None:
            rewrite_root_case.append((index, existing_default))
        else:
            rewrite_root_case.append((index, "@__auto_default__"))
            if not implicit_default_ops:
                implicit_default_ops.append({
                    "operation_type": OP_ADD_NODE,
                    "parent_id": artifact.root_node_id,
                    "node_type": NODE_TYPE_MODULE,
                    "title": DEFAULT_MODULE_TITLE,
                    "ref": "__auto_default__",
                })
    if implicit_default_ops:
        work_operations = implicit_default_ops + work_operations
    for index, parent in rewrite_root_case:
        work_operations[index + len(implicit_default_ops)] = dict(
            work_operations[index + len(implicit_default_ops)], parent_id=parent)

    changed = 0
    ref_to_node: dict[str, int] = {}  # 批内引用：add_node 可携带 ref，后续 op 用 "@ref" 引用其 id
    for index, request in enumerate(work_operations):
        if not isinstance(request, dict):
            raise TestArtifactValidationError("operation 必须是对象")
        op_type = request.get("operation_type")
        if op_type not in _ALLOWED_KEYS:
            raise TestArtifactValidationError(f"未知 operation_type: {op_type}")
        work = dict(request)
        for ref_key in ("parent_id", "new_parent_id"):
            value = work.get(ref_key)
            if isinstance(value, str):
                ref_name = value[1:] if value.startswith("@") else None
                if ref_name is None or ref_name not in ref_to_node:
                    raise TestArtifactValidationError(
                        f"批内引用未知：{value}（只能引用本批先前的 add_node.ref）")
                work[ref_key] = ref_to_node[ref_name]
        _validate_request_keys(op_type, work)
        if op_type == OP_ADD_NODE:
            result = _apply_add(db, artifact, new_no, work, actor_user_id)
            if work.get("ref"):
                if work["ref"] in ref_to_node:
                    raise TestArtifactValidationError(f"批内 ref 重复：{work['ref']}")
                ref_to_node[work["ref"]] = result["target_node_id"]
        elif op_type == OP_UPDATE_NODE:
            result = _apply_update(db, artifact, work, enforce_requirement=enforce_requirement_live)
        elif op_type == OP_MOVE_NODE:
            result = _apply_move(db, artifact, work)
        elif op_type == OP_DELETE_NODE:
            result = _apply_delete(db, artifact, new_no, work)
        elif op_type == OP_RESTORE:
            result = _apply_restore(db, artifact, work, enforce_requirement=enforce_requirement_live)
        else:  # pragma: no cover - guarded above
            raise TestArtifactValidationError(f"未知 operation_type: {op_type}")
        db.add(ArtifactOperation(
            revision_id=revision.id,
            op_index=index,
            operation_type=op_type,
            target_node_id=result["target_node_id"],
            payload_json=result["payload"],
            before_json=result["before"],
            after_json=result["after"],
        ))
        changed += 1

    # 权威乐观并发裁决：条件 UPDATE。rowcount=0 → 另一个连接已把版本推进 → 冲突。
    result_update = db.execute(
        update(TestArtifact)
        .where(TestArtifact.id == artifact.id, TestArtifact.current_revision == expected_revision)
        .values(current_revision=new_no, updated_at=func.now())
    )
    if result_update.rowcount != 1:
        actual = db.execute(
            select(TestArtifact.current_revision).where(TestArtifact.id == artifact.id)
        ).scalar()
        raise RevisionConflictError(expected_revision, actual if actual is not None else 0)
    artifact.current_revision = new_no  # 同步 ORM 状态
    return {
        "artifact_id": artifact.id,
        "expected_revision": expected_revision,
        "new_revision": new_no,
        "changed": changed,
        "revision_id": revision.id,
    }


# ── Artifact 生命周期 ──


def create_artifact(db: Session, *, requester, title: str, artifact_type: str = "test_design",
                    project_id: int | None = None,
                    actor_type: str = ACTOR_TYPE_USER, conversation_id: int | None = None,
                    run_id: int | None = None) -> TestArtifact:
    title = (title or "").strip()
    if not title:
        raise TestArtifactValidationError("title 不能为空")
    if artifact_type != "test_design":
        raise TestArtifactValidationError("首期仅支持 artifact_type=test_design")
    if project_id is not None and not can_operate_project(db, requester, project_id):
        raise TestArtifactPermissionError("没有该项目的操作权限")
    artifact = TestArtifact(
        owner_user_id=requester.id,
        project_id=project_id,
        title=title,
        artifact_type=artifact_type,
        status="active",
        current_revision=0,
        root_node_id=None,
        schema_version=1,
    )
    db.add(artifact)
    db.flush()
    # 同事务自动建立 root → Revision 1（走同一 apply 主路径，保证一致性）
    apply_operations(
        db,
        artifact_id=artifact.id,
        expected_revision=0,
        operations=[{
            "operation_type": OP_ADD_NODE,
            "parent_id": None,
            "node_type": "root",
            "title": title,
        }],
        requester=requester,
        actor_type=actor_type,
        actor_user_id=requester.id if actor_type == ACTOR_TYPE_USER else None,
        conversation_id=conversation_id,
        run_id=run_id,
        summary="创建 Artifact",
    )
    return repo.get_artifact(db, artifact.id)


def list_artifacts(db: Session, *, requester) -> list[TestArtifact]:
    rows = db.execute(
        select(TestArtifact).order_by(TestArtifact.id.desc())
    ).scalars().all()
    result = []
    for artifact in rows:
        if artifact.owner_user_id == requester.id:
            result.append(artifact)
        elif artifact.project_id is not None and can_read_project(db, requester, artifact.project_id):
            result.append(artifact)
    return result


def get_artifact(db: Session, *, artifact_id: int, requester) -> TestArtifact:
    return _load_readable(db, artifact_id, requester)


def permissions_for_artifact(db: Session, *, artifact_id: int, requester) -> frozenset[str]:
    artifact = repo.get_artifact(db, artifact_id)
    if artifact is None or not _readable(db, artifact, requester):
        return frozenset()
    permissions = {"artifact:read"}
    if _writable(db, artifact, requester):
        permissions.add("artifact:write")
    return frozenset(permissions)


def _tree_node(node: ArtifactNode) -> dict:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "title": node.title,
        "order_key": node.order_key,
        "parent_id": node.parent_id,
        "content": node.content_json,
        "source_refs": node.source_refs_json,
        "created_revision": node.created_revision,
        "children": [],
    }


def get_tree(db: Session, *, artifact_id: int, requester) -> dict:
    artifact = _load_readable(db, artifact_id, requester)
    nodes = repo.list_visible_nodes(db, artifact.id)
    items = {row.id: _tree_node(row) for row in nodes}
    for row in nodes:
        if row.parent_id is not None and row.parent_id in items:
            items[row.parent_id]["children"].append(items[row.id])
    # 构树完成后对所有层级的 children 统一按 (order_key, id) 排序，
    # 不依赖 DB 返回顺序（nested module/test_case 同样稳定有序）。
    for item in items.values():
        item["children"].sort(key=lambda child: (child["order_key"], child["id"]))
    root = None
    if artifact.root_node_id is not None and artifact.root_node_id in items:
        root = items[artifact.root_node_id]
    return {"artifact_id": artifact.id, "current_revision": artifact.current_revision, "root": root}


def get_nodes(db: Session, *, artifact_id: int, node_ids: list[int], requester,
              max_nodes: int = 20) -> list[dict]:
    """Read a bounded, caller-ordered set of visible nodes."""
    artifact = _load_readable(db, artifact_id, requester)
    if not isinstance(node_ids, list) or not node_ids or len(node_ids) > max_nodes:
        raise TestArtifactValidationError(f"node_ids 必须包含 1～{max_nodes} 个节点")
    if any(type(node_id) is not int or node_id <= 0 for node_id in node_ids):
        raise TestArtifactValidationError("node_ids 必须为正整数")
    if len(set(node_ids)) != len(node_ids):
        raise TestArtifactValidationError("node_ids 不允许重复")
    rows = {row.id: row for row in repo.list_visible_nodes(db, artifact.id)}
    if any(node_id not in rows for node_id in node_ids):
        raise TestArtifactValidationError("节点不存在、已删除或不属于该 Artifact")
    return [node_snapshot(rows[node_id]) | {"created_revision": rows[node_id].created_revision}
            for node_id in node_ids]


def search_nodes(db: Session, *, artifact_id: int, requester, keyword: str | None = None,
                 node_type: str | None = None, tag: str | None = None,
                 limit: int = 20) -> list[dict]:
    """Deterministic bounded search; no embeddings or external index."""
    artifact = _load_readable(db, artifact_id, requester)
    if not 1 <= limit <= 50:
        raise TestArtifactValidationError("limit 必须在 1～50 之间")
    if node_type is not None and node_type not in NODE_TYPES:
        raise TestArtifactValidationError("node_type 无效")
    needle = (keyword or "").strip().casefold()
    wanted_tag = (tag or "").strip().casefold()
    if not needle and not node_type and not wanted_tag:
        raise TestArtifactValidationError("keyword、node_type、tag 至少提供一个")
    matches: list[ArtifactNode] = []
    for row in repo.list_visible_nodes(db, artifact.id):
        content = row.content_json if isinstance(row.content_json, dict) else {}
        tags = content.get("tags") if isinstance(content.get("tags"), list) else []
        haystack = f"{row.title} {json.dumps(content, ensure_ascii=False, sort_keys=True)}".casefold()
        if needle and needle not in haystack:
            continue
        if node_type and row.node_type != node_type:
            continue
        if wanted_tag and not any(isinstance(item, str) and item.casefold() == wanted_tag for item in tags):
            continue
        matches.append(row)
    matches.sort(key=lambda row: (row.order_key, row.id))
    return [{"id": row.id, "node_type": row.node_type, "title": row.title,
             "parent_id": row.parent_id, "order_key": row.order_key,
             "created_revision": row.created_revision}
            for row in matches[:limit]]


def get_delete_impact(db: Session, *, artifact_id: int, node_id: int, requester) -> dict:
    artifact = _load_readable(db, artifact_id, requester)
    node = _require_visible_node(db, artifact, node_id, what="节点")
    descendants = _descendant_ids(db, artifact, node.id)
    rows = {row.id: row for row in repo.list_visible_nodes(db, artifact.id)}
    summary: dict[str, int] = {}
    for affected_id in [node.id, *descendants]:
        kind = rows[affected_id].node_type
        summary[kind] = summary.get(kind, 0) + 1
    return {
        "target_node_id": node.id,
        "descendant_count": len(descendants),
        "total_affected_nodes": len(descendants) + 1,
        "node_types": dict(sorted(summary.items())),
    }


def get_recent_diff(db: Session, *, artifact_id: int, requester,
                    revision_count: int = 1) -> dict:
    artifact = _load_readable(db, artifact_id, requester)
    if not 1 <= revision_count <= 10:
        raise TestArtifactValidationError("revision_count 必须在 1～10 之间")
    to_revision = artifact.current_revision
    from_revision = max(0, to_revision - revision_count)
    return get_diff(db, artifact_id=artifact.id, from_revision=from_revision,
                    to_revision=to_revision, requester=requester)


# ── Project Functional Artifact & Default Module（P09.1） ──


def get_project_functional_artifact(db: Session, *, project_id: int, requester) -> TestArtifact | None:
    """项目的主 Functional TestArtifact；未创建返回 None。"""
    row = db.execute(
        select(TestArtifact).where(
            TestArtifact.project_id == project_id,
            TestArtifact.artifact_type == FUNCTIONAL_ARTIFACT_TYPE,
        ).order_by(TestArtifact.id.asc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return _load_readable(db, row.id, requester)


def ensure_project_functional_artifact(db: Session, *, project_id: int, requester,
                                       title: str | None = None) -> TestArtifact:
    """确保项目存在唯一主 Functional TestArtifact（含 root）。

    并发安全：同一 (project_id, artifact_type) 由 DB 唯一约束裁决，
    冲突方回滚后读取既有 Artifact 返回（不使用 Python 全局锁）。
    """
    existing = get_project_functional_artifact(db, project_id=project_id, requester=requester)
    if existing is not None:
        return existing
    try:
        artifact = create_artifact(
            db, requester=requester, title=(title or "功能测试").strip() or "功能测试",
            artifact_type=FUNCTIONAL_ARTIFACT_TYPE, project_id=project_id,
        )
        db.commit()
        return artifact
    except IntegrityError:
        db.rollback()
        existing = get_project_functional_artifact(db, project_id=project_id, requester=requester)
        if existing is not None:
            return existing
        raise TestArtifactDataError("并发创建主 Functional Artifact 失败，请重试") from None


def get_or_create_default_module(db: Session, *, artifact_id: int, requester) -> ArtifactNode:
    """每个 Artifact 至多一个一级「默认模块」；缺少时用一次 Revision 创建。

    并发安全：复用 revision 条件写裁决——两个并发创建者只有一方成功；
    冲突方回滚后读取既有默认模块返回（循环上限 2 次）。
    """
    for attempt in range(2):
        artifact = _load_writable(db, artifact_id, requester)
        existing = db.execute(
            select(ArtifactNode).where(
                ArtifactNode.artifact_id == artifact.id,
                ArtifactNode.node_type == NODE_TYPE_MODULE,
                ArtifactNode.parent_id == artifact.root_node_id,
                ArtifactNode.title == DEFAULT_MODULE_TITLE,
                ArtifactNode.deleted_revision.is_(None),
            ).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        try:
            apply_operations(
                db,
                artifact_id=artifact.id,
                expected_revision=artifact.current_revision,
                operations=[{
                    "operation_type": OP_ADD_NODE,
                    "parent_id": artifact.root_node_id,
                    "node_type": NODE_TYPE_MODULE,
                    "title": DEFAULT_MODULE_TITLE,
                }],
                requester=requester,
                summary="确保默认模块",
            )
            db.commit()
            return db.execute(
                select(ArtifactNode).where(
                    ArtifactNode.artifact_id == artifact.id,
                    ArtifactNode.node_type == NODE_TYPE_MODULE,
                    ArtifactNode.parent_id == artifact.root_node_id,
                    ArtifactNode.title == DEFAULT_MODULE_TITLE,
                    ArtifactNode.deleted_revision.is_(None),
                ).limit(1)
            ).scalar_one()
        except RevisionConflictError:
            db.rollback()
            continue
    raise TestArtifactDataError("并发创建默认模块失败，请重试") from None


# ── Revision / Diff ──


def list_revisions(db: Session, *, artifact_id: int, requester) -> list[ArtifactRevision]:
    _load_readable(db, artifact_id, requester)
    return repo.list_revisions(db, artifact_id)


def get_revision(db: Session, *, artifact_id: int, revision_no: int, requester) -> tuple[ArtifactRevision, list[ArtifactOperation]]:
    _load_readable(db, artifact_id, requester)
    revision = repo.get_revision(db, artifact_id, revision_no)
    if revision is None:
        raise TestArtifactNotFoundError("Revision 不存在")
    return revision, repo.list_operations_for_revision(db, revision.id)


def get_diff(db: Session, *, artifact_id: int, from_revision: int, to_revision: int,
             requester) -> dict:
    artifact = _load_readable(db, artifact_id, requester)
    if from_revision < 0 or to_revision > artifact.current_revision or from_revision >= to_revision:
        raise TestArtifactValidationError("diff 区间无效：0 <= from < to <= current_revision")
    ops = repo.list_operations_range(db, artifact.id, from_revision, to_revision)
    return {
        "artifact_id": artifact.id,
        "from_revision": from_revision,
        "to_revision": to_revision,
        "changes": diff_mod.derive_changes(ops),
    }


# ── Undo / Restore（反向 Revision，不删历史） ──


def _reconcile_to(db: Session, *, artifact: TestArtifact, target_revision: int, requester,
                  action_summary: str) -> dict:
    """把树对齐到 target_revision 的状态，产出一个新 Revision（不删任何历史）。"""
    previous_revision = artifact.current_revision
    ops_history = repo.list_operations_upto(db, artifact.id, target_revision)
    desired = diff_mod.visible_entries(diff_mod.replay_to_state(ops_history))
    current_rows = repo.list_visible_nodes(db, artifact.id)
    current = diff_mod.visible_entries(diff_mod.state_from_rows(current_rows))
    plan = _plan_reconcile(current, desired)
    if not plan:
        # 目标态与当前态一致：no-op，不产生空 Revision，也不 400
        return {
            "artifact_id": artifact.id,
            "previous_revision": previous_revision,
            "new_revision": previous_revision,
            "changed": 0,
            "summary": action_summary,
        }
    result = apply_operations(
        db,
        artifact_id=artifact.id,
        expected_revision=previous_revision,
        operations=plan,
        requester=requester,
        actor_type=ACTOR_TYPE_USER,
        actor_user_id=requester.id,
        summary=action_summary,
        enforce_requirement_live=False,  # P08.2：恢复历史 provenance，不要求 Requirement 当前存活
    )
    return {
        "artifact_id": artifact.id,
        "previous_revision": previous_revision,
        "new_revision": result["new_revision"],
        "changed": result["changed"],
        "summary": action_summary,
    }


def undo_latest(db: Session, *, artifact_id: int, requester) -> dict:
    artifact = _load_writable(db, artifact_id, requester)
    if artifact.current_revision <= 1:
        raise TestArtifactValidationError("没有可撤销的修订（仅剩根创建 Revision 1）")
    return _reconcile_to(
        db, artifact=artifact, target_revision=artifact.current_revision - 1, requester=requester,
        action_summary=f"撤销修订 {artifact.current_revision}",
    )


def restore_revision(db: Session, *, artifact_id: int, target_revision: int, requester) -> dict:
    artifact = _load_writable(db, artifact_id, requester)
    if target_revision < 1 or target_revision >= artifact.current_revision:
        raise TestArtifactValidationError(
            f"restore 目标必须在 [1, {artifact.current_revision}) 之间"
        )
    return _reconcile_to(
        db, artifact=artifact, target_revision=target_revision, requester=requester,
        action_summary=f"恢复到修订 {target_revision}",
    )


def _plan_reconcile(current: dict[int, dict], desired: dict[int, dict]) -> list[dict]:
    """由 当前可见态 → 目标态 规划一个规范化 operation batch。"""
    ops: list[dict] = []
    cur_ids = set(current)
    des_ids = set(desired)
    to_delete = cur_ids - des_ids
    to_restore = des_ids - cur_ids
    common = cur_ids & des_ids

    # 1) 恢复：以“目标父链不在待恢复集”的顶层节点为单位
    if to_restore:
        root_of: dict[int, int] = {}
        for nid in to_restore:
            p = nid
            guard = set()
            while desired[p].get("parent_id") in to_restore:
                if p in guard:
                    break
                guard.add(p)
                p = desired[p]["parent_id"]
            root_of[nid] = p
        for top in sorted({v for v in root_of.values()}):
            subtree_ids = sorted(
                (n for n, r in root_of.items() if r == top),
                key=lambda n: (desired[n]["parent_id"] is None, n),
            )
            # 按目标树 DFS 排序
            ordered = _topo_by_desired(desired, top, set(subtree_ids))
            nodes = [{k: desired[sid].get(k) for k in
                      ("id", "parent_id", "order_key", "node_type", "title", "content", "source_refs")}
                     for sid in ordered]
            ops.append({"operation_type": OP_RESTORE, "target_node_id": top, "nodes": nodes})

    # 2) move：仅 common 中 parent/order 变化；目标父先于子（按目标深度升序）
    depth = _desired_depth(desired)
    moved = [
        n for n in common
        if (current[n].get("parent_id"), current[n].get("order_key"))
        != (desired[n].get("parent_id"), desired[n].get("order_key"))
    ]
    for nid in sorted(moved, key=lambda n: (depth[n], n)):
        ops.append({
            "operation_type": OP_MOVE_NODE,
            "target_node_id": nid,
            "new_parent_id": desired[nid].get("parent_id"),
            "new_order_key": desired[nid].get("order_key"),
        })

    # 3) update：内容/标题/来源差异
    for nid in sorted(common, key=lambda n: (depth[n], n)):
        patch: dict = {}
        if desired[nid].get("title") != current[nid].get("title"):
            patch["title"] = desired[nid].get("title")
        if desired[nid].get("content") != current[nid].get("content"):
            patch["content"] = desired[nid].get("content")
        if desired[nid].get("source_refs") != current[nid].get("source_refs"):
            patch["source_refs"] = desired[nid].get("source_refs")
        if patch:
            ops.append({"operation_type": OP_UPDATE_NODE, "target_node_id": nid, "patch": patch})

    # 4) delete：仅删除顶层目标（子孙随子树逻辑删除一起处理）
    deletion_roots = sorted(
        n for n in to_delete
        if current[n].get("parent_id") is None or current[n].get("parent_id") not in to_delete
    )
    for nid in deletion_roots:
        ops.append({"operation_type": OP_DELETE_NODE, "target_node_id": nid})
    return ops


def _topo_by_desired(desired: dict[int, dict], top: int, subtree: set[int]) -> list[int]:
    children: dict[int | None, list[int]] = {}
    for nid in subtree:
        children.setdefault(desired[nid].get("parent_id"), []).append(nid)
    for key in children:
        children[key].sort(key=lambda n: (desired[n].get("order_key") or 0, n))
    ordered: list[int] = []

    def walk(node_id: int) -> None:
        ordered.append(node_id)
        for child in children.get(node_id, []):
            walk(child)

    walk(top)
    return ordered


def _desired_depth(desired: dict[int, dict]) -> dict[int, int]:
    depth: dict[int, int] = {}
    cache: dict[int, int] = {}

    def get_depth(nid: int) -> int:
        if nid in cache:
            return cache[nid]
        parent = desired[nid].get("parent_id")
        if parent is None:
            cache[nid] = 0
        else:
            cache[nid] = get_depth(parent) + 1
        return cache[nid]

    for nid in desired:
        depth[nid] = get_depth(nid)
    return depth


# 便捷引用：确保 diff 模块与 tree helper 对外可用
__all__ = [
    "create_artifact", "list_artifacts", "get_artifact", "get_tree", "apply_operations",
    "list_revisions", "get_revision", "get_diff", "undo_latest", "restore_revision",
    "node_snapshot", "get_nodes", "search_nodes", "get_delete_impact", "get_recent_diff",
    "permissions_for_artifact",
]
