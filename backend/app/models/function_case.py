from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class FunctionCase(Base):
    __tablename__ = "function_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, comment="所属项目ID")
    module_id = Column(Integer, nullable=True, comment="所属模块ID")
    requirement_id = Column(Integer, nullable=True, comment="关联需求文本ID")
    case_code = Column(String(100), nullable=True, comment="用例编号，如 FC-LOGIN-001")
    case_name = Column(String(200), nullable=False, comment="用例名称")
    case_type = Column(String(50), nullable=True, comment="用例类型：正常场景/异常场景/边界场景/业务规则场景/其他")
    source = Column(String(20), default="manual", comment="来源：manual/llm")
    priority = Column(String(20), default="P1", comment="优先级：P0/P1/P2")
    precondition = Column(Text, nullable=True, comment="前置条件")
    steps_json = Column(JSON, nullable=True, comment="测试步骤JSON")
    test_data_json = Column(JSON, nullable=True, comment="测试数据JSON")
    expected_result = Column(Text, nullable=True, comment="预期结果")
    status = Column(String(20), default="active", comment="用例状态：active/disabled/draft")
    remark = Column(Text, nullable=True, comment="备注")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
