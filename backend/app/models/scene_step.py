from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class SceneStep(Base):
    __tablename__ = "scene_steps"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False, index=True, comment="所属场景ID")
    step_order = Column(Integer, nullable=False, comment="步骤顺序")
    case_id = Column(Integer, ForeignKey("api_cases.id"), nullable=False, comment="关联测试用例ID")
    step_name = Column(String(100), nullable=True, comment="步骤名称")
    extract_rules_json = Column(JSON, nullable=True, comment="变量提取规则JSON")
    request_override_json = Column(JSON, nullable=True, comment="请求覆盖配置JSON")
    assertions_json = Column(JSON, nullable=True, comment="场景步骤断言规则JSON")
    enabled = Column(Boolean, default=True, comment="是否启用")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
