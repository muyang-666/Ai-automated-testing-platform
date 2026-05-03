from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="供应商名称")
    provider_type = Column(String(50), default="openai_compatible", comment="供应商类型")
    base_url = Column(String(255), nullable=False, comment="API Base URL")
    api_key = Column(Text, nullable=False, comment="API Key")
    status = Column(String(20), default="active", comment="状态：active/disabled")
    remark = Column(Text, nullable=True, comment="备注")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
