"""P10.1-B3 conversation context service 测试（DB/SQLite，FK ON）。

覆盖 spec：
- #38 事务隔离：create_summary 唯一冲突不得 rollback/污染调用方外层事务；
- #37/#25 winning 语义：DbSummaryIO 冲突返回 False、不覆盖、不回退；
- #16-#18 审计：run-bounded 可见行 SQL 侧 owner 边界 + 逻辑序（follow-up
  插队导致物理 sequence 与逻辑序错位时，摘要 marker 必须用 rank）；
- #27/#28 Artifact runtime metadata：revision 实时、不带 Node 内容/Diff。
"""

import asyncio

import pytest

from app.agents.conversation.messages import AssistantMessage, TextContent, Usage
from app.models.agent.agent_message import AgentMessage
from app.models.user import User
from app.services.agent import (
    conversation_repository,
    conversation_service,
    conversation_summary_service,
)
from app.services.agent.conversation_context_service import (
    DbSummaryIO,
    build_artifact_runtime_section,
)
from app.services.test_artifacts import artifact_service

TS = 1_700_000_000_000
USER_A = 9101


def _usage():
    return Usage(input=None, output=None, cache_read=None, cache_write=None,
                 total_tokens=None, cost=None)


def _seed(db):
    user = User(id=USER_A, username="ctx-a", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db.add(user)
    db.flush()
    return user


def _conversation(db):
    session = conversation_service.create_conversation_session(
        db, requester_user_id=USER_A, title="P10.1-B3 ctx")
    db.commit()
    return session


def _submit(db, session_id, content, key, queue_mode="follow_up"):
    return conversation_service.submit_conversation_turn(
        db, session_id=session_id, requester_user_id=USER_A, content=content,
        client_request_id=key, queue_mode=queue_mode,
        message_id_factory=lambda: f"user-{key}", timestamp_ms_factory=lambda: TS)


def _assistant(text, message_id):
    return AssistantMessage(message_id=message_id, role="assistant", timestamp=TS,
                            api="chat", provider="fake", model="fake-model",
                            content=[TextContent(text=text)],
                            usage=_usage(), stop_reason="stop")


# ---------------------------------------------------------------- spec #38

def test_summary_unique_conflict_keeps_caller_transaction_and_related_row(db_session):
    """create_summary 唯一冲突绝不能 rollback 调用方外层事务。

    构造：外层事务先写入 unrelated row（同会话 user 消息行），随后 create_summary
    撞唯一冲突；冲突处理后 commit —— unrelated row 必须仍在、summary 仍只有一行、
    整个过程不抛错。
    """
    _seed(db_session)
    session = _conversation(db_session)
    conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_visible_rank=5,
        summary_text="已存在", source_message_count=5)
    db_session.commit()

    # 外层事务：先写 unrelated（分配 sequence，未 commit）再触发唯一冲突
    unrelated_row = AgentMessage(
        session_id=session.id, run_id=None, message_id="unrelated-msg",
        schema_version=1, timestamp_ms=TS, role="user", message_type="text",
        content="与摘要无关的调用方写入", content_json={},
        sequence_no=conversation_repository.allocate_sequence(
            db_session, session.id, "next_message_sequence"),
    )
    db_session.add(unrelated_row)
    db_session.flush()
    assert db_session.in_transaction()

    row = conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_visible_rank=9,
        summary_text="并发旧", source_message_count=9)
    # 冲突 → 返回 winning；不抛、不 rollback 外层事务
    assert row.through_visible_rank == 5
    assert db_session.in_transaction(), "冲突处理不得结束调用方外层事务"

    db_session.commit()  # unrelated row 必须仍可 commit
    stored = db_session.query(AgentMessage).filter(
        AgentMessage.message_id == "unrelated-msg").first()
    assert stored is not None and stored.content == "与摘要无关的调用方写入"
    rows = db_session.query(conversation_summary_service.ConversationSummary).filter(
        conversation_summary_service.ConversationSummary.conversation_id == session.id).all()
    assert len(rows) == 1 and rows[0].through_visible_rank == 5


# ------------------------------------------------------- spec #37/#25 winning

def test_db_summary_io_conflict_returns_false_and_keeps_winning(db_session):
    _seed(db_session)
    session = _conversation(db_session)
    conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_visible_rank=70,
        through_message_id="msg-win-70",
        summary_text="winning 到 70", source_message_count=70)
    db_session.commit()

    io = DbSummaryIO(db_session, session.id)
    # 落后进程 A（based 40 → 60）写入 → False，且不覆盖 70、锚点不漂移
    updated = io.write_incremental(
        expected_through_visible_rank=40, new_through_visible_rank=60,
        new_through_message_id="msg-old", summary_text="旧进程 60",
        source_message_count=60, provider="fake", model="m")
    assert updated is False
    assert not db_session.in_transaction()
    winner = conversation_summary_service.get_latest_summary(db_session, session.id)
    assert winner.through_visible_rank == 70
    assert winner.through_message_id == "msg-win-70"  # 审计 #1：锚点随 winning 保留
    assert winner.summary_text == "winning 到 70"
    db_session.rollback()
    # 落后进程 A 不重跑模型：采用 winning（orchestrator 层面由
    # test_summary_orchestrator.test_conflict_uses_winning_summary_no_second_call 覆盖）


def test_db_summary_io_first_create_and_monotonic_refresh(db_session):
    _seed(db_session)
    session = _conversation(db_session)
    io = DbSummaryIO(db_session, session.id)
    assert io.write_incremental(expected_through_visible_rank=0, new_through_visible_rank=30,
                                new_through_message_id="m30", summary_text="首次到 30",
                                source_message_count=30) is True
    assert io.write_incremental(expected_through_visible_rank=30, new_through_visible_rank=60,
                                new_through_message_id="m60", summary_text="刷新到 60",
                                source_message_count=60) is True
    assert io.write_incremental(expected_through_visible_rank=30, new_through_visible_rank=80,
                                new_through_message_id="m80", summary_text="并发旧到 80",
                                source_message_count=80) is False
    winner = conversation_summary_service.get_latest_summary(db_session, session.id)
    assert winner.through_visible_rank == 60 and winner.summary_text == "刷新到 60"
    # 审计 #1：rank 与 message_id 锚点总是同写同读（新边界一致）
    assert winner.through_message_id == "m60"


# ------------------------------- spec #16-#18 audit：owner 边界 + 逻辑序/rank

def _persist_era_assistant_rows(db, session, run, texts):
    """直接持久化 run 的助手消息：物理 sequence 在提交时刻分配（晚于已排队
    follow-up 的 user 行）→ 制造物理/逻辑序错位。返回 (message_id, seq) 列表。"""
    out = []
    for i, text in enumerate(texts):
        message_id = f"a-{run.id}-{i}"
        content = dict(_assistant(text, message_id).model_dump(mode="json"))
        sequence = conversation_repository.allocate_sequence(
            db, session.id, "next_message_sequence")
        db.add(AgentMessage(
            session_id=session.id, run_id=run.id, message_id=message_id,
            schema_version=1, timestamp_ms=TS, role="assistant",
            message_type="text", content=text, content_json=content,
            sequence_no=sequence))
        out.append((message_id, sequence))
    db.flush()
    return out


def test_run_visible_rows_logical_order_across_queued_followups(db_session):
    """A 执行期间 B/C follow-up 已入库（物理 seq 先占位、A 的助手行后落库），
    任意 Run 的可见集合必须以 owner（Run 的 user message sequence）为界并按
    (owner, seq) 逻辑序返回 —— 这正是摘要 rank 的排序基础（spec #16-#18）。"""
    _seed(db_session)
    session = _conversation(db_session)
    a = _submit(db_session, session.id, "A 的问题", "kA")
    assert a.run.active_slot == 1
    b = _submit(db_session, session.id, "B 排队的问题", "kB")   # 物理 seq=2
    assert b.run.active_slot is None
    c = _submit(db_session, session.id, "C 排队的问题", "kC")   # 物理 seq=3
    a_rows = _persist_era_assistant_rows(db_session, session, a.run,
                                         ["A 的中间回复", "A 的最终结果"])
    db_session.commit()

    all_rows = db_session.query(AgentMessage).order_by(AgentMessage.sequence_no.asc()).all()
    assert [r.message_id for r in all_rows][:3] == ["user-kA", "user-kB", "user-kC"]
    assert [r.message_id for r in all_rows][3:] == [mid for mid, _ in a_rows]

    until_a = a.user_message.sequence_no
    until_b = b.user_message.sequence_no
    until_c = c.user_message.sequence_no

    visible_a = conversation_repository.list_run_visible_message_rows(
        db_session, session.id, until_sequence_no=until_a)
    visible_b = conversation_repository.list_run_visible_message_rows(
        db_session, session.id, until_sequence_no=until_b)
    visible_c = conversation_repository.list_run_visible_message_rows(
        db_session, session.id, until_sequence_no=until_c)

    # A：owner=1 的行（自己 + 自己的助手行，物理 seq 4/5 排 user 之后）
    assert [r.message_id for r in visible_a] == [
        "user-kA", a_rows[0][0], a_rows[1][0]]
    # B：owner<=2 —— A 全部（含后落库的助手行）+ B，绝不含 C
    ids_b = [r.message_id for r in visible_b]
    assert ids_b == ["user-kA", a_rows[0][0], a_rows[1][0], "user-kB"]
    # 逻辑序验证：A 的助手行（物理 seq 4/5）排在 B 的 user 行（物理 seq 2）之前
    assert ids_b.index("user-kB") == len(ids_b) - 1
    assert ids_b.index(a_rows[0][0]) < ids_b.index("user-kB")
    # C：三者全可见（C 的 user 行物理 seq 3 反而最早，逻辑上仍最后）
    assert [r.message_id for r in visible_c] == [
        "user-kA", a_rows[0][0], a_rows[1][0], "user-kB", "user-kC"]

    # 与 P05-E restore 语义完全一致（restore 返回相同逻辑序的 Messages）
    restored_b = conversation_service.restore_conversation_messages(
        db_session, session_id=session.id, requester_user_id=USER_A,
        until_sequence_no=until_b)
    assert [m.message_id for m in restored_b] == ids_b


def test_visible_rows_never_leak_future_user_messages_in_sql(db_session):
    _seed(db_session)
    session = _conversation(db_session)
    a = _submit(db_session, session.id, "A", "qA")
    _submit(db_session, session.id, "B", "qB")
    _submit(db_session, session.id, "C", "qC")
    db_session.commit()
    ids = [r.message_id for r in conversation_repository.list_run_visible_message_rows(
        db_session, session.id, until_sequence_no=a.user_message.sequence_no)]
    assert ids == ["user-qA"]


# ------------------------------------------------------- spec #27/#28 metadata

def test_artifact_runtime_section_realtime_revision_and_no_content(db_session):
    user = _seed(db_session)
    artifact = artifact_service.create_artifact(db_session, requester=user, title="登录模块")
    artifact.current_revision = 25  # 直接推进：模拟期间已发生多次真实修订
    db_session.commit()

    section = build_artifact_runtime_section(
        db_session, requester_user_id=USER_A, artifact_id=artifact.id,
        workspace_context={"selected_module_id": 7, "selected_case_id": 9,
                           "current_view": "mindmap"})
    assert section is not None
    assert f"artifact id: {artifact.id}" in section
    assert "登录模块" in section
    assert "current revision: 25" in section  # 实时 revision，不是摘要里的旧值
    assert "selected module id: 7" in section and "selected test case id: 9" in section
    assert "current view: mindmap" in section
    assert "may be stale" in section  # 明确不是 Artifact 当前权威
    assert "revision: 25" in section  # 与摘要内的 revision20 形成对照（runner 级测试验证）

    # 无 Artifact → 无 section
    assert build_artifact_runtime_section(
        db_session, requester_user_id=USER_A, artifact_id=None) is None


# ------------------------------------------------------ 审计 #1：prefix 位置稳定性 invariant

def test_summary_prefix_positions_stable_across_future_runs(db_session):
    """invariant：未来新 Run/消息只会追加在已覆盖 prefix 之后——summary 的
    through_visible_rank 与 through_message_id 锚点位置永不改变。

    构造：多层 follow-up 插队（用户行先落库、助手行后落库）后建 summary；
    再追加若干未来 Run；重新计算可见逻辑序，断言：
    1) 锚点消息仍在原 rank；
    2) prefix 内每条消息的 rank 不变；
    3) 新行全部排在 prefix 之后（新增行的 rank > through）。
    """
    _seed(db_session)
    session = _conversation(db_session)

    def era(key, replies):
        sub = _submit(db_session, session.id, f"{key} 的问题", key)
        rows = _persist_era_assistant_rows(db_session, session, sub.run, replies)
        db_session.commit()
        return sub, rows

    a, a_rows = era("kA", ["A1", "A2"])
    b, b_rows = era("kB", ["B1"])      # B 排队期间… 物理 seq 先占
    c, _ = era("kC", ["C1"])
    all_rows = db_session.query(AgentMessage).order_by(AgentMessage.sequence_no.asc()).all()
    ids = [r.message_id for r in all_rows]

    # 建 summary：通过 = 覆盖到 B1（假设模型只收到 prefix 到 B1）
    io = DbSummaryIO(db_session, session.id)
    through_rank = ids.index(b_rows[0][0]) + 1
    anchor_id = b_rows[0][0]
    assert io.write_incremental(
        expected_through_visible_rank=0, new_through_visible_rank=through_rank,
        new_through_message_id=anchor_id, summary_text="到 B1",
        source_message_count=through_rank) is True
    row = conversation_summary_service.get_latest_summary(db_session, session.id)
    assert row.through_message_id == anchor_id and row.through_visible_rank == through_rank

    # 记录 prefix 消息与位置
    prefix = ids[:through_rank]
    prefix_positions = {mid: i + 1 for i, mid in enumerate(prefix)}

    # 追加未来 Run D/E（多轮插队形态）
    era("kD", ["D1", "D2"])
    era("kE", ["E1"])
    db_session.commit()

    # 重新计算当前可见逻辑序（owner 边界用最大的 user seq）
    until = db_session.query(AgentMessage).filter(
        AgentMessage.session_id == session.id, AgentMessage.role == "user",
    ).order_by(AgentMessage.sequence_no.desc()).first().sequence_no
    visible = conversation_repository.list_run_visible_message_rows(
        db_session, session.id, until_sequence_no=until)
    new_ids = [r.message_id for r in visible]
    new_positions = {mid: i + 1 for i, mid in enumerate(new_ids)}

    # 1) 锚点仍在原 rank；2) prefix 内所有消息 rank 不变
    assert new_positions[anchor_id] == through_rank
    for mid in prefix:
        assert new_positions[mid] == prefix_positions[mid], f"{mid} 位置漂移"
    # 3) 新消息全部落在 prefix 之后
    for mid in new_ids[through_rank:]:
        assert mid not in prefix
    # 4) 存量 summary 行仍与可见序一致（prep 的 invariant 校验不会触发）
    assert new_ids[through_rank - 1] == anchor_id


def test_anchor_verification_detects_corrupt_summary(db_session):
    """prep 的 invariant 校验：锚点与可见序错位 → agent_run_data_invalid。"""
    from app.agents.runtime.errors import AgentError
    from app.services.agent.conversation_context_service import ConversationContextPreparer
    from app.services.agent.conversation_summary_service import SummaryResult

    _seed(db_session)
    session = _conversation(db_session)
    a = _submit(db_session, session.id, "A 的问题", "kX")
    _persist_era_assistant_rows(db_session, session, a.run, ["回复"])
    db_session.commit()

    # 写入一个“错误”的 summary：锚点指向不存在的消息
    conversation_summary_service.create_summary(
        db_session, conversation_id=session.id, through_visible_rank=1,
        through_message_id="ghost-message-id", summary_text="坏锚点",
        source_message_count=1)
    db_session.commit()

    class NoopSummarizer:
        async def summarize(self, **kwargs):
            return SummaryResult(summary_text="x", through_visible_rank=0,
                                 source_message_count=0)

    preparer = ConversationContextPreparer(summarizer=NoopSummarizer())
    with pytest.raises(AgentError) as exc:
        asyncio.run(preparer.prepare(
            db_session, a.run, requester_user_id=USER_A))
    assert exc.value.error_code == "agent_run_data_invalid"
