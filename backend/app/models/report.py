from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, Float
from sqlalchemy.sql import func

from app.core.database import Base

# 测试报告历史表
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=False, comment="关联执行记录ID")
    summary = Column(Text, nullable=False, comment="测试总结")
    total_count = Column(Integer, default=0, comment="总执行数")
    passed_count = Column(Integer, default=0, comment="通过数")
    failed_count = Column(Integer, default=0, comment="失败数")
    pass_rate = Column(Float, default=0.0, comment="通过率")
    risk_summary = Column(Text, nullable=True, comment="风险总结")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")