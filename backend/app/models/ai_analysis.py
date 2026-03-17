from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, String
from sqlalchemy.sql import func

from app.core.database import Base


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=False, comment="关联执行记录ID")
    analysis_type = Column(String(50), nullable=False, comment="分析类型")
    content = Column(Text, nullable=False, comment="分析内容")
    risk_level = Column(String(20), nullable=True, comment="风险等级")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")