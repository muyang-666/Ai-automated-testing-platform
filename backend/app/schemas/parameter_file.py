from pydantic import BaseModel


class ParameterFileResponse(BaseModel):
    content: str


class ParameterFileUpdate(BaseModel):
    content: str