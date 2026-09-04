"""V2-P01 复审收尾：工具参数纯校验与结果构造边界（不执行 handler）。

职责（对齐 Pi 的 prepareToolCall / validateToolArguments 与
createToolResultMessage 的纯构造部分，仅取当前 P01 子集）：
- prepare_tool_call：只接收确定的 ToolCall，按既有 ToolRegistry 查名称与
  input_model，入口处强制 strict=True 并按对应 Pydantic 输入模型校验，
  产出 PreparedToolCall。
- validate_tool_calls_from_final_message：只接受终态助手消息（stop/toolUse）
  中的工具调用；length/pending/error/aborted/deferred 一律不产出候选；
  缺少有效调用 ID 的块也绝不产出候选。
- build_tool_result_message：结果 ID/名称取自原 ToolCall，不接受调用方
  覆盖成另一次调用；content=None 归一化为 []（对应 Pi createToolResultMessage）。

安全边界（P01 复审收尾）：
- 对外只返回固定错误码与固定文案，不转发 loc/type/msg/str(exc)/未注册
  工具名或其它动态字符串；任何“长得合法”的动态键/字段/type 都不可信；
- input_model 必须是有效 Pydantic 模型类，否则稳定失败（invalid_config）；
- 校验、序列化结果形状检查与 PreparedToolCall 候选构造全部纳入同一受控
  边界：ValidationError → invalid_arguments，其它/序列化非字典/候选构造
  失败 → validation_failed，均不回显原始输入或异常链；
- ToolCall.id 允许空字符串只在流式早期公有形状里出现；本入口（候选准备/
  结果构造）遇到空 ID/空名称一律拒绝（empty_call_id），不放宽最终安全门禁；
- 参数已校验不等于已获授权：权限/审批/预算/实际执行在 P03/P09；
  本模块不注册/不执行业务工具，绝不调用 handler；
- 不复制 Pi TypeBox 类型转换器；入口 strict=True 使严格类型策略不依赖
  工具作者是否配置 strict。

参考来源（只读）：Pi 固定提交 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6 的
packages/ai/src/utils/validation.ts、packages/ai/src/api/openai-completions.ts
（ensureToolCallBlock：早期 toolcall_start 可携带 id="" / name / {} 参数）、
packages/agent/src/agent-loop.ts（prepareToolCallArguments/prepareToolCall/
failToolCallsFromTruncatedMessage/createToolResultMessage）。
MIT License（Copyright (c) 2025 Mario Zechner，完整文本见 messages.py 模块头）。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.registry.tool_registry import ToolRegistry, UnknownToolError
from app.agents.conversation.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
)

# 固定外部文案：不携带任何动态内容（字段位置/错误类型/msg/工具名等）
_FIXED_UNKNOWN_TOOL = "未知工具，已拒绝"
_FIXED_INVALID_CONFIG = "工具输入模型配置无效（必须是可用的 Pydantic 模型类型）"
_FIXED_INVALID_ARGUMENTS = "工具参数校验未通过"
_FIXED_VALIDATION_FAILED = "工具参数校验内部失败，未执行任何调用"
_FIXED_EMPTY_CALL = "工具调用缺少有效 ID/名称，不能进入候选准备或结果构造"
_FIXED_NOT_COMPLETE = "该停止原因的消息不产出可执行工具候选"


class ToolValidationError(Exception):
    """安全、稳定的参数/配置校验失败（error_code + 固定用户可读文案，不含敏感值）。"""

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


class PreparedToolCall(BaseModel):
    """已通过输入模型校验的工具调用候选（不等于已获授权/已执行）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    tool_call_id: str = Field(min_length=1, description="原 ToolCall.id（最终候选必须非空）")
    tool_name: str = Field(description="原 ToolCall.name")
    arguments: dict[str, Any] = Field(description="经输入模型校验后的参数（调用方不应据此覆盖原始调用关联）")


def _is_valid_input_model(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def _require_usable_call_id(tool_call: ToolCall) -> None:
    if not isinstance(tool_call.id, str) or not tool_call.id or not tool_call.name:
        raise ToolValidationError("empty_call_id", _FIXED_EMPTY_CALL)


def prepare_tool_call(tool_registry: ToolRegistry, tool_call: ToolCall) -> PreparedToolCall:
    """按名称查注册表并严格校验参数；配置/参数问题都稳定安全失败。"""
    try:
        definition = tool_registry.get(tool_call.name)
    except UnknownToolError:
        raise ToolValidationError("unknown_tool", _FIXED_UNKNOWN_TOOL) from None
    _require_usable_call_id(tool_call)
    if not _is_valid_input_model(definition.input_model):
        raise ToolValidationError("invalid_config", _FIXED_INVALID_CONFIG)
    # 校验、序列化、结果形状检查与候选构造在同一受控边界内
    try:
        validated = definition.input_model.model_validate(tool_call.arguments, strict=True)
        arguments = validated.model_dump(mode="python")
    except ValidationError:
        raise ToolValidationError("invalid_arguments", _FIXED_INVALID_ARGUMENTS) from None
    except Exception:
        raise ToolValidationError("validation_failed", _FIXED_VALIDATION_FAILED) from None
    if not isinstance(arguments, dict):
        raise ToolValidationError("validation_failed", _FIXED_VALIDATION_FAILED)
    try:
        return PreparedToolCall(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            arguments=arguments,
        )
    except Exception:
        raise ToolValidationError("validation_failed", _FIXED_VALIDATION_FAILED) from None


def validate_tool_calls_from_final_message(
    assistant: AssistantMessage,
    tool_registry: ToolRegistry,
) -> list[PreparedToolCall]:
    """只允许终态助手消息产出候选工具调用。

    length 即使携带形状合法的工具块也必须拒绝；pending/error/aborted/
    deferred 同样阻断。stop/toolUse 均可携带工具块并进入参数校验；块缺有效
    调用 ID 时在 prepare_tool_call 拒绝，不放宽最终工具安全门禁。
    """
    if assistant.stop_reason not in ("stop", "toolUse"):
        raise ToolValidationError("not_complete", _FIXED_NOT_COMPLETE)
    calls = [item for item in assistant.content if isinstance(item, ToolCall)]
    return [prepare_tool_call(tool_registry, call) for call in calls]


def build_tool_result_message(
    tool_call: ToolCall,
    *,
    message_id: str,
    timestamp: int,
    is_error: bool,
    content: list[TextContent] | None = None,
    details: Any = None,
    usage: Any = None,
) -> ToolResultMessage:
    """按原 ToolCall 构造独立 ToolResultMessage。

    tool_call_id/tool_name 只能取自 tool_call，调用方无法覆盖成另一次调用；
    空 ID/空名称在此最终结果边界拒绝；content 缺省归一化为 []。
    """
    _require_usable_call_id(tool_call)
    try:
        return ToolResultMessage(
            message_id=message_id,
            timestamp=timestamp,
            role="toolResult",
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=list(content or []),
            details=details,
            usage=usage,
            is_error=is_error,
        )
    except ValidationError:
        # 构造失败同样稳定失败，不回显内部载荷
        raise ToolValidationError("validation_failed", _FIXED_VALIDATION_FAILED) from None
