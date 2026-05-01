from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TestModuleCreate(BaseModel):
    project_id: int = Field(..., description="所属项目ID")
    parent_id: Optional[int] = Field(default=None, description="父模块ID，不传则创建一级模块")
    name: str = Field(..., min_length=1, max_length=100, description="模块名称")
    description: Optional[str] = Field(default=None, description="模块描述")
    module_type: str = Field(default="common", description="模块类型")


class TestModuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模块名称")
    description: Optional[str] = Field(default=None, description="模块描述")
    status: Optional[Literal["active", "archived", "disabled"]] = Field(default=None, description="状态")


class TestModuleResponse(BaseModel):
    id: int
    project_id: int
    parent_id: Optional[int]
    name: str
    description: Optional[str]
    module_type: str
    level: int
    sort_order: int
    path: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestModuleTreeResponse(BaseModel):
    id: int
    project_id: int
    parent_id: Optional[int]
    name: str
    description: Optional[str]
    module_type: str
    level: int
    sort_order: int
    path: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    children: list[TestModuleTreeResponse] = []

    class Config:
        from_attributes = True


class MoveModuleRequest(BaseModel):
    new_parent_id: Optional[int] = Field(default=None, description="新父模块ID，不传则移动到一级")


class ReorderRequest(BaseModel):
    parent_id: Optional[int] = Field(default=None, description="父模块ID，None表示一级模块")
    ordered_module_ids: list[int] = Field(..., description="排序后的模块ID列表")
