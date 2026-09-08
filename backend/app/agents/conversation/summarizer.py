"""P10.1-B3 ConversationSummarizer abstraction + 固定 Prompt（不绑定某家 SDK）。

- ConversationSummarizer：Runner/Orchestrator 依赖的唯一摘要接口。Runner 不拼
  prompt、不直接调 Provider 具体 SDK；模型调用必须复用现有 Provider
  abstraction（ProviderConversationSummarizer 经 gateway.stream 走同一通道）。
- 业务层压缩节流：每个 Run 最多一次 Summarizer 调用由 SummaryOrchestrator
  保证（max_compaction_calls_per_run=1）；Provider transport 自带有限 retry 保留。
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import (
    _split_into_exchange_units,
    estimate_text_tokens,
)
from app.agents.conversation.messages import (
    Message,
    TextContent,
    ToolCall,
    ToolResultMessage,
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

# 固定 Prompt（常量；增量正文由 render_summarizer_input 生成后作为 user 消息）。
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
    target_through_visible_rank: int | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    estimated_tokens: int | None = None


class ConversationSummarizer:
    """摘要接口：async summarize(existing, messages, target, budget, runtime) -> SummaryResult。

    Runner 永远不直接构造该抽象的具体 Provider 调用；Orchestrator 只依赖本接口。
    """

    async def summarize(self, *, existing_summary, messages, target_through_visible_rank,
                        summary_token_budget, runtime_context=None):
        raise NotImplementedError


_TEXT_PREVIEW_CAP = 600        # 单条文本正文进入摘要输入的最大字符数
_TOOL_ARGS_PREVIEW_CAP = 300   # ToolCall arguments JSON 预览上限
_RESULT_PREVIEW_CAP = 800      # 单个 ToolResult 文本预览上限


def _preview(text: str, cap: int) -> str:
    """正文截断必须保留明确省略标记；绝不静默吞掉整条消息。"""
    if len(text) <= cap:
        return text
    return f"{text[:cap]}[… 省略 {len(text) - cap} 字符]"


def _render_text_content(block: TextContent) -> str:
    return _preview(block.text, _TEXT_PREVIEW_CAP)


def _render_tool_call(block: ToolCall) -> str:
    """ToolCall 语义标记：name/id/参数键 + 小 JSON 预览。参数超长时仍保留
    结构存在标记（不丢整条调用）。"""
    arguments = block.arguments or {}
    preview = json.dumps(arguments, ensure_ascii=False,
                         separators=(",", ":"), default=str)
    if len(preview) > _TOOL_ARGS_PREVIEW_CAP:
        keys = ",".join(str(k) for k in arguments) or "-"
        preview = _preview(preview, _TOOL_ARGS_PREVIEW_CAP)
        preview = f"{preview} (args keys: {keys})"
    return f"[toolCall name={block.name} id={block.id} args={preview}]"


def _render_message(message: Message) -> str:
    """把一条原始消息渲染为摘要输入行（审计要求 #2）：
    - 每条 Message 必须出现在渲染结果里（角色 + 语义标记），禁止整条丢弃；
    - 单个超大 Tool payload 允许缩写正文，但保留 tool_name/id/is_error 与
      长度省略标记 —— 模型因此知道该 Message/ToolResult 存在及其语义。
    """
    if isinstance(message, UserMessage):
        body = message.content
        text = body if isinstance(body, str) else "".join(b.text for b in body)
        return f"user: {_preview(text, _TEXT_PREVIEW_CAP)}"
    if isinstance(message, ToolResultMessage):
        text = "".join(b.text for b in message.content)
        preview = _preview(text, _RESULT_PREVIEW_CAP)
        marker = f" [原始 {len(text)} 字符已缩写]" if len(text) > _RESULT_PREVIEW_CAP else ""
        return (f"toolResult tool={message.tool_name} id={message.tool_call_id} "
                f"is_error={message.is_error}: {preview}{marker}")
    role = getattr(message, "role", "?")
    blocks = getattr(message, "content", []) or []
    parts = []
    for block in blocks:
        if isinstance(block, TextContent):
            parts.append(_render_text_content(block))
        elif isinstance(block, ToolCall):
            parts.append(_render_tool_call(block))
        else:
            parts.append(str(block))
    return f"{role}: " + " ".join(parts) if parts else f"{role}: (无内容)"


def _rendered_chars(message: Message) -> int:
    return len(_render_message(message))


def render_summarizer_input(*, existing_summary, messages,
                            existing_through_visible_rank: int | None = None) -> str:
    """把给定 messages **全部**渲染为固定输入正文（审计要求 #2 的单一事实源）。

    渲染只做单条消息内部缩写，绝不丢弃整条 Message；因此本函数返回的文本
    覆盖的边界 == 入参 messages 的边界。Orchestrator 用
    summarizer_coverable_messages 预先选出能完整送入的 chunk，二者共用本
    渲染规则，保证 marker 永远不会越过模型实际收到的最后一条消息。
    """
    lines: list[str] = []
    if existing_summary:
        through = (f" (through {existing_through_visible_rank})"
                   if existing_through_visible_rank is not None else "")
        lines.append(f"[Existing summary{through}]\n{existing_summary}")
    if messages:
        lines.append("[New messages]\n" + "\n".join(_render_message(m) for m in messages))
    return "\n\n".join(lines)


def summarizer_coverable_messages(messages: list[Message], *,
                                  max_chars: int,
                                  existing_chars: int = 0) -> list[Message]:
    """选出能在 max_chars 内**完整渲染**的最大覆盖前缀（审计要求 #2）。

    - 输入 chunk 必须是连续完整 exchange 组序列；超限时从**最新端**整组移除
      （不切散 assistant+toolResult 对），绝不用尾部截断掩盖边界；
    - 保证至少保留一个完整组：任意单条消息经单条内部缩写后都能装下；
    - 调用方只能把返回的 chunk 交给 Summarizer，并把 marker 推进到
      chunk 最后一条消息 —— 被 marker 覆盖的每条消息都真实进入模型输入。
    """
    if not messages:
        return []
    units, _ = _split_into_exchange_units(messages)
    if not units:
        units = [[m] for m in messages]
    unit_costs = [sum(_rendered_chars(m) for m in unit) + 1 for unit in units]
    total = existing_chars + sum(unit_costs)
    keep = len(units)
    while total > max_chars and keep > 1:
        keep -= 1
        total -= unit_costs[keep]
    out: list[Message] = []
    for unit in units[:keep]:
        out.extend(unit)
    return out


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

    async def summarize(self, *, existing_summary, messages, target_through_visible_rank,
                        summary_token_budget, runtime_context=None) -> SummaryResult:
        """响应 Run 的 cancel_event / deadline（审计 #3）：
        - 调用前已取消 → 立即失败，不发起 Provider 请求；
        - 流中取消/超时由同一 StreamControl 传入 gateway（P02 协调器在帧间
          观察 control.cancel_event/deadline），不会长时间阻塞 context preparation。
        """
        runtime = runtime_context if isinstance(runtime_context, dict) else {}
        cancel_event = runtime.get("cancel_event")
        deadline = runtime.get("deadline")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("summarize canceled before request")
        request_id = self._id_factory()
        user_text = render_summarizer_input(
            existing_summary=existing_summary, messages=messages,
            existing_through_visible_rank=runtime.get("existing_through_visible_rank"),
        )
        request = StreamRequest(
            system_prompt=SUMMARY_PROMPT,
            messages=[UserMessage(message_id=f"summary-{request_id}", timestamp=0,
                                  role="user", content=user_text)],
            # 只请求一段无工具文本补全（tools=[]，审计 #3 顺手确认项）；
            # 输出上限与摘要预算对齐（超预算由 validate 拒绝）
            max_tokens=max(1, int(summary_token_budget)),
            timeout_seconds=self._timeout_seconds,
            request_usage=True,
        )
        control = StreamControl(
            cancel_event=cancel_event if cancel_event is not None else asyncio.Event(),
            deadline=deadline,
            budget=AttemptBudget(limit=1),
        )
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
            through_visible_rank=target_through_visible_rank,
            source_message_count=len(messages),
            provider=provider,
            model=model,
            usage=usage,
            estimated_tokens=estimate_summary_tokens(text),
        )
