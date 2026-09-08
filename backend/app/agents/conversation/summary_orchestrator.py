"""P10.1-B3 SummaryOrchestrator：bounded history → incremental summary → PreparedContext。

设计目标（P10.1-B3 审计定稿）：
- Runner 不拼 prompt、不直接调 Provider、不直接处理某家模型返回；本模块把
  "读 bounded history / 读 latest summary / build context / 判定压缩 / 选增量 /
  调 Summarizer / 持久化 / 重建 PreparedContext" 全部收敛，Runner 只消费结果；
- DB 事务边界归调用方：io 提供 get/write 两个独立短事务阶段（读阶段结束后才
  summarize；写阶段独立 commit）。本模块自身不持任何 DB 事务；
- 每个 Run 最多一次 Summarizer 调用（max_compaction_calls_per_run=1）；
  冲突时采用 winning Summary，绝不覆盖、绝不因冲突重跑模型；
- 覆盖边界 = 最后一条**实际进入 Summarizer 输入**的消息：增量 chunk 超输入
  预算时按完整 exchange 组从最新端裁减（summarizer_coverable_messages），
  marker（through_visible_rank + through_message_id 锚点）只推进到 chunk 末条，
  绝不越过模型实际收到的最后一条消息；
- 增量边界语义为"逻辑位置 rank"（见 conversation_summary_service 模块头）；
- current_turn_too_large 与摘要无关：不调用 Summarizer，直接返回 context_limit；
- Summarizer 调用响应调用方 cancel_event/deadline（经 runtime_context 传入
  Provider 适配层），取消时快速失败；
- 压缩成功后的最终上下文 = summary(≤实际覆盖边界) + 边界之后全部原始行；
  若重建时连"摘要 + 尾部窗口"都放不进预算 → context_limit
  （working_context_too_large），绝不静默丢行。
"""

from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import (
    ContextBudgetConfig,
    PreparedContext,
    build_prepared_context,
)
from app.agents.conversation.summarizer import summarizer_coverable_messages
from app.services.agent.conversation_summary_service import (
    SummaryResult,
    select_incremental_inputs,
    validate_summary_result,
)


@dataclass
class SummaryStoreView:
    """winning summary 视图：覆盖边界 = (through_visible_rank, through_message_id)。"""

    through_visible_rank: int | None = None
    through_message_id: str | None = None
    summary_text: str | None = None


class SummaryIO:
    """依赖注入：真实实现负责两个独立短事务阶段；测试用内存实现。

    get_current：返回当前 winning summary 视图（读后即释放事务）。
    write_incremental：expected_through_visible_rank == 0 → 首次创建（唯一冲突 =
    已被抢先）；否则单调条件更新。new_through_message_id = 新边界最后一条被摘要
    消息的稳定 message_id（与新 rank 永远一致）。返回 True = 本次写入生效；
    False = 被更晚 Summary 抢先（调用方读 winning，不回退、不重调 Summarizer）。
    """

    def get_current(self) -> SummaryStoreView:
        raise NotImplementedError

    def write_incremental(self, *, expected_through_visible_rank, new_through_visible_rank,
                          new_through_message_id, summary_text, source_message_count,
                          provider=None, model=None) -> bool:
        raise NotImplementedError


@dataclass
class OrchestrationResult:
    prepared: PreparedContext
    compaction_model_calls: int = 0
    summary_refreshed: bool = False
    summary_refresh_failed: bool = False
    # 压缩/失败后的精确原因（供 Runner 映射 error_code 与 context_limit 事件）
    context_limit_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class SummaryOrchestrator:
    def __init__(self, summarizer: Any, budget: ContextBudgetConfig | None = None,
                 io: SummaryIO | None = None):
        self.summarizer = summarizer
        self.budget = budget or ContextBudgetConfig()
        self.io = io
        self._compaction_calls = 0

    async def prepare(
        self,
        *,
        seq_messages: list[tuple[int, Any]],
        current_user_message_id: str,
        system_sections: list[str] | None = None,
        io: SummaryIO | None = None,
        cancel_event: Any | None = None,
        deadline: float | None = None,
    ) -> OrchestrationResult:
        """seq_messages：(rank, Message) 列表（rank 为 run-bounded 逻辑位置，1 起连续）。

        cancel_event/deadline 转发给 Summarizer（审计 #3）：取消时 _summarize_once
        快速失败（不调模型），Prepare 正常返回后由 Runner 走取消路径。
        """
        io = io or self.io
        assert io is not None
        self._compaction_calls = 0  # 每 Run 一次 prepare = 至多一次模型调用
        current = await _maybe_async(io.get_current)
        existing_text = current.summary_text
        existing_through = current.through_visible_rank or 0
        existing_through_message_id = current.through_message_id
        messages = [message for _, message in seq_messages]
        rank_by_message_id = {
            message.message_id: rank for rank, message in seq_messages
            if getattr(message, "message_id", None)
        }
        base_diagnostics = {
            "existing_summary_present": bool(existing_text) and existing_through > 0,
            "existing_summary_through_visible_rank": existing_through if existing_through > 0 else None,
            "existing_summary_through_message_id": existing_through_message_id,
        }

        # 第一次尝试：不加 summary。若可完整容纳 → 不调用 Summarizer（短对话 0 次）。
        probe = build_prepared_context(
            messages=messages,
            current_user_message_id=current_user_message_id,
            budget=self.budget,
            system_sections=system_sections,
        )
        if not probe.compaction_used and not probe.context_limit:
            return OrchestrationResult(prepared=probe,
                                       diagnostics={**probe.diagnostics, **base_diagnostics})
        # 当前 UserMessage 自身超限与历史压缩无关：不调用 Summarizer。
        if probe.context_limit and probe.context_limit_reason == "current_turn_too_large":
            return OrchestrationResult(prepared=probe,
                                       context_limit_reason="current_turn_too_large",
                                       diagnostics={**probe.diagnostics, **base_diagnostics})

        compaction_calls = 0
        refreshed = False
        refresh_failed = False
        summary_meta: dict[str, Any] = {}
        reason: str | None = None
        final: PreparedContext | None = None

        if existing_through > 0 and existing_text:
            # ---- 已有 summary：需要时只做一次增量刷新 ----
            cut, for_summary, kept = select_incremental_inputs(
                seq_messages, existing_through_visible_rank=existing_through,
                recent_message_limit=self.budget.recent_message_limit)
            if for_summary and cut > existing_through:
                chunk, new_rank, new_message_id = self._bounded_chunk(
                    for_summary, existing_text, rank_by_message_id)
                if not chunk:
                    compaction_calls = 1
                    reason = "summary_unavailable"  # 防御：单组缩写后也超输入预算
                    final = probe
                else:
                    compaction_calls = 1
                    result = await self._summarize_once(
                        existing_text, existing_through, chunk, new_rank, summary_meta,
                        cancel_event=cancel_event, deadline=deadline)
                    if result is not None:
                        ok = io.write_incremental(
                            expected_through_visible_rank=existing_through,
                            new_through_visible_rank=new_rank,
                            new_through_message_id=new_message_id,
                            summary_text=result.summary_text,
                            source_message_count=new_rank,  # 累计覆盖数 = 新逻辑上界
                            provider=result.provider, model=result.model)
                        if ok:
                            existing_text = result.summary_text
                            existing_through = new_rank
                            existing_through_message_id = new_message_id
                            refreshed = True
                            summary_meta["summary_covered_visible_rank"] = new_rank
                            summary_meta["summary_covered_message_id"] = new_message_id
                        else:
                            # 已被更晚 Summary 抢先：采用 winning，不重跑模型
                            (existing_text, existing_through,
                             existing_through_message_id) = await self._adopt_winning(io)
                    else:
                        refresh_failed = True
            if refreshed:
                # 压缩成功：最终上下文 = summary(<=新边界) + 边界后原始行（kept），
                # 连续覆盖、不留未覆盖空洞。
                final = build_prepared_context(
                    messages=kept,
                    current_user_message_id=current_user_message_id,
                    budget=self.budget,
                    system_sections=system_sections,
                    summary_text=existing_text,
                    summary_through_visible_rank=existing_through,
                )
            else:
                # 未刷新成功（失败/无增量可做）或采纳 winning：旧 summary + 尾部
                # 完整组回退重建；摘要只覆盖 <= through 部分（空洞容忍见 spec #23）。
                if existing_through <= 0:
                    reason = "summary_unavailable"
                final = build_prepared_context(
                    messages=messages,
                    current_user_message_id=current_user_message_id,
                    budget=self.budget,
                    system_sections=system_sections,
                    summary_text=existing_text if existing_through > 0 else None,
                    summary_through_visible_rank=existing_through if existing_through > 0 else None,
                )
        else:
            # ---- 无 summary：probe 无法容纳 → 首建一次 ----
            cut, for_summary, kept = select_incremental_inputs(
                seq_messages, existing_through_visible_rank=0,
                recent_message_limit=self.budget.recent_message_limit)
            if for_summary and cut > 0:
                chunk, new_rank, new_message_id = self._bounded_chunk(
                    for_summary, None, rank_by_message_id)
                compaction_calls = 1
                if chunk:
                    result = await self._summarize_once(
                        None, 0, chunk, new_rank, summary_meta,
                        cancel_event=cancel_event, deadline=deadline)
                    if result is not None:
                        created = io.write_incremental(
                            expected_through_visible_rank=0,
                            new_through_visible_rank=new_rank,
                            new_through_message_id=new_message_id,
                            summary_text=result.summary_text,
                            source_message_count=new_rank,
                            provider=result.provider, model=result.model)
                        if created:
                            existing_text = result.summary_text
                            existing_through = new_rank
                            existing_through_message_id = new_message_id
                            refreshed = True
                            summary_meta["summary_covered_visible_rank"] = new_rank
                            summary_meta["summary_covered_message_id"] = new_message_id
                        else:
                            # 并发首建冲突：winning 覆盖更多，直接采用
                            (existing_text, existing_through,
                             existing_through_message_id) = await self._adopt_winning(io)
                            refreshed = existing_through > 0
                    else:
                        refresh_failed = True
                else:
                    reason = "summary_unavailable"  # 防御：单组缩写后也超输入预算
                    final = probe
            if existing_through > 0:
                if refreshed:
                    # 首建成功：最终上下文 = summary(<=新边界) + 边界后原始行（kept）
                    final = build_prepared_context(
                        messages=kept,
                        current_user_message_id=current_user_message_id,
                        budget=self.budget,
                        system_sections=system_sections,
                        summary_text=existing_text,
                        summary_through_visible_rank=existing_through,
                    )
                else:
                    # 采用 winning：以其 through 为界重选尾部完整组
                    _, _fs, kept_winning = select_incremental_inputs(
                        seq_messages, existing_through_visible_rank=existing_through,
                        recent_message_limit=self.budget.recent_message_limit)
                    final = build_prepared_context(
                        messages=kept_winning,
                        current_user_message_id=current_user_message_id,
                        budget=self.budget,
                        system_sections=system_sections,
                        summary_text=existing_text,
                        summary_through_visible_rank=existing_through,
                    )
            elif final is None:
                if for_summary:
                    # 无 summary 且压缩失败：不删行、不硬凑 —— context_limit
                    final = probe
                    reason = "summary_unavailable"
                else:
                    # 行数未超窗口但 token 超限（无旧可摘）：工作上下文过大
                    final = probe
                    reason = "working_context_too_large"

        if final is None:  # pragma: no cover - 防御
            final = probe

        # 最终合法性复核：摘要 + 尾部窗口仍放不进预算 → 明确 context_limit，
        # 绝不把 over-budget 上下文交给主 Agent Provider。
        limit_reason = reason or final.context_limit_reason
        if (final.context_limit
                or final.estimated_tokens > self.budget.max_input_tokens
                or (refreshed and final.omitted_message_ids)):
            final.context_limit = True
            if limit_reason is None:
                limit_reason = ("current_turn_too_large"
                                if final.context_limit_reason == "current_turn_too_large"
                                else "working_context_too_large")
            final.context_limit_reason = limit_reason

        diagnostics = dict(final.diagnostics)
        diagnostics.update(base_diagnostics)
        diagnostics.update({
            "compaction_model_calls": compaction_calls,
            "summary_refreshed": refreshed,
            "summary_refresh_failed": refresh_failed,
        })
        if summary_meta:
            diagnostics.update(summary_meta)
        return OrchestrationResult(prepared=final, compaction_model_calls=compaction_calls,
                                   summary_refreshed=refreshed,
                                   summary_refresh_failed=refresh_failed,
                                   context_limit_reason=limit_reason,
                                   diagnostics=diagnostics)

    def _bounded_chunk(self, for_summary, existing_text,
                       rank_by_message_id) -> tuple[list, int, str | None]:
        """审计 #2：把增量 chunk 裁到 Summarizer 输入预算内（整组裁减，不静默丢消息）。

        返回 (chunk, 实际覆盖 rank, 边界 message_id)。chunk 为空 = 防御性失败。
        调用方只能把 chunk 交给 Summarizer；marker 只推进到 chunk 末条消息。
        """
        if not for_summary:
            return [], 0, None
        existing_chars = len(existing_text or "") + 200  # 正文 + 页眉余量
        chunk = summarizer_coverable_messages(
            for_summary, max_chars=self.budget.summarizer_input_max_chars,
            existing_chars=existing_chars)
        if not chunk:
            return [], 0, None
        boundary = chunk[-1]
        message_id = getattr(boundary, "message_id", None)
        rank = rank_by_message_id.get(message_id, 0) if message_id else 0
        return chunk, rank, message_id

    async def _adopt_winning(self, io: SummaryIO) -> tuple[str, int, str | None]:
        winning = await _maybe_async(io.get_current)
        if winning.summary_text and (winning.through_visible_rank or 0) > 0:
            return (winning.summary_text, winning.through_visible_rank or 0,
                    winning.through_message_id)
        return "", 0, None

    async def _summarize_once(self, existing_text, existing_through, chunk,
                              cut, summary_meta, *, cancel_event=None,
                              deadline=None) -> SummaryResult | None:
        if self._compaction_calls >= 1:
            return None  # max_compaction_calls_per_run=1（业务层不 while retry）
        if cancel_event is not None and cancel_event.is_set():
            return None  # 已取消：快速失败，不发起模型调用（审计 #3）
        self._compaction_calls += 1
        try:
            result = await self.summarizer.summarize(
                existing_summary=existing_text,
                messages=chunk,
                target_through_visible_rank=cut,
                summary_token_budget=self.budget.summary_token_budget,
                runtime_context={
                    "existing_through_visible_rank": existing_through,
                    "cancel_event": cancel_event,
                    "deadline": deadline,
                },
            )
        except Exception:
            return None
        if not validate_summary_result(result, summary_token_budget=self.budget.summary_token_budget):
            return None
        # usage/accounting 观测（provider/model/cache/cost/估算），见 spec #8
        meta = {
            "summary_provider": result.provider,
            "summary_model": result.model,
            "summary_source_message_count": len(chunk),
            "summary_estimated_tokens": result.estimated_tokens,
        }
        if isinstance(result.usage, dict):
            for key, value in result.usage.items():
                meta[f"summary_{key}"] = value
        summary_meta.update(meta)
        return result


async def _maybe_async(value_or_callable):
    value = value_or_callable() if callable(value_or_callable) else value_or_callable
    if hasattr(value, "__await__"):
        return await value
    return value
