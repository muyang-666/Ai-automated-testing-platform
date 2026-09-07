"""P10.1-B3 ConversationSummarizer abstraction + 固定 Prompt（不绑定某家 SDK）。

- ConversationSummarizer：Runner/Orchestrator 依赖的唯一摘要接口。Runner 不拼
  prompt、不直接调 Provider 具体 SDK；模型调用必须复用现有 Provider
  abstraction（ProviderConversationSummarizer 经 gateway.stream 走同一通道）。
- 业务层压缩节流：每个 Run 最多一次 Summarizer 调用由 SummaryOrchestrator
  保证（max_compaction_calls_per_run=1）；Provider transport 自带有限 retry 保留。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import estimate_text_tokens
from app.agents.conversation.messages import (
    Message,
    TextContent,
    ToolCall,
    UserMessage,
)
from app.agents.providers.streaming import (
    AttemptBudget,
    ProviderSnapshot,
    StreamControl,
    StreamContext,
    StreamError,
    StreamLimits,
    StreamRequest,
)
from app.services.agent.conversation_summary_service import SummaryResult

# 固定 Prompt（常量；增量正文由 build_summary_input_text 生成后作为 user 消息）。
SUMMARY_PROMPT = """You are writing a concise incremental conversation summary in Chinese.

The user message below contains an existing summary (if any) followed by the
new messages to fold in. Keep only:
- the user's current goal
- confirmed constraints
- important completed actions and their outcomes
- relevant module/case/artifact references and their id relations
- unresolved items the user still waits for
- referents needed later ("第一个/第二个/这个模块/这个用例")
- recent meaningful changes

Drop greetings, repeated small talk, streaming deltas, large raw Tool JSON,
debug output and hidden reasoning.
Do not invent information. Artifact state may have changed.
This summary is historical context, not current Artifact authority.

Return only the short, stable summary text — no markdown report, no headings,
no preamble."""


@dataclass
class SummaryCallRecord:
    existing_summary: str | None = None
    received_message_ids: list[str] = field(default_factory=list)
    target_through_sequence: int | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    estimated_tokens: int | None = None


class ConversationSummarizer:
    """摘要接口：async summarize(existing, messages, target, budget, runtime) -> SummaryResult。

    Runner 永远不直接构造该抽象的具体 Provider 调用；Orchestrator 只依赖本接口。
    """

    async def summarize(self, *, existing_summary, messages, target_through_sequence,
                        summary_token_budget, runtime_context=None):
        raise NotImplementedError


def _render_message(message: Message) -> str:
    """把一条原始消息渲染为摘要输入行：保留角色/工具名与文本，丢弃大型原始 JSON。

    工具调用只保留名称与参数键（不 dump 参数正文）；工具结果保留工具名与文本
    摘要（外层统一截断总量，防止超大 ToolResult 撑爆摘要输入）。
    """
    body = getattr(message, "content", "")
    if isinstance(message, UserMessage):
        text = body if isinstance(body, str) else "".join(b.text for b in body)
        return f"user: {text}"
    role = getattr(message, "role", "?")
    if isinstance(body, list):
        parts = []
        for block in body:
            if isinstance(block, TextContent):
                parts.append(block.text)
            elif isinstance(block, ToolCall):
                keys = ",".join(str(k) for k in (block.arguments or {})) or "-"
                parts.append(f"[toolCall:{block.name}({keys})]")
        return f"{role}: " + " ".join(parts)
    return f"{role}: {body}"


def build_summary_input_text(*, existing_summary, messages,
                             existing_through_sequence: int | None = None,
                             max_chars: int = 120_000) -> str:
    """组装 Summarizer 的固定输入正文（Prompt 保持常量，正文按增量生成）。

    existing_through_sequence/messages 为调用方已选好的增量范围；渲染不信任
    文本内容，只做结构化呈现。绝不携带未来/当前工作上下文之外的消息。
    """
    lines: list[str] = []
    if existing_summary:
        through = (f" (through {existing_through_sequence})"
                   if existing_through_sequence is not None else "")
        lines.append(f"[Existing summary{through}]\n{existing_summary}")
    if messages:
        rendered = [_render_message(m) for m in messages]
        # 总长钳制：超长历史只做展示截断（剪尾），不改变选择语义
        text = "\n".join(rendered)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(truncated)"
        lines.append(f"[New messages]\n{text}")
    return "\n\n".join(lines)


def estimate_summary_tokens(text: str) -> int:
    return estimate_text_tokens(text)


def _usage_payload(usage) -> dict[str, Any] | None:
    """把 Usage 模型压缩成可观测的 accounting payload（未知一律省略）。"""
    if usage is None:
        return None
    cost = getattr(usage, "cost", None)
    return {
        "input_tokens": getattr(usage, "input", None),
        "output_tokens": getattr(usage, "output", None),
        "cache_read_tokens": getattr(usage, "cache_read", None),
        "cache_write_tokens": getattr(usage, "cache_write", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "cost": cost.model_dump(exclude_none=True) if cost is not None else None,
    }


class ProviderConversationSummarizer(ConversationSummarizer):
    """正式 Summarizer：复用现有 Provider abstraction（gateway.stream），无第二套 SDK。

    只请求一段无工具文本补全；stream 事件由 P02 合同统一解析；usage/cost 从
    最终 AssistantMessage 提取（不为摘要另建 LLM Gateway / 计费通道）。
    """

    def __init__(self, gateway: Any, snapshot: ProviderSnapshot, *,
                 stream_limits: StreamLimits | None = None,
                 id_factory=None, timeout_seconds: float | None = None):
        self.gateway = gateway
        self.snapshot = snapshot
        self._stream_limits = stream_limits or StreamLimits()
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._timeout_seconds = timeout_seconds

    async def summarize(self, *, existing_summary, messages, target_through_sequence,
                        summary_token_budget, runtime_context=None) -> SummaryResult:
        request_id = self._id_factory()
        user_text = build_summary_input_text(
            existing_summary=existing_summary, messages=messages,
            existing_through_sequence=runtime_context.get("existing_through_sequence")
            if isinstance(runtime_context, dict) else None,
        )
        request = StreamRequest(
            system_prompt=SUMMARY_PROMPT,
            messages=[UserMessage(message_id=f"summary-{request_id}", timestamp=0,
                                  role="user", content=user_text)],
            # 只请求一段短文本补全；输出上限与摘要预算对齐（超预算由 validate 拒绝）
            max_tokens=max(1, int(summary_token_budget)),
            timeout_seconds=self._timeout_seconds,
            request_usage=True,
        )
        control = StreamControl(cancel_event=asyncio.Event(), budget=AttemptBudget(limit=1))
        final = None
        error_code = None
        try:
            async with self.gateway.stream(
                self.snapshot, request,
                context=StreamContext(message_id=request_id, timestamp=0),
                control=control, limits=self._stream_limits,
            ) as events:
                async for event in events:
                    if event.type == "done":
                        final = event.message
                        break
                    if event.type == "error":
                        final = event.error
                        error_code = control.error_code or "synthetic_model_error"
                        break
        except StreamError as exc:
            raise RuntimeError(f"summary provider stream failed: {exc.error_code}") from exc
        if final is None:
            raise RuntimeError("summary provider closed without terminal event")
        if final.stop_reason in {"error", "aborted", "length"} or error_code is not None:
            raise RuntimeError(
                f"summary generation failed: {error_code or final.stop_reason}")
        text = "".join(block.text for block in final.content if isinstance(block, TextContent))
        if not text.strip():
            raise RuntimeError("summary provider returned empty content")
        usage = _usage_payload(getattr(final, "usage", None))
        provider = getattr(final, "provider", None) or self.snapshot.name
        model = getattr(final, "model", None) or self.snapshot.model_name
        return SummaryResult(
            summary_text=text,
            through_sequence_no=target_through_sequence,
            source_message_count=len(messages),
            provider=provider,
            model=model,
            usage=usage,
            estimated_tokens=estimate_summary_tokens(text),
        )
