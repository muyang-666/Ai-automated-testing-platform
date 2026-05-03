from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    status: str
    roles: list[str]


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: CurrentUserResponse


class LogoutResponse(BaseModel):
    message: str
