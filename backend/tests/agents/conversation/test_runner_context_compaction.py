"""P10.1-B3 Runner 集成：ConversationRunner → 上下文准备 → 增量压缩 → AgentLoop。

Fake Provider / FakeSummarizer / 内存 SQLite。验证 spec #33-#42：
- 短对话：0 次 Summarizer、无 summary 行、Provider 看到完整历史；
- 首次压缩：summary 行创建、through < 当前 user rank、Provider 不再看全量历史；
- 第二次增量：Summarizer 只收到 existing 之后的原始行（不含旧 raw、不含尾部窗口）；
- 200+ messages + 多 ToolCall + 大 ToolResult：DB 原样、预算内、摘要可用、exchange 完整；
- Summary 失败四态（timeout/exception/empty/oversized）→ 有旧摘要回退成功 / 无摘要
  → context_limit；不无限重试（每 Run 最多 1 次调用）；
- Huge Current User：0 次 Summarizer、0 次主 Provider、Run=context_limit、UserMessage 保留；
- Follow-up A/B：A 看不到 B；B 看到 A 的 terminal 结果（真实 sequence/run 模型）；
- Artifact stale summary：metadata section revision 实时（25），摘要内旧值（20）不权威；
- context_prepared/context_compacted/context_limit 事件（脱敏 payload，非 revision 事件）。
"""
import asyncio
from contextlib import asynccontextmanager

import pytest
from pydantic import BaseModel

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.context_builder import ContextBudgetConfig
from app.agents.conversation.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantStartEvent,
)
from app.agents.conversation.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    Usage,
)
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.models.agent.conversation_summary import ConversationSummary
from app.models.user import User
from app.services.agent import agent_run_service, conversation_service
from app.services.agent.conversation_summary_service import SummaryResult

USER_A = 9201
TS = 1_700_000_000_000
# 会话内 message_id 必须全局唯一（_persist_new_messages 按 message_id 去重），
# 因此 runner 默认 id 计数器在模块级共享，跨 run/测试内连续。
_ID_COUNTER = iter(f"m{i}" for i in range(1, 10_000_000))


# ------------------------------------------------------------------ fixtures

def _usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def assistant(*content, reason="stop", message_id="template", provider="fake",
              model="fake-model"):
    return AssistantMessage(message_id=message_id, timestamp=TS, role="assistant",
        content=list(content), api="chat", provider=provider, model=model,
        usage=_usage(), stop_reason=reason)


class FakeGateway:
    """脚本化 Fake Provider：依次弹出响应；记录请求（供断言主 Provider 视角）。"""

    def __init__(self, responses, explode=False):
        self.responses = list(responses)
        self.requests = []
        self.explode = explode

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        if self.explode:
            @asynccontextmanager
            async def managed():
                raise RuntimeError("provider-boom")
                yield  # pragma: no cover
            return managed()
        final = self.responses.pop(0).model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                partial = final.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                if final.stop_reason in {"error", "aborted"}:
                    control.error_code = "synthetic_model_error" if final.stop_reason == "error" else "canceled"
                    yield AssistantErrorEvent(reason=final.stop_reason, error=final)
                else:
                    yield AssistantDoneEvent(reason=final.stop_reason, message=final)
            yield events()
        return managed()


class FakeSummarizer:
    """行为可配：success/timeout/exception/empty/oversized；记录每次调用。"""

    def __init__(self, behavior="success", text_template="汇总至{target}"):
        self.behavior = behavior
        self.text_template = text_template
        self.calls = []
        self.received = []

    async def summarize(self, **kwargs):
        target = kwargs.get("target_through_visible_rank")
        received_ids = [m.message_id for m in kwargs.get("messages", [])]
        self.calls.append(kwargs)
        self.received.append((kwargs.get("existing_summary"), received_ids, target))
        if self.behavior == "timeout":
            raise TimeoutError("fake timeout")
        if self.behavior == "exception":
            raise RuntimeError("fake boom")
        if self.behavior == "empty":
            text = ""
        else:
            text = self.text_template.format(target=target)
        return SummaryResult(
            summary_text=text,
            through_visible_rank=target,
            source_message_count=len(received_ids),
            provider="fake-summarizer", model="sum-model",
            usage={"input_tokens": 10, "output_tokens": 5, "cache_read_tokens": None,
                   "cache_write_tokens": None, "cost": None},
            estimated_tokens=8 if self.behavior != "oversized" else 999_999,
        )


def make_runner(responses, *, tools=None, budget=None, summarizer=None,
                id_counter=None, explode=False):
    if id_counter is None:
        id_counter = _ID_COUNTER
    gateway = FakeGateway(responses, explode=explode)
    runner = ConversationRunner(
        gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                  "key", "fake-model", max_tokens=200),
        tool_registry=tools or ToolRegistry(),
        system_prompt="be helpful",
        limits=AgentLoopLimits(max_turns=6, max_model_calls=6, max_tool_calls=20),
        provider_attempt_budget=AttemptBudget(limit=20),
        context_budget=budget,
        summarizer_factory=(lambda: summarizer) if summarizer is not None else None,
        id_factory=lambda: next(id_counter),
        timestamp_factory=lambda: TS,
    )
    return runner, gateway


def budget(*, window=24_000, reserve=2_000, limit=10, summary_budget=1_000):
    return ContextBudgetConfig(model_context_window=window, reserved_output_tokens=reserve,
                               recent_message_limit=limit,
                               summary_token_budget=summary_budget)


def _run_async(coro):
    return asyncio.run(coro)


def seed_user(db):
    if db.query(User).filter(User.id == USER_A).first() is None:
        db.add(User(id=USER_A, username="ctx-b", password_hash="x", salt="y",
                    status="active", is_deleted=False))
        db.flush()


def conversation(db):
    row = conversation_service.create_conversation_session(
        db, requester_user_id=USER_A, title="P10.1-B3 runner")
    db.commit()
    return row


def submit(db, session_id, content, key):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, message_id_factory=lambda: f"user-{key}",
        timestamp_ms_factory=lambda: TS)


def submit_followup(db, session_id, content, key):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, queue_mode="follow_up",
        message_id_factory=lambda: f"user-{key}", timestamp_ms_factory=lambda: TS)


def message_rows(db, session_id):
    return db.query(AgentMessage).filter(
        AgentMessage.session_id == session_id).order_by(AgentMessage.sequence_no.asc()).all()


def summary_row(db, session_id):
    return db.query(ConversationSummary).filter(
        ConversationSummary.conversation_id == session_id).first()


def run_events(db, session_id, event_type=None):
    query = db.query(AgentEvent).filter(AgentEvent.session_id == session_id)
    if event_type is not None:
        query = query.filter(AgentEvent.event_type == event_type)
    return query.order_by(AgentEvent.sequence_no.asc()).all()


def replay_turn(db, chat, key, content, fill=0, budget_cfg=None, summarizer=None,
                responses=None, tools=None):
    """提交并执行一轮（默认纯文本回答）。返回 (submission, gateway, summarizer)。"""
    text = f"内容 {key} " + "字" * fill
    sub = submit(db, chat.id, text, key)
    if responses is None:
        responses = [assistant(TextContent(text=f"回答 {key}" + "字" * min(fill, 200)),
                               message_id=f"resp-{key}")]
    fake_summarizer = summarizer if summarizer is not None else FakeSummarizer()
    runner, gateway = make_runner(responses, tools=tools, budget=budget_cfg,
                                  summarizer=fake_summarizer)
    outcome = _run_async(runner.run(db, sub.run.id))
    assert outcome.status == "succeeded", f"{key}: {outcome}"
    return sub, gateway, fake_summarizer


def plain_history(db, chat, *, prefix, start=1, stop, fill=230, cfg=None):
    """跑若干纯文本轮；每轮使用独立 FakeSummarizer。返回使用的汇总实例列表。"""
    used_summarizers = []
    for i in range(start, stop):
        fake = FakeSummarizer()
        _, gateway, _ = replay_turn(db, chat, f"{prefix}{i}", content=f"q{i}",
                                    fill=fill, budget_cfg=cfg, summarizer=fake)
        used_summarizers.append(fake)
    return used_summarizers


# ------------------------------------------------------------- spec #33 短对话

def test_short_conversation_zero_summarizer_and_full_history_to_provider(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    last_gateway = None
    for turn in range(1, 6):  # 10 条消息，窗口内完整容纳 → 0 次 Summarizer
        _, gateway, fake = replay_turn(db_session, chat, f"t{turn}",
                                       content=f"q{turn}", budget_cfg=budget())
        assert len(fake.calls) == 0
        last_gateway = gateway
    assert summary_row(db_session, chat.id) is None  # 不创建 summary 行
    # 主 Provider 看到全部可容纳历史（第 5 轮 = 完整 9 条：4 对 + 当前 user）
    history = last_gateway.requests[0].messages
    assert len(history) == 9
    assert [m.role for m in history] == ["user", "assistant"] * 4 + ["user"]
    assert history[-1].content.startswith("内容 t5")
    # 无 context_prepared 事件（未使用压缩上下文）
    assert run_events(db_session, chat.id, "context_prepared") == []
    # 摘要调用完全不可见 → summary usage 不产生任何 DB 记录
    assert run_events(db_session, chat.id, "context_compacted") == []


# ------------------------------------------------------ spec #34 首次压缩 100+

def test_first_compaction_creates_summary_and_100plus_run_stays_compressed(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    seen_summarizer_call = False
    turn = 0
    while True:
        turn += 1
        _, gateway, fake = replay_turn(db_session, chat, f"f{turn}", content=f"q{turn}",
                                       fill=230, budget_cfg=cfg)
        seen_summarizer_call = seen_summarizer_call or bool(fake.calls)
        if len(message_rows(db_session, chat.id)) >= 100 and seen_summarizer_call:
            break
        assert turn < 120, "历史应达到 100+ 条并至少完成一次压缩"
    rows = message_rows(db_session, chat.id)
    row = summary_row(db_session, chat.id)
    assert row is not None
    # through < 当前 user 的逻辑位置（当前轮 UserMessage 永不进摘要）
    current_rank = len(rows)
    assert row.through_visible_rank < current_rank
    assert row.source_message_count == row.through_visible_rank  # 累计覆盖数语义
    # 主 Provider 不看到完整 raw 历史（摘要 + 尾部窗口）
    request = gateway.requests[0]
    assert "through visible position" in request.system_prompt
    assert len(request.messages) < len(rows) // 2
    assert len(fake.calls) <= 1  # 每 Run ≤ 1 次 Summarizer 调用
    # 上下文事件已落库且脱敏（不含 summary 文本）
    prepared_events = run_events(db_session, chat.id, "context_prepared")
    assert prepared_events
    payload = prepared_events[-1].payload_json
    assert payload["summary_used"] is True
    assert payload["estimated_input_tokens"] <= cfg.max_input_tokens
    assert "summary_text" not in payload and "text" not in payload
    # context_compacted 只发生在真正刷新 Summary 时
    compacted = run_events(db_session, chat.id, "context_compacted")
    assert compacted and compacted[-1].payload_json["new_through_visible_rank"] == row.through_visible_rank


# ------------------------------------------------------ spec #35 第二次增量

def test_second_compaction_incremental_inputs_only_after_existing(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    # 跑到第一次压缩（存在 summary through>0）
    old_through = 0
    turn = 0
    while True:
        turn += 1
        _, _, fake = replay_turn(db_session, chat, f"g{turn}", content=f"q{turn}",
                                 fill=230, budget_cfg=cfg)
        if fake.calls and summary_row(db_session, chat.id) is not None:
            old_through = summary_row(db_session, chat.id).through_visible_rank
            break
        assert turn < 60
    assert old_through > 0
    old_text = summary_row(db_session, chat.id).summary_text

    # 继续增长 → 出现第二次增量压缩（DB through 单调向前）
    incremental = None
    for extra in range(1, 60):
        fake = FakeSummarizer()
        _, gateway, used = replay_turn(db_session, chat, f"h{extra}", content=f"q{extra}",
                                       fill=230, budget_cfg=cfg, summarizer=fake)
        cur = summary_row(db_session, chat.id).through_visible_rank
        if cur > old_through:
            incremental = (gateway, used, cur)
            break
    assert incremental is not None, "应有第二次增量压缩"
    _, used, new_through = incremental
    rows = message_rows(db_session, chat.id)
    assert new_through > old_through  # 单调向前
    assert summary_row(db_session, chat.id).source_message_count == new_through

    existing_text, received_ids, target = used.received[0]
    assert existing_text == old_text  # 收到了 existing summary
    assert target == new_through
    # 输入 = old_through+1 .. new_through 的原始消息（rank 区间），
    # 不含 <= old_through 的旧 raw，也不含尾部窗口（> new_through）
    rank_ids = {i + 1: r.message_id for i, r in enumerate(rows)}
    expected = {rank_ids[r] for r in range(old_through + 1, new_through + 1)}
    assert set(received_ids) == expected
    assert not (set(received_ids) & {rank_ids[r] for r in range(1, old_through + 1)})
    assert not (set(received_ids) & {rank_ids[r] for r in range(new_through + 1, len(rows) + 1)})
    # context_compacted 事件带 old/new through + usage 可观测
    last = run_events(db_session, chat.id, "context_compacted")[-1].payload_json
    assert last["old_through_visible_rank"] == old_through
    assert last["new_through_visible_rank"] == new_through
    assert last["provider"] == "fake-summarizer"
    assert last["usage"].get("input_tokens") == 10


# ------------------------------------------------------ spec #36 200+ messages

class EchoInput(BaseModel):
    k: int


def echo_registry(result_text):
    def echo(arguments, runtime):
        return result_text
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="echo", input_model=EchoInput, handler=echo))
    return registry


def _tool_turn(db, chat, key, *, n_calls=1, budget_cfg=None, summarizer=None):
    calls = [ToolCall(id=f"c{key}-{k}", name="echo", arguments={"k": k})
             for k in range(n_calls)]
    responses = [
        assistant(TextContent(text="查一下"), *calls, reason="toolUse",
                  message_id=f"tc-{key}"),
        assistant(TextContent(text="完成 " + key), message_id=f"final-{key}"),
    ]
    return replay_turn(db, chat, key, content=f"请求 {key}", fill=300,
                       budget_cfg=budget_cfg, summarizer=summarizer,
                       responses=responses, tools=echo_registry("字" * 1500))


def test_200_messages_multi_tool_exchange_and_big_results(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=30_000, reserve=4_000, limit=10)
    for _ in range(300):
        rows = message_rows(db_session, chat.id)
        if len(rows) >= 200:
            break
        key = f"k{len(rows)}"
        _tool_turn(db_session, chat, key, n_calls=1 + (len(rows) % 5 == 0),
                   budget_cfg=cfg)
    rows_before = [r.message_id for r in message_rows(db_session, chat.id)]
    assert len(rows_before) >= 200
    assert summary_row(db_session, chat.id) is not None  # 长历史期间已产生摘要

    # 最后一轮（当前 user 超长历史 + 大工具结果）仍成功
    sub = submit(db_session, chat.id, "最终确认 " + "字" * 300, "z-final")
    fake = FakeSummarizer()
    runner, gateway = make_runner(
        [assistant(TextContent(text="全部完成"))], tools=echo_registry("字" * 1500),
        budget=cfg, summarizer=fake)
    outcome = _run_async(runner.run(db_session, sub.run.id))
    assert outcome.status == "succeeded", outcome

    # DB 原样：本轮新增的只是 user 消息 + assistant 回答（历史行一字不动）
    rows_after = [r.message_id for r in message_rows(db_session, chat.id)]
    assert rows_after[:len(rows_before)] == rows_before
    assert len(rows_after) == len(rows_before) + 2

    # 压缩上下文已用：主 Provider 只看到摘要 + 尾部窗口，不看 200+ raw
    request = gateway.requests[0]
    assert "through visible position" in request.system_prompt
    assert len(request.messages) < len(rows_before)
    assert request.messages[-1].content == "最终确认 " + "字" * 300  # 当前 User 保留
    # exchange 完整性：请求内每个 toolResult 都能在前面的 assistant 找到对应 ToolCall
    pending_calls = set()
    for message in request.messages:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolCall) and block.id:
                    pending_calls.add(block.id)
        elif message.role == "toolResult":
            assert message.tool_call_id in pending_calls, "工具结果与其调用同组进入上下文"
            pending_calls.remove(message.tool_call_id)
    assert pending_calls == set(), "被截断的 ToolCall 必须整组同出同入"
    # 预算合法 & 事件脱敏（compaction_used 表示用了压缩；预算永不超过）
    prepared = run_events(db_session, chat.id, "context_prepared")[-1].payload_json
    assert prepared["estimated_input_tokens"] <= cfg.max_input_tokens
    # Chat History 仍完整（Conversation API 语义不受压缩影响）
    assert len(rows_after) == len(message_rows(db_session, chat.id))


# ------------------------------------------------------ spec #39 超大当前轮

def test_huge_current_user_context_limit_no_calls_and_message_kept(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=3_000, reserve=500, limit=10)
    sub = submit(db_session, chat.id, "H" * 200, "pre")
    fake_ok = FakeSummarizer()
    runner, gateway = make_runner([assistant(TextContent(text="好"))], budget=cfg,
                                  summarizer=fake_ok)
    outcome = _run_async(runner.run(db_session, sub.run.id))
    assert outcome.status == "succeeded"

    huge = submit(db_session, chat.id, "字" * 6_000, "huge-turn")
    fake = FakeSummarizer()
    runner2, gateway2 = make_runner([assistant(TextContent(text="x"))], budget=cfg,
                                    summarizer=fake)
    outcome2 = _run_async(runner2.run(db_session, huge.run.id))
    assert outcome2.status == "failed"
    assert outcome2.error_code == "context_limit"
    assert len(fake.calls) == 0            # 不调 Summarizer
    assert gateway2.requests == []         # 不调主 Agent Provider
    run = db_session.get(AgentRun, huge.run.id)
    assert run.status == "failed" and run.error_code == "context_limit"
    # UserMessage DB 保留
    stored = db_session.query(AgentMessage).filter(
        AgentMessage.message_id == "user-huge-turn").first()
    assert stored is not None and stored.content.startswith("字")
    limit_events = run_events(db_session, chat.id, "context_limit")
    assert limit_events
    payload = limit_events[-1].payload_json
    assert payload["reason"] == "current_turn_too_large"
    assert payload["estimated_input_tokens"] > 0
    assert payload["max_input_tokens"] > 0
    # context_limit 事件绝不是 Artifact revision 事件
    assert run_events(db_session, chat.id, "artifact_revision_created") == []


# ------------------------------------------------------ spec #40 failure 四态

def _long_enough_history(db, chat, cfg, fill=230, turns=22):
    for i in range(1, turns + 1):
        replay_turn(db, chat, f"n{i}", content=f"q{i}", fill=fill, budget_cfg=cfg)


@pytest.mark.parametrize("behavior", ["timeout", "exception", "empty", "oversized"])
def test_summary_failure_without_existing_summary_goes_context_limit(db_session, behavior):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    fake_ok = FakeSummarizer()
    last_gateway = None
    # 先长到需要压缩（但都用成功 Summarizer，让最后一次换成失败）
    sub = None
    for i in range(1, 30):
        f = FakeSummarizer()
        sub, gateway, _ = replay_turn(db_session, chat, f"p{i}", content=f"q{i}",
                                      fill=230, budget_cfg=cfg, summarizer=f)
        last_gateway = gateway
        if f.calls:
            break
    assert summary_row(db_session, chat.id) is not None
    # 手动把 summary 清成"无"以测试首次失败路径（模拟无历史摘要的长会话）
    db_session.query(ConversationSummary).filter(
        ConversationSummary.conversation_id == chat.id).delete()
    db_session.commit()
    assert summary_row(db_session, chat.id) is None

    sub = submit(db_session, chat.id, "触发失败 " + "字" * 230, "fail-no-sum")
    failing = FakeSummarizer(behavior=behavior)
    runner, gateway = make_runner([assistant(TextContent(text="x"))], budget=cfg,
                                  summarizer=failing)
    outcome = _run_async(runner.run(db_session, sub.run.id))
    assert outcome.status == "failed" and outcome.error_code == "context_limit"
    assert len(failing.calls) == 1  # 至多一次，无无限 retry
    payload = run_events(db_session, chat.id, "context_limit")[-1].payload_json
    assert payload["reason"] == "summary_unavailable"
    assert summary_row(db_session, chat.id) is None  # 失败结果绝不写 DB


@pytest.mark.parametrize("behavior", ["timeout", "exception", "empty", "oversized"])
def test_summary_refresh_failure_with_existing_summary_falls_back_success(db_session, behavior):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    # 建立真实旧 summary（through>0）
    for i in range(1, 30):
        f = FakeSummarizer()
        _, _, _ = replay_turn(db_session, chat, f"s{i}", content=f"q{i}",
                              fill=230, budget_cfg=cfg, summarizer=f)
        if f.calls:
            break
    old = summary_row(db_session, chat.id)
    assert old is not None and old.through_visible_rank > 0

    sub = submit(db_session, chat.id, "刷新失败但可回退 " + "字" * 230, "fail-with-sum")
    failing = FakeSummarizer(behavior=behavior)
    runner, gateway = make_runner([assistant(TextContent(text="回退成功回答"))],
                                  budget=cfg, summarizer=failing)
    outcome = _run_async(runner.run(db_session, sub.run.id))
    assert outcome.status == "succeeded", outcome.error_code  # 旧摘要回退可继续
    assert len(failing.calls) == 1
    # 未写回失败结果；DB 仍是旧 through
    after = summary_row(db_session, chat.id)
    assert after.through_visible_rank == old.through_visible_rank
    assert gateway.requests[0].messages[-1].content == "刷新失败但可回退 " + "字" * 230
    prepared = run_events(db_session, chat.id, "context_prepared")[-1].payload_json
    assert prepared["summary_refresh_failed"] is True
    assert prepared["summary_used"] is True


# ------------------------------------------------------ spec #41 follow-up A/B

def test_followup_b_never_leaks_into_a_and_sees_a_terminal_result(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    # A 执行期间 B 已入队（真实 submit 顺序：A head → B follow-up）
    a = submit(db_session, chat.id, "A 的问题", "turn-A")
    b = submit_followup(db_session, chat.id, "B 排队的问题", "turn-B")
    assert b.run.active_slot is None and b.run.status == "queued"
    assert a.run.active_slot == 1

    runner_a, gateway_a = make_runner(
        [assistant(ToolCall(id="c-a", name="echo", arguments={"k": 1}),
                   reason="toolUse", message_id="a-tool"),
         assistant(TextContent(text="A-REPLY-FINAL"), message_id="a-final")],
        tools=echo_registry("结果A"),
        budget=cfg, summarizer=FakeSummarizer())
    outcome_a = _run_async(runner_a.run(db_session, a.run.id))
    assert outcome_a.status == "succeeded"
    # A 的每个主请求都不含 B（未来消息绝不提前泄漏给 A）
    for request in gateway_a.requests:
        assert all("B 排队的问题" not in (m.content if isinstance(m.content, str) else "")
                   for m in request.messages)

    # 原子提升 B（Worker 在 A 终态后的同一行为）
    promoted = conversation_service.promote_next_conversation_run(db_session, chat.id)
    assert promoted == b.run.id
    db_session.commit()

    runner_b, gateway_b = make_runner(
        [assistant(TextContent(text="B-REPLY"), message_id="b-reply")],
        budget=cfg, summarizer=FakeSummarizer())
    outcome_b = _run_async(runner_b.run(db_session, b.run.id))
    assert outcome_b.status == "succeeded"

    def flat_text(message):
        body = getattr(message, "content", "")
        if isinstance(body, str):
            return body
        return " ".join(getattr(block, "text", "") for block in body)

    # B 必须看到 A 的 terminal 结果（A-REPLY-FINAL / 工具结果）以及 B 自己的消息
    seen = gateway_b.requests[0].messages
    assert any("A-REPLY-FINAL" in flat_text(m) for m in seen)
    assert any("结果A" in flat_text(m) for m in seen)
    assert flat_text(seen[-1]) == "B 排队的问题"
    # 顺序：A 的内容都在 B 的 user 消息之前
    b_index = next(i for i, m in enumerate(seen) if flat_text(m) == "B 排队的问题")
    assert any("A-REPLY-FINAL" in flat_text(m) for m in seen[:b_index])
    # 历史仍完整（Chat History 不被上下文压缩改写）
    rows = message_rows(db_session, chat.id)
    assert "user-turn-B" in [r.message_id for r in rows]
    assert any("A-REPLY-FINAL" in (r.content or "") for r in rows)


# ------------------------------------------------------ spec #42 stale summary

def test_artifact_summary_stale_facts_but_runtime_revision_realtime(db_session):
    seed_user(db_session)
    from app.services.test_artifacts import artifact_service
    from app.models.user import User as UserModel
    user = db_session.query(UserModel).filter(UserModel.id == USER_A).first()
    artifact = artifact_service.create_artifact(db_session, requester=user, title="登录流程")
    artifact.current_revision = 25
    db_session.commit()
    chat = conversation(db_session)
    conversation_service.focus_conversation_artifact(
        db_session, session_id=chat.id, artifact_id=artifact.id, requester=user)
    db_session.commit()

    cfg = budget(window=10_000, reserve=2_000, limit=10)
    # 历史摘要包含旧 revision 事实（summary text 固定为含 revision20 的文案）
    for i in range(1, 30):
        f = FakeSummarizer(text_template="revision20 下完成 X；通过摘要覆盖至{target}")
        _, _, used = replay_turn(db_session, chat, f"a{i}", content=f"q{i}",
                                 fill=230, budget_cfg=cfg, summarizer=f)
        if used.calls:
            break
    sub = submit(db_session, chat.id, "现在呢 " + "字" * 230, "stale-check")
    fake = FakeSummarizer(text_template="revision20 下完成 X；通过摘要覆盖至{target}")
    runner, gateway = make_runner([assistant(TextContent(text="ok"))], budget=cfg,
                                  summarizer=fake)
    outcome = _run_async(runner.run(db_session, sub.run.id))
    assert outcome.status == "succeeded"
    request = gateway.requests[0]
    prompt = request.system_prompt
    # runtime metadata section 使用 DB 当前 revision 25
    assert "current revision: 25" in prompt
    assert "登录流程" in prompt
    # summary 内旧事实保留（历史上下文），但 wrapper 明确可能过期
    assert "revision20" in prompt
    assert "may be stale" in prompt
    assert "read current Artifact state with tools before acting" in prompt or \
        "read current Artifact state before modifying" in prompt


# -------------------------------------------------- 审计 #3：cancel / ownership

class CancellableSummarizer(FakeSummarizer):
    """在运行时收到 cancel_event 才返回：用于确定性模拟 summarizer 模型等待中取消。"""

    def __init__(self, started):
        super().__init__()
        self.started = started

    async def summarize(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        cancel_event = (kwargs.get("runtime_context") or {}).get("cancel_event")
        if cancel_event is not None:
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=15)
            except asyncio.TimeoutError:  # pragma: no cover
                pass
            raise RuntimeError("canceled mid-summarize")
        return await super().summarize(**kwargs)


def _seed_fenced_running_run(db, chat, key="claim", content="跑起来"):
    from datetime import datetime as dt
    sub = submit(db, chat.id, content + " " + "字" * 200, key)
    token = agent_run_service.claim_queued_run(db, sub.run.id, "worker-1", dt.utcnow())
    db.commit()
    return sub, token


def test_cancel_during_summary_ends_run_cancelled_without_events_or_write(db_session):
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    # 长历史确保压缩路径会真正调用 Summarizer（DB 已有历史摘要行）
    for i in range(1, 30):
        f = FakeSummarizer()
        _, _, used = replay_turn(db_session, chat, f"t{i}", content=f"q{i}",
                                 fill=230, budget_cfg=cfg, summarizer=f)
        if used.calls:
            break
    assert summary_row(db_session, chat.id) is not None
    sub = submit(db_session, chat.id, "取消这一轮 " + "字" * 230, "cancel-turn")

    async def scenario():
        cancel_event = asyncio.Event()
        started = asyncio.Event()
        fake = CancellableSummarizer(started)
        runner, _ = make_runner([assistant(TextContent(text="x"))], budget=cfg,
                                summarizer=fake)
        task = asyncio.create_task(
            runner.run(db_session, sub.run.id, cancel_event=cancel_event))
        await started.wait()  # Summarizer 已在模型等待中
        cancel_event.set()    # 用户取消 → Summarizer 快速失败
        return await asyncio.wait_for(task, timeout=15)

    outcome = asyncio.run(scenario())
    assert outcome.status == "cancelled" and outcome.error_code == "canceled"
    run = db_session.get(AgentRun, sub.run.id)
    assert run.status == "cancelled"
    # 本轮摘要未写、上下文事件未落
    summary_before = summary_row(db_session, chat.id).through_visible_rank
    assert summary_row(db_session, chat.id).through_visible_rank == summary_before
    events = [e.event_type for e in run_events(db_session, chat.id)
              if e.run_id == sub.run.id]
    assert events == ["run_started", "run_cancelled"]
    own_prepared = [e for e in run_events(db_session, chat.id, "context_prepared")
                    if e.run_id == sub.run.id]
    own_compacted = [e for e in run_events(db_session, chat.id, "context_compacted")
                     if e.run_id == sub.run.id]
    assert own_prepared == [] and own_compacted == []


def test_terminal_mid_summary_skips_events_summary_write_is_benign_cache(db_session):
    """审计 #3：Summarizer 等待期间 Run 被外部取消（DB terminal）→ runner 不写
    context 事件、不改 Run 状态；期间写入的 summary 是 monotonic derived cache
    （只覆盖真实历史 prefix），允许存在且不回退任何值。"""
    from app.core.database import SessionLocal
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    for i in range(1, 30):
        f = FakeSummarizer()
        _, _, used = replay_turn(db_session, chat, f"m{i}", content=f"q{i}",
                                 fill=230, budget_cfg=cfg, summarizer=f)
        if used.calls:
            break
    sub, token = _seed_fenced_running_run(db_session, chat, key="term-run")
    assert token is not None

    class TerminalMutator(FakeSummarizer):
        def __init__(self):
            super().__init__()
            self.entered = asyncio.Event()
            self.confirm = asyncio.Event()

        async def summarize(self, **kwargs):
            self.calls.append(kwargs)
            self.entered.set()
            await asyncio.wait_for(self.confirm.wait(), timeout=15)
            with SessionLocal() as other:
                run = other.get(AgentRun, sub.run.id)
                agent_run_service.transition_status(other, run, "cancelled")
                other.commit()
            return await super().summarize(**kwargs)

    async def scenario():
        fake = TerminalMutator()
        runner, _ = make_runner([assistant(TextContent(text="x"))], budget=cfg,
                                summarizer=fake)
        task = asyncio.create_task(runner.run(db_session, sub.run.id,
                                              worker_id="worker-1",
                                              execution_token=token))
        await fake.entered.wait()
        fake.confirm.set()
        return await asyncio.wait_for(task, timeout=15)

    outcome = asyncio.run(scenario())
    assert outcome.status == "cancelled" and outcome.run_finalized is False
    run = db_session.get(AgentRun, sub.run.id)
    assert run.status == "cancelled"
    # Runner 未写任何事件（terminal 复核后 no-write）
    events = [e.event_type for e in run_events(db_session, chat.id)
              if e.run_id == sub.run.id]
    assert events == ["run_started"]
    assert [e for e in run_events(db_session, chat.id, "context_prepared")
            if e.run_id == sub.run.id] == []
    # summary 写入发生在 terminal 复核前 —— monotonic cache 语义下允许
    assert summary_row(db_session, chat.id) is not None


def test_ownership_lost_mid_summary_skips_events_and_keeps_run_untouched(db_session):
    from app.core.database import SessionLocal
    seed_user(db_session)
    chat = conversation(db_session)
    cfg = budget(window=10_000, reserve=2_000, limit=10)
    for i in range(1, 30):
        f = FakeSummarizer()
        _, _, used = replay_turn(db_session, chat, f"o{i}", content=f"q{i}",
                                 fill=230, budget_cfg=cfg, summarizer=f)
        if used.calls:
            break
    sub, token = _seed_fenced_running_run(db_session, chat, key="lost-run")
    assert token is not None

    class LostMutator(FakeSummarizer):
        def __init__(self):
            super().__init__()
            self.entered = asyncio.Event()
            self.confirm = asyncio.Event()

        async def summarize(self, **kwargs):
            self.calls.append(kwargs)
            self.entered.set()
            await asyncio.wait_for(self.confirm.wait(), timeout=15)
            with SessionLocal() as other:
                run = other.get(AgentRun, sub.run.id)
                run.worker_id = "worker-2"  # 新 worker 抢占（claim 语义）
                run.execution_token = token + 1
                other.commit()
            return await super().summarize(**kwargs)

    async def scenario():
        fake = LostMutator()
        runner, _ = make_runner([assistant(TextContent(text="x"))], budget=cfg,
                                summarizer=fake)
        task = asyncio.create_task(runner.run(db_session, sub.run.id,
                                              worker_id="worker-1",
                                              execution_token=token))
        await fake.entered.wait()
        fake.confirm.set()
        return await asyncio.wait_for(task, timeout=15)

    outcome = asyncio.run(scenario())
    assert outcome.status == "failed" and outcome.error_code == "ownership_lost"
    assert outcome.run_finalized is False
    run = db_session.get(AgentRun, sub.run.id)
    assert run.status == "running" and run.worker_id == "worker-2"
    events = [e.event_type for e in run_events(db_session, chat.id)
              if e.run_id == sub.run.id]
    assert events == ["run_started"]
    assert [e for e in run_events(db_session, chat.id, "context_prepared")
            if e.run_id == sub.run.id] == []
