"""LLM Gateway 统一数据合同。

- metadata / raw_metadata 只允许非敏感信息，禁止放入 Secret；
- Pydantic 模型类型由方法参数 response_model 单独传入，不塞进 request。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

MessageRole = Literal["system", "user", "assistant", "tool"]
ResponseMode = Literal["text", "json", "pydantic"]


class LLMToolCall(BaseModel):
    """模型返回的工具调用。只解析，不执行。"""

    id: str = Field(..., description="工具调用 ID")
    name: str = Field(..., description="工具名称")
    arguments_json: str = Field(default="{}", description="参数 JSON 字符串")


class LLMMessage(BaseModel):
    role: MessageRole = Field(..., description="消息角色：system/user/assistant/tool")
    content: Optional[str] = Field(default=None, description="消息内容，可空")
    tool_call_id: Optional[str] = Field(default=None, description="tool 消息关联的工具调用 ID")
    name: Optional[str] = Field(default=None, description="消息名称，可空")
    tool_calls: list[LLMToolCall] = Field(
        default_factory=list, description="assistant 消息携带的工具调用（多轮工具对话映射用）"
    )


class LLMToolSpec(BaseModel):
    """模型可见的工具 Schema。只定义，不执行。"""

    name: str = Field(..., description="工具名称")
    description: str = Field(default="", description="工具描述")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="输入 JSON Schema")


class LLMRequest(BaseModel):
    messages: list[LLMMessage] = Field(..., description="消息列表")
    tools: Optional[list[LLMToolSpec]] = Field(default=None, description="工具定义，可空")
    temperature: Optional[float] = Field(default=None, description="温度，可空")
    max_tokens: Optional[int] = Field(default=None, description="最大输出 token，可空")
    timeout_seconds: Optional[float] = Field(default=None, description="超时秒数，可空")
    response_mode: ResponseMode = Field(default="text", description="text/json/pydantic")
    metadata: dict[str, Any] = Field(default_factory=dict, description="非敏感元数据，禁止放入 Secret")


class LLMResult(BaseModel):
    model_config = {"protected_namespaces": ()}

    content: str = Field(default="", description="模型文本输出")
    parsed: Optional[Any] = Field(default=None, description="结构化解析结果（json/pydantic 模式）")
    tool_calls: list[LLMToolCall] = Field(default_factory=list, description="模型返回的工具调用")
    provider_name: str = Field(..., description="供应商名称")
    model_name: str = Field(..., description="模型名称")
    prompt_tokens: Optional[int] = Field(default=None, description="提示词 token 数")
    completion_tokens: Optional[int] = Field(default=None, description="补全 token 数")
    duration_ms: int = Field(..., description="耗时(毫秒)")
    request_id: Optional[str] = Field(default=None, description="请求 ID")
    finish_reason: Optional[str] = Field(default=None, description="结束原因")
    raw_metadata: dict[str, Any] = Field(default_factory=dict, description="仅保留非敏感必要字段")
