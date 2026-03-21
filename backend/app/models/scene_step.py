from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func

from app.core.database import Base


# 场景步骤表：表示某个场景下，按顺序执行的步骤
class SceneStep(Base):
    __tablename__ = "scene_steps"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False, index=True, comment="所属场景ID")
    step_order = Column(Integer, nullable=False, comment="步骤顺序")
    case_id = Column(Integer, ForeignKey("api_cases.id"), nullable=False, comment="关联测试用例ID")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")