from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SceneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(default=None, max_length=255, description="场景描述")
    project_id: Optional[int] = Field(default=None, description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    status: str = Field(default="active", description="状态：active/disabled/draft")


class SceneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(default=None, max_length=255, description="场景描述")
    project_id: Optional[int] = Field(default=None, description="归属项目ID")
    module_id: Optional[int] = Field(default=None, description="归属模块ID")
    status: Optional[str] = Field(default=None, description="状态：active/disabled/draft")


class SceneResponse(BaseModel):
    id: int
    project_id: Optional[int]
    module_id: Optional[int]
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SceneStepCreate(BaseModel):
    step_order: int = Field(..., ge=1, description="步骤顺序")
    case_id: int = Field(..., ge=1, description="关联测试用例ID")
    step_name: Optional[str] = Field(default=None, max_length=100, description="步骤名称")
    extract_rules_json: Optional[Any] = Field(default=None, description="变量提取规则JSON")
    request_override_json: Optional[Any] = Field(default=None, description="请求覆盖配置JSON")
    assertions_json: Optional[Any] = Field(default=None, description="场景步骤断言规则JSON")
    enabled: bool = Field(default=True, description="是否启用")


class SceneStepUpdate(BaseModel):
    step_order: Optional[int] = Field(default=None, ge=1, description="步骤顺序")
    case_id: Optional[int] = Field(default=None, ge=1, description="关联测试用例ID")
    step_name: Optional[str] = Field(default=None, max_length=100, description="步骤名称")
    extract_rules_json: Optional[Any] = Field(default=None, description="变量提取规则JSON")
    request_override_json: Optional[Any] = Field(default=None, description="请求覆盖配置JSON")
    assertions_json: Optional[Any] = Field(default=None, description="场景步骤断言规则JSON")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class SceneStepResponse(BaseModel):
    id: int
    scene_id: int
    step_order: int
    case_id: int
    case_name: str
    case_url: str
    step_name: Optional[str]
    extract_rules_json: Optional[Any]
    request_override_json: Optional[Any]
    assertions_json: Optional[Any]
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime]


class ReorderSceneStepsRequest(BaseModel):
    ordered_step_ids: list[int] = Field(..., description="排序后的步骤ID列表")


class SceneExecuteStepResult(BaseModel):
    step_order: int
    case_id: int
    case_name: str
    run_id: Optional[int] = None
    status: str
    result: str
    response_status_code: Optional[int] = None
    response_content: Optional[str] = None
    error_message: Optional[str] = None


class SceneExecuteResponse(BaseModel):
    scene_id: int
    scene_name: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    final_result: str
    steps: list[SceneExecuteStepResult]
