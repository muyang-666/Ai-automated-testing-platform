from datetime import datetime, timedelta
import hashlib
import hmac
import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.auth import LoginRequest

TOKEN_EXPIRE_DAYS = 7

DEFAULT_ROLES = [
    {"code": "admin", "name": "管理员", "description": "系统管理员", "is_system": True},
    {"code": "tester", "name": "测试人员", "description": "测试执行和用例维护人员", "is_system": True},
    {"code": "viewer", "name": "只读用户", "description": "只读查看人员", "is_system": True},
]


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    ).hex()
    return salt, password_hash


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    current_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    ).hex()
    return hmac.compare_digest(current_hash, password_hash)


def create_token() -> str:
    return secrets.token_urlsafe(32)


def get_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="无效的登录凭证")

    return parts[1].strip()


def get_user_role_codes(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(
            UserRole.user_id == user_id,
            Role.status == "active",
        )
        .order_by(Role.id.asc())
        .all()
    )
    return [row[0] for row in rows]


def build_current_user_response(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "status": user.status,
        "roles": get_user_role_codes(db, user.id),
    }


def get_current_user_by_token(db: Session, token: str) -> User:
    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token == token,
            AuthSession.is_revoked == False,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")

    if session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="登录已过期")

    user = (
        db.query(User)
        .filter(
            User.id == session.user_id,
            User.is_deleted == False,
            User.status == "active",
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="用户不可用")

    return user


def require_admin(db: Session, token: str) -> User:
    user = get_current_user_by_token(db, token)
    if "admin" not in get_user_role_codes(db, user.id):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def login_user(db: Session, login_data: LoginRequest) -> dict:
    user = (
        db.query(User)
        .filter(
            User.username == login_data.username,
            User.is_deleted == False,
        )
        .first()
    )
    if not user or not verify_password(login_data.password, user.salt, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="用户已停用")

    token = create_token()
    expires_at = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    auth_session = AuthSession(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        is_revoked=False,
    )
    user.last_login_at = datetime.utcnow()

    db.add(auth_session)
    db.commit()
    db.refresh(auth_session)
    db.refresh(user)

    return {
        "token": token,
        "expires_at": auth_session.expires_at,
        "user": build_current_user_response(db, user),
    }


def logout_by_token(db: Session, token: str) -> dict:
    auth_session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token == token,
            AuthSession.is_revoked == False,
        )
        .first()
    )
    if not auth_session:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")

    auth_session.is_revoked = True
    db.commit()
    return {"message": "退出登录成功"}


def init_default_auth_data(db: Session) -> None:
    role_map = {}
    for role_data in DEFAULT_ROLES:
        role = db.query(Role).filter(Role.code == role_data["code"]).first()
        if not role:
            role = Role(**role_data, status="active")
            db.add(role)
            db.flush()
        role_map[role.code] = role

    if db.query(User).count() == 0:
        salt, password_hash = hash_password("123456")
        admin_user = User(
            username="admin",
            password_hash=password_hash,
            salt=salt,
            display_name="系统管理员",
            status="active",
            is_deleted=False,
        )
        db.add(admin_user)
        db.flush()
        db.add(UserRole(user_id=admin_user.id, role_id=role_map["admin"].id))

    db.commit()
