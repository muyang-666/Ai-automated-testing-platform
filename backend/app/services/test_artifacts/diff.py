"""Artifact 状态回放与 Diff 派生（V2-P07 §9/§15）。

Diff 不重新比较整棵 JSON Tree：直接从 ArtifactOperation（before_json/after_json）
派生。本模块同时提供 revision 状态回放（replay_to_state），供
undo_latest / restore_revision 做“生成反向 Revision”时的目标态计算。

快照(snapshot)形状（JSON 安全，避免直接引用 ORM）：
  {id, node_type, title, content, source_refs, parent_id, order_key, deleted}
"""

from app.models.test_artifact.artifact_operation import (
    OP_ADD_NODE,
    OP_DELETE_NODE,
    OP_MOVE_NODE,
    OP_RESTORE,
    OP_UPDATE_NODE,
)


def snapshot_from_row(row) -> dict:
    return {
        "id": row.id,
        "node_type": row.node_type,
        "title": row.title,
        "content": row.content_json,
        "source_refs": row.source_refs_json,
        "parent_id": row.parent_id,
        "order_key": row.order_key,
        "deleted": row.deleted_revision is not None,
    }


def _clone(snapshot: dict) -> dict:
    return dict(snapshot)


def state_from_rows(rows) -> dict[int, dict]:
    return {row.id: snapshot_from_row(row) for row in rows}


def visible_entries(state: dict[int, dict]) -> dict[int, dict]:
    return {nid: snap for nid, snap in state.items() if not snap.get("deleted")}


def _payload_of(op) -> dict:
    return op.payload_json if isinstance(op.payload_json, dict) else {}


def _after_of(op):
    return op.after_json


def apply_operations_to_state(state: dict[int, dict], ops) -> dict[int, dict]:
    """在给定 state 上回放一批 Operation（按 revision_no/op_index 已排序）。

    供 replay_to_state 与 diff 复用；原地修改并返回 state。
    """
    for op in ops:
        t = op.operation_type
        after = _after_of(op)
        if t == OP_ADD_NODE:
            snap = dict(after)
            snap["deleted"] = False
            state[snap["id"]] = snap
        elif t == OP_UPDATE_NODE:
            if op.target_node_id in state:
                merged = dict(state[op.target_node_id])
                merged.update(dict(after))
                merged["deleted"] = False
                state[op.target_node_id] = merged
        elif t == OP_MOVE_NODE:
            if op.target_node_id in state:
                merged = dict(state[op.target_node_id])
                merged.update(dict(after or {}))
                state[op.target_node_id] = merged
        elif t == OP_DELETE_NODE:
            for node_id in (_payload_of(op).get("affected_node_ids") or []):
                if node_id in state:
                    state[node_id] = dict(state[node_id])
                    state[node_id]["deleted"] = True
        elif t == OP_RESTORE:
            for snap in (after if isinstance(after, list) else []):
                restored = dict(snap)
                restored["deleted"] = False
                state[restored["id"]] = restored
    return state


def replay_to_state(ops) -> dict[int, dict]:
    """从空状态回放 ops（覆盖 revision 1..N 的历史）得到某个 revision 的快照集。"""
    return apply_operations_to_state({}, list(ops))


def derive_changes(ops) -> list[dict]:
    """由 (from, to] 区间的 Operation 派生 diff changes（added/updated/deleted/moved）。"""
    changes: list[dict] = []
    for op in ops:
        t = op.operation_type
        payload = _payload_of(op)
        before = op.before_json if isinstance(op.before_json, dict) else {}
        after = _after_of(op)
        if t == OP_ADD_NODE:
            snap = dict(after or {})
            changes.append({
                "change": "added",
                "node_id": op.target_node_id,
                "parent_id": snap.get("parent_id"),
                "node_type": snap.get("node_type"),
                "title": snap.get("title"),
            })
        elif t == OP_UPDATE_NODE:
            fields = {}
            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
            for key in patch.keys():
                fields[key] = {"before": before.get(key), "after": after.get(key)}
            changes.append({"change": "updated", "node_id": op.target_node_id,
                            "node_type": after.get("node_type"),
                            "title": after.get("title"), "fields": fields or None})
        elif t == OP_MOVE_NODE:
            changes.append({
                "change": "moved",
                "node_id": op.target_node_id,
                "before": {"parent_id": before.get("parent_id"), "order_key": before.get("order_key")},
                "after": {"parent_id": after.get("parent_id"), "order_key": after.get("order_key")},
            })
        elif t == OP_DELETE_NODE:
            changes.append({
                "change": "deleted",
                "node_id": op.target_node_id,
                "node_type": before.get("node_type"),
                "title": before.get("title"),
                "descendant_count": payload.get("descendant_count"),
            })
        elif t == OP_RESTORE:
            for snap in (after if isinstance(after, list) else []):
                changes.append({
                    "change": "added",
                    "node_id": snap.get("id"),
                    "parent_id": snap.get("parent_id"),
                    "node_type": snap.get("node_type"),
                    "title": snap.get("title"),
                })
    return changes
