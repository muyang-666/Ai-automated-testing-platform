from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentRun(Base):
    """Agent Run：会话中一次具体 Skill 任务，如"为需求 12 生成用例"。"""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "workflow_code", "idempotency_key", name="uq_agent_runs_idempotency"),
        UniqueConstraint("session_id", "active_slot", name="uq_agent_runs_session_active_slot"),
        CheckConstraint("active_slot IS NULL OR (active_slot = 1 AND workflow_code = 'conversation')",
                        name="ck_agent_runs_active_slot"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话ID")
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True, comment="可选项目ID；conversation 可为空")
    requester_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="发起用户ID")
    workflow_code = Column(String(100), nullable=False, comment="Workflow 编码，如 case_generation")
    workflow_version = Column(String(50), nullable=True, comment="Workflow 版本")
    status = Column(String(20), default="queued", index=True, comment="状态：queued/running/waiting_approval/succeeded/failed/cancelled/interrupted")
    current_step = Column(String(100), nullable=True, comment="当前步骤")
    input_json = Column(JSON, nullable=True, comment="任务输入JSON")
    output_json = Column(JSON, nullable=True, comment="任务输出JSON，含候选用例等")
    input_hash = Column(String(64), nullable=True, comment="输入内容哈希，用于幂等与来源变化检测")
    idempotency_key = Column(String(128), nullable=True, comment="幂等键，可空；提供时在(session_id, workflow_code)内唯一")
    user_message_id = Column(Integer, nullable=True, index=True, comment="conversation Turn 的首条用户消息；归属由同事务服务校验")
    active_slot = Column(Integer, nullable=True, comment="conversation 活跃槽固定为1；终态清空")
    model_snapshot_json = Column(JSON, nullable=True, comment="模型快照，只存 provider/model 名称等非敏感信息")
    prompt_version = Column(String(50), nullable=True, comment="Prompt 版本")
    max_steps = Column(Integer, default=20, comment="最大步骤数")
    steps_used = Column(Integer, default=0, comment="已用步骤数")
    llm_calls_used = Column(Integer, default=0, comment="模型调用次数")
    tool_calls_used = Column(Integer, default=0, comment="工具调用次数")
    prompt_tokens = Column(Integer, default=0, comment="提示词 token 数")
    completion_tokens = Column(Integer, default=0, comment="补全 token 数")
    error_code = Column(String(50), nullable=True, comment="错误码")
    error_message = Column(Text, nullable=True, comment="错误信息")
    worker_id = Column(String(64), nullable=True, comment="执行 Worker 标识")
    heartbeat_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="心跳时间，用于中断恢复")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
