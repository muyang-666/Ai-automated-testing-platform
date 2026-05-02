from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class SceneRun(Base):
    __tablename__ = "scene_runs"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, nullable=False, comment="场景ID")
    project_id = Column(Integer, nullable=True, comment="项目ID")
    module_id = Column(Integer, nullable=True, comment="模块ID")
    status = Column(String(20), default="running", comment="执行状态：running/passed/failed/error")
    total_steps = Column(Integer, default=0, comment="总步骤数")
    passed_steps = Column(Integer, default=0, comment="通过数")
    failed_steps = Column(Integer, default=0, comment="失败数")
    skipped_steps = Column(Integer, default=0, comment="跳过数")
    context_json = Column(JSON, nullable=True, comment="最终运行时上下文")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
