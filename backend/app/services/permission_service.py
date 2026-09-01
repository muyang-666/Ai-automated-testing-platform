from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.services.auth_service import (
    ADMIN_ROLE_CODE,
    SYSTEM_ADMIN_ROLE_CODE,
    TESTER_ROLE_CODE,
    VIEWER_ROLE_CODE,
    get_bearer_token,
    get_current_user_by_token,
    get_user_role_codes,
)


def get_current_user_from_header(
    authorization: str | None,
    db: Session,
) -> User:
    token = get_bearer_token(authorization)
    return get_current_user_by_token(db, token)


def current_user_dependency(
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    # 仅用于类型提示占位。路由中需要同时 Depends(get_db)，所以不要直接使用本函数。
    return authorization


def get_roles(db: Session, user: User) -> list[str]:
    return get_user_role_codes(db, user.id)


def is_system_admin(db: Session, user: User) -> bool:
    return SYSTEM_ADMIN_ROLE_CODE in get_roles(db, user)


def is_admin(db: Session, user: User) -> bool:
    roles = get_roles(db, user)
    return SYSTEM_ADMIN_ROLE_CODE in roles or ADMIN_ROLE_CODE in roles


def is_tester(db: Session, user: User) -> bool:
    return TESTER_ROLE_CODE in get_roles(db, user)


def is_viewer(db: Session, user: User) -> bool:
    roles = get_roles(db, user)
    return VIEWER_ROLE_CODE in roles and not is_admin(db, user) and TESTER_ROLE_CODE not in roles


def require_admin_role(db: Session, user: User) -> None:
    if not is_admin(db, user):
        raise HTTPException(status_code=403, detail="需要管理员权限")


def require_write_role(db: Session, user: User) -> None:
    roles = get_roles(db, user)
    if SYSTEM_ADMIN_ROLE_CODE in roles or ADMIN_ROLE_CODE in roles or TESTER_ROLE_CODE in roles:
        return
    raise HTTPException(status_code=403, detail="当前角色仅允许查看，不能新增、编辑、删除或执行")


def get_operable_project_ids(db: Session, user: User) -> list[int]:
    rows = (
        db.query(UserProjectPermission.project_id)
        .filter(
            UserProjectPermission.user_id == user.id,
            UserProjectPermission.can_operate == True,
        )
        .order_by(UserProjectPermission.project_id.asc())
        .all()
    )
    return [row[0] for row in rows]


def can_operate_project(db: Session, user: User, project_id: int | None) -> bool:
    if project_id is None:
        return is_admin(db, user)
    if is_admin(db, user):
        return True
    if not is_tester(db, user):
        return False
    return project_id in get_operable_project_ids(db, user)


def can_read_project(db: Session, user: User, project_id: int | None) -> bool:
    if project_id is None:
        return True
    if is_admin(db, user) or is_viewer(db, user):
        return True
    if is_tester(db, user):
        return project_id in get_operable_project_ids(db, user)
    return False


def require_project_read(db: Session, user: User, project_id: int | None) -> None:
    if not can_read_project(db, user, project_id):
        raise HTTPException(status_code=403, detail="没有该项目的查看权限")


def require_project_write(db: Session, user: User, project_id: int | None) -> None:
    require_write_role(db, user)
    if not can_operate_project(db, user, project_id):
        raise HTTPException(status_code=403, detail="没有该项目的操作权限")


def allowed_project_ids_for_query(db: Session, user: User) -> list[int] | None:
    if is_admin(db, user) or is_viewer(db, user):
        return None
    if is_tester(db, user):
        return get_operable_project_ids(db, user)
    return []
