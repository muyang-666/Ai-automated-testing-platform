"""P10.1 Conversation Summary：持久化/单调更新/增量选择（薄层，不跨 LLM 持事务）。

事务边界由调用方保证：读阶段结束事务后再调 Summarizer；写阶段开启短事务
调用 create / conditional_update 并 commit。

through_visible_rank 语义（P10.1-B3 审计后定稿）：
- 它是"覆盖到第 N 个逻辑位置"的单调上界。逻辑位置按本会话 run-bounded
  可见序（owner user sequence, sequence_no）排序——正常无 follow-up 插队的
  会话中逻辑位置 == 物理 sequence_no（连续 1..N），因此 B3 之前按物理序号
  建立的测试与数据完全兼容；
- follow-up 在活跃 Turn 执行期间排队入库时，物理 sequence_no 会与逻辑顺序
  错位（例如 B/C 的用户消息先落库、A 的助手消息后落库但逻辑上属于 A）。
  此时不能用物理 sequence_no 过滤"摘要未覆盖的新消息"——否则那些用户消息
  会因物理序号小于 marker 而被错误当作已覆盖，永久丢出后续上下文。B3 起
  增量选择一律以调用方提供的逻辑排序键（rank）为边界；cut 落在完整
  exchange 组边界；marker = 最后一条被摘要消息的逻辑位置（即累计覆盖
  source_message_count，见 source_message_count 语义注释）。
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session

from app.agents.conversation.context_builder import _split_into_exchange_units
from app.models.agent.conversation_summary import ConversationSummary


def get_latest_summary(db: Session, conversation_id: int) -> ConversationSummary | None:
    return db.execute(select(ConversationSummary).where(
        ConversationSummary.conversation_id == conversation_id)
    ).scalars().first()


def create_summary(db: Session, *, conversation_id: int, through_visible_rank: int,
                   summary_text: str, source_message_count: int,
                   through_message_id: str | None = None,
                   provider: str | None = None, model: str | None = None,
                   schema_version: int = 1) -> ConversationSummary:
    """首次创建；并发唯一冲突用 SAVEPOINT 隔离并安全重读（不产生两行 current）。

    through_message_id：边界处最后一条被摘要消息的稳定 message_id cursor（rank
    的可审计锚点；新 Run/消息只会追加在已覆盖 prefix 之后，锚点位置不变）。
    P10.1-B3 事务边界：冲突绝对不回滚调用方外层事务——外层可能同事务写入了
    UserMessage/AgentRun/AgentEvent/Artifact。SAVEPOINT 回滚后必须 expunge
    未落库的 pending 行，否则调用方稍后 commit 会重放唯一冲突并整体失败。
    """
    if through_visible_rank < 0:
        raise ValueError("through_visible_rank 必须 >= 0")
    row = ConversationSummary(
        conversation_id=conversation_id,
        through_visible_rank=through_visible_rank,
        through_message_id=through_message_id,
        summary_text=summary_text,
        source_message_count=source_message_count,
        schema_version=schema_version,
        provider=provider,
        model=model,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        # 内层 SAVEPOINT 已回滚；failed pending 行不再参与外层 commit。
        # SQLAlchemy 2.0 在 savepoint 内 flush 失败后会自动把该 pending 对象
        # 移出 Session（此时 commit 不会重放唯一冲突）；保险起见显式 expunge
        # （对象已不在 Session 时忽略）。
        try:
            db.expunge(row)
        except InvalidRequestError:
            pass  # 对象已在 flush 失败时被自动移出 Session
        # 冲突 = 别的进程已提交 current summary。用锁定读取最新已提交行：
        # MySQL REPEATABLE READ 的一致性快照可能早于对方提交，普通 SELECT
        # 会读不到胜者；FOR UPDATE 是当前读。SQLite 忽略 FOR UPDATE 语义一致。
        latest = db.execute(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .with_for_update()
        ).scalars().first()
        if latest is None:
            raise
        return latest


def conditional_update_summary(
    db: Session, *, conversation_id: int,
    expected_through_visible_rank: int, new_through_visible_rank: int,
    summary_text: str, source_message_count: int,
    new_through_message_id: str | None = None,
    provider: str | None = None, model: str | None = None,
    schema_version: int = 1,
) -> bool:
    """单调向前：仅当 DB 行仍是 expected_old 且 :new > 当前 through 才更新。

    返回 False 表示被更晚 Summary 抢先，调用方丢弃旧结果并重读。rank 与
    through_message_id 一同更新（新边界锚点与新 rank 永远一致）。
    """
    if new_through_visible_rank < 0 or new_through_visible_rank <= expected_through_visible_rank:
        return False
    result = db.execute(
        update(ConversationSummary)
        .where(
            ConversationSummary.conversation_id == conversation_id,
            ConversationSummary.through_visible_rank == expected_through_visible_rank,
            ConversationSummary.through_visible_rank < new_through_visible_rank,
        )
        .values(
            through_visible_rank=new_through_visible_rank,
            through_message_id=new_through_message_id,
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
    existing_through_visible_rank: int,
    recent_message_limit: int,
) -> tuple[int, list[Any], list[Any]]:
    """增量压缩：只处理 existing_through_visible_rank 之后的消息；cut 落在完整 exchange 组边界。

    seq_messages 的 key 必须是单调递增的逻辑排序键（run-bounded 可见序的
    rank；见模块 docstring）——B3 起禁止用物理 sequence_no 充当该键（物理序
    与逻辑序在 follow-up 插队时错位，会导致用户消息被错误视为已覆盖）。
    从尾部保留 recent_message_limit 条消息（不足整组时整组多留，绝不切散工具对）；
    其余完整组进入 summary。返回 (cut_key, for_summarizer_messages, kept_recent_messages)。
    cut_key = 最后一条被摘要消息的逻辑键；把该键作为新 marker 落库后，
    marker 数值 == 摘要累计覆盖的原始消息数（逻辑位置连续 1..N，见
    source_message_count 语义）。
    """
    if recent_message_limit < 1:
        recent_message_limit = 1
    after = [(seq, message) for seq, message in seq_messages
             if seq > existing_through_visible_rank]
    if not after:
        return existing_through_visible_rank, [], []
    messages = [message for _, message in after]
    units, _malformed = _split_into_exchange_units(messages)
    if not units:
        return existing_through_visible_rank, [], []

    kept_units: list[list[Any]] = []
    kept_count = 0
    for unit in reversed(units):
        kept_units.append(unit)
        kept_count += len(unit)
        if kept_count >= recent_message_limit:
            break
    keep_ids = {id(msg) for unit in kept_units for msg in unit}

    index = 0
    cut_rank = existing_through_visible_rank
    for unit in units:
        if any(id(msg) in keep_ids for msg in unit):
            break
        index += len(unit)
        if unit:
            cut_rank = after[index - 1][0]
    for_summary = [message for _, message in after[:index]]
    kept_msgs = [message for _, message in after[index:]]
    return cut_rank, for_summary, kept_msgs


@dataclass
class SummaryResult:
    """Summarizer 的单次返回。

    through_visible_rank：Summarizer 收到的 target_through_visible_rank（最后被摘要
    消息的逻辑键），仅作回传核对；落库 marker 与 source_message_count 由
    Orchestrator 在写路径上统一计算（cut 键即累计覆盖数），不信任模型侧自报。
    """

    summary_text: str
    through_visible_rank: int
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
