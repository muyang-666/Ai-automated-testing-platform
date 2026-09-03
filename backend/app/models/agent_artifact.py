from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class AgentArtifact(Base):
    """Agent Artifact：覆盖矩阵、用例集等结构化业务产物。

    候选仍未保存到业务表；只有用户批准并调用保存后才写入 function_cases/api_cases。
    """

    __tablename__ = "agent_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话ID")
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False, index=True, comment="产生该产物的 Run ID")
    artifact_type = Column(String(50), nullable=False, index=True, comment="产物类型：coverage_matrix/test_case_set 等")
    version = Column(Integer, default=1, nullable=False, comment="产物版本号")
    status = Column(String(20), default="draft", index=True, comment="状态：draft/reviewing/approved/saved/rejected")
    payload_json = Column(JSON, nullable=False, comment="结构化业务成果JSON")
    source_refs_json = Column(JSON, nullable=True, comment="来源引用JSON，如需求ID与子句")
    source_hash = Column(String(64), nullable=True, comment="来源内容哈希，用于来源变化检测")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="创建者用户ID，可空")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
