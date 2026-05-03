from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True, comment="角色编码")
    name = Column(String(100), nullable=False, comment="角色名称")
    description = Column(Text, nullable=True, comment="描述")
    is_system = Column(Boolean, default=False, comment="是否系统内置角色")
    status = Column(String(20), default="active", comment="状态")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
