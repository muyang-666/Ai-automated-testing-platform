from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ApiDocument(Base):
    __tablename__ = "api_documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, comment="所属项目ID")
    module_id = Column(Integer, nullable=True, comment="所属模块ID")
    name = Column(String(200), nullable=False, comment="接口名称")
    description = Column(Text, nullable=True, comment="接口描述")
    method = Column(String(20), default="", nullable=False, comment="请求方法")
    url = Column(String(500), default="", nullable=False, comment="接口地址")
    headers_json = Column(JSON, nullable=True, comment="请求头JSON")
    params_json = Column(JSON, nullable=True, comment="请求参数JSON")
    body_json = Column(JSON, nullable=True, comment="请求体JSON")
    response_example_json = Column(JSON, nullable=True, comment="响应示例JSON")
    content = Column(Text, nullable=True, comment="原始接口文档文本")
    supplementary_prompt = Column(Text, nullable=True, comment="补充提示词（优先级最高）")
    status = Column(String(20), default="active", comment="状态：active/disabled/draft")
    is_deleted = Column(Boolean, default=False, comment="软删除标记")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
