"""P09.1.1：Project-scoped Artifact 权限服从 Project ACL；创建入口唯一化等加固测试。"""

import pytest

from app.models.project import Project
from app.models.role import Role
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.services.test_artifacts import artifact_service
from app.services.test_artifacts.errors import (
    TestArtifactNotFoundError as ArtifactNotFoundError,
    TestArtifactPermissionError as ArtifactPermissionError,
    TestArtifactValidationError as ArtifactValidationError,
)

OWNER = 9501
PROJECT_P = 9601


def _seed(db, extra_role="tester", grant_membership=True, uid=OWNER):
    for code in ("system_admin", "tester", "viewer"):
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(code=code, name=code, status="active"))
    db.flush()
    roles = {r.code: r for r in db.query(Role).all()}
    if not db.query(Project).filter(Project.id == PROJECT_P).first():
        db.add(Project(id=PROJECT_P, name="项目P", status="active", is_deleted=False))
    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        user = User(id=uid, username=f"acl-{uid}", password_hash="x", salt="y",
                    status="active", is_deleted=False)
        db.add(user)
        db.flush()
    if not db.query(UserRole).filter(UserRole.user_id == uid).first():
        db.add(UserRole(user_id=uid, role_id=roles[extra_role].id))
    if grant_membership and not db.query(UserProjectPermission).filter(
            UserProjectPermission.user_id == uid,
            UserProjectPermission.project_id == PROJECT_P).first():
        db.add(UserProjectPermission(user_id=uid, project_id=PROJECT_P, can_operate=True))
    db.commit()
    return user


def test_owner_removed_from_project_loses_read_write(db_session):
    user = _seed(db_session)
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="P资产")
    db_session.commit()
    # 移除项目成员资格后：owner 不再例外
    db_session.query(UserProjectPermission).filter(
        UserProjectPermission.user_id == OWNER,
        UserProjectPermission.project_id == PROJECT_P).delete()
    db_session.commit()
    with pytest.raises(ArtifactNotFoundError):
        artifact_service.get_artifact(db_session, artifact_id=artifact.id, requester=user)
    with pytest.raises(ArtifactNotFoundError):
        artifact_service.apply_operations(
            db_session, artifact_id=artifact.id, expected_revision=artifact.current_revision,
            requester=user,
            operations=[{"operation_type": "add_node", "parent_id": artifact.root_node_id,
                         "node_type": "module", "title": "越权"}])
    db_session.rollback()


def test_viewer_read_allowed_write_denied(db_session):
    user = _seed(db_session)  # tester owner w/ membership 创建
    artifact = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="P资产")
    db_session.commit()
    viewer = User(id=OWNER + 1, username="acl-viewer", password_hash="x", salt="y",
                  status="active", is_deleted=False)
    db_session.add(viewer)
    db_session.flush()
    role = db_session.query(Role).filter(Role.code == "viewer").one()
    db_session.add(UserRole(user_id=viewer.id, role_id=role.id))
    db_session.commit()
    tree = artifact_service.get_tree(db_session, artifact_id=artifact.id, requester=viewer)
    assert tree["artifact_id"] == artifact.id
    with pytest.raises(ArtifactPermissionError):
        artifact_service.apply_operations(
            db_session, artifact_id=artifact.id,
            expected_revision=artifact.current_revision, requester=viewer,
            operations=[{"operation_type": "add_node", "parent_id": artifact.root_node_id,
                         "node_type": "module", "title": "只读"}])
    db_session.rollback()


def test_projectless_owner_permission_unaffected(db_session):
    user = _seed(db_session, extra_role="tester", grant_membership=False)
    artifact = artifact_service.create_artifact(db_session, requester=user, title="私有")
    db_session.commit()
    assert artifact_service.get_artifact(db_session, artifact_id=artifact.id,
                                         requester=user).id == artifact.id
    result = artifact_service.apply_operations(
        db_session, artifact_id=artifact.id, expected_revision=1, requester=user,
        operations=[{"operation_type": "add_node", "parent_id": artifact.root_node_id,
                     "node_type": "module", "title": "M"}])
    db_session.commit()
    assert result["new_revision"] == 2


def test_second_project_functional_artifact_create_rejected(db_session):
    user = _seed(db_session)
    first = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user, title="主")
    db_session.commit()
    # 普通 create 对任何 project-scoped artifact 一律拒绝（确保唯一入口）
    with pytest.raises(ArtifactValidationError) as exc:
        artifact_service.create_artifact(db_session, requester=user,
                                         title="第二份", project_id=PROJECT_P)
    db_session.rollback()
    assert exc.value.error_code == "artifact_project_ensure_required"
    assert first.id is not None
    again = artifact_service.ensure_project_functional_artifact(
        db_session, project_id=PROJECT_P, requester=user)
    assert again.id == first.id


def test_ensure_conflict_does_not_rollback_caller_uncommitted_work(db_session, monkeypatch):
    """P09.2 Preflight A：SAVEPOINT 冲突只回滚内部尝试，不波及外层未提交修改。"""
    from sqlalchemy.exc import IntegrityError

    from app.services.test_artifacts.errors import TestArtifactDataError as DataError

    user = _seed(db_session)
    # caller 未提交的一条修改（marker，projectless artifact）
    marker = artifact_service.create_artifact(db_session, requester=user, title="标记")
    db_session.flush()
    assert marker.id is not None

    def _boom(*_args, **_kwargs):
        raise IntegrityError("stmt", {}, Exception("duplicate"))

    monkeypatch.setattr(artifact_service, "create_artifact", _boom)
    with pytest.raises(DataError):
        artifact_service.ensure_project_functional_artifact(
            db_session, project_id=PROJECT_P, requester=user)
    # 外层事务仍健康：marker 未丢，可提交
    db_session.commit()
    assert artifact_service.list_artifacts(db_session, requester=user)  # marker 可读
