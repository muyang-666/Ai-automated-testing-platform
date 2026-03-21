from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


# 报告表
# 当前升级为“项目级测试报告”存储表，不再强绑定单个 run_id
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_name = Column(String(200), nullable=False, comment="报告名称")
    report_type = Column(String(50), nullable=False, default="project_scene_report", comment="报告类型")

    # 报告正文（LLM 生成的整段报告）
    summary = Column(Text, nullable=False, comment="报告正文")

    # 基础统计
    total_count = Column(Integer, nullable=False, default=0, comment="总步骤数")
    passed_count = Column(Integer, nullable=False, default=0, comment="通过步骤数")
    failed_count = Column(Integer, nullable=False, default=0, comment="失败步骤数")
    pass_rate = Column(Float, nullable=False, default=0.0, comment="通过率")

    # 风险总结
    risk_summary = Column(Text, nullable=True, comment="风险总结")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")