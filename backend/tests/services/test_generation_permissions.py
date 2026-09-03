"""生成/保存用例涉及的确定性权限规则 Baseline 测试。

只测试 permission_service 的纯权限规则（Router 集成测试不在本任务范围）。
数据库为每条测试重建的内存 SQLite，不依赖真实项目数据。
"""

import pytest
from fastapi import HTTPException

from app.models.project import Project
from app.models.role import Role
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.services import permission_service
from app.services.auth_service import (
    ADMIN_ROLE_CODE,
    TESTER_ROLE_CODE,
    VIEWER_ROLE_CODE,
)


def _seed_role(db, code):
    role = Role(code=code, name=code, status="active")
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _seed_user(db, username, role_codes):
    user = User(
        username=username,
        password_hash="x",
        salt="y",
        display_name=username,
        status="active",
        is_deleted=False,
    )
    db.add(user)
    db.flush()
    for code in role_codes:
        role = db.query(Role).filter(Role.code == code).one()
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def _seed_project(db, name="测试项目"):
    project = Project(name=name, status="active", is_deleted=False)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _grant(db, user, project, can_operate=True):
    perm = UserProjectPermission(
        user_id=user.id, project_id=project.id, can_operate=can_operate
    )
    db.add(perm)
    db.commit()
    return perm


# ── C.1 tester 对已授权且 can_operate=true 的项目拥有写权限 ──


def test_tester_with_operate_permission_can_write(db_session):
    _seed_role(db_session, TESTER_ROLE_CODE)
    user = _seed_user(db_session, "tester01", [TESTER_ROLE_CODE])
    project = _seed_project(db_session)
    _grant(db_session, user, project, can_operate=True)

    permission_service.require_project_write(db_session, user, project.id)  # 不抛异常
    assert permission_service.can_operate_project(db_session, user, project.id) is True


# ── C.2 tester 对未授权项目返回 403 ──


def test_tester_unauthorized_project_write_403(db_session):
    _seed_role(db_session, TESTER_ROLE_CODE)
    user = _seed_user(db_session, "tester01", [TESTER_ROLE_CODE])
    authorized = _seed_project(db_session, "已授权项目")
    _grant(db_session, user, authorized, can_operate=True)
    other = _seed_project(db_session, "未授权项目")

    assert permission_service.can_operate_project(db_session, user, other.id) is False
    with pytest.raises(HTTPException) as exc:
        permission_service.require_project_write(db_session, user, other.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "没有该项目的操作权限"


def test_tester_can_operate_false_403(db_session):
    _seed_role(db_session, TESTER_ROLE_CODE)
    user = _seed_user(db_session, "tester01", [TESTER_ROLE_CODE])
    project = _seed_project(db_session)
    _grant(db_session, user, project, can_operate=False)

    with pytest.raises(HTTPException) as exc:
        permission_service.require_project_write(db_session, user, project.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "没有该项目的操作权限"


# ── C.3 viewer 即使存在项目记录也不能执行写操作 ──


def test_viewer_cannot_write_even_with_permission_row(db_session):
    _seed_role(db_session, VIEWER_ROLE_CODE)
    user = _seed_user(db_session, "viewer01", [VIEWER_ROLE_CODE])
    project = _seed_project(db_session)
    _grant(db_session, user, project, can_operate=True)

    assert permission_service.can_operate_project(db_session, user, project.id) is False
    with pytest.raises(HTTPException) as exc:
        permission_service.require_project_write(db_session, user, project.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "当前角色仅允许查看，不能新增、编辑、删除或执行"


# ── 补充：确定性读取规则 ──


def test_viewer_can_read(db_session):
    _seed_role(db_session, VIEWER_ROLE_CODE)
    user = _seed_user(db_session, "viewer01", [VIEWER_ROLE_CODE])
    project = _seed_project(db_session)

    assert permission_service.can_read_project(db_session, user, project.id) is True
    permission_service.require_project_read(db_session, user, project.id)  # 不抛异常


def test_tester_read_requires_authorization(db_session):
    _seed_role(db_session, TESTER_ROLE_CODE)
    user = _seed_user(db_session, "tester01", [TESTER_ROLE_CODE])
    authorized = _seed_project(db_session, "已授权项目")
    _grant(db_session, user, authorized, can_operate=True)
    other = _seed_project(db_session, "未授权项目")

    assert permission_service.can_read_project(db_session, user, authorized.id) is True
    permission_service.require_project_read(db_session, user, authorized.id)  # 不抛异常

    assert permission_service.can_read_project(db_session, user, other.id) is False
    with pytest.raises(HTTPException) as exc:
        permission_service.require_project_read(db_session, user, other.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "没有该项目的查看权限"


def test_admin_can_operate_without_permission_row(db_session):
    _seed_role(db_session, ADMIN_ROLE_CODE)
    user = _seed_user(db_session, "admin01", [ADMIN_ROLE_CODE])
    project = _seed_project(db_session)

    assert permission_service.can_operate_project(db_session, user, project.id) is True
    permission_service.require_project_write(db_session, user, project.id)  # 不抛异常
