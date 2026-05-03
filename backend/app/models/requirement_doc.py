from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class RequirementDoc(Base):
    __tablename__ = "requirement_docs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, comment="所属项目ID")
    module_id = Column(Integer, nullable=True, comment="所属模块ID")
    title = Column(String(200), nullable=False, comment="需求标题")
    content = Column(Text, nullable=False, comment="需求文本内容")
    requirement_type = Column(String(50), nullable=True, comment="需求类型")
    status = Column(String(20), default="confirmed", comment="状态：draft/confirmed/disabled")
    remark = Column(Text, nullable=True, comment="备注")
    supplementary_prompt = Column(Text, nullable=True, comment="补充提示词（生成用例时使用）")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
