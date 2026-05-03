from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.user import RoleResponse, UserCreate, UserResponse, UserRoleUpdate, UserUpdate
from app.services.auth_service import get_bearer_token, get_current_user_by_token, require_admin
from app.services.user_service import (
    create_user,
    get_role_list,
    get_user_list,
    soft_delete_user,
    update_user,
    update_user_roles,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/roles", response_model=list[RoleResponse], summary="查询角色列表")
def list_roles_api(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    get_current_user_by_token(db, token)
    return get_role_list(db)


@router.get("", response_model=list[UserResponse], summary="查询用户列表")
def list_users_api(
    keyword: Optional[str] = Query(default=None, description="按用户名/显示名称/邮箱搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    require_admin(db, token)
    return get_user_list(db, keyword=keyword, status=status)


@router.post("", response_model=UserResponse, summary="创建用户")
def create_user_api(
    user_data: UserCreate,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    require_admin(db, token)
    try:
        return create_user(db, user_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户")
def update_user_api(
    user_id: int,
    user_data: UserUpdate,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    require_admin(db, token)
    user = update_user(db, user_id, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.delete("/{user_id}", summary="删除用户")
def delete_user_api(
    user_id: int,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    require_admin(db, token)
    success = soft_delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "用户删除成功"}


@router.put("/{user_id}/roles", response_model=UserResponse, summary="分配用户角色")
def update_user_roles_api(
    user_id: int,
    role_data: UserRoleUpdate,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    require_admin(db, token)
    try:
        user = update_user_roles(db, user_id, role_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user
