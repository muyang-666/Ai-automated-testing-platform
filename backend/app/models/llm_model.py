from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class LLMModel(Base):
    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, nullable=False, comment="所属 provider ID")
    model_name = Column(String(100), nullable=False, comment="模型实际名称")
    display_name = Column(String(100), nullable=True, comment="展示名称")
    temperature = Column(Float, default=0.7, comment="温度参数")
    max_tokens = Column(Integer, default=2048, comment="最大 token 数")
    timeout_seconds = Column(Integer, default=60, comment="超时时间(秒)")
    status = Column(String(20), default="active", comment="状态：active/disabled")
    remark = Column(Text, nullable=True, comment="备注")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
