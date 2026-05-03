from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    salt = Column(String(64), nullable=False, comment="密码盐")
    display_name = Column(String(100), nullable=True, comment="显示名称")
    email = Column(String(100), nullable=True, comment="邮箱")
    status = Column(String(20), default="active", comment="状态：active/disabled")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    last_login_at = Column(DateTime(timezone=True), nullable=True, comment="最后登录时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
