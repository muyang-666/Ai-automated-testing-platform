"""LLM 层统一异常。

- 每个异常带 error_code 与 retryable 标记；
- 消息只包含用户可读信息，禁止包含 API Key、Authorization 或完整敏感 payload；
- 调用方应保留原始异常链（raise ... from e），API 输出不暴露内部对象。
"""


class LLMError(Exception):
    """LLM 层异常基类。"""

    error_code: str = "llm_error"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code
        if retryable is not None:
            self.retryable = retryable


class LLMConfigurationError(LLMError, ValueError):
    """配置不可用（场景缺失/未启用/未绑定、模型或供应商不可用）。

    继承 ValueError 以保持 V1 兼容：旧调用方 `except ValueError` 仍能捕获，
    且消息文案与 V1 完全一致（被 T01 Baseline 冻结）。
    """

    error_code = "llm_configuration_error"
    retryable = False


class LLMTimeoutError(LLMError):
    """请求超时。可重试。"""

    error_code = "llm_timeout"
    retryable = True


class LLMProviderError(LLMError):
    """Provider HTTP/连接错误。默认不可重试；5xx 与连接错误由调用方标记 retryable=True。"""

    error_code = "llm_provider_error"
    retryable = False


class LLMRateLimitError(LLMProviderError):
    """HTTP 429 限流。可重试。"""

    error_code = "llm_rate_limit"
    retryable = True


class LLMOutputValidationError(LLMError):
    """模型输出无法解析为 JSON 或未通过 Pydantic Schema 校验。不重试。

    摘要只包含字段位置/错误类型，不包含输入值，避免泄露内容。
    """

    error_code = "llm_output_validation"
    retryable = False


class LLMUnsupportedFeatureError(LLMError):
    """请求了当前供应商/模型不支持的能力（如 tools、未知 provider_type）。不重试。"""

    error_code = "llm_unsupported_feature"
    retryable = False
