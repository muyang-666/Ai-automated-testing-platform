from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# 创建场景
class SceneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(default=None, max_length=255, description="场景描述")


# 更新场景
class SceneUpdate(SceneCreate):
    pass


# 返回场景
class SceneResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 新增场景步骤
class SceneStepCreate(BaseModel):
    step_order: int = Field(..., ge=1, description="步骤顺序")
    case_id: int = Field(..., ge=1, description="关联测试用例ID")


# 返回场景步骤
class SceneStepResponse(BaseModel):
    id: int
    scene_id: int
    step_order: int
    case_id: int
    case_name: str
    case_url: str
    created_at: datetime


# 场景执行结果中的单步结果
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


# 场景执行总结果
class SceneExecuteResponse(BaseModel):
    scene_id: int
    scene_name: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    final_result: str
    steps: list[SceneExecuteStepResult]
