from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户ID")
    token = Column(String(128), unique=True, nullable=False, index=True, comment="登录token")
    expires_at = Column(DateTime(timezone=True), nullable=False, comment="过期时间")
    is_revoked = Column(Boolean, default=False, comment="是否已退出")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
