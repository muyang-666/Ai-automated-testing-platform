"""P10.1-B3 SummaryOrchestrator：bounded history → incremental summary → PreparedContext。

设计目标（P10.1-B3）：
- Runner 不拼 prompt、不直接调 Provider、不直接处理某家模型返回；本模块把
  "读 bounded history / 读 latest summary / build context / 判定压缩 / 选增量 /
  调 Summarizer / 持久化 / 重建 PreparedContext" 全部收敛，Runner 只消费结果；
- DB 事务边界归调用方：io 提供 get/write 两个独立短事务阶段（读阶段结束后才
  summarize；写阶段独立 commit）。本模块自身不持任何 DB 事务；
- 每个 Run 最多一次 Summarizer 调用（max_compaction_calls_per_run=1）；
  冲突时采用 winning Summary，绝不覆盖、绝不因冲突重跑模型；
- 增量边界语义为"逻辑位置 rank"（见 conversation_summary_service 模块头）；
- current_turn_too_large 与摘要无关：不调用 Summarizer，直接返回 context_limit；
- 压缩成功后的最终上下文 = summary(through=cut) + cut 之后全部原始行；若重建
  时连"摘要 + 尾部窗口"都放不进预算 → context_limit（working_context_too_large），
  绝不静默丢行。
"""

from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import (
    ContextBudgetConfig,
    PreparedContext,
    build_prepared_context,
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
    """依赖注入：真实实现负责两个独立短事务阶段；测试用内存实现。

    get_current：返回当前 winning summary 视图（读后即释放事务）。
    write_incremental：expected_through == 0 → 首次创建（唯一冲突 = 已被抢先）；
    否则单调条件更新。返回 True = 本次写入生效；False = 被更晚 Summary 抢先
    （调用方读 winning，不回退、不重调 Summarizer）。
    """

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
    ) -> OrchestrationResult:
        """seq_messages：(rank, Message) 列表（rank 为 run-bounded 逻辑位置，1 起连续）。"""
        io = io or self.io
        assert io is not None
        self._compaction_calls = 0  # 每 Run 一次 prepare = 至多一次模型调用
        current = await _maybe_async(io.get_current)
        existing_text = current.summary_text
        existing_through = current.through_sequence_no or 0
        messages = [message for _, message in seq_messages]
        base_diagnostics = {
            "existing_summary_present": bool(existing_text) and existing_through > 0,
            "existing_summary_through_sequence": existing_through if existing_through > 0 else None,
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

        # 当前 UserMessage 自身超限与历史压缩无关：压缩旧历史不减少当前轮 token。
        if probe.context_limit and probe.context_limit_reason == "current_turn_too_large":
            return OrchestrationResult(prepared=probe,
                                       context_limit_reason="current_turn_too_large",
                                       diagnostics={**probe.diagnostics, **base_diagnostics})

        compaction_calls = 0
        refreshed = False
        refresh_failed = False
        summary_meta: dict[str, Any] = {}
        reason: str | None = None

        if existing_through > 0 and existing_text:
            # ---- 已有 summary：需要时只做一次增量刷新 ----
            cut, for_summary, kept = select_incremental_inputs(
                seq_messages, existing_through_sequence=existing_through,
                recent_message_limit=self.budget.recent_message_limit)
            if for_summary and cut > existing_through:
                compaction_calls = 1
                result = await self._summarize_once(
                    existing_text, existing_through, for_summary, cut, summary_meta)
                if result is not None:
                    ok = io.write_incremental(
                        expected_through=existing_through,
                        new_through=cut,
                        summary_text=result.summary_text,
                        source_message_count=cut,  # 累计覆盖数 = 新逻辑上界
                        provider=result.provider, model=result.model)
                    if ok:
                        existing_text = result.summary_text
                        existing_through = cut
                        refreshed = True
                    else:
                        # 已被更晚 Summary 抢先：采用 winning，不重跑模型
                        existing_text, existing_through = await self._adopt_winning(io)
                else:
                    refresh_failed = True
            if refreshed:
                # 压缩成功：最终上下文 = summary(≤cut) + cut 后原始行（kept），
                # 保证连续覆盖、不留未覆盖空洞。
                final = build_prepared_context(
                    messages=kept,
                    current_user_message_id=current_user_message_id,
                    budget=self.budget,
                    system_sections=system_sections,
                    summary_text=existing_text,
                    summary_through_sequence=existing_through,
                )
            else:
                # 未刷新成功（失败/无增量可做）或采纳 winning：用旧 summary + 尾部
                # 完整组回退重建；摘要只覆盖 ≤ through 部分（空洞容忍见 spec #23）。
                if existing_through <= 0:
                    reason = "summary_unavailable"
                final = build_prepared_context(
                    messages=messages,
                    current_user_message_id=current_user_message_id,
                    budget=self.budget,
                    system_sections=system_sections,
                    summary_text=existing_text if existing_through > 0 else None,
                    summary_through_sequence=existing_through if existing_through > 0 else None,
                )
        else:
            # ---- 无 summary：probe 无法容纳 → 首建一次 ----
            cut, for_summary, kept = select_incremental_inputs(
                seq_messages, existing_through_sequence=0,
                recent_message_limit=self.budget.recent_message_limit)
            if for_summary and cut > 0:
                compaction_calls = 1
                result = await self._summarize_once(None, 0, for_summary, cut, summary_meta)
                if result is not None:
                    created = io.write_incremental(
                        expected_through=0,
                        new_through=cut,
                        summary_text=result.summary_text,
                        source_message_count=cut,
                        provider=result.provider, model=result.model)
                    if created:
                        existing_text = result.summary_text
                        existing_through = cut
                        refreshed = True
                    else:
                        # 并发首建冲突：winning 覆盖更多，直接采用
                        existing_text, existing_through = await self._adopt_winning(io)
                        refreshed = existing_through > 0
                else:
                    refresh_failed = True
            if existing_through > 0:
                if refreshed:
                    final = build_prepared_context(
                        messages=kept,
                        current_user_message_id=current_user_message_id,
                        budget=self.budget,
                        system_sections=system_sections,
                        summary_text=existing_text,
                        summary_through_sequence=existing_through,
                    )
                else:
                    # 采用 winning：以其 through 为界重选尾部完整组
                    _, _fs, kept_winning = select_incremental_inputs(
                        seq_messages, existing_through_sequence=existing_through,
                        recent_message_limit=self.budget.recent_message_limit)
                    final = build_prepared_context(
                        messages=kept_winning,
                        current_user_message_id=current_user_message_id,
                        budget=self.budget,
                        system_sections=system_sections,
                        summary_text=existing_text,
                        summary_through_sequence=existing_through,
                    )
            elif for_summary:
                # 无 summary 且 Summarizer 失败：不删行、不硬凑 —— context_limit
                final = probe
                reason = "summary_unavailable"
            else:
                # 行数未超窗口但 token 超限（无旧可摘）：摘要救不了，归因工作上下文过大
                final = probe
                reason = "working_context_too_large"

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

    async def _adopt_winning(self, io: SummaryIO) -> tuple[str, int]:
        winning = await _maybe_async(io.get_current)
        if winning.summary_text and (winning.through_sequence_no or 0) > 0:
            return winning.summary_text, winning.through_sequence_no or 0
        return "", 0

    async def _summarize_once(self, existing_text, existing_through, for_summary,
                              cut, summary_meta) -> SummaryResult | None:
        if self._compaction_calls >= 1:
            return None  # max_compaction_calls_per_run=1（业务层不 while retry）
        self._compaction_calls += 1
        try:
            result = await self.summarizer.summarize(
                existing_summary=existing_text,
                messages=for_summary,
                target_through_sequence=cut,
                summary_token_budget=self.budget.summary_token_budget,
                runtime_context={"existing_through_sequence": existing_through},
            )
        except Exception:
            return None
        if not validate_summary_result(result, summary_token_budget=self.budget.summary_token_budget):
            return None
        # usage/accounting 观测（provider/model/cache/cost/估算），见 spec #8
        meta = {
            "summary_provider": result.provider,
            "summary_model": result.model,
            "summary_source_message_count": len(for_summary),
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
