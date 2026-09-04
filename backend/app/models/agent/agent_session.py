from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class AgentSession(Base):
    """Agent 对话会话：用户与测试 Agent 的一次持续工作空间。"""

    __tablename__ = "agent_sessions"
    __table_args__ = (
        CheckConstraint("mode IN ('legacy_workflow', 'conversation')", name="ck_agent_sessions_mode"),
        CheckConstraint("mode = 'conversation' OR project_id IS NOT NULL",
                        name="ck_agent_sessions_legacy_project"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True, comment="可选项目ID；conversation 可为空")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="会话所属用户ID")
    mode = Column(String(20), nullable=False, default="legacy_workflow", index=True, comment="legacy_workflow/conversation")
    title = Column(String(200), nullable=False, comment="会话标题")
    status = Column(String(20), default="active", comment="状态：active/closed/archived")
    current_skill_code = Column(String(100), nullable=True, comment="当前选中的 Skill 编码")
    agent_version = Column(String(50), nullable=True, comment="当前 Agent 版本")
    context_json = Column(JSON, nullable=True, comment="会话业务上下文JSON，如来源需求/文档ID")
    next_message_sequence = Column(Integer, nullable=False, default=1, comment="下一条消息序号，数据库原子分配")
    next_event_sequence = Column(Integer, nullable=False, default=1, comment="下一条事件序号，数据库原子分配")
    last_activity_at = Column(DateTime(timezone=True), nullable=True, comment="最后活动时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
