"""TestArtifact API 冒烟测试（V2-P07）：Router 是 Application Service 的薄壳。

TestClient + SQLite + get_current_user 覆盖；不启动 Worker / 不调 LLM。
覆盖：create 201、tree、operations 一批一个 revision、409 载荷、400 校验、
owner 隔离 404、undo/restore 端点、服务端控制字段拒绝。
"""

import pytest
from fastapi.testclient import TestClient

from app.models.project import Project
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.routers.dependencies import get_current_user

USER_A = 1001
USER_B = 1002


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

    a = user(USER_A, "api_a", "tester")
    b = user(USER_B, "api_b", "tester")
    db.commit()
    return a, b


@pytest.fixture()
def client(db_session):
    from app.main import app

    a, b = _seed(db_session)
    state = {"user": a}
    app.dependency_overrides[get_current_user] = lambda: state["user"]

    def make(user):
        state["user"] = user

    with TestClient(app) as test_client:
        yield test_client, a, b, make
    app.dependency_overrides.clear()


def _create_artifact(client, title="登录测试", extra=None):
    payload = {"title": title}
    if extra:
        payload.update(extra)
    return client.post("/test-artifacts", json=payload)


def _root_id(client, artifact_id):
    tree = client.get(f"/test-artifacts/{artifact_id}/tree").json()
    return tree["root"]["id"]


def test_create_and_tree(client):
    test_client, a, b, switch = client
    response = _create_artifact(test_client)
    assert response.status_code == 201
    body = response.json()
    assert body["current_revision"] == 1 and body["title"] == "登录测试"
    tree = test_client.get(f"/test-artifacts/{body['id']}/tree").json()
    assert tree["root"]["node_type"] == "root"
    assert tree["root"]["children"] == []


def test_operations_batch_one_revision(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    response = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [
            {"operation_type": "add_node", "parent_id": root, "node_type": "module", "title": "功能"},
            {"operation_type": "add_node", "parent_id": root, "node_type": "module", "title": "状态"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["new_revision"] == 2
    revisions = test_client.get(f"/test-artifacts/{artifact['id']}/revisions").json()
    assert len(revisions) == 2
    tree = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    assert sorted(c["title"] for c in tree["root"]["children"]) == ["功能", "状态"]


def test_stale_revision_409_payload(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    assert test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [{"operation_type": "add_node", "parent_id": root,
                        "node_type": "test_case", "title": "TC-A"}],
    }).status_code == 200
    conflict = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,  # 已过期（current=2）
        "operations": [{"operation_type": "add_node", "parent_id": root,
                        "node_type": "test_case", "title": "TC-B"}],
    })
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["error_code"] == "revision_conflict"
    assert detail["expected_revision"] == 1 and detail["current_revision"] == 2


def test_invalid_operation_400(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    bad = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [{"operation_type": "update_node", "target_node_id": 12345,
                        "patch": {"title": "不存在节点"}}],
    })
    assert bad.status_code == 400


def test_owner_isolation_404(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client, title="A 的资产").json()
    switch(b)
    assert test_client.get(f"/test-artifacts/{artifact['id']}").status_code == 404
    assert test_client.get(f"/test-artifacts/{artifact['id']}/tree").status_code == 404
    assert test_client.post(f"/test-artifacts/{artifact['id']}/undo").status_code == 404


def test_server_controlled_field_forged_400(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [{"operation_type": "add_node", "parent_id": root,
                        "node_type": "test_case", "title": "TC1"}],
    })
    # TC1 直接挂在 root 下 → 取 children 第一个
    tree = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    tc_id = tree["root"]["children"][0]["id"]
    forged = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 2,
        "operations": [{"operation_type": "update_node", "target_node_id": tc_id,
                        "patch": {"node_type": "root", "title": "篡改"}}],
    })
    assert forged.status_code == 400


def test_undo_and_restore_endpoints(client):
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [{"operation_type": "add_node", "parent_id": root,
                        "node_type": "test_case", "title": "TC1"}],
    })
    tree = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    default = tree["root"]["children"][0]
    assert default["title"] == "默认模块"
    tc_id = default["children"][0]["id"]
    test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 2,
        "operations": [{"operation_type": "delete_node", "target_node_id": tc_id}],
    })
    undo = test_client.post(f"/test-artifacts/{artifact['id']}/undo").json()
    assert undo["new_revision"] == 4
    tree_after = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    assert [c["title"] for c in tree_after["root"]["children"]] == ["默认模块"]
    # 再删除 TC1（rev5），随后 restore 到 Revision 2（rev6）恢复它
    tree_tmp = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    default_tmp = tree_tmp["root"]["children"][0]
    tc = default_tmp["children"][0]["id"]
    test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 4,
        "operations": [{"operation_type": "delete_node", "target_node_id": tc}],
    })
    restore = test_client.post(f"/test-artifacts/{artifact['id']}/restore",
                               json={"target_revision": 2}).json()
    assert restore["new_revision"] == 6
    tree_final = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    assert [c["title"] for c in tree_final["root"]["children"]] == ["默认模块"]
    assert [c["title"] for c in tree_final["root"]["children"][0]["children"]] == ["TC1"]
    revisions = test_client.get(f"/test-artifacts/{artifact['id']}/revisions").json()
    assert [r["revision_no"] for r in revisions] == [1, 2, 3, 4, 5, 6]


def test_public_operations_cannot_submit_internal_restore(client):
    """restore 为内部操作：普通 /operations API 直接拒绝（undo/restore 端点仍可用）。"""
    test_client, a, b, switch = client
    artifact = _create_artifact(test_client).json()
    root = _root_id(test_client, artifact["id"])
    tc = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 1,
        "operations": [{"operation_type": "add_node", "parent_id": root,
                        "node_type": "test_case", "title": "TC1"}],
    }).json()
    tree = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    default = tree["root"]["children"][0]
    tc_id = default["children"][0]["id"]
    test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 2,
        "operations": [{"operation_type": "delete_node", "target_node_id": tc_id}],
    })
    rejected = test_client.post(f"/test-artifacts/{artifact['id']}/operations", json={
        "expected_revision": 3,
        "operations": [{
            "operation_type": "restore", "target_node_id": tc_id,
            "nodes": [{"id": tc_id, "parent_id": default["id"], "order_key": 1,
                       "node_type": "test_case", "title": "TC1"}],
        }],
    })
    assert rejected.status_code == 400
    assert "内部操作" in rejected.json()["detail"]
    # undo 端点（内部生成 restore）仍正常
    undo = test_client.post(f"/test-artifacts/{artifact['id']}/undo").json()
    assert undo["new_revision"] == 4
    tree_after = test_client.get(f"/test-artifacts/{artifact['id']}/tree").json()
    assert [c["title"] for c in tree_after["root"]["children"]] == ["默认模块"]
    assert [c["title"] for c in tree_after["root"]["children"][0]["children"]] == ["TC1"]
