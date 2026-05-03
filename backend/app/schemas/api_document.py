from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApiDocumentCreate(BaseModel):
    project_id: int = Field(..., description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    name: str = Field(..., min_length=1, max_length=200, description="接口文档名称")
    description: Optional[str] = Field(default=None, description="描述")
    method: str = Field(default="", max_length=20, description="请求方法")
    url: str = Field(default="", max_length=500, description="接口地址")
    headers_json: Optional[Any] = Field(default=None, description="请求头JSON对象")
    params_json: Optional[Any] = Field(default=None, description="请求参数JSON对象")
    body_json: Optional[Any] = Field(default=None, description="请求体JSON")
    response_example_json: Optional[Any] = Field(default=None, description="响应示例JSON")
    content: Optional[str] = Field(default=None, description="接口文档内容")
    supplementary_prompt: Optional[str] = Field(default=None, description="补充提示词（优先级最高）")
    status: str = Field(default="active", description="状态")


class ApiDocumentUpdate(BaseModel):
    project_id: Optional[int] = Field(default=None, description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="接口文档名称")
    description: Optional[str] = Field(default=None, description="描述")
    method: Optional[str] = Field(default=None, max_length=20, description="请求方法")
    url: Optional[str] = Field(default=None, max_length=500, description="接口地址")
    headers_json: Optional[Any] = Field(default=None, description="请求头JSON对象")
    params_json: Optional[Any] = Field(default=None, description="请求参数JSON对象")
    body_json: Optional[Any] = Field(default=None, description="请求体JSON")
    response_example_json: Optional[Any] = Field(default=None, description="响应示例JSON")
    content: Optional[str] = Field(default=None, description="接口文档内容")
    supplementary_prompt: Optional[str] = Field(default=None, description="补充提示词（优先级最高）")
    status: Optional[str] = Field(default=None, description="状态")


class ApiDocumentResponse(BaseModel):
    id: int
    project_id: int
    module_id: Optional[int]
    name: str
    description: Optional[str]
    method: str
    url: str
    headers_json: Optional[Any]
    params_json: Optional[Any]
    body_json: Optional[Any]
    response_example_json: Optional[Any]
    content: Optional[str]
    supplementary_prompt: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
