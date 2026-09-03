from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentMessage(Base):
    """Agent 消息：用户、Agent、系统和工具的可展示消息。"""

    __tablename__ = "agent_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="uq_agent_messages_session_seq"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话ID")
    run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=True, index=True, comment="关联 Run ID，可空")
    role = Column(String(20), nullable=False, comment="角色：user/assistant/system/tool")
    message_type = Column(String(20), default="text", comment="类型：text/status/gate/artifact_ref/error")
    content = Column(Text, nullable=True, comment="消息文本内容")
    content_json = Column(JSON, nullable=True, comment="结构化内容JSON")
    sequence_no = Column(Integer, nullable=False, comment="会话内消息序号")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
