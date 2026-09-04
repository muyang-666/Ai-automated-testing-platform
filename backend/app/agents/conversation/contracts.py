"""V2-P01 阶段收尾：最小纯元数据类型（ConversationTurn / ModelTurn）。

用于澄清三层单位，仅承载引用与索引，不自建运行状态机，不声称 Pi 存在
同名类型（Pi 的 turn 是一次助手响应加本轮工具结果，与 TestMind 一次用户
输入的产品 ConversationTurn 不同；Pi 的物理重试也独立于模型逻辑轮次）。

- ConversationTurn：产品的一次用户请求，未来对应旧 AgentRun 存储；
  只保存 session/run/user_message 引用。
- ModelTurn：一次逻辑模型请求；物理 Provider 重试与模型轮次分离，
  model_turn_index 不把重试次数混成轮次。

本模块只导入 pydantic，不触发数据库/配置/网络初始化。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal[1] = 1


class ConversationTurn(BaseModel):
    """一次用户请求的引用元数据（产品层单位，未来对应 AgentRun）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = Field(default=1, description="合同版本，固定 1")
    session_id: int = Field(ge=1, description="会话正整数 ID")
    run_id: int = Field(ge=1, description="Run 正整数 ID（未来承载本次请求）")
    user_message_id: str = Field(min_length=1, description="触发本次请求的用户消息稳定 ID")


class ModelTurn(BaseModel):
    """一次逻辑模型请求的引用元数据（不保存中间产物，也不当执行状态）。"""

    model_config = ConfigDict(extra="forbid", strict=True, protected_namespaces=())

    schema_version: Literal[1] = Field(default=1, description="合同版本，固定 1")
    run_id: int = Field(ge=1, description="所属 Run 正整数 ID")
    model_turn_id: str = Field(min_length=1, description="调用方提供的稳定模型轮次 ID")
    model_turn_index: int = Field(ge=1, description="本次请求的逻辑轮次序号（物理重试不计数）")
