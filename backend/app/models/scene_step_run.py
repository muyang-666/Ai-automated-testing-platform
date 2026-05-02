from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class SceneStepRun(Base):
    __tablename__ = "scene_step_runs"

    id = Column(Integer, primary_key=True, index=True)
    scene_run_id = Column(Integer, nullable=False, comment="关联scene_runs.id")
    scene_step_id = Column(Integer, nullable=True, comment="关联scene_steps.id")
    case_id = Column(Integer, nullable=True, comment="关联api_cases.id")
    step_order = Column(Integer, nullable=True, comment="步骤顺序")
    step_name = Column(String(100), nullable=True, comment="步骤名称")
    status = Column(String(20), nullable=False, comment="执行状态：passed/failed/skipped/error")
    request_method = Column(String(20), nullable=True, comment="请求方法")
    request_url = Column(Text, nullable=True, comment="请求地址")
    request_headers_json = Column(JSON, nullable=True, comment="请求头JSON")
    request_body_json = Column(JSON, nullable=True, comment="请求体JSON")
    response_status_code = Column(Integer, nullable=True, comment="响应状态码")
    response_body = Column(Text, nullable=True, comment="响应内容")
    extracted_variables_json = Column(JSON, nullable=True, comment="提取的变量JSON")
    assertion_results_json = Column(JSON, nullable=True, comment="断言结果JSON")
    error_message = Column(Text, nullable=True, comment="错误信息")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
