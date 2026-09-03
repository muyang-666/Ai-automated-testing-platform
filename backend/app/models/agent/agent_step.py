from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AgentStep(Base):
    """Agent Step：Run 的 LLM/Tool/Validation/Approval 步骤。

    input_json/output_json 只保存脱敏摘要，不保存 Secret、API Key 或隐藏思维链。
    """

    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence_no", name="uq_agent_steps_run_seq"),
    )

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属 Run ID")
    sequence_no = Column(Integer, nullable=False, comment="Run 内步骤序号")
    step_kind = Column(String(20), nullable=False, comment="步骤类型：llm/tool/validation/approval")
    step_name = Column(String(100), nullable=False, comment="步骤名称")
    tool_name = Column(String(100), nullable=True, comment="工具名称，非工具步骤为空")
    status = Column(String(20), default="pending", index=True, comment="状态：pending/running/succeeded/failed/skipped")
    input_json = Column(JSON, nullable=True, comment="输入JSON，只保存脱敏摘要")
    output_json = Column(JSON, nullable=True, comment="输出JSON，只保存脱敏摘要")
    provider_name = Column(String(100), nullable=True, comment="模型供应商名称")
    model_name = Column(String(100), nullable=True, comment="模型名称")
    prompt_tokens = Column(Integer, nullable=True, comment="提示词 token 数")
    completion_tokens = Column(Integer, nullable=True, comment="补全 token 数")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    error_code = Column(String(50), nullable=True, comment="错误码")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
