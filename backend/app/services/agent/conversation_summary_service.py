"""P10.1 Conversation Summary：持久化/单调更新/增量选择（薄层，不跨 LLM 持事务）。

事务边界由调用方保证：读阶段结束事务后再调 Summarizer；写阶段开启短事务
调用 create / conditional_update 并 commit。
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.conversation.context_builder import _split_into_exchange_units
from app.models.agent.conversation_summary import ConversationSummary


def get_latest_summary(db: Session, conversation_id: int) -> ConversationSummary | None:
    return db.execute(select(ConversationSummary).where(
        ConversationSummary.conversation_id == conversation_id)
    ).scalars().first()


def create_summary(db: Session, *, conversation_id: int, through_sequence_no: int,
                   summary_text: str, source_message_count: int,
                   provider: str | None = None, model: str | None = None,
                   schema_version: int = 1) -> ConversationSummary:
    """首次创建；并发唯一冲突时回滚并安全重读（不产生两行 current）。"""
    if through_sequence_no < 0:
        raise ValueError("through_sequence_no 必须 >= 0")
    row = ConversationSummary(
        conversation_id=conversation_id,
        through_sequence_no=through_sequence_no,
        summary_text=summary_text,
        source_message_count=source_message_count,
        schema_version=schema_version,
        provider=provider,
        model=model,
    )
    # P10.1-B3：唯一冲突用 SAVEPOINT 隔离，绝不 rollback 调用方外层事务
    # （外层可能同时写入 UserMessage/AgentRun/AgentEvent/Artifact）。
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        # 内层 SAVEPOINT 已回滚；冲突意味着 current summary 已存在
        latest = get_latest_summary(db, conversation_id)
        if latest is None:
            raise
        return latest


def conditional_update_summary(
    db: Session, *, conversation_id: int,
    expected_through_sequence: int, new_through_sequence: int,
    summary_text: str, source_message_count: int,
    provider: str | None = None, model: str | None = None,
    schema_version: int = 1,
) -> bool:
    """单调向前：仅当 DB 行仍是 expected_old 且 :new > 当前 through 才更新。

    返回 False 表示被更晚 Summary 抢先，调用方丢弃旧结果并重读。
    """
    if new_through_sequence < 0 or new_through_sequence <= expected_through_sequence:
        return False
    result = db.execute(
        update(ConversationSummary)
        .where(
            ConversationSummary.conversation_id == conversation_id,
            ConversationSummary.through_sequence_no == expected_through_sequence,
            ConversationSummary.through_sequence_no < new_through_sequence,
        )
        .values(
            through_sequence_no=new_through_sequence,
            summary_text=summary_text,
            source_message_count=source_message_count,
            schema_version=schema_version,
            provider=provider,
            model=model,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def select_incremental_inputs(
    seq_messages: list[tuple[int, Any]],
    *,
    existing_through_sequence: int,
    recent_message_limit: int,
) -> tuple[int, list[Any], list[Any]]:
    """增量压缩：只处理 existing_through 之后的消息；cut 落在完整 exchange 组边界。

    从尾部保留 recent_message_limit 条消息（不足整组时整组多留，绝不切散工具对）；
    其余完整组进入 summary。返回 (cut_sequence, for_summarizer_messages, kept_recent_messages)。
    """
    if recent_message_limit < 1:
        recent_message_limit = 1
    after = [(seq, message) for seq, message in seq_messages
             if seq > existing_through_sequence]
    if not after:
        return existing_through_sequence, [], []
    messages = [message for _, message in after]
    units, _malformed = _split_into_exchange_units(messages)
    if not units:
        return existing_through_sequence, [], []

    kept_units: list[list[Any]] = []
    kept_count = 0
    for unit in reversed(units):
        kept_units.append(unit)
        kept_count += len(unit)
        if kept_count >= recent_message_limit:
            break
    keep_ids = {id(msg) for unit in kept_units for msg in unit}

    index = 0
    cut_sequence = existing_through_sequence
    for unit in units:
        if any(id(msg) in keep_ids for msg in unit):
            break
        index += len(unit)
        if unit:
            cut_sequence = after[index - 1][0]
    for_summary = [message for _, message in after[:index]]
    kept_msgs = [message for _, message in after[index:]]
    return cut_sequence, for_summary, kept_msgs


@dataclass
class SummaryResult:
    summary_text: str
    through_sequence_no: int
    source_message_count: int
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    estimated_tokens: int | None = None


def validate_summary_result(result: SummaryResult | None, *, summary_token_budget: int) -> bool:
    """空/纯空白/超预算 → False（视为 summary failure，不写 DB）。"""
    if result is None or not result.summary_text or not result.summary_text.strip():
        return False
    if result.estimated_tokens is not None and result.estimated_tokens > summary_token_budget:
        return False
    return True
