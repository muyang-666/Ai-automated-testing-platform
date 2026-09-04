"""V2-P01-01/02/03：按 Pi 翻译消息、模型信息、用量与停止原因（纯 Python，无副作用导入）。

本模块定义 TestMind 对话消息合同（文本/工具调用/工具结果子集）：

- TextContent：文本内容块，type="text"。
- ToolCall：工具调用内容块，type="toolCall"，与请求里的调用一一对应，
  只有结构，不代表已获准执行。
- Usage / UsageCost：模型（或工具执行自身）用量与费用；计数与费用允许
  显式 None 表示未知，禁止 bool 冒充计数，不把未知补成 0、不求和补全。
- DeferredHandle：deferred 运行句柄的数据表达，不实现提交/轮询/恢复。
- StopReason：停止原因，保留 Pi 原值 pending/stop/length/toolUse/error/
  aborted/deferred；未知值拒绝，不默认为 stop，不加入 Run 预算耗尽等状态。
- UserMessage：role="user"，content 为字符串或 TextContent 列表。
- AssistantMessage：role="assistant"，必填 api/provider/model/usage/
  stop_reason 与有序 content；支持纯文本、纯工具与混合内容。
- ToolResultMessage：独立消息，role="toolResult"，顶层 tool_call_id /
  tool_name / content / is_error，可选 usage（工具执行自身用量）。
- Message：以上三种消息的按 role 判别联合；parse_message 提供解析入口。

StopReason 语义（仅注释，控制流留对应 Pi Loop 翻译任务）：
length 是截断不是成功；toolUse 是工具请求不代表已执行；pending/deferred
不是完成；error/aborted 不自动关闭会话。数据模型不伪造执行保证。

明确边界（本小步不实现，也不宣称已完成）：
- AssistantMessage 的 providerThinkingLevel、diagnostics 未翻译；
- ToolResultMessage 的 addedToolNames 与动态工具加载未翻译；
- ToolCall 的 thoughtSignature、namespace 未翻译；
- 多模态 ImageContent、thinking 内容、AssistantMessageEvent 事件未翻译；
- 不实现事件、Turn、Agent Loop、Tool Executor、Provider 适配、数据库、
  独立历史配对扫描、重试或预算器；保序运行逻辑在翻译对应 Pi
  Loop/Executor 函数时落实；
- content 允许空列表（Pi 工具结果可为空；助手部分/错误状态可为空）；
  空内容是否构成可执行调用或成功回复由结束原因/执行边界判断，本层不判定；
- 不自动收集异常堆栈或凭证；reasoning 只记录数值用量，不保存推理正文。

轻适配（相对 Pi）：
- Python snake_case：tool_call_id ← toolCallId、is_error ← isError、
  stop_reason ← stopReason、response_id ← responseId、raw_stop_reason ←
  rawStopReason、end_turn ← endTurn、model_id ← modelId、expires_at ←
  expiresAt、poll_after_ms ← pollAfterMs、cache_read/cache_write/
  cache_write_1h ← cacheRead/cacheWrite/cacheWrite1h、total_tokens ←
  totalTokens；
- 补 TestMind 应用层 message_id / schema_version（沿用 P01-01 严格校验，
  只接受真正整数 1）与调用方提供的 timestamp（Unix 毫秒）；
- 上游必填的计数/费用字段仍须提供，但允许显式 None 表示未知，cost 也可
  显式为 None；原可选字段默认 None。不做任何加总/换算/价格计算；
- 内核角色名保留 Pi 语义 "toolResult"；未来 Provider 适配时才映射到旧接口的 tool。
- P01-01 的统一 Message 经复核未被业务引用，已直接收敛为联合类型，不为
  教学保留第二套消息系统或兼容工厂。

参考来源（只读，D:\\pi 固定提交
f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6）：
- packages/ai/src/types.ts：TextContent、ToolCall、Usage、StopReason、
  DeferredHandle、UserMessage、AssistantMessage、ToolResultMessage、
  Message、AssistantMessageEvent；
- packages/agent/src/agent-loop.ts：runLoop / streamAssistantResponse /
  createToolResultMessage / executeToolCallsSequential 及并行执行按原调用
  顺序产出结果消息的部分；
- packages/agent/test/agent-loop.test.ts：工具调用与结果、length 截断助手
  消息等测试（只读参考，不运行）。

MIT License

Copyright (c) 2025 Mario Zechner

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

# 上游参考：packages/ai/src/types.ts 的 TextContent.type / ToolCall.type
TEXT_TYPE = Literal["text"]
TOOL_CALL_TYPE = Literal["toolCall"]

# 固定合同版本：未知版本在 Pydantic 校验层直接拒绝
SCHEMA_VERSION: Literal[1] = 1

# 停止原因：保留 Pi 原值；不加入 Run 的 budget_exceeded 等执行层状态
StopReason = Literal["pending", "stop", "length", "toolUse", "error", "aborted", "deferred"]


def _ensure_count_or_none(value: object, field: str) -> int | None:
    """计数必须是真正的非负整数或显式 None（未知）；拒绝 bool/float/str。"""
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} 必须是非负整数或显式 None（未知），拒绝 bool/float/字符串")
    return value


def _ensure_finite_number_or_none(value: object, field: str) -> int | float | None:
    """费用必须是有限非负数字或显式 None（未知）；拒绝 bool、NaN/Infinity。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} 拒绝 bool")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{field} 必须非负")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{field} 必须是有限非负数字")
        return value
    raise ValueError(f"{field} 必须是有限非负数字或显式 None（未知）")


def _ensure_json_safe(value: object) -> None:
    """data 只接受 JSON 数据；JSON 数组只接受 list，tuple/set 等一律拒绝。"""
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("data 不允许 NaN/Infinity")
        return
    if isinstance(value, list):
        for item in value:
            _ensure_json_safe(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("data 对象键必须是字符串")
            _ensure_json_safe(item)
        return
    raise ValueError("data 只接受 JSON 数据（对象/数组(list)/字符串/数字/bool/null），tuple 等容器类型拒绝")


class TextContent(BaseModel):
    """一个文本内容块。type 固定为 "text"，text 为普通字符串（允许空）。"""

    # strict=True：拒绝隐式类型转换（如 int→str）；extra="forbid"：拒绝多余字段
    model_config = ConfigDict(extra="forbid", strict=True)

    type: TEXT_TYPE = Field(default="text", description="内容块类型，固定为 text")
    text: str = Field(description="文本正文；允许空字符串，完整模型空响应语义留结束原因合同")


class ToolCall(BaseModel):
    """工具调用内容块（Pi ToolCall）。

    id/name/arguments 与一次请求一一对应；arguments 用字符串键字典表达
    Pi 的 Record<string, any>。结构合法不等于已获准执行。

    早期流式公有形状（Pi ensureToolCallBlock）会在 toolcall_start/delta 阶段
    出现 id=""、name 可空、arguments={} 的临时块；因此 id 允许空字符串。
    是否已到达可执行候选/可建结果，由 tool_validation 的最终边界判定
    （空 ID/名称不产出候选、不构造结果），不在本数据类型层面拒绝。
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    type: TOOL_CALL_TYPE = Field(default="toolCall", description="内容块类型，固定为 toolCall")
    id: str = Field(description="工具调用 ID（Pi ToolCall.id；流式早期可为空串，最终候选边界要求非空）")
    name: str = Field(description="工具名称（Pi ToolCall.name）")
    arguments: dict[str, Any] = Field(description="完整参数对象（Pi ToolCall.arguments），键为字符串")


class UsageCost(BaseModel):
    """费用对象（Pi Usage.cost：{input, output, cacheRead, cacheWrite, total}）。

    上游必填字段仍须提供，但允许显式 None 表示未知；不自动加总、不计算价格。
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    input: int | float | None = Field(description="输入费用；None=未知")
    output: int | float | None = Field(description="输出费用；None=未知")
    cache_read: int | float | None = Field(description="缓存读取费用；None=未知")
    cache_write: int | float | None = Field(description="缓存写入费用；None=未知")
    total: int | float | None = Field(description="总费用；None=未知，不在此自动求和")

    @field_validator("input", "output", "cache_read", "cache_write", "total", mode="before")
    @classmethod
    def _cost_values(cls, value: object) -> int | float | None:
        return _ensure_finite_number_or_none(value, "费用")


class Usage(BaseModel):
    """模型（或工具执行自身）用量（Pi Usage）。

    cache_write_1h 是 cache_write 的子集，reasoning 是 output 的子集，
    不重复累计（仅注释说明，不做计算）；reasoning 只记数值，不保存推理正文。
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    input: int | None = Field(description="输入 token 数；None=未知")
    output: int | None = Field(description="输出 token 数；None=未知")
    cache_read: int | None = Field(description="缓存读取 token 数；None=未知")
    cache_write: int | None = Field(description="缓存写入 token 数；None=未知")
    cache_write_1h: int | None = Field(default=None, description="可选：cache_write 中保留 1 小时的部分")
    reasoning: int | None = Field(default=None, description="可选：推理 token 数，output 的子集，仅数值")
    total_tokens: int | None = Field(description="总 token 数；None=未知，不在此自动求和")
    cost: UsageCost | None = Field(description="费用对象；可为 None 表示未知")

    @field_validator("input", "output", "cache_read", "cache_write", "cache_write_1h", "reasoning", "total_tokens", mode="before")
    @classmethod
    def _token_counts(cls, value: object) -> int | None:
        return _ensure_count_or_none(value, "用量计数")


class DeferredHandle(BaseModel):
    """deferred 运行句柄（Pi DeferredHandle）：只表达数据，不提交/轮询/恢复。

    data 只接受 JSON 数据，不接受任意可执行对象；不宣称已支持 deferred 运行。
    """

    model_config = ConfigDict(extra="forbid", strict=True, protected_namespaces=())

    provider: str = Field(description="供应商标识（保持字符串可扩展，不建枚举）")
    model_id: str = Field(description="模型标识")
    api: str = Field(description="供应商 API 标识（如 responses/chat 的字符串形态）")
    id: str = Field(min_length=1, description="供应商侧句柄 token（如 response/batch id）")
    expires_at: int | None = Field(default=None, description="可选：过期 Unix 毫秒")
    poll_after_ms: int | None = Field(default=None, description="可选：建议轮询间隔毫秒")
    data: Any = Field(default=None, description="可选：供应商重建数据（仅 JSON 数据）")

    @field_validator("expires_at", "poll_after_ms", mode="before")
    @classmethod
    def _optional_time_values(cls, value: object) -> int | None:
        return _ensure_count_or_none(value, "deferred 时间")

    @field_validator("data", mode="after")
    @classmethod
    def _data_must_be_json(cls, value: object) -> object:
        _ensure_json_safe(value)
        return value


class _MessageFields(BaseModel):
    """三种消息共享的应用层元数据与严格校验（不直接实例化）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    message_id: str = Field(min_length=1, description="调用方提供的稳定消息 ID（非空），往返不重新生成")
    schema_version: Literal[1] = Field(default=1, description="合同版本，固定为 1，未知版本拒绝")
    timestamp: int = Field(description="Unix 毫秒时间戳（Pi 三种消息均携带），由调用方提供")

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_must_be_real_int_one(cls, value: object) -> int:
        """只接受真正的整数 1。

        strict/Literal 不能单独覆盖全部边界：Python 中 True == 1、1.0 == 1，
        因此这里在类型解析前用 type(value) is int 显式排除 bool/float/str，
        再要求值等于 1，保证 True、1.0、"1"、2 都被拒绝。
        """
        if type(value) is not int or value != 1:
            raise ValueError("schema_version 必须是真正的整数 1（True/1.0/字符串等均不接受）")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def _timestamp_must_be_real_non_negative_int(cls, value: object) -> int:
        """timestamp 必须是真正的非负整数毫秒值，拒绝 True/1.0/"1" 等。"""
        if type(value) is not int or value < 0:
            raise ValueError("timestamp 必须是真正的非负整数（Unix 毫秒）")
        return value


class UserMessage(_MessageFields):
    """用户消息（Pi UserMessage）。content 为字符串或文本内容块列表。"""

    role: Literal["user"] = Field(description="角色，固定为 user")
    content: str | list[TextContent] = Field(description="文本字符串，或 TextContent 有序列表")


class AssistantMessage(_MessageFields):
    """助手消息（Pi AssistantMessage）。

    必填 api/provider/model/usage/stop_reason 与有序 content（可为 []，
    允许部分/错误状态）；文本与工具内容按原顺序保留。模型元信息只按上游
    含义保存；end_turn 仅诊断用途，不据此改变循环。
    """

    role: Literal["assistant"] = Field(description="角色，固定为 assistant")
    content: list[TextContent | ToolCall] = Field(description="TextContent/ToolCall 有序内容块列表；必填，可为空 []")
    api: str = Field(description="供应商 API 标识字符串（保持可扩展，不建枚举、不静默选默认模型）")
    provider: str = Field(description="供应商名称字符串（Pi ProviderId 的字符串形态）")
    model: str = Field(description="请求使用的模型名")
    usage: Usage = Field(description="本次模型调用用量与费用")
    stop_reason: StopReason = Field(description="停止原因；未知值拒绝，不默认为 stop")
    response_model: str | None = Field(default=None, description="可选：实际响应的具体模型（与请求 model 不同时）")
    response_id: str | None = Field(default=None, description="可选：供应商响应/消息标识")
    deferred: DeferredHandle | None = Field(default=None, description="可选：deferred 运行句柄（仅数据表达）")
    error_message: str | None = Field(default=None, description="可选：失败/恢复时的脱敏错误信息")
    raw_stop_reason: str | None = Field(default=None, description="可选：供应商原始结束原因，仅诊断")
    end_turn: bool | None = Field(default=None, description="可选：供应商是否显式结束回合；仅诊断，不据此改循环")


class ToolResultMessage(_MessageFields):
    """工具结果消息（Pi ToolResultMessage，独立消息，非 assistant 内容块）。

    通过顶层 tool_call_id / tool_name 指回请求；content 必填但可为空；
    details 保留 Pi 的可选通用字段；usage 是工具执行自身的用量，不能自动
    算成模型用量。
    """

    role: Literal["toolResult"] = Field(description="角色，固定为 toolResult（未来 Provider 适配时才映射到旧接口 tool）")
    tool_call_id: str = Field(min_length=1, description="对应的工具调用 ID（Pi toolCallId）")
    tool_name: str = Field(min_length=1, description="工具名称（Pi toolName）")
    content: list[TextContent] = Field(description="文本内容块列表；必填，可为空 []（Pi 工具结果可为空）")
    details: Any = Field(default=None, description="可选结构化结果（Pi details），不自动收集堆栈/凭证")
    usage: Usage | None = Field(default=None, description="可选：工具执行自身用量；不计入模型用量")
    is_error: bool = Field(description="是否失败（Pi isError）")


# 按 role 判别解析的三种消息联合（Pi Message = UserMessage | AssistantMessage | ToolResultMessage）
Message = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage],
    Field(discriminator="role"),
]

_message_adapter: TypeAdapter = TypeAdapter(Message)


def parse_message(data: object) -> UserMessage | AssistantMessage | ToolResultMessage:
    """把 dict/模型输入按 role 判别解析为对应的消息子类。

    未知 role、错误内容块类型、混入 ToolResult 的助手消息由类型结构拒绝；
    解析不生成或修改 message_id。不做工具配对扫描，也不代表运行已执行。
    """
    return _message_adapter.validate_python(data)
