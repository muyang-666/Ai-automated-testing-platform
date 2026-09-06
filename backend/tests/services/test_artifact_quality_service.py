"""P08.1 duplicate 规模保护：MAX_DUPLICATE_CANDIDATES 上限与 total/analyzed/truncated。"""

from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services.test_artifacts import artifact_service, quality_service

USER_A = 8401


def _token_text(token: str) -> str:
    # 短而互异的确定性文本：不同 token 相似度远低于阈值，相同 token 完全一致
    return f"预期行为 token={token} 步骤与前置条件固定表述{token[-4:]}"


def _seed(db):
    for code in ("system_admin",):
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(code=code, name=code, status="active"))
    db.flush()
    role = db.query(Role).filter(Role.code == "system_admin").one()
    user = db.query(User).filter(User.id == USER_A).first()
    if user is None:
        user = User(id=USER_A, username="quality-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db.add(user)
        db.flush()
    if not db.query(UserRole).filter(UserRole.user_id == USER_A).first():
        db.add(UserRole(user_id=USER_A, role_id=role.id))
    db.commit()
    return user


def test_duplicate_analysis_truncates_large_scope(db_session):
    user = _seed(db_session)
    artifact = artifact_service.create_artifact(db_session, requester=user, title="大库")
    root = artifact.root_node_id
    ops = []
    # 65 个 test_case；i=1/2 与 i=61/62 各是一对完全重复（后者在 cap 之外）
    for i in range(1, 66):
        token = "dup-alpha" if i in (1, 2) else ("dup-beta" if i in (61, 62) else f"case-{i:04d}")
        title = "完全重复Alpha" if i in (1, 2) else ("完全重复Beta" if i in (61, 62) else f"TC-{i:03d}")
        ops.append({"operation_type": "add_node", "parent_id": root,
                    "node_type": "test_case", "title": title,
                    "content": {"steps": [{"action": "执行", "data": None}],
                                "expected_results": [_token_text(token)], "priority": "P2"}})
    artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=1, operations=ops,
        requester=user)
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=user)
    child_ids = [child["id"] for child in tree["root"]["children"]]
    in_cap_pair = tuple(sorted(child_ids[0:2]))     # TC-001/TC-002（cap 内重复）
    out_cap_pair = tuple(sorted(child_ids[60:62]))  # TC-061/TC-062（cap 外重复）

    data = quality_service.find_duplicates(db_session, artifact_id=artifact.id,
                                           requester=user, threshold=0.99,
                                           candidate_cap=40)
    assert data["total_cases"] == 65
    assert data["eligible_cases"] == 65
    assert data["analyzed_cases"] == 40
    assert data["truncated"] is True
    pair_ids = {(p["node_a"], p["node_b"]) for p in data["pairs"]}
    assert in_cap_pair in pair_ids  # cap 内重复对被发现
    assert out_cap_pair not in pair_ids  # cap 外重复对不被分析

    data_all = quality_service.find_duplicates(db_session, artifact_id=artifact.id,
                                               requester=user, threshold=0.99,
                                               candidate_cap=400)
    assert data_all["total_cases"] == 65
    assert data_all["eligible_cases"] == 65
    assert data_all["analyzed_cases"] == 65
    assert data_all["truncated"] is False
    pair_ids_all = {(p["node_a"], p["node_b"]) for p in data_all["pairs"]}
    assert out_cap_pair in pair_ids_all
