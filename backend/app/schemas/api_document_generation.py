from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerateApiCasesRequest(BaseModel):
    document_id: int = Field(..., description="接口文档ID")


class GeneratedApiCaseItem(BaseModel):
    name: str = Field(default="", description="用例名称")
    description: Optional[str] = Field(default="", description="用例描述")
    method: str = Field(default="GET", description="请求方法")
    url: str = Field(default="", description="接口地址")
    headers: Optional[Any] = Field(default=None, description="请求头")
    body: Optional[Any] = Field(default=None, description="请求体")
    expected_result: Optional[Any] = Field(default=None, description="预期结果")
    case_type: str = Field(default="正常场景", description="用例类型")
    priority: str = Field(default="P1", description="优先级")
    remark: Optional[str] = Field(default="", description="备注")


class GenerateApiCasesResponse(BaseModel):
    document_id: int
    project_id: Optional[int] = None
    module_id: Optional[int] = None
    cases: list[GeneratedApiCaseItem] = []
    raw_output: Optional[str] = None
    errors: list[str] = []


class SaveGeneratedApiCasesRequest(BaseModel):
    document_id: int = Field(..., description="接口文档ID")
    project_id: int = Field(..., description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    cases: list[GeneratedApiCaseItem] = Field(..., description="要保存的用例列表")


class SaveGeneratedApiCasesResponse(BaseModel):
    saved_count: int = 0
    case_ids: list[int] = []
