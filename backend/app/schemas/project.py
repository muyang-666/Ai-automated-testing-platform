from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="项目名称")
    description: Optional[str] = Field(default=None, description="项目描述")
    status: Literal["active", "archived", "disabled"] = Field(default="active", description="项目状态")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="项目名称")
    description: Optional[str] = Field(default=None, description="项目描述")
    status: Optional[Literal["active", "archived", "disabled"]] = Field(default=None, description="项目状态")


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectSummaryResponse(ProjectResponse):
    api_case_count: int = 0
    function_case_count: int = 0
    requirement_count: int = 0
    scene_count: int = 0
