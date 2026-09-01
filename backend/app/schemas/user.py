from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)
    display_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=100)
    status: Literal["active", "disabled"] = "active"
    role_ids: list[int] = Field(default_factory=list)
    project_ids: list[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=100)
    status: Literal["active", "disabled"] | None = None
    password: str | None = Field(default=None, min_length=1)
    project_ids: list[int] | None = None


class UserRoleUpdate(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class UserProjectPermissionUpdate(BaseModel):
    project_ids: list[int] = Field(default_factory=list)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    status: str
    roles: list[str]
    project_ids: list[int] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    is_system: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
