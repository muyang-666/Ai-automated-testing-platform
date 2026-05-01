from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class APICaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用例名称")
    description: Optional[str] = Field(default=None, max_length=255, description="用例描述")
    method: str = Field(..., min_length=1, max_length=10, description="请求方法")
    url: str = Field(..., min_length=1, max_length=255, description="请求地址")
    headers: Optional[str] = Field(default=None, description="请求头JSON字符串")
    body: Optional[str] = Field(default=None, description="请求体JSON字符串")
    expected_result: Optional[str] = Field(default=None, description="预期结果JSON字符串")
    project_id: Optional[int] = Field(default=None, description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    case_type: Optional[str] = Field(default="正常场景", description="用例类型")
    source: Optional[str] = Field(default="manual", description="来源：manual/llm/rule")
    priority: Optional[str] = Field(default="P1", description="优先级：P0/P1/P2")
    status: Optional[str] = Field(default="active", description="用例状态：active/disabled/draft")


class APICaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="用例名称")
    description: Optional[str] = Field(default=None, max_length=255, description="用例描述")
    method: Optional[str] = Field(default=None, min_length=1, max_length=10, description="请求方法")
    url: Optional[str] = Field(default=None, min_length=1, max_length=255, description="请求地址")
    headers: Optional[str] = Field(default=None, description="请求头JSON字符串")
    body: Optional[str] = Field(default=None, description="请求体JSON字符串")
    expected_result: Optional[str] = Field(default=None, description="预期结果JSON字符串")
    project_id: Optional[int] = Field(default=None, description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    case_type: Optional[str] = Field(default=None, description="用例类型")
    source: Optional[str] = Field(default=None, description="来源：manual/llm/rule")
    priority: Optional[str] = Field(default=None, description="优先级：P0/P1/P2")
    status: Optional[str] = Field(default=None, description="用例状态：active/disabled/draft")


class APICaseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    method: str
    url: str
    headers: Optional[str]
    body: Optional[str]
    expected_result: Optional[str]
    generated_test_code: Optional[str]
    project_id: Optional[int]
    module_id: Optional[int]
    case_type: Optional[str]
    source: Optional[str]
    priority: Optional[str]
    status: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
