from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse
from app.services.auth_service import (
    build_current_user_response,
    get_bearer_token,
    get_current_user_by_token,
    login_user,
    logout_by_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse, summary="登录")
def login_api(login_data: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, login_data)


@router.post("/logout", response_model=LogoutResponse, summary="退出登录")
def logout_api(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    return logout_by_token(db, token)


@router.get("/me", response_model=CurrentUserResponse, summary="获取当前用户")
def get_current_user_api(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    token = get_bearer_token(authorization)
    user = get_current_user_by_token(db, token)
    return build_current_user_response(db, user)
