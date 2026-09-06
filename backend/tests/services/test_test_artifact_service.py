"""TestArtifact Application Service 确定性测试（V2-P07 §27/§28）。

全部使用 SQLite（conftest 已强制）+ 直接 Service 调用：不启动 Worker、不调用 LLM。
覆盖 §27 的 32 项清单与 §28 的完整 P07 E2E（Revision 1..7）。
"""

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.project import Project
from app.models.role import Role
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.test_artifact.artifact_operation import ArtifactOperation
from app.models.test_artifact.artifact_revision import ArtifactRevision
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.services.test_artifacts import artifact_service
# 以非 "Test" 前缀的别名导入：避免 pytest 把领域异常类当测试类收集
from app.services.test_artifacts.errors import (
    RevisionConflictError,
    TestArtifactNotFoundError as ArtifactNotFoundError,
    TestArtifactPermissionError as ArtifactPermissionError,
    TestArtifactValidationError as ArtifactValidationError,
)

USER_A = 101
USER_B = 102
VIEWER = 103
PROJECT_P = 201


def _seed(db):
    for code in ("system_admin", "tester", "viewer"):
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(code=code, name=code, status="active"))
    db.flush()
    roles = {r.code: r for r in db.query(Role).all()}

    def user(uid, username, role_code):
        row = db.query(User).filter(User.id == uid).first()
        if row is None:
            row = User(id=uid, username=username, password_hash="x", salt="y",
                       status="active", is_deleted=False)
            db.add(row)
            db.flush()
        if not db.query(UserRole).filter(UserRole.user_id == uid).first():
            db.add(UserRole(user_id=uid, role_id=roles[role_code].id))
        return row

    a = user(USER_A, "artifact_a", "tester")
    user(USER_B, "artifact_b", "tester")
    user(VIEWER, "artifact_viewer", "viewer")
    if not db.query(Project).filter(Project.id == PROJECT_P).first():
        db.add(Project(id=PROJECT_P, name="项目P", status="active", is_deleted=False))
    if not db.query(UserProjectPermission).filter(
            UserProjectPermission.user_id == USER_A,
            UserProjectPermission.project_id == PROJECT_P).first():
        db.add(UserProjectPermission(user_id=USER_A, project_id=PROJECT_P, can_operate=True))
    db.commit()
    return a


def _user(db, uid):
    return db.get(User, uid)


def _create(db, user, title="登录测试", project_id=None):
    artifact = artifact_service.create_artifact(db, requester=user, title=title,
                                                project_id=project_id)
    db.commit()
    return artifact


def _apply(db, artifact_id, expected, ops, user):
    result = artifact_service.apply_operations(
        db, artifact_id=artifact_id, expected_revision=expected,
        operations=ops, requester=user)
    db.commit()
    return result


def _add_op(parent_id, node_type, title, content=None, source_refs=None, ref=None,
            order_key=None):
    op = {"operation_type": "add_node", "parent_id": parent_id,
          "node_type": node_type, "title": title}
    if content is not None:
        op["content"] = content
    if source_refs is not None:
        op["source_refs"] = source_refs
    if ref is not None:
        op["ref"] = ref
    if order_key is not None:
        op["order_key"] = order_key
    return op


def _node(db, artifact_id, title):
    return db.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact_id, ArtifactNode.title == title).one()


def _visible_titles(db, artifact_id):
    return sorted(n.title for n in
                  db.query(ArtifactNode)
                  .filter(ArtifactNode.artifact_id == artifact_id,
                          ArtifactNode.deleted_revision.is_(None)).all())


def _revision_nos(db, artifact_id):
    return [r.revision_no for r in artifact_service.list_revisions(
        db, artifact_id=artifact_id, requester=_user(db, USER_A))]


# ── Artifact（1-3） ──


def test_01_create_artifact_auto_root(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a, title="登录测试")
    assert artifact.title == "登录测试"
    assert artifact.artifact_type == "test_design"
    assert artifact.status == "active"
    assert artifact.current_revision == 1
    assert artifact.root_node_id is not None


def test_02_auto_root_is_revision_1_with_add_operation(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    revision = db_session.query(ArtifactRevision).filter(
        ArtifactRevision.artifact_id == artifact.id).one()
    assert revision.revision_no == 1
    assert revision.base_revision == 0
    ops = db_session.query(ArtifactOperation).filter(
        ArtifactOperation.revision_id == revision.id).all()
    assert len(ops) == 1 and ops[0].operation_type == "add_node"
    root = db_session.get(ArtifactNode, artifact.root_node_id)
    assert root.node_type == "root"
    assert root.parent_id is None
    assert root.created_revision == 1


def test_03_list_and_owner_isolation(db_session):
    a = _seed(db_session)
    b = _user(db_session, USER_B)
    artifact_a = _create(db_session, a)
    assert [x.id for x in artifact_service.list_artifacts(db_session, requester=a)] == [artifact_a.id]
    assert artifact_service.list_artifacts(db_session, requester=b) == []
    with pytest.raises(ArtifactNotFoundError):
        artifact_service.get_artifact(db_session, artifact_id=artifact_a.id, requester=b)


# ── Node CRUD（4-9） ──


def test_04_add_group_under_root(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    result = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "group", "功能")], a)
    assert result["new_revision"] == 2
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    assert tree["current_revision"] == 2
    assert [c["title"] for c in tree["root"]["children"]] == ["功能"]
    assert tree["root"]["children"][0]["node_type"] == "group"


def test_05_add_test_point_under_group(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "group", "功能")], a)
    group = _node(db_session, artifact.id, "功能")
    _apply(db_session, artifact.id, r2["new_revision"],
           [_add_op(group.id, "test_point", "正常登录")], a)
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    assert tree["root"]["children"][0]["children"][0]["node_type"] == "test_point"


def test_06_add_test_case_with_content_validation(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_point", "正常登录")], a)
    point = _node(db_session, artifact.id, "正常登录")
    content = {
        "preconditions": ["账号存在且未锁定"],
        "steps": [{"action": "输入账号", "data": "user@example.com"},
                  {"action": "输入错误密码"}],
        "expected_results": ["登录失败", "失败次数增加"],
        "priority": "P1",
        "tags": ["异常", "状态"],
    }
    _apply(db_session, artifact.id, r2["new_revision"],
           [_add_op(point.id, "test_case", "TC001", content=content)], a)
    case = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id,
        ArtifactNode.node_type == "test_case").one()
    assert case.content_json["priority"] == "P1"
    assert case.content_json["steps"][1]["action"] == "输入错误密码"
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, 3,
               [_add_op(point.id, "test_case", "TC-BAD", content={"steps": "x"})], a)
    db_session.rollback()


def test_07_update_node_title_and_content(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(
        artifact.root_node_id, "test_case", "TC001", content={"priority": "P2"})], a)
    case = _node(db_session, artifact.id, "TC001")
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [{
        "operation_type": "update_node", "target_node_id": case.id,
        "patch": {"title": "TC001-改名", "content": {"priority": "P1", "tags": ["边界"]}},
    }], a)
    assert r3["new_revision"] == 3
    refreshed = db_session.get(ArtifactNode, case.id)
    assert refreshed.title == "TC001-改名"
    assert refreshed.content_json["priority"] == "P1"
    assert refreshed.content_json["tags"] == ["边界"]


def test_08_move_node_reparent_and_order(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [
        _add_op(artifact.root_node_id, "group", "G1"),
        _add_op(artifact.root_node_id, "group", "G2")], a)
    g1 = _node(db_session, artifact.id, "G1")
    g2 = _node(db_session, artifact.id, "G2")
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [_add_op(g1.id, "test_case", "TC-X")], a)
    tc = _node(db_session, artifact.id, "TC-X")
    _apply(db_session, artifact.id, r3["new_revision"], [{
        "operation_type": "move_node", "target_node_id": tc.id,
        "new_parent_id": g2.id, "new_order_key": 1,
    }], a)
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    g1_node = next(c for c in tree["root"]["children"] if c["title"] == "G1")
    g2_node = next(c for c in tree["root"]["children"] if c["title"] == "G2")
    assert g1_node["children"] == []
    assert [c["title"] for c in g2_node["children"]] == ["TC-X"]
    tc_row = db_session.get(ArtifactNode, tc.id)
    assert tc_row.parent_id == g2.id and tc_row.order_key == 1


def test_09_delete_subtree_is_logical(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "group", "锁定")], a)
    gid = _node(db_session, artifact.id, "锁定").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [
        _add_op(gid, "test_point", "TP_LOCK"),
        _add_op(gid, "test_point", "TP2"),
    ], a)
    tp = _node(db_session, artifact.id, "TP_LOCK").id
    r4 = _apply(db_session, artifact.id, r3["new_revision"], [
        _add_op(tp, "test_case", "TC001"), _add_op(tp, "test_case", "TC002")], a)
    _apply(db_session, artifact.id, r4["new_revision"],
           [{"operation_type": "delete_node", "target_node_id": tp}], a)
    flagged = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id,
        ArtifactNode.deleted_revision.isnot(None)).all()
    assert len(flagged) == 3  # TP_LOCK + TC001 + TC002
    assert all(row.deleted_revision == 5 for row in flagged)
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    lock_group = next(c for c in tree["root"]["children"] if c["title"] == "锁定")
    assert [c["title"] for c in lock_group["children"]] == ["TP2"]


# ── Tree integrity（10-14 + 父类型规则） ──


def test_10_second_root_rejected(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, 1, [
            {"operation_type": "add_node", "parent_id": None,
             "node_type": "root", "title": "第二个root"}], a)
    db_session.rollback()


def test_11_cross_artifact_parent_rejected(db_session):
    a = _seed(db_session)
    art1 = _create(db_session, a, title="A1")
    art2 = _create(db_session, a, title="A2")
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, art2.id, 1,
               [_add_op(art1.root_node_id, "group", "跨库组")], a)
    db_session.rollback()


def test_12_cycle_rejected(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "group", "G1")], a)
    g1 = _node(db_session, artifact.id, "G1")
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [_add_op(g1.id, "test_point", "P1")], a)
    p1 = _node(db_session, artifact.id, "P1")
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r3["new_revision"], [{
            "operation_type": "move_node", "target_node_id": g1.id,
            "new_parent_id": p1.id,
        }], a)
    db_session.rollback()


def test_13_deleted_parent_rejected(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_point", "P1")], a)
    p1 = _node(db_session, artifact.id, "P1").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": p1}], a)
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r3["new_revision"],
               [_add_op(p1, "test_case", "孤儿")], a)
    db_session.rollback()


def test_14_root_delete_and_move_rejected(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    root_id = artifact.root_node_id
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, 1,
               [{"operation_type": "delete_node", "target_node_id": root_id}], a)
    db_session.rollback()
    r2 = _apply(db_session, artifact.id, 1, [_add_op(root_id, "group", "G1")], a)
    g1 = _node(db_session, artifact.id, "G1").id
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r2["new_revision"], [{
            "operation_type": "move_node", "target_node_id": root_id,
            "new_parent_id": g1,
        }], a)
    db_session.rollback()


def test_14b_test_case_cannot_be_parent(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_case", "TC1")], a)
    tc = _node(db_session, artifact.id, "TC1").id
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r2["new_revision"],
               [_add_op(tc, "test_case", "TC2")], a)
    db_session.rollback()


# ── Revision（15-17） ──


def test_15_every_batch_exactly_one_revision(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    result = _apply(db_session, artifact.id, 1, [
        _add_op(artifact.root_node_id, "group", "G1"),
        _add_op(artifact.root_node_id, "group", "G2"),
    ], a)
    assert result["changed"] == 2
    assert db_session.query(ArtifactRevision).filter(
        ArtifactRevision.artifact_id == artifact.id).count() == 2  # root + 本批
    ops = db_session.query(ArtifactOperation).filter(
        ArtifactOperation.revision_id == result["revision_id"]).all()
    assert [o.op_index for o in ops] == [0, 1]
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 2


def test_16_sequential_revision_no(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    current = 1
    for index in range(3):
        current = _apply(db_session, artifact.id, current,
                         [_add_op(artifact.root_node_id, "test_case", f"TC-{index}")], a)["new_revision"]
    assert _revision_nos(db_session, artifact.id) == [1, 2, 3, 4]


def test_17_operation_order_stable(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r = _apply(db_session, artifact.id, 1, [
        _add_op(artifact.root_node_id, "test_case", "TC-2"),
        _add_op(artifact.root_node_id, "test_case", "TC-1"),
    ], a)
    _, ops = artifact_service.get_revision(
        db_session, artifact_id=artifact.id, revision_no=r["new_revision"], requester=a)
    assert [op.op_index for op in ops] == [0, 1]
    assert [op.after_json["title"] for op in ops] == ["TC-2", "TC-1"]


# ── Atomicity（18） ──


def test_18_batch_rollback_when_third_operation_fails(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, 1, [
            _add_op(artifact.root_node_id, "test_case", "TC001"),
            _add_op(artifact.root_node_id, "test_case", "TC002"),
            {"operation_type": "move_node", "target_node_id": 999999,
             "new_parent_id": artifact.root_node_id},
        ], a)
    db_session.rollback()
    assert _visible_titles(db_session, artifact.id) == ["登录测试"]
    assert db_session.query(ArtifactRevision).filter(
        ArtifactRevision.artifact_id == artifact.id).count() == 1
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 1


# ── Diff（19-22） ──


def test_19_diff_add(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "group", "功能")], a)
    diff = artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                     from_revision=1, to_revision=r["new_revision"], requester=a)
    assert diff["from_revision"] == 1 and diff["to_revision"] == 2
    change = diff["changes"][0]
    assert change["change"] == "added"
    assert change["parent_id"] == artifact.root_node_id
    assert change["node_type"] == "group" and change["title"] == "功能"


def test_20_diff_update_field(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(
        artifact.root_node_id, "test_case", "TC001",
        content={"priority": "P1", "expected_results": ["锁定后无法登录"]})], a)
    tc = _node(db_session, artifact.id, "TC001").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [{
        "operation_type": "update_node", "target_node_id": tc,
        "patch": {"content": {"priority": "P1",
                              "expected_results": ["锁定期间正确密码仍无法登录"]}},
    }], a)
    diff = artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                     from_revision=r2["new_revision"], to_revision=r3["new_revision"],
                                     requester=a)
    change = diff["changes"][0]
    assert change["change"] == "updated"
    assert change["fields"]["content"]["after"]["expected_results"] == \
        ["锁定期间正确密码仍无法登录"]
    assert change["fields"]["content"]["before"]["expected_results"] == ["锁定后无法登录"]


def test_21_diff_move(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [
        _add_op(artifact.root_node_id, "group", "G1"),
        _add_op(artifact.root_node_id, "group", "G2")], a)
    g1_id = _node(db_session, artifact.id, "G1").id
    g2_id = _node(db_session, artifact.id, "G2").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [_add_op(g1_id, "test_case", "TC-X")], a)
    tc = _node(db_session, artifact.id, "TC-X").id
    r4 = _apply(db_session, artifact.id, r3["new_revision"], [{
        "operation_type": "move_node", "target_node_id": tc,
        "new_parent_id": g2_id, "new_order_key": 5,
    }], a)
    diff = artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                     from_revision=r3["new_revision"], to_revision=r4["new_revision"],
                                     requester=a)
    change = diff["changes"][0]
    assert change["change"] == "moved"
    assert change["before"] == {"parent_id": g1_id, "order_key": 1}
    assert change["after"] == {"parent_id": g2_id, "order_key": 5}


def test_22_diff_delete_subtree(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_point", "TP_LOCK")], a)
    tp = _node(db_session, artifact.id, "TP_LOCK").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [_add_op(tp, "test_case", "TC001"), _add_op(tp, "test_case", "TC002")], a)
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": tp}], a)
    diff = artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                     from_revision=r3["new_revision"], to_revision=r4["new_revision"],
                                     requester=a)
    assert diff["changes"] == [{"change": "deleted", "node_id": tp, "descendant_count": 2}]


# ── Undo / Restore（23-26） ──


def test_23_undo_latest_delete_restores_tree(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_point", "TP_LOCK")], a)
    tp = _node(db_session, artifact.id, "TP_LOCK").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [_add_op(tp, "test_case", "TC001")], a)
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": tp}], a)
    assert _visible_titles(db_session, artifact.id) == ["登录测试"]
    result = artifact_service.undo_latest(db_session, artifact_id=artifact.id, requester=a)
    db_session.commit()
    assert result["previous_revision"] == 4
    assert result["new_revision"] == 5
    assert set(_visible_titles(db_session, artifact.id)) == {"登录测试", "TC001", "TP_LOCK"}


def test_24_undo_produces_new_revision_and_keeps_history(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "test_case", "TC1")], a)
    tc = _node(db_session, artifact.id, "TC1").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [{
        "operation_type": "update_node", "target_node_id": tc, "patch": {"title": "TC1-改"},
    }], a)
    result = artifact_service.undo_latest(db_session, artifact_id=artifact.id, requester=a)
    db_session.commit()
    assert result["new_revision"] == 4
    assert _revision_nos(db_session, artifact.id) == [1, 2, 3, 4]  # 被撤销的 rev3 仍在
    assert db_session.get(ArtifactNode, tc).title == "TC1"  # 回到原名


def test_25_restore_older_revision_creates_new_revision(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "test_case", "TC1")], a)
    tc = _node(db_session, artifact.id, "TC1").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": tc}], a)
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [_add_op(artifact.root_node_id, "test_case", "TC2")], a)
    result = artifact_service.restore_revision(db_session, artifact_id=artifact.id,
                                               target_revision=r2["new_revision"], requester=a)
    db_session.commit()
    assert result["new_revision"] == 5
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    assert [c["title"] for c in tree["root"]["children"]] == ["TC1"]


def test_26_history_preserved_across_undo_restore(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    current = 1
    for step in range(4):
        current = _apply(db_session, artifact.id, current,
                         [_add_op(artifact.root_node_id, "test_case", f"TC-{step}")], a)["new_revision"]
    artifact_service.undo_latest(db_session, artifact_id=artifact.id, requester=a)
    db_session.commit()
    artifact_service.restore_revision(db_session, artifact_id=artifact.id,
                                      target_revision=2, requester=a)
    db_session.commit()
    assert _revision_nos(db_session, artifact.id) == [1, 2, 3, 4, 5, 6, 7]
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 7


# ── Concurrency（27-29） ──


def test_27_stale_expected_revision_conflict(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    _apply(db_session, artifact.id, 1, [_add_op(artifact.root_node_id, "test_case", "TC-A")], a)
    with pytest.raises(RevisionConflictError) as exc:
        _apply(db_session, artifact.id, 1,
               [_add_op(artifact.root_node_id, "test_case", "TC-B")], a)
    db_session.rollback()
    assert exc.value.detail == {"expected_revision": 1, "current_revision": 2}
    assert db_session.query(ArtifactRevision).filter(
        ArtifactRevision.artifact_id == artifact.id).count() == 2
    assert set(_visible_titles(db_session, artifact.id)) == {"登录测试", "TC-A"}


def test_28_two_sessions_same_expected_only_one_wins(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    session1 = SessionLocal()
    try:
        art1 = artifact_service.get_artifact(session1, artifact_id=artifact.id, requester=a)
        result = artifact_service.apply_operations(
            session1, artifact_id=art1.id, expected_revision=1,
            operations=[_add_op(art1.root_node_id, "test_case", "胜者")], requester=a)
        session1.commit()
        assert result["new_revision"] == 2
    finally:
        session1.close()
    session2 = SessionLocal()
    try:
        with pytest.raises(RevisionConflictError):
            artifact_service.apply_operations(
                session2, artifact_id=artifact.id, expected_revision=1,
                operations=[_add_op(artifact.root_node_id, "test_case", "败者")], requester=a)
        session2.rollback()
    finally:
        session2.close()
    db_session.expire_all()  # 让外层 session 重新从库读，避免 stale identity map
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 2
    assert set(_visible_titles(db_session, artifact.id)) == {"登录测试", "胜者"}
    assert db_session.query(ArtifactRevision).filter(
        ArtifactRevision.artifact_id == artifact.id).count() == 2


def test_28b_conditional_update_is_authoritative(db_session):
    """即使提前检查通过（ORM 读到旧值），条件 UPDATE 也必须裁决出冲突。"""
    a = _seed(db_session)
    artifact = _create(db_session, a)
    # 模拟“另一连接已把版本推到 2”：直接改库，且不让 ORM 缓存刷新
    db_session.execute(text(
        "UPDATE test_artifact SET current_revision = 2 WHERE id = :id"
    ).bindparams(id=artifact.id))
    assert artifact.current_revision == 1  # ORM 仍持旧值 → 提前检查会放行
    with pytest.raises(RevisionConflictError) as exc:
        artifact_service.apply_operations(
            db_session, artifact_id=artifact.id, expected_revision=1,
            operations=[_add_op(artifact.root_node_id, "test_case", "TC-X")], requester=a)
    db_session.rollback()
    assert exc.value.detail == {"expected_revision": 1, "current_revision": 2}


def test_29_current_revision_tracks_all_writes(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    current = artifact.current_revision
    for step in range(5):
        current = _apply(db_session, artifact.id, current,
                         [_add_op(artifact.root_node_id, "test_case", f"N{step}")], a)["new_revision"]
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 6


# ── Security（30-32 + source_refs 合同） ──


def test_30_cross_user_read_blocked(db_session):
    a = _seed(db_session)
    b = _user(db_session, USER_B)
    artifact = _create(db_session, a, title="A 的资产")
    calls = [
        lambda: artifact_service.get_artifact(db_session, artifact_id=artifact.id, requester=b),
        lambda: artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=b),
        lambda: artifact_service.list_revisions(db_session, artifact_id=artifact.id, requester=b),
        lambda: artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                          from_revision=1, to_revision=1, requester=b),
        lambda: artifact_service.undo_latest(db_session, artifact_id=artifact.id, requester=b),
    ]
    for call in calls:
        with pytest.raises(ArtifactNotFoundError):
            call()
        db_session.rollback()


def test_31_cross_user_write_and_project_permission(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)  # 无项目：他人写 → 404（隔离，同 read）
    b = _user(db_session, USER_B)
    with pytest.raises(ArtifactNotFoundError):
        artifact_service.apply_operations(
            db_session, artifact_id=artifact.id,
            expected_revision=artifact.current_revision,
            operations=[_add_op(artifact.root_node_id, "group", "越权")], requester=b)
    db_session.rollback()
    # 项目 Artifact：viewer 可读（项目级只读）但不可操作 → 403
    artifact_p = _create(db_session, a, title="项目资产", project_id=PROJECT_P)
    viewer = _user(db_session, VIEWER)
    assert artifact_service.get_tree(db_session, artifact_id=artifact_p.id,
                                     requester=viewer)["artifact_id"] == artifact_p.id
    with pytest.raises(ArtifactPermissionError):
        artifact_service.apply_operations(
            db_session, artifact_id=artifact_p.id,
            expected_revision=artifact_p.current_revision,
            operations=[_add_op(artifact_p.root_node_id, "group", "越权")], requester=viewer)
    db_session.rollback()


def test_32_server_controlled_fields_cannot_be_forged(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1,
                [_add_op(artifact.root_node_id, "test_case", "TC1")], a)
    tc = _node(db_session, artifact.id, "TC1")
    forged_keys = ["id", "node_type", "created_revision", "deleted_revision",
                   "created_by", "artifact_id", "parent_id", "order_key"]
    for key in forged_keys:
        with pytest.raises(ArtifactValidationError):
            _apply(db_session, artifact.id, r2["new_revision"], [{
                "operation_type": "update_node", "target_node_id": tc.id,
                "patch": {key: 123, "title": "篡改"},
            }], a)
        db_session.rollback()
    with pytest.raises(ArtifactValidationError):  # add 请求携带 id 同样被拒
        _apply(db_session, artifact.id, r2["new_revision"], [{
            "operation_type": "add_node", "parent_id": artifact.root_node_id,
            "node_type": "test_case", "title": "TC2", "id": 9999,
        }], a)
    db_session.rollback()
    with pytest.raises(ArtifactValidationError):  # 未知 patch 字段
        _apply(db_session, artifact.id, r2["new_revision"], [{
            "operation_type": "update_node", "target_node_id": tc.id,
            "patch": {"unknown_field": "x"},
        }], a)
    db_session.rollback()
    row = db_session.get(ArtifactNode, tc.id)
    assert row.id == tc.id and row.title == "TC1"


def test_source_refs_contract(db_session):
    """非 Requirement 类型的 source_refs 是纯 provenance，可在 projectless Artifact 存续。"""
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r = _apply(db_session, artifact.id, 1, [{
        "operation_type": "add_node", "parent_id": artifact.root_node_id,
        "node_type": "test_case", "title": "TC-REQ",
        "source_refs": [{"source_type": "manual", "source_id": "DOC-123",
                         "fragment_id": "clause-7", "snapshot_hash": "abc"}],
    }], a)
    tc = _node(db_session, artifact.id, "TC-REQ")
    assert tc.source_refs_json == [{"source_type": "manual", "source_id": "DOC-123",
                                    "fragment_id": "clause-7", "snapshot_hash": "abc"}]
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r["new_revision"], [{
            "operation_type": "update_node", "target_node_id": tc.id,
            "patch": {"source_refs": [{"source_type": "manual"}]},
        }], a)
    db_session.rollback()


def test_requirement_refs_require_same_project_binding(db_session):
    """P08.1：requirement 类型 SourceRef 写入必须属于 Artifact 项目；SourceRef ≠ 授权。"""
    from app.models.requirement_doc import RequirementDoc

    a = _seed(db_session)
    other_project = Project(id=PROJECT_P + 100, name="项目Q", status="active", is_deleted=False)
    db_session.add(other_project)
    req_p = RequirementDoc(project_id=PROJECT_P, title="本项目需求", content="内容",
                           requirement_type="功能需求", status="confirmed", is_deleted=False)
    req_q = RequirementDoc(project_id=PROJECT_P + 100, title="跨项目需求", content="内容",
                           requirement_type="功能需求", status="confirmed", is_deleted=False)
    db_session.add_all([req_p, req_q])
    db_session.commit()

    artifact_p = _create(db_session, a, title="项目内Artifact", project_id=PROJECT_P)
    root_p = artifact_p.root_node_id
    # 同项目 Requirement → 允许
    r2 = _apply(db_session, artifact_p.id, 1, [{
        "operation_type": "add_node", "parent_id": root_p, "node_type": "test_case",
        "title": "TC-OK",
        "source_refs": [{"source_type": "requirement", "source_id": str(req_p.id)}],
    }], a)
    tc = _node(db_session, artifact_p.id, "TC-OK")
    assert tc.source_refs_json[0]["source_id"] == str(req_p.id)
    # 其他项目 Requirement → 拒绝（即使同用户可见该项目也不行——跨项目绑定不成立）
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact_p.id, r2["new_revision"], [{
            "operation_type": "update_node", "target_node_id": tc.id,
            "patch": {"source_refs": [{"source_type": "requirement",
                                       "source_id": str(req_q.id)}]},
        }], a)
    db_session.rollback()
    # 非数字 source_id → 拒绝
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact_p.id, r2["new_revision"], [{
            "operation_type": "update_node", "target_node_id": tc.id,
            "patch": {"source_refs": [{"source_type": "requirement",
                                       "source_id": "REQ-ABC"}]},
        }], a)
    db_session.rollback()
    # projectless Artifact → 一律拒绝 requirement 引用（SourceRef 不授予读取权限）
    artifact_free = _create(db_session, a, title="无项目Artifact")
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact_free.id, 1, [{
            "operation_type": "add_node", "parent_id": artifact_free.root_node_id,
            "node_type": "test_case", "title": "TC-FORGE",
            "source_refs": [{"source_type": "requirement", "source_id": str(req_p.id)}],
        }], a)
    db_session.rollback()


def test_update_patch_null_contract_rejected(db_session):
    """P08.1：patch 显式 null 一律拒绝；source_refs=[] 表示清空。"""
    a = _seed(db_session)
    artifact = _create(db_session, a)
    r2 = _apply(db_session, artifact.id, 1, [{
        "operation_type": "add_node", "parent_id": artifact.root_node_id,
        "node_type": "test_case", "title": "TC1",
        "source_refs": [{"source_type": "manual", "source_id": "M-1"}],
    }], a)
    tc = _node(db_session, artifact.id, "TC1").id
    for patch in ({"title": None}, {"content": None}, {"source_refs": None}):
        with pytest.raises(ArtifactValidationError):
            _apply(db_session, artifact.id, r2["new_revision"], [{
                "operation_type": "update_node", "target_node_id": tc,
                "patch": patch,
            }], a)
        db_session.rollback()
    # source_refs=[] 清空
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [{
        "operation_type": "update_node", "target_node_id": tc,
        "patch": {"source_refs": []},
    }], a)
    assert r3["new_revision"] == 3
    assert db_session.get(ArtifactNode, tc).source_refs_json is None


# ── §28 完整 P07 E2E（无 Agent，Revision 1..7） ──


def test_p07_e2e_login_artifact_full_journey(db_session):
    a = _seed(db_session)

    # Revision 1：create + auto root（事务内同批）
    artifact = _create(db_session, a, title="登录测试")
    assert artifact.current_revision == 1

    # Revision 2：一个 batch = 功能 group + 正常登录/密码错误 point + TC001/TC002
    # 用批内 ref（@g/@pt）引用同批先建节点 → 仍是“恰好一个 Revision”
    r2 = _apply(db_session, artifact.id, 1, [
        _add_op(artifact.root_node_id, "group", "功能", ref="g"),
        _add_op("@g", "test_point", "正常登录", ref="pt"),
        _add_op("@pt", "test_case", "TC001"),
        _add_op("@pt", "test_case", "TC002"),
        _add_op("@g", "test_point", "密码错误"),
    ], a)
    assert r2["new_revision"] == 2 and r2["changed"] == 5

    # Revision 3：Update TC002
    tc002 = _node(db_session, artifact.id, "TC002").id
    r3 = _apply(db_session, artifact.id, 2, [{
        "operation_type": "update_node", "target_node_id": tc002,
        "patch": {"title": "TC002 输入错误密码"},
    }], a)
    assert r3["new_revision"] == 3

    # Revision 4：Move TC002 → 密码错误 point
    wrong_point = _node(db_session, artifact.id, "密码错误").id
    r4 = _apply(db_session, artifact.id, 3, [{
        "operation_type": "move_node", "target_node_id": tc002,
        "new_parent_id": wrong_point, "new_order_key": 1,
    }], a)
    assert r4["new_revision"] == 4

    # Revision 5：Delete TC001
    tc001 = _node(db_session, artifact.id, "TC001").id
    r5 = _apply(db_session, artifact.id, 4,
                [{"operation_type": "delete_node", "target_node_id": tc001}], a)
    assert r5["new_revision"] == 5

    # Revision 6：Undo（恢复 TC001）
    undo = artifact_service.undo_latest(db_session, artifact_id=artifact.id, requester=a)
    db_session.commit()
    assert undo["previous_revision"] == 5 and undo["new_revision"] == 6
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    group_node = next(c for c in tree["root"]["children"] if c["title"] == "功能")
    normal = next(c for c in group_node["children"] if c["title"] == "正常登录")
    wrong = next(c for c in group_node["children"] if c["title"] == "密码错误")
    assert sorted(c["title"] for c in normal["children"]) == ["TC001"]
    assert [c["title"] for c in wrong["children"]] == ["TC002 输入错误密码"]

    # Diff 5→6：TC001 恢复 → added
    diff_undo = artifact_service.get_diff(db_session, artifact_id=artifact.id,
                                          from_revision=5, to_revision=6, requester=a)
    assert [c["node_id"] for c in diff_undo["changes"] if c["change"] == "added"] == [tc001]

    # Revision 7：Restore Revision 3（TC002 回到正常登录且保持改名）
    restore = artifact_service.restore_revision(db_session, artifact_id=artifact.id,
                                                target_revision=3, requester=a)
    db_session.commit()
    assert restore["new_revision"] == 7
    tree_final = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    group_final = next(c for c in tree_final["root"]["children"] if c["title"] == "功能")
    normal_final = next(c for c in group_final["children"] if c["title"] == "正常登录")
    wrong_final = next(c for c in group_final["children"] if c["title"] == "密码错误")
    assert sorted(c["title"] for c in normal_final["children"]) == ["TC001", "TC002 输入错误密码"]
    assert wrong_final["children"] == []

    # 最终：完整历史 1..7，current_revision=7
    assert _revision_nos(db_session, artifact.id) == [1, 2, 3, 4, 5, 6, 7]
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=a).current_revision == 7


# ── P07.1 Hardening：get_tree 全层级排序 + restore Tree Integrity ──


def _restore_snapshot(node_id, parent_id, node_type, title, order_key=1):
    return {"id": node_id, "parent_id": parent_id, "order_key": order_key,
            "node_type": node_type, "title": title, "content": None, "source_refs": None}


def test_tree_nested_children_sorted_by_order_key(db_session):
    """≥2 层嵌套：构树后所有层级 children 都按 (order_key, id) 排序，不依赖 DB 顺序。"""
    a = _seed(db_session)
    artifact = _create(db_session, a)
    root_id = artifact.root_node_id
    # 第 1 层：故意乱序插入（晚到的高 order 在前，早到的低 order 在后）
    r2 = _apply(db_session, artifact.id, 1, [
        _add_op(root_id, "group", "G-晚", order_key=30),
        _add_op(root_id, "group", "G-早", order_key=10),
    ], a)
    g_early = _node(db_session, artifact.id, "G-早").id
    # 第 2 层：point 乱序插入（B,A,C）
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [
        _add_op(g_early, "test_point", "pt-B", order_key=30),
        _add_op(g_early, "test_point", "pt-A", order_key=10),
        _add_op(g_early, "test_point", "pt-C", order_key=20),
    ], a)
    pt_a = _node(db_session, artifact.id, "pt-A").id
    # 第 3 层：test_case 乱序插入（TC-2 先于 TC-1）
    _apply(db_session, artifact.id, r3["new_revision"], [
        _add_op(pt_a, "test_case", "TC-2", order_key=20),
        _add_op(pt_a, "test_case", "TC-1", order_key=10),
    ], a)
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=a)
    assert [c["title"] for c in tree["root"]["children"]] == ["G-早", "G-晚"]
    g_early_node = next(c for c in tree["root"]["children"] if c["title"] == "G-早")
    assert [c["title"] for c in g_early_node["children"]] == ["pt-A", "pt-C", "pt-B"]
    pt_a_node = next(c for c in g_early_node["children"] if c["title"] == "pt-A")
    assert [c["title"] for c in pt_a_node["children"]] == ["TC-1", "TC-2"]


def test_restore_rejects_group_under_visible_test_case(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    root_id = artifact.root_node_id
    r2 = _apply(db_session, artifact.id, 1, [_add_op(root_id, "test_case", "TC")], a)
    tc = _node(db_session, artifact.id, "TC").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [_add_op(root_id, "group", "G")], a)
    g = _node(db_session, artifact.id, "G").id
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": g}], a)
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r4["new_revision"], [{
            "operation_type": "restore", "target_node_id": g,
            "nodes": [_restore_snapshot(g, tc, "group", "G")],
        }], a)
    db_session.rollback()


def test_restore_rejects_parent_test_case_being_restored(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    root_id = artifact.root_node_id
    r2 = _apply(db_session, artifact.id, 1, [_add_op(root_id, "test_case", "TC")], a)
    tc = _node(db_session, artifact.id, "TC").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"], [_add_op(root_id, "group", "G")], a)
    g = _node(db_session, artifact.id, "G").id
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": tc}], a)
    r5 = _apply(db_session, artifact.id, r4["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": g}], a)
    # 同批恢复 TC 与 G，但 G 快照把 TC（test_case）当父节点 → 拒绝
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r5["new_revision"], [{
            "operation_type": "restore", "target_node_id": tc,
            "nodes": [
                _restore_snapshot(tc, root_id, "test_case", "TC"),
                _restore_snapshot(g, tc, "group", "G"),
            ],
        }], a)
    db_session.rollback()


def test_restore_rejects_cycle_a_to_b(db_session):
    a = _seed(db_session)
    artifact = _create(db_session, a)
    root_id = artifact.root_node_id
    r2 = _apply(db_session, artifact.id, 1, [
        _add_op(root_id, "group", "GA"), _add_op(root_id, "group", "GB")], a)
    ga = _node(db_session, artifact.id, "GA").id
    gb = _node(db_session, artifact.id, "GB").id
    r3 = _apply(db_session, artifact.id, r2["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": ga}], a)
    r4 = _apply(db_session, artifact.id, r3["new_revision"],
                [{"operation_type": "delete_node", "target_node_id": gb}], a)
    with pytest.raises(ArtifactValidationError):
        _apply(db_session, artifact.id, r4["new_revision"], [{
            "operation_type": "restore", "target_node_id": ga,
            "nodes": [
                _restore_snapshot(ga, gb, "group", "GA"),
                _restore_snapshot(gb, ga, "group", "GB"),
            ],
        }], a)
    db_session.rollback()
