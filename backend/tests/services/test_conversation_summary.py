"""P10.1 Conversation Summary 持久化/单调/增量选择 测试（临时 SQLite，FK ON）。"""

import pytest

from app.models.agent.agent_session import AgentSession
from app.models.user import User
from app.agents.conversation.messages import (
    AssistantMessage, TextContent, ToolCall, ToolResultMessage, Usage, UserMessage,
)
from app.services.agent import conversation_service, conversation_summary_service

TS = 1_700_000_000_000


def _usage():
    return Usage(input=None, output=None, cache_read=None, cache_write=None,
                 total_tokens=None, cost=None)


def _u(id_, text):
    return UserMessage(message_id=id_, role="user", content=text, timestamp=TS)


def _a(id_, content, stop_reason="stop"):
    return AssistantMessage(message_id=id_, role="assistant", timestamp=TS, content=content,
                            api="chat", provider="fake", model="fake-model",
                            usage=_usage(), stop_reason=stop_reason)


def _r(call, id_):
    return ToolResultMessage(message_id=id_, role="toolResult", timestamp=TS,
                             tool_call_id=call.id, tool_name=call.name,
                             content=[TextContent(text="ok")], is_error=False)


def _session(db_session):
    user = User(id=1, username="summary_user", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db_session.add(user)
    db_session.flush()
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=1, title="P10.1 summary test")
    db_session.commit()
    return session


def test_create_read_conditional_update_monotonic(db_session):
    session = _session(db_session)
    row = conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_sequence_no=30,
        summary_text="到 30 的摘要", source_message_count=30, provider="fake", model="fake-model")
    db_session.commit()
    assert row.through_sequence_no == 30

    updated = conversation_summary_service.conditional_update_summary(
        db_session, conversation_id=session.id, expected_through_sequence=30,
        new_through_sequence=60, summary_text="到 60 的摘要", source_message_count=60)
    assert updated is True
    db_session.commit()
    assert conversation_summary_service.get_latest_summary(db_session, session.id).through_sequence_no == 60

    # 旧进程 (expected=40) 不能覆盖 60
    stale = conversation_summary_service.conditional_update_summary(
        db_session, conversation_id=session.id, expected_through_sequence=40,
        new_through_sequence=80, summary_text="旧结果", source_message_count=80)
    assert stale is False
    db_session.rollback()
    assert conversation_summary_service.get_latest_summary(db_session, session.id).through_sequence_no == 60


def test_first_create_concurrent_conflict_only_one_row(db_session):
    session = _session(db_session)
    conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_sequence_no=10,
        summary_text="首次", source_message_count=10)
    db_session.commit()
    # 并发第二进程相同 conversation 创建 → 唯一冲突后安全重读
    again = conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_sequence_no=11,
        summary_text="并发旧", source_message_count=11)
    db_session.commit()
    assert again.through_sequence_no == 10
    rows = db_session.query(conversation_summary_service.ConversationSummary).filter(
        conversation_summary_service.ConversationSummary.conversation_id == session.id).all()
    assert len(rows) == 1


def _exchange_pairs():
    # sequence: 1 user / 2 assistant(call) / 3 result 为一个完整组
    call = ToolCall(id="c1", name="echo", arguments={})
    return [
        (1, _u("u1", "一")),
        (2, _a("a1", [call], stop_reason="toolUse")),
        (3, _r(call, "r1")),
        (4, _u("u2", "二")),
        (5, _a("a2", [ToolCall(id="c2", name="echo", arguments={})], stop_reason="toolUse")),
        (6, _u("u3", "三")),
        (7, _a("a3", [TextContent(text="回答三")])),
    ]


def test_incremental_inputs_cut_on_exchange_boundary():
    pairs = _exchange_pairs()
    cut, for_summary, kept = conversation_summary_service.select_incremental_inputs(
        pairs, existing_through_sequence=0, recent_message_limit=4)
    # 保留尾 4 条消息（整组多留）→ summary 覆盖 [1..3]（完整 exchange：assistant+result 同组不拆）
    assert cut == 3
    assert [m.message_id for m in for_summary] == ["u1", "a1", "r1"]
    assert [m.message_id for m in kept] == ["u2", "a2", "u3", "a3"]
    # 摘要输入不含 cut 之后消息
    assert "u2" not in [m.message_id for m in for_summary]


def test_incremental_only_sends_after_existing_through():
    pairs = _exchange_pairs()
    cut, for_summary, _kept = conversation_summary_service.select_incremental_inputs(
        pairs, existing_through_sequence=3, recent_message_limit=1)
    # existing=3 → 只处理 4..；cut 落在组边界（u3/a3 组保留 → cut=6 后组 7? 见尾组）
    ids = [m.message_id for m in for_summary]
    assert "u1" not in ids and "a1" not in ids and "r1" not in ids  # 不重复发旧原始消息
    assert cut == 6
    assert [m.message_id for m in for_summary] == ['u2', 'a2', 'u3']
    assert [m.message_id for m in _kept] == ['a3']


def test_summary_validation_empty_and_oversized():
    ok = conversation_summary_service.SummaryResult(
        summary_text="正常摘要", through_sequence_no=5,
        source_message_count=5, estimated_tokens=20)
    assert conversation_summary_service.validate_summary_result(ok, summary_token_budget=100) is True
    empty = conversation_summary_service.SummaryResult(
        summary_text="   ", through_sequence_no=5, source_message_count=5, estimated_tokens=1)
    assert conversation_summary_service.validate_summary_result(empty, summary_token_budget=100) is False
    big = conversation_summary_service.SummaryResult(
        summary_text="很大", through_sequence_no=5, source_message_count=5, estimated_tokens=500)
    assert conversation_summary_service.validate_summary_result(big, summary_token_budget=100) is False
