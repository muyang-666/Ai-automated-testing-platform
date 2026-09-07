"""P10.1-B3 SummaryOrchestrator：bounded history → incremental summary → PreparedContext。

设计目标：
- Runner 不拼 prompt、不直接调 Provider，只消费本 Orchestrator 的结果；
- DB 事务边界归调用方：io 提供 get/write 两个独立阶段回调（读阶段结束后才 summarize）；
- 每个 run 最多一次 Summarizer 调用（max_compaction_calls_per_run=1）；
- 冲突时采用 winning Summary，不重复调模型、不回退。
"""

from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import (
    ContextBudgetConfig,
    PreparedContext,
    build_prepared_context,
    estimate_text_tokens,
)
from app.services.agent.conversation_summary_service import (
    SummaryResult,
    select_incremental_inputs,
    validate_summary_result,
)


@dataclass
class SummaryStoreView:
    through_sequence_no: int | None = None
    summary_text: str | None = None


class SummaryIO:
    """依赖注入：真实实现负责两个独立短事务阶段；测试用内存实现。"""

    def get_current(self) -> SummaryStoreView:
        raise NotImplementedError

    def write_incremental(self, *, expected_through, new_through, summary_text,
                          source_message_count, provider=None, model=None) -> bool:
        raise NotImplementedError


@dataclass
class OrchestrationResult:
    prepared: PreparedContext
    compaction_model_calls: int = 0
    summary_refreshed: bool = False
    summary_refresh_failed: bool = False
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
    ) -> OrchestrationResult:
        io = io or self.io
        assert io is not None
        current = await _maybe_async(io.get_current)
        existing_text = current.summary_text
        existing_through = current.through_sequence_no or 0
        messages = [message for _, message in seq_messages]

        # 第一次尝试：不加 summary。若可完整容纳 → 不调 Summarizer。
        probe = build_prepared_context(
            messages=messages,
            current_user_message_id=current_user_message_id,
            budget=self.budget,
            system_sections=system_sections,
        )
        if not probe.compaction_used and not probe.context_limit:
            return OrchestrationResult(prepared=probe, diagnostics=probe.diagnostics)

        compaction_calls = 0
        refreshed = False
        refresh_failed = False

        if existing_through > 0 and existing_text:
            # 已有 summary：需要时只做增量刷新一次
            cut, for_summary, _kept = select_incremental_inputs(
                seq_messages, existing_through_sequence=existing_through,
                recent_message_limit=self.budget.recent_message_limit)
            if for_summary and cut > existing_through:
                result = await self._summarize_once(
                    existing_text, existing_through, for_summary, cut,
                    provider_meta={})
                if result is not None:
                    ok = io.write_incremental(
                        expected_through=existing_through,
                        new_through=cut,
                        summary_text=result.summary_text,
                        source_message_count=result.source_message_count,
                        provider=result.provider, model=result.model)
                    if ok:
                        existing_text = result.summary_text
                        existing_through = cut
                        refreshed = True
                    else:
                        # 已被更晚 Summary 抢先：采用 winning，不再调模型
                        winning = await _maybe_async(io.get_current)
                        if winning.summary_text:
                            existing_text = winning.summary_text
                            existing_through = winning.through_sequence_no or 0
                else:
                    refresh_failed = True
            compaction_calls = 1
        else:
            # 无 summary：若 context_limit（无法完整容纳）→ 尝试首建一次
            if probe.context_limit:
                cut, for_summary, _kept = select_incremental_inputs(
                    seq_messages, existing_through_sequence=0,
                    recent_message_limit=self.budget.recent_message_limit)
                compaction_calls = 1
                if for_summary:
                    result = await self._summarize_once(
                        None, 0, for_summary, cut, provider_meta={})
                    if result is not None:
                        created = io.write_incremental(
                            expected_through=0,
                            new_through=cut,
                            summary_text=result.summary_text,
                            source_message_count=result.source_message_count,
                            provider=result.provider, model=result.model)
                        if not created:
                            winning = await _maybe_async(io.get_current)
                            if winning.summary_text:
                                existing_text = winning.summary_text
                                existing_through = winning.through_sequence_no or 0
                        else:
                            existing_text = result.summary_text
                            existing_through = cut
                            refreshed = True
                    else:
                        refresh_failed = True

        final_summary = existing_text if existing_through > 0 else None
        prepared = build_prepared_context(
            messages=messages,
            current_user_message_id=current_user_message_id,
            budget=self.budget,
            system_sections=system_sections,
            summary_text=final_summary,
            summary_through_sequence=existing_through if final_summary else None,
        )
        diagnostics = dict(prepared.diagnostics)
        diagnostics.update({
            "compaction_model_calls": compaction_calls,
            "summary_refreshed": refreshed,
            "summary_refresh_failed": refresh_failed,
        })
        return OrchestrationResult(prepared=prepared, compaction_model_calls=compaction_calls,
                                   summary_refreshed=refreshed,
                                   summary_refresh_failed=refresh_failed,
                                   diagnostics=diagnostics)

    async def _summarize_once(self, existing_text, existing_through, for_summary,
                              cut, provider_meta) -> SummaryResult | None:
        if self._compaction_calls >= 1:
            return None  # max_compaction_calls_per_run=1（业务层不 while retry）
        self._compaction_calls += 1
        try:
            result = await self.summarizer.summarize(
                existing_summary=existing_text,
                messages=for_summary,
                target_through_sequence=cut,
                summary_token_budget=self.budget.summary_token_budget,
                runtime_context=provider_meta,
            )
        except Exception:
            return None
        if not validate_summary_result(result, summary_token_budget=self.budget.summary_token_budget):
            return None
        return result


async def _maybe_async(value_or_callable):
    value = value_or_callable() if callable(value_or_callable) else value_or_callable
    if hasattr(value, "__await__"):
        return await value
    return value
