from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class TestModule(Base):
    __tablename__ = "test_modules"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, comment="所属项目ID")
    parent_id = Column(Integer, nullable=True, comment="父模块ID，一级模块为空")
    name = Column(String(100), nullable=False, comment="模块名称")
    description = Column(Text, nullable=True, comment="模块描述")
    module_type = Column(String(20), default="common", comment="模块类型")
    level = Column(Integer, default=1, comment="模块层级")
    sort_order = Column(Integer, default=0, comment="同级排序值")
    path = Column(String(255), nullable=True, comment="模块路径，如 1/2/3")
    status = Column(String(20), default="active", comment="状态：active/archived/disabled")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
