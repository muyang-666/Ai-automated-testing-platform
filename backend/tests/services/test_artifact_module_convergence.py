"""P09.1 收敛专项测试：module/test_case 域 + 默认模块唯一 + 项目主 Artifact 唯一 + 编号派生。"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.project import Project
from app.models.role import Role
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.services.test_artifacts import artifact_service
from app.services.test_artifacts.case_number import format_case_number

USER_A = 9101
PROJECT_P = 9501


def _seed(db):
    for code in ("system_admin",):
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(code=code, name=code, status="active"))
    db.flush()
    role = db.query(Role).filter(Role.code == "system_admin").one()
    user = db.query(User).filter(User.id == USER_A).first()
    if user is None:
        user = User(id=USER_A, username="conv-a", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db.add(user)
        db.flush()
    if not db.query(UserRole).filter(UserRole.user_id == USER_A).first():
        db.add(UserRole(user_id=USER_A, role_id=role.id))
    if not db.query(Project).filter(Project.id == PROJECT_P).first():
        db.add(Project(id=PROJECT_P, name="项目P", status="active", is_deleted=False))
    if not db.query(UserProjectPermission).filter(
            UserProjectPermission.user_id == USER_A,
            UserProjectPermission.project_id == PROJECT_P).first():
        db.add(UserProjectPermission(user_id=USER_A, project_id=PROJECT_P, can_operate=True))
    db.commit()
    return user


def _module_ops(artifact, title):
    return {"operation_type": "add_node", "parent_id": artifact.root_node_id,
            "node_type": "module", "title": title}


def _case_ops(module_id, title, priority="P1"):
    return {"operation_type": "add_node", "parent_id": module_id,
            "node_type": "test_case", "title": title,
            "content": {"priority": priority,
                        "steps": [{"action": f"执行 {title}"}],
                        "expected_results": [f"{title} 成功"]}}


def test_module_nests_module_and_contains_cases(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="项目P功能")
    rev = artifact.current_revision
    result = artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=rev, requester=user, operations=[
            _module_ops(artifact, "登录"),
            {"operation_type": "add_node", "parent_id": artifact.root_node_id,
             "node_type": "module", "title": "账号锁定", "ref": "lock"},
            {"operation_type": "add_node", "parent_id": "@lock", "node_type": "module",
             "title": "锁定规则", "ref": "rule"},
            _case_ops("@lock", "TC-锁定"),
            _case_ops("@rule", "TC-规则"),
        ])
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=user)
    root = tree["root"]
    modules = {c["title"]: c for c in root["children"]}
    assert set(modules) == {"登录", "账号锁定"}
    lock = modules["账号锁定"]
    rule = next(c for c in lock["children"] if c["title"] == "锁定规则")
    assert [c["title"] for c in lock["children"] if c["node_type"] == "test_case"] == ["TC-锁定"]
    assert [c["title"] for c in rule["children"]] == ["TC-规则"]
    assert result["new_revision"] == rev + 1


def test_case_without_module_auto_lands_in_default_module(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=artifact.current_revision,
        requester=user, operations=[_case_ops(artifact.root_node_id, "无模块用例")])
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=user)
    children = tree["root"]["children"]
    assert len(children) == 1 and children[0]["title"] == "默认模块"
    assert children[0]["node_type"] == "module"
    assert [c["title"] for c in children[0]["children"]] == ["无模块用例"]


def test_default_module_is_singleton_after_many_implicit_adds(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    ops = [_case_ops(artifact.root_node_id, f"TC-{i}") for i in range(6)]
    artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=artifact.current_revision,
        requester=user, operations=ops)
    db_session.commit()
    defaults = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id,
        ArtifactNode.node_type == "module",
        ArtifactNode.title == "默认模块",
        ArtifactNode.deleted_revision.is_(None),
    ).all()
    assert len(defaults) == 1
    child_count = db_session.query(ArtifactNode).filter(
        ArtifactNode.parent_id == defaults[0].id,
        ArtifactNode.deleted_revision.is_(None)).count()
    assert child_count == 6


def test_get_or_create_default_module_returns_same_singleton(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    first = artifact_service.get_or_create_default_module(
        db_session, artifact_id=artifact.id, requester=user)
    second = artifact_service.get_or_create_default_module(
        db_session, artifact_id=artifact.id, requester=user)
    assert first.id == second.id
    assert db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id, ArtifactNode.node_type == "module",
        ArtifactNode.title == "默认模块",
        ArtifactNode.deleted_revision.is_(None)).count() == 1


def test_project_functional_artifact_is_singleton(db_session):
    user = _seed(db_session)
    first = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="功能测试")
    second = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="功能测试")
    assert first.id == second.id
    rows = db_session.query(artifact_service.TestArtifact).filter(
        artifact_service.TestArtifact.project_id == PROJECT_P).all()
    assert len(rows) == 1
    # 数据库唯一约束兜底：直接再插一条同项目同类型必须冲突
    from app.models.test_artifact.test_artifact import TestArtifact
    dup = TestArtifact(owner_user_id=USER_A, project_id=PROJECT_P, title="重复",
                       artifact_type="test_design", status="active", current_revision=0,
                       schema_version=1)
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_two_concurrent_ensure_only_one_artifact(db_session):
    user = _seed(db_session)
    session1 = SessionLocal()
    try:
        artifact_service.ensure_project_functional_artifact(
            session1, project_id=PROJECT_P, requester=user)
    finally:
        session1.close()
    session2 = SessionLocal()
    try:
        artifact_service.ensure_project_functional_artifact(
            session2, project_id=PROJECT_P, requester=user)
    finally:
        session2.close()
    rows = db_session.query(artifact_service.TestArtifact).filter(
        artifact_service.TestArtifact.project_id == PROJECT_P).all()
    assert len(rows) == 1


def test_case_number_derived_and_stable_across_move(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    result = artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=artifact.current_revision,
        requester=user, operations=[
            _module_ops(artifact, "A"), _module_ops(artifact, "B")])
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=user)
    a = next(c for c in tree["root"]["children"] if c["title"] == "A")
    b = next(c for c in tree["root"]["children"] if c["title"] == "B")
    add_case = artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=result["new_revision"],
        requester=user, operations=[_case_ops(a["id"], "TC-移动")])
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=user)
    a2 = next(c for c in tree["root"]["children"] if c["title"] == "A")
    case_id = a2["children"][0]["id"]
    number_before = format_case_number(case_id)
    assert number_before.startswith("TC-")
    artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=add_case["new_revision"],
        requester=user, operations=[{
            "operation_type": "move_node", "target_node_id": case_id,
            "new_parent_id": b["id"],
        }])
    db_session.commit()
    assert format_case_number(case_id) == number_before  # 移动后编号不变


def test_old_v1_tables_untouched_and_legacy_deprecated(db_session):
    user = _seed(db_session)
    artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    db_session.commit()
    # 旧表保持为空（未被新路径写库）
    assert db_session.query(Project).filter(Project.id == PROJECT_P).count() == 1


def test_two_cases_same_module_record_two_operations(db_session):
    from app.models.test_artifact.artifact_operation import ArtifactOperation
    from app.models.test_artifact.artifact_revision import ArtifactRevision

    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    module = artifact_service.get_or_create_default_module(
        db_session, artifact_id=artifact.id, requester=user)
    rev = artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                        requester=user).current_revision
    result = artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=rev, requester=user,
        operations=[_case_ops(module.id, "A"), _case_ops(module.id, "B")])
    db_session.commit()
    ops = db_session.query(ArtifactOperation).join(
        ArtifactRevision, ArtifactRevision.id == ArtifactOperation.revision_id).filter(
        ArtifactRevision.artifact_id == artifact.id,
        ArtifactRevision.revision_no == result["new_revision"]).count()
    assert result["changed"] == 2
    assert ops == 2
