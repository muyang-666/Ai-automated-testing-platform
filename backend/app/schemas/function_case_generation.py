from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerateFunctionCasesRequest(BaseModel):
    requirement_id: int = Field(..., description="需求文本ID")
    generate_count: int = Field(default=6, ge=1, le=20, description="生成用例数量")
    case_types: list[str] = Field(
        default_factory=lambda: ["正常场景", "异常场景", "边界场景", "业务规则场景"],
        description="覆盖的用例类型",
    )


class GeneratedFunctionCaseItem(BaseModel):
    case_code: Optional[str] = None
    case_name: str = ""
    case_type: str = "其他"
    priority: str = "P1"
    precondition: Optional[str] = None
    steps_json: Optional[Any] = None
    test_data_json: Optional[Any] = None
    expected_result: Optional[str] = None
    remark: Optional[str] = None


class GenerateFunctionCasesResponse(BaseModel):
    requirement_id: int
    project_id: Optional[int] = None
    module_id: Optional[int] = None
    cases: list[GeneratedFunctionCaseItem] = []
    raw_output: Optional[str] = None
    errors: list[str] = []


class SaveGeneratedFunctionCasesRequest(BaseModel):
    requirement_id: int = Field(..., description="需求文本ID")
    project_id: int = Field(..., description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    cases: list[GeneratedFunctionCaseItem] = Field(..., description="要保存的功能用例")


class SaveGeneratedFunctionCasesResponse(BaseModel):
    saved_count: int
    case_ids: list[int]
