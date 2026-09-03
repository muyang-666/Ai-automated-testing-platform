from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class AgentApproval(Base):
    """Agent Approval：保存、造数、重跑等写操作的人工审批。"""

    __tablename__ = "agent_approvals"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话ID")
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属 Run ID")
    artifact_id = Column(Integer, ForeignKey("agent_artifacts.id", ondelete="RESTRICT"), nullable=True, index=True, comment="关联产物ID，可空")
    action_code = Column(String(100), nullable=False, comment="审批动作编码，如 save_selected_candidates")
    status = Column(String(20), default="pending", index=True, comment="状态：pending/approved/rejected/expired/cancelled")
    request_json = Column(JSON, nullable=True, comment="审批请求JSON，只保存脱敏摘要")
    resolution_json = Column(JSON, nullable=True, comment="审批结果JSON")
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="发起时间")
    expires_at = Column(DateTime(timezone=True), nullable=True, comment="过期时间，可空")
    resolved_at = Column(DateTime(timezone=True), nullable=True, comment="处理时间，可空")
    resolved_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True, comment="处理人用户ID，可空")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
