from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.user import UserCreate, UserRoleUpdate, UserUpdate
from app.services.auth_service import get_user_role_codes, hash_password


def serialize_user(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "status": user.status,
        "roles": get_user_role_codes(db, user.id),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def get_user_list(db: Session, keyword: str | None = None, status: str | None = None) -> list[dict]:
    query = db.query(User).filter(User.is_deleted == False)
    if keyword:
        query = query.filter(
            or_(
                User.username.contains(keyword),
                User.display_name.contains(keyword),
                User.email.contains(keyword),
            )
        )
    if status:
        query = query.filter(User.status == status)

    users = query.order_by(User.id.desc()).all()
    return [serialize_user(db, user) for user in users]


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted == False,
        )
        .first()
    )


def get_role_list(db: Session) -> list[Role]:
    return db.query(Role).filter(Role.status == "active").order_by(Role.id.asc()).all()


def get_valid_roles(db: Session, role_ids: list[int]) -> list[Role]:
    unique_role_ids = list(dict.fromkeys(role_ids or []))
    if not unique_role_ids:
        return []

    roles = (
        db.query(Role)
        .filter(
            Role.id.in_(unique_role_ids),
            Role.status == "active",
        )
        .all()
    )
    if len(roles) != len(unique_role_ids):
        raise ValueError("角色不存在或已停用")
    return roles


def replace_user_roles(db: Session, user_id: int, role_ids: list[int]) -> None:
    roles = get_valid_roles(db, role_ids)
    db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)

    seen_role_ids = set()
    for role in roles:
        if role.id in seen_role_ids:
            continue
        db.add(UserRole(user_id=user_id, role_id=role.id))
        seen_role_ids.add(role.id)


def create_user(db: Session, user_data: UserCreate) -> dict:
    existed_user = db.query(User).filter(User.username == user_data.username).first()
    if existed_user:
        raise ValueError("用户名已存在")

    salt, password_hash = hash_password(user_data.password)
    db_user = User(
        username=user_data.username,
        password_hash=password_hash,
        salt=salt,
        display_name=user_data.display_name,
        email=user_data.email,
        status=user_data.status,
        is_deleted=False,
    )
    db.add(db_user)
    db.flush()
    replace_user_roles(db, db_user.id, user_data.role_ids)
    db.commit()
    db.refresh(db_user)
    return serialize_user(db, db_user)


def update_user(db: Session, user_id: int, user_data: UserUpdate) -> dict | None:
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    update_data = user_data.model_dump(exclude_unset=True)
    password = update_data.pop("password", None)
    if password:
        salt, password_hash = hash_password(password)
        db_user.salt = salt
        db_user.password_hash = password_hash

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return serialize_user(db, db_user)


def soft_delete_user(db: Session, user_id: int) -> bool:
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return False

    db_user.is_deleted = True
    db.commit()
    return True


def update_user_roles(db: Session, user_id: int, role_data: UserRoleUpdate) -> dict | None:
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    replace_user_roles(db, db_user.id, role_data.role_ids)
    db.commit()
    db.refresh(db_user)
    return serialize_user(db, db_user)
