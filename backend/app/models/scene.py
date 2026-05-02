from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=True, comment="归属项目ID")
    module_id = Column(Integer, nullable=True, comment="归属模块ID")
    name = Column(String(100), nullable=False, comment="场景名称")
    description = Column(String(255), nullable=True, comment="场景描述")
    status = Column(String(20), default="active", comment="状态：active/disabled/draft")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
