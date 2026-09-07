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
    through_sequence_no = Column(Integer, nullable=False, comment="覆盖到的会话事件序列上界")
    summary_text = Column(Text, nullable=False, comment="旧历史的工作摘要（非事实 Source of Truth）")
    source_message_count = Column(Integer, nullable=False, default=0,
                                  comment="被摘要覆盖的源消息数")
    schema_version = Column(Integer, nullable=False, default=1, comment="Summary 合同版本")
    provider = Column(String(100), nullable=True, comment="生成摘要的 Provider 名称")
    model = Column(String(100), nullable=True, comment="生成摘要的模型名称")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(),
                        onupdate=sa_func.now(), comment="更新时间")
