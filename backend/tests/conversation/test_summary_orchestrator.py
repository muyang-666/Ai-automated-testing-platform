"""P10.1-B3 SummaryOrchestrator 合同测试（FakeSummarizer + 内存 SummaryIO，零 DB/模型）。"""

import asyncio

from app.agents.conversation.context_builder import ContextBudgetConfig
from app.agents.conversation.messages import TextContent
from app.agents.conversation.summary_orchestrator import (
    OrchestrationResult, SummaryIO, SummaryOrchestrator, SummaryStoreView,
)
from app.services.agent.conversation_summary_service import SummaryResult
from conversation_samples import make_assistant, make_user


def _history(n, fill=120):
    # 会话事件序按真实连续 sequence：uN=2N-1, aN=2N
    pairs = []
    for i in range(1, n + 1):
        pairs.append((2 * i - 1, make_user(message_id=f"u{i}", text=f"用户 {i} " + "字" * fill)))
        pairs.append((2 * i, make_assistant(
            message_id=f"a{i}", content=[TextContent(text=f"回复 {i} " + "字" * fill)],
            stop_reason="stop")))
    return pairs


class FakeSummarizer:
    def __init__(self, behavior="success", oversized=False, estimate=10):
        self.behavior = behavior
        self.oversized = oversized
        self.estimate = estimate
        self.calls = []
        self.received = []

    async def summarize(self, **kwargs):
        self.calls.append(kwargs)
        self.received.append((kwargs.get("existing_summary"),
                              [m.message_id for m in kwargs.get("messages", [])],
                              kwargs.get("target_through_visible_rank")))
        if self.behavior == "timeout":
            raise TimeoutError("fake timeout")
        if self.behavior == "exception":
            raise RuntimeError("fake boom")
        if self.behavior == "empty":
            text = ""
        else:
            text = f"增量摘要至 {kwargs.get('target_through_visible_rank')}"
        return SummaryResult(summary_text=text,
                             through_visible_rank=kwargs.get("target_through_visible_rank"),
                             source_message_count=len(kwargs.get("messages", [])),
                             provider="fake", model="fake-model",
                             estimated_tokens=self.estimate if not self.oversized
                             else 999_999)


class MemoryIO(SummaryIO):
    def __init__(self, existing=None):
        self.current = existing or SummaryStoreView()

    def get_current(self):
        return self.current

    def write_incremental(self, *, expected_through_visible_rank, new_through_visible_rank,
                          new_through_message_id, summary_text, source_message_count,
                          provider=None, model=None):
        cur = self.current
        if cur.through_visible_rank is None:
            self.current = SummaryStoreView(through_visible_rank=new_through_visible_rank,
                                            through_message_id=new_through_message_id,
                                            summary_text=summary_text)
            return True
        if cur.through_visible_rank == expected_through_visible_rank \
                and new_through_visible_rank > cur.through_visible_rank:
            self.current = SummaryStoreView(through_visible_rank=new_through_visible_rank,
                                            through_message_id=new_through_message_id,
                                            summary_text=summary_text)
            return True
        return False


def _budget():
    # 现实预算：压缩成功后 summary+尾部窗口必须整体放得进 max_input；
    # 过小的人工预算会把"尾部窗口自身超限"误判成压缩失败路径。
    return ContextBudgetConfig(model_context_window=40_000, reserved_output_tokens=4_000,
                               recent_message_limit=12, summary_token_budget=3_000)


def _run(coro):
    return asyncio.run(coro)


def test_short_conversation_no_summarizer_call():
    pairs = _history(3, fill=10)
    fake = FakeSummarizer()
    result = _run(SummaryOrchestrator(fake, _budget(), MemoryIO()).prepare(
        seq_messages=pairs, current_user_message_id="u3"))
    assert result.compaction_model_calls == 0
    assert fake.calls == []
    assert result.summary_refreshed is False
    assert result.prepared.context_limit is False


def test_first_compaction_success_creates_summary():
    pairs = _history(100, fill=300)
    fake = FakeSummarizer()
    io = MemoryIO()
    result = _run(SummaryOrchestrator(fake, _budget(), io).prepare(
        seq_messages=pairs, current_user_message_id="u100"))
    assert result.compaction_model_calls == 1
    assert result.summary_refreshed is True
    assert io.current.through_visible_rank is not None
    assert io.current.through_visible_rank < 199  # 不含 current user（u100=seq199）
    assert result.prepared.context_limit is False
    assert len(result.prepared.included_message_ids) < len(pairs)
    # Summarizer 收到的原始消息不含完整历史（incremental 输入受 exchange/cut 限制）
    assert len(fake.received[0][1]) < len(pairs)


def test_incremental_second_only_after_existing():
    fake = FakeSummarizer()
    io = MemoryIO(existing=SummaryStoreView(through_visible_rank=40, summary_text="旧摘要到40"))
    pairs = _history(80, fill=300)
    result = _run(SummaryOrchestrator(fake, _budget(), io).prepare(
        seq_messages=pairs, current_user_message_id="u80"))
    _, ids, target = fake.received[0]
    assert target > 40
    assert "u1" not in ids and "a1" not in ids and "a20" not in ids  # 1..40 原始消息不进 Summarizer
    assert ids[0].startswith("u21") or ids[0].startswith("a21")  # existing=40 之后从 41 起
    assert result.summary_refreshed is True
    assert io.current.through_visible_rank > 40


def test_conflict_uses_winning_summary_no_second_call():
    fake = FakeSummarizer()
    io = MemoryIO(existing=SummaryStoreView(through_visible_rank=200,
                                            summary_text="别人已写 200"))
    pairs = _history(60, fill=300)
    result = _run(SummaryOrchestrator(fake, _budget(), io).prepare(
        seq_messages=pairs, current_user_message_id="u60"))
    # existing=80 已覆盖全部历史 → 不需要调用
    assert fake.calls == []
    assert result.prepared.context_limit is False
    assert "200" in (result.prepared.summary_text or "")


def test_failure_fallbacks_no_infinite_calls():
    for behavior in ("timeout", "exception", "empty", "oversized"):
        fake = FakeSummarizer(behavior=behavior, oversized=behavior == "oversized")
        io = MemoryIO(existing=SummaryStoreView(through_visible_rank=40, summary_text="旧摘要"))
        pairs = _history(80, fill=300)
        result = _run(SummaryOrchestrator(fake, _budget(), io).prepare(
            seq_messages=pairs, current_user_message_id="u80"))
        assert len(fake.calls) == 1  # 最多一次，无 while-retry
        assert result.summary_refresh_failed is True
        assert result.prepared.context_limit is False  # old summary fallback fits
        assert io.current.through_visible_rank == 40  # 未写回失败结果


# ----------------------------------------------- 审计 #2：marker 不越过实际输入

def test_marker_never_overclaims_when_input_budget_small():
    """增量 chunk 超 Summarizer 输入预算 → 按完整组裁减；落库 marker（rank +
    message_id 锚点）只推进到 fake 实际收到的最后一条消息，绝不越过。"""
    budget = ContextBudgetConfig(model_context_window=40_000, reserved_output_tokens=4_000,
                                 recent_message_limit=8, summary_token_budget=2_000,
                                 summarizer_input_max_chars=900)
    pairs = _history(30, fill=160)  # 每条 ~165 chars → 全部渲染远超 900
    fake = FakeSummarizer()
    io = MemoryIO()
    result = _run(SummaryOrchestrator(fake, budget, io).prepare(
        seq_messages=pairs, current_user_message_id="u30"))
    assert result.summary_refreshed is True
    assert len(fake.calls) == 1
    existing, received_ids, target = fake.received[0]
    assert target == io.current.through_visible_rank  # 落库 rank == 实际覆盖
    assert io.current.through_message_id == received_ids[-1]  # 锚点 == chunk 末条
    rank_by_id = {m.message_id: rank for rank, m in pairs}
    # 关键断言：任何 rank <= marker 的消息都真实进入了 Summarizer 输入
    covered_ranks = set(received_ids)
    for message_id, rank in rank_by_id.items():
        if rank <= io.current.through_visible_rank:
            assert message_id in covered_ranks, f"rank {rank} 被 marker 覆盖但未进入输入"
    # 且没有任何输入消息 rank > marker（不把窗口/未来行送进摘要）
    assert all(rank_by_id[mid] <= io.current.through_visible_rank for mid in received_ids)
    # 若预算充足则不受影响（回归：正常 chunk 不裁减）
    assert len(received_ids) < len(pairs)


def test_incremental_shrink_keeps_existing_summary_anchor_consistent():
    """已有 summary + 输入预算过小：新 marker/锚点仍落在实际送达的最后一条。"""
    budget = ContextBudgetConfig(model_context_window=40_000, reserved_output_tokens=4_000,
                                 recent_message_limit=8, summary_token_budget=2_000,
                                 summarizer_input_max_chars=1200)
    pairs = _history(80, fill=160)
    io = MemoryIO(existing=SummaryStoreView(through_visible_rank=40,
                                            through_message_id="u20",
                                            summary_text="旧摘要到40"))
    fake = FakeSummarizer()
    result = _run(SummaryOrchestrator(fake, budget, io).prepare(
        seq_messages=pairs, current_user_message_id="u80"))
    assert result.summary_refreshed is True
    existing, received_ids, target = fake.received[0]
    assert existing == "旧摘要到40"
    assert io.current.through_visible_rank > 40
    assert io.current.through_visible_rank == target
    assert io.current.through_message_id == received_ids[-1]
    rank_by_id = {m.message_id: rank for rank, m in pairs}
    assert all(rank_by_id[mid] > 40 for mid in received_ids)  # 不重发旧 raw
    assert all(rank_by_id[mid] <= io.current.through_visible_rank for mid in received_ids)
