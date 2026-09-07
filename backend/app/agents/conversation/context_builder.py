"""P10.1 Context Builder：Persistence History → 有限 Working Context（纯/确定性）。

原则：
- 不删除/改写持久化 Message/ToolCall/ToolResult/Revision/Event；
- Compaction 只影响“本次模型请求看什么”；
- 最小窗口单元是 Tool 交换组（Assistant ToolCall + 对应 ToolResult 同进同出），
  绝不按 messages[-N:] 切散工具对；
- 当前 UserMessage 永远完整保留；未知 token 用保守估算（绝不当 0 无限塞）；
- 本模块不返回 ORM Entity、不调模型、不读 Secret。

参考 Pi packages/agent（固定提交 f41f80…）：上游以整段 transcript 直传；
Summary/Compaction 为 TestMind 适配层，行为差异按任务书登记。
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.messages import (
    AssistantMessage,
    Message,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


@dataclass(frozen=True)
class ContextBudgetConfig:
    recent_message_limit: int = 24
    context_token_budget: int = 24000
    reserved_output_tokens: int = 4000
    summary_token_budget: int = 3000
    artifact_context_token_budget: int = 1200
    chars_per_token: float = 3.0

    def available_input_tokens(self) -> int:
        return max(0, self.context_token_budget - self.reserved_output_tokens)


@dataclass
class PreparedContext:
    system_sections: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    summary_text: str | None = None
    included_message_ids: list[str] = field(default_factory=list)
    omitted_message_ids: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    compaction_used: bool = False
    context_limit: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def system_prompt(self) -> str:
        return "\n\n".join(section for section in self.system_sections if section)


def estimate_text_tokens(text: str, chars_per_token: float = 3.0) -> int:
    chars = len(str(text or ""))
    if chars == 0:
        return 0
    return max(1, int(math.ceil(chars / max(1.0, chars_per_token))))


def estimate_message_tokens(message: Message, chars_per_token: float = 3.0) -> int:
    if isinstance(message, UserMessage):
        if isinstance(message.content, str):
            return estimate_text_tokens(message.content, chars_per_token)
        return estimate_text_tokens(
            "".join(b.text for b in message.content if isinstance(b, TextContent)),
            chars_per_token)
    if isinstance(message, ToolResultMessage):
        text = "".join(b.text for b in message.content if isinstance(b, TextContent))
        return estimate_text_tokens(f"{message.tool_name}:{text}", chars_per_token)
    if isinstance(message, AssistantMessage):
        total = 0
        for block in message.content:
            if isinstance(block, TextContent):
                total += estimate_text_tokens(block.text, chars_per_token)
            elif isinstance(block, ToolCall):
                total += estimate_text_tokens(
                    json.dumps(block.arguments, ensure_ascii=False, default=str), chars_per_token)
        return total
    return estimate_text_tokens(str(message), chars_per_token)


def _collect_tool_calls(message: AssistantMessage) -> set[str]:
    return {b.id for b in message.content if isinstance(b, ToolCall) and b.id}


def _split_into_exchange_units(messages: list[Message]) -> list[list[Message]]:
    """切成原子交换组：user 自成组；assistant + 其后引用其 ToolCall 的 ToolResult 成组。

    ToolResult 归属其**最近** assistant（其调用 ID 在最近 assistant 的调用集合内）。
    """
    units: list[list[Message]] = []
    for message in messages:
        if isinstance(message, UserMessage):
            units.append([message])
        elif isinstance(message, AssistantMessage):
            units.append([message])
        elif isinstance(message, ToolResultMessage):
            if units and units[-1][-1].role == "assistant" and any(
                isinstance(b, ToolCall) and b.id == message.tool_call_id
                for b in units[-1][-1].content
            ):
                units[-1].append(message)
            else:
                units.append([message])
    return units


def build_prepared_context(
    *,
    messages: list[Message],
    current_user_message_id: str,
    budget: ContextBudgetConfig | None = None,
    system_sections: list[str] | None = None,
    summary_text: str | None = None,
    summary_through_sequence: int | None = None,
    chars_per_token: float | None = None,
) -> PreparedContext:
    """构造有限 Working Context（确定性，见模块 docstring）。"""
    config = budget or ContextBudgetConfig()
    ratio = chars_per_token or config.chars_per_token
    units = _split_into_exchange_units(messages)
    limit_tokens = config.available_input_tokens()

    selected: list[Message] = []
    selected_ids: set[str] = set()
    estimated = 0
    current_unit: list[Message] | None = None
    compaction = False

    # 定位当前用户组（无条件保留）
    for unit in units:
        if any(getattr(m, "message_id", None) == current_user_message_id for m in unit):
            current_unit = unit
            break
    if current_unit is None:
        # 防御：调用方错误；保留最近 recent_message_limit 条
        selected = messages[-config.recent_message_limit:]
    else:
        kept_units = 1  # current unit 已保留
        current_tokens = sum(estimate_message_tokens(m, ratio) for m in current_unit)
        estimated = current_tokens
        selected_ids = {m.message_id for m in current_unit if getattr(m, "message_id", None)}

        # 从尾部向前补充（跳过 current unit），受 count/token 双重限制
        for unit in reversed(units):
            if unit is current_unit:
                continue
            if kept_units >= config.recent_message_limit:
                compaction = True
                if summary_text is not None:
                    break
                continue
            unit_tokens = sum(estimate_message_tokens(m, ratio) for m in unit)
            if estimated + unit_tokens > limit_tokens:
                compaction = True
                break
            estimated += unit_tokens
            kept_units += 1
            selected_ids.update(
                m.message_id for m in unit if getattr(m, "message_id", None))
        # 重建成正序（selected_ids 无序，按 messages 原序过滤）
        selected = [m for m in messages if getattr(m, "message_id", None) in selected_ids]

    included_ids = [m.message_id for m in selected if getattr(m, "message_id", None)]
    all_ids = [m.message_id for m in messages if getattr(m, "message_id", None)]
    omitted = [mid for mid in all_ids if mid not in included_ids]

    sections = list(system_sections or [])
    if summary_text and summary_through_sequence is not None:
        sections.append(
            "[Earlier conversation summary through sequence "
            f"{summary_through_sequence}]\n{summary_text}\n"
            "[End of summary — not the current Artifact state; read tools before modifying.]"
        )

    total_tokens = estimated + sum(estimate_text_tokens(s, ratio) for s in sections)
    # 无 summary 却发生裁切（budget/count 任一截断）→ 需要调用方先补 summary/降级，
    # 标 context_limit 由调用方决定是否结束当前 Turn（绝不静默丢当前用户消息）。
    context_limit = compaction and summary_text is None and bool(omitted)
    return PreparedContext(
        system_sections=[s for s in sections if s],
        messages=selected,
        summary_text=summary_text,
        included_message_ids=included_ids,
        omitted_message_ids=omitted,
        estimated_tokens=total_tokens,
        compaction_used=compaction,
        context_limit=context_limit,
        diagnostics={
            "context_budget": config.context_token_budget,
            "estimated_tokens": total_tokens,
            "summary_used": bool(summary_text),
            "summary_through_sequence": summary_through_sequence,
            "recent_message_count": len(selected),
            "omitted_message_count": len(omitted),
        },
    )
