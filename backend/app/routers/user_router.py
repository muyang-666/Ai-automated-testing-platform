from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    RoleResponse,
    UserCreate,
    UserProjectPermissionUpdate,
    UserResponse,
    UserRoleUpdate,
    UserUpdate,
)
from app.services.auth_service import get_bearer_token, require_admin
from app.services.user_service import (
    count_active_admin_users,
    count_active_system_admin_users,
    create_user,
    get_role_list,
    get_user_by_id,
    get_user_list,
    role_ids_include_admin,
    role_ids_include_system_admin,
    soft_delete_user,
    update_user,
    update_user_project_permissions,
    update_user_roles,
    user_has_any_role,
    user_has_role,
)

router = APIRouter(prefix="/users", tags=["Users"])


def get_current_admin_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = get_bearer_token(authorization)
    return require_admin(db, token)


def ensure_roles_selected(role_ids: list[int]) -> None:
    if not role_ids:
        raise HTTPException(status_code=400, detail="请至少分配一个角色")


def ensure_self_protection(current_admin: User, target_user_id: int, action: str) -> None:
    if current_admin.id == target_user_id:
        raise HTTPException(status_code=400, detail=f"不能{action}当前登录用户")


def ensure_last_admin_protection(db: Session, target_user_id: int, action: str) -> None:
    if user_has_role(db, target_user_id, "admin") and count_active_admin_users(db) <= 1:
        raise HTTPException(status_code=400, detail=f"不能{action}系统最后一个启用管理员")


def current_is_system_admin(db: Session, current_admin: User) -> bool:
    return user_has_role(db, current_admin.id, "system_admin")


def target_is_admin_level(db: Session, target_user_id: int) -> bool:
    return user_has_any_role(db, target_user_id, {"system_admin", "admin"})


def ensure_can_manage_target(db: Session, current_admin: User, target_user_id: int) -> None:
    if current_is_system_admin(db, current_admin):
        return
    if current_admin.id != target_user_id and target_is_admin_level(db, target_user_id):
        raise HTTPException(status_code=403, detail="管理员不能操作其他管理员或系统管理员")


def ensure_can_assign_roles(db: Session, current_admin: User, role_ids: list[int], target_user_id: int | None = None) -> None:
    assigning_system_admin = role_ids_include_system_admin(db, role_ids)
    assigning_admin = role_ids_include_admin(db, role_ids)

    if not current_is_system_admin(db, current_admin) and (assigning_system_admin or assigning_admin):
        raise HTTPException(status_code=403, detail="只有系统管理员可以分配管理员角色")

    if assigning_system_admin and count_active_system_admin_users(db, exclude_user_id=target_user_id) > 0:
        raise HTTPException(status_code=400, detail="系统管理员只能有一个")


def ensure_system_admin_protection(db: Session, target_user_id: int, action: str) -> None:
    if user_has_role(db, target_user_id, "system_admin") and count_active_system_admin_users(db) <= 1:
        raise HTTPException(status_code=400, detail=f"不能{action}唯一系统管理员")


def ensure_system_admin_activation(db: Session, target_user_id: int) -> None:
    if (
        user_has_role(db, target_user_id, "system_admin")
        and count_active_system_admin_users(db, exclude_user_id=target_user_id) > 0
    ):
        raise HTTPException(status_code=400, detail="系统管理员只能有一个")


@router.get("/roles", response_model=list[RoleResponse], summary="查询角色列表")
def list_roles_api(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    return get_role_list(db)


@router.get("", response_model=list[UserResponse], summary="查询用户列表")
def list_users_api(
    keyword: Optional[str] = Query(default=None, description="按用户名/显示名称/邮箱搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    return get_user_list(db, keyword=keyword, status=status)


@router.post("", response_model=UserResponse, summary="创建用户")
def create_user_api(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    ensure_roles_selected(user_data.role_ids)
    ensure_can_assign_roles(db, current_admin, user_data.role_ids)
    try:
        return create_user(db, user_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户")
def update_user_api(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    ensure_can_manage_target(db, current_admin, user_id)
    if user_data.status == "disabled":
        ensure_self_protection(current_admin, user_id, "停用")
        ensure_last_admin_protection(db, user_id, "停用")
        ensure_system_admin_protection(db, user_id, "停用")
    elif user_data.status == "active":
        ensure_system_admin_activation(db, user_id)

    user = update_user(db, user_id, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.delete("/{user_id}", summary="删除用户")
def delete_user_api(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    ensure_can_manage_target(db, current_admin, user_id)
    ensure_self_protection(current_admin, user_id, "删除")
    ensure_last_admin_protection(db, user_id, "删除")
    ensure_system_admin_protection(db, user_id, "删除")

    success = soft_delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "用户删除成功"}


@router.put("/{user_id}/roles", response_model=UserResponse, summary="分配用户角色")
def update_user_roles_api(
    user_id: int,
    role_data: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    ensure_roles_selected(role_data.role_ids)
    ensure_can_manage_target(db, current_admin, user_id)

    target_user = get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    will_have_admin = role_ids_include_admin(db, role_data.role_ids)
    will_have_system_admin = role_ids_include_system_admin(db, role_data.role_ids)
    ensure_can_assign_roles(db, current_admin, role_data.role_ids, target_user_id=user_id)

    if current_admin.id == user_id and user_has_role(db, user_id, "admin") and not will_have_admin:
        raise HTTPException(status_code=400, detail="不能移除当前登录用户的管理员角色")
    if current_admin.id == user_id and user_has_role(db, user_id, "system_admin") and not will_have_system_admin:
        raise HTTPException(status_code=400, detail="不能移除当前登录用户的系统管理员角色")

    if (
        target_user.status == "active"
        and user_has_role(db, user_id, "admin")
        and not will_have_admin
        and count_active_admin_users(db) <= 1
    ):
        raise HTTPException(status_code=400, detail="不能移除系统最后一个启用管理员的管理员角色")
    if (
        target_user.status == "active"
        and user_has_role(db, user_id, "system_admin")
        and not will_have_system_admin
        and count_active_system_admin_users(db) <= 1
    ):
        raise HTTPException(status_code=400, detail="不能移除唯一系统管理员的系统管理员角色")

    try:
        user = update_user_roles(db, user_id, role_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return user


@router.put("/{user_id}/projects", response_model=UserResponse, summary="分配用户项目操作权限")
def update_user_projects_api(
    user_id: int,
    data: UserProjectPermissionUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    ensure_can_manage_target(db, current_admin, user_id)
    target_user = get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        user = update_user_project_permissions(db, user_id, data.project_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user
