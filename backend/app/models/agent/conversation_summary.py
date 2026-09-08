"""P10.1 ConversationSummary：每会话一个 current summary（持久化、through 单调）。"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.sql import func as sa_func

from app.core.database import Base


class ConversationSummary(Base):
    __tablename__ = "conversation_summary"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_conversation_summary_conversation"),
    )

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"),
        nullable=False, index=True, comment="Conversation 会话 ID（agent_sessions.id）")
    through_visible_rank = Column(Integer, nullable=False,
                                  comment="覆盖逻辑位置（run-bounded 可见逻辑序 rank）上界；单调向前，"
                                          "新 Run/消息只追加在已覆盖 prefix 之后，prefix 位置不变")
    through_message_id = Column(String(64), nullable=True,
                                comment="覆盖边界处最后一条被摘要消息的稳定 message_id cursor"
                                        "（immutable 锚点，rank 的语义校验/审计依据）")
    summary_text = Column(Text, nullable=False, comment="旧历史的工作摘要（非事实 Source of Truth）")
    source_message_count = Column(Integer, nullable=False, default=0,
                                  comment="摘要累计覆盖的原始消息数（= 最新 through_visible_rank，稳定语义）")
    schema_version = Column(Integer, nullable=False, default=1, comment="Summary 合同版本")
    provider = Column(String(100), nullable=True, comment="生成摘要的 Provider 名称")
    model = Column(String(100), nullable=True, comment="生成摘要的模型名称")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(),
                        onupdate=sa_func.now(), comment="更新时间")
