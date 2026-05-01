from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class FunctionCaseCreate(BaseModel):
    project_id: int = Field(..., description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    requirement_id: Optional[int] = Field(default=None, description="关联需求文本ID")
    case_code: Optional[str] = Field(default=None, max_length=100, description="用例编号")
    case_name: str = Field(..., min_length=1, max_length=200, description="用例名称")
    case_type: Optional[str] = Field(default=None, description="用例类型")
    source: str = Field(default="manual", description="来源：manual/llm")
    priority: str = Field(default="P1", description="优先级：P0/P1/P2")
    precondition: Optional[str] = Field(default=None, description="前置条件")
    steps_json: Optional[Any] = Field(default=None, description="测试步骤JSON")
    test_data_json: Optional[Any] = Field(default=None, description="测试数据JSON")
    expected_result: Optional[str] = Field(default=None, description="预期结果")
    status: str = Field(default="active", description="用例状态：active/disabled/draft")
    remark: Optional[str] = Field(default=None, description="备注")


class FunctionCaseUpdate(BaseModel):
    project_id: Optional[int] = Field(default=None, description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    requirement_id: Optional[int] = Field(default=None, description="关联需求文本ID")
    case_code: Optional[str] = Field(default=None, max_length=100, description="用例编号")
    case_name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="用例名称")
    case_type: Optional[str] = Field(default=None, description="用例类型")
    source: Optional[str] = Field(default=None, description="来源：manual/llm")
    priority: Optional[str] = Field(default=None, description="优先级：P0/P1/P2")
    precondition: Optional[str] = Field(default=None, description="前置条件")
    steps_json: Optional[Any] = Field(default=None, description="测试步骤JSON")
    test_data_json: Optional[Any] = Field(default=None, description="测试数据JSON")
    expected_result: Optional[str] = Field(default=None, description="预期结果")
    status: Optional[str] = Field(default=None, description="用例状态：active/disabled/draft")
    remark: Optional[str] = Field(default=None, description="备注")


class FunctionCaseResponse(BaseModel):
    id: int
    project_id: int
    module_id: Optional[int]
    requirement_id: Optional[int]
    case_code: Optional[str]
    case_name: str
    case_type: Optional[str]
    source: Optional[str]
    priority: Optional[str]
    precondition: Optional[str]
    steps_json: Optional[Any]
    test_data_json: Optional[Any]
    expected_result: Optional[str]
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
