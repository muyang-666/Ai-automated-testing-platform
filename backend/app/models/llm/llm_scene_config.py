from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class LLMSceneConfig(Base):
    __tablename__ = "llm_scene_configs"

    id = Column(Integer, primary_key=True, index=True)
    scene_code = Column(String(100), unique=True, nullable=False, comment="业务场景编码")
    scene_name = Column(String(100), nullable=False, comment="业务场景名称")
    model_id = Column(Integer, nullable=True, comment="绑定模型 ID")
    enabled = Column(Boolean, default=True, comment="是否启用")
    prompt_template = Column(Text, nullable=True, comment="Prompt 模板")
    remark = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
