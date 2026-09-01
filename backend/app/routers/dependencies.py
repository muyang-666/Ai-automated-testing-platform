from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.services.permission_service import get_current_user_from_header


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    return get_current_user_from_header(authorization, db)
