"""Provider Adapter 协议与能力三态定义。

- Adapter 只负责请求/响应转换与 tool_calls 解析，不查询数据库、不执行工具、
  不保存 AgentRun/AgentStep；
- 重试统一由 LLMGateway 负责，Adapter 单次尝试（SDK 客户端 max_retries=0）；
- 错误统一转换为 app.exceptions.llm_errors 异常。
"""

from enum import Enum
from typing import Protocol, runtime_checkable

from app.schemas.llm.llm_gateway import LLMRequest, LLMResult

PROVIDER_TYPE_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_TYPE_ANTHROPIC = "anthropic"


class Capability(str, Enum):
    """能力三态。

    - SUPPORTED：明确支持，可以使用原生能力（如原生结构化输出）；
    - UNSUPPORTED：明确不支持，请求该能力时拒绝（如 tools）；
    - UNKNOWN：兼容性未知，默认走保守路径（如"JSON 提示约束 + Pydantic 本地校验"）。
    """

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ProviderCapabilities:
    """一次调用解析出的能力集合（Gateway 将 override 与 Adapter 基线合并）。"""

    def __init__(
        self,
        tools: Capability = Capability.UNKNOWN,
        structured_output: Capability = Capability.UNKNOWN,
        streaming: Capability = Capability.UNKNOWN,
    ):
        self.tools = tools
        self.structured_output = structured_output
        self.streaming = streaming


@runtime_checkable
class LLMProviderAdapter(Protocol):
    """Provider Adapter 协议。"""

    provider_type: str

    def complete(
        self,
        provider,
        model,
        request: LLMRequest,
        response_model=None,
        capabilities: ProviderCapabilities | None = None,
    ) -> LLMResult:
        """执行一次模型调用并返回统一结果。不做重试、不做结构化校验（Gateway 负责）。"""
        ...
