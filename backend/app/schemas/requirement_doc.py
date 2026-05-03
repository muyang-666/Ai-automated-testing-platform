from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RequirementDocCreate(BaseModel):
    project_id: int = Field(..., description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    title: str = Field(..., min_length=1, max_length=200, description="需求标题")
    content: str = Field(..., min_length=1, description="需求文本内容")
    requirement_type: Optional[str] = Field(default=None, description="需求类型")
    status: str = Field(default="confirmed", description="状态：draft/confirmed/disabled")
    remark: Optional[str] = Field(default=None, description="备注")
    supplementary_prompt: Optional[str] = Field(default=None, description="补充提示词")


class RequirementDocUpdate(BaseModel):
    project_id: Optional[int] = Field(default=None, description="所属项目ID")
    module_id: Optional[int] = Field(default=None, description="所属模块ID")
    title: Optional[str] = Field(default=None, min_length=1, max_length=200, description="需求标题")
    content: Optional[str] = Field(default=None, min_length=1, description="需求文本内容")
    requirement_type: Optional[str] = Field(default=None, description="需求类型")
    status: Optional[str] = Field(default=None, description="状态：draft/confirmed/disabled")
    remark: Optional[str] = Field(default=None, description="备注")
    supplementary_prompt: Optional[str] = Field(default=None, description="补充提示词")


class RequirementDocResponse(BaseModel):
    id: int
    project_id: int
    module_id: Optional[int]
    title: str
    content: str
    requirement_type: Optional[str]
    status: str
    remark: Optional[str]
    supplementary_prompt: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
