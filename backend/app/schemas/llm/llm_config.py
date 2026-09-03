from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Provider ──

class LLMProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="供应商名称")
    provider_type: str = Field(default="openai_compatible", description="供应商类型")
    base_url: str = Field(..., min_length=1, max_length=255, description="API Base URL")
    api_key: str = Field(..., min_length=1, description="API Key")
    status: str = Field(default="active", description="状态")
    remark: Optional[str] = Field(default=None, description="备注")


class LLMProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="供应商名称")
    provider_type: Optional[str] = Field(default=None, description="供应商类型")
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=255, description="API Base URL")
    api_key: Optional[str] = Field(default=None, description="API Key（留空则不修改）")
    status: Optional[str] = Field(default=None, description="状态")
    remark: Optional[str] = Field(default=None, description="备注")


class LLMProviderResponse(BaseModel):
    id: int
    name: str
    provider_type: str
    base_url: str
    masked_api_key: str = ""
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Model ──

class LLMModelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider_id: int = Field(..., description="所属供应商 ID")
    model_name: str = Field(..., min_length=1, max_length=100, description="模型名称")
    display_name: Optional[str] = Field(default=None, max_length=100, description="展示名称")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int = Field(default=2048, description="最大 token 数")
    timeout_seconds: int = Field(default=60, description="超时时间(秒)")
    status: str = Field(default="active", description="状态")
    remark: Optional[str] = Field(default=None, description="备注")


class LLMModelUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider_id: Optional[int] = Field(default=None, description="所属供应商 ID")
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模型名称")
    display_name: Optional[str] = Field(default=None, max_length=100, description="展示名称")
    temperature: Optional[float] = Field(default=None, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, description="最大 token 数")
    timeout_seconds: Optional[int] = Field(default=None, description="超时时间(秒)")
    status: Optional[str] = Field(default=None, description="状态")
    remark: Optional[str] = Field(default=None, description="备注")


class LLMModelResponse(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    provider_id: int
    provider_name: Optional[str] = ""
    model_name: str
    display_name: Optional[str]
    temperature: float
    max_tokens: int
    timeout_seconds: int
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Scene Config ──

class LLMSceneConfigUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: Optional[int] = Field(default=None, description="绑定模型 ID（可为空）")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    prompt_template: Optional[str] = Field(default=None, description="Prompt 模板")
    remark: Optional[str] = Field(default=None, description="备注")


class LLMSceneConfigResponse(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    scene_code: str
    scene_name: str
    model_id: Optional[int]
    model_name: Optional[str] = ""
    display_name: Optional[str] = ""
    provider_name: Optional[str] = ""
    enabled: bool
    prompt_template: Optional[str]
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Test ──

class LLMTestRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="测试 prompt")


class LLMTestResponse(BaseModel):
    success: bool
    output: Optional[str] = ""
    error: Optional[str] = None
