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

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

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

NODE_TYPES = ("root", "group", "test_point", "test_case")

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


def _require_visible_node(db: Session, artifact: TestArtifact, node_id: int | None, *, what: str) -> ArtifactNode:
    node = repo.get_node(db, node_id) if node_id is not None else None
    if node is None or node.artifact_id != artifact.id or node.deleted_revision is not None:
        raise TestArtifactValidationError(f"{what} 不存在、已删除或不属于该 Artifact")
    return node


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
    source_refs = _validated_refs(request.get("source_refs"))
    order_key = request.get("order_key")

    if node_type == "root":
        if parent_id is not None:
            raise TestArtifactValidationError("root 节点的 parent_id 必须为空")
        _ensure_root_available(db, artifact)
        parent_row = None
    else:
        if parent_id is None:
            raise TestArtifactValidationError("非 root 节点必须提供 parent_id")
        parent_row = _require_visible_node(db, artifact, parent_id, what="父节点")
        if parent_row.node_type == NODE_TYPE_TEST_CASE:
            raise TestArtifactValidationError("test_case 节点不能作为父节点")
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


def _apply_update(db: Session, artifact: TestArtifact, request: dict) -> dict:
    node = _require_visible_node(db, artifact, request.get("target_node_id"), what="节点")
    patch = request.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise TestArtifactValidationError("update_node 必须提供非空 patch")
    for key in patch:
        if key in SERVER_CONTROLLED_FIELDS:
            raise TestArtifactValidationError(f"服务端控制字段不可被客户端 patch: {key}")
        if key not in WRITABLE_NODE_FIELDS:
            raise TestArtifactValidationError(f"不可 patch 的字段: {key}")
    before = node_snapshot(node)
    if "title" in patch:
        value = patch["title"]
        if not isinstance(value, str) or not value:
            raise TestArtifactValidationError("title 必须为非空字符串")
        node.title = value
    if "content" in patch:
        node.content_json = _validated_content(node.node_type, patch["content"])
    if "source_refs" in patch:
        node.source_refs_json = _validated_refs(patch["source_refs"])
    db.flush()
    return {"target_node_id": node.id, "payload": {"patch": patch}, "before": before, "after": node_snapshot(node)}


def _apply_move(db: Session, artifact: TestArtifact, request: dict) -> dict:
    node = _require_visible_node(db, artifact, request.get("target_node_id"), what="节点")
    if node.node_type == "root":
        raise TestArtifactValidationError("root 节点不可移动")
    new_parent_id = request.get("new_parent_id")
    if new_parent_id is None:
        raise TestArtifactValidationError("move_node 必须提供 new_parent_id")
    new_parent = _require_visible_node(db, artifact, new_parent_id, what="目标父节点")
    if new_parent.node_type == NODE_TYPE_TEST_CASE:
        raise TestArtifactValidationError("test_case 节点不能作为父节点")
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


def _apply_restore(db: Session, artifact: TestArtifact, request: dict) -> dict:
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
    # 完整性：父引用必须指向“本批恢复节点”或“当前存活节点”，且不得指向自身
    allowed_parents = set(ids) | visible_ids
    for snap in raw_nodes:
        parent = snap.get("parent_id")
        snap_id = int(snap["id"])
        if parent is not None and parent not in allowed_parents:
            raise TestArtifactValidationError("restore 父节点不存在/已删除/跨 Artifact")
        if parent == snap_id:
            raise TestArtifactValidationError("restore 节点不能以自身为父节点")
        row = by_id[snap_id]
        if row.node_type == NODE_TYPE_TEST_CASE and parent is not None:
            parent_row = by_id.get(parent)
            if parent_row is not None and parent_row.node_type == NODE_TYPE_TEST_CASE:
                raise TestArtifactValidationError("test_case 节点不能作为父节点")
        if not isinstance(snap.get("title"), str):
            raise TestArtifactValidationError("restore 快照缺少合法 title")
        _validated_content(row.node_type, snap.get("content"))  # 防御：快照内容必须匹配节点类型
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
        row.source_refs_json = _validated_refs(snap.get("source_refs"))
    db.flush()
    after = [node_snapshot(restored_by_id[sid]) for sid in ids]
    return {"target_node_id": target_id, "payload": {"affected_node_ids": ids}, "before": None, "after": after}


# ── 主写入口 ──

_ACTOR_TYPE_VALUES = ("user", "agent", "system")


def apply_operations(db: Session, *, artifact_id: int, expected_revision: int,
                     operations: list[dict], requester, actor_type: str = ACTOR_TYPE_USER,
                     actor_user_id: int | None = None, conversation_id: int | None = None,
                     run_id: int | None = None, summary: str | None = None) -> dict:
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

    changed = 0
    ref_to_node: dict[str, int] = {}  # 批内引用：add_node 可携带 ref，后续 op 用 "@ref" 引用其 id
    for index, request in enumerate(operations):
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
            result = _apply_update(db, artifact, work)
        elif op_type == OP_MOVE_NODE:
            result = _apply_move(db, artifact, work)
        elif op_type == OP_DELETE_NODE:
            result = _apply_delete(db, artifact, new_no, work)
        elif op_type == OP_RESTORE:
            result = _apply_restore(db, artifact, work)
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
    for row in nodes:
        if row.parent_id is None or row.parent_id not in items:
            items[row.id]["children"].sort(key=lambda n: (n["order_key"], n["id"]))
    root = None
    if artifact.root_node_id is not None and artifact.root_node_id in items:
        root = items[artifact.root_node_id]
    return {"artifact_id": artifact.id, "current_revision": artifact.current_revision, "root": root}


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
    "node_snapshot",
]
