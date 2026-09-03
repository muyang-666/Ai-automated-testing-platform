from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentEvent(Base):
    """Agent 事件：可观察的运行与 GATE 事件。

    只保存可观察步骤与脱敏摘要，不保存 Secret、API Key 或隐藏思维链。
    """

    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="uq_agent_events_session_seq"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话ID")
    run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=True, index=True, comment="关联 Run ID，可空")
    event_type = Column(String(50), nullable=False, comment="事件类型，如 skill_selected/phase_started/approval_required")
    sequence_no = Column(Integer, nullable=False, comment="会话内事件序号")
    payload_json = Column(JSON, nullable=True, comment="事件负载JSON，只保存脱敏摘要")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
