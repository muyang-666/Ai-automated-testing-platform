from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base

# actor_type 值域：user / agent / system（P07 主要 user/system，agent 留给 P08）
ACTOR_TYPE_USER = "user"
ACTOR_TYPE_AGENT = "agent"
ACTOR_TYPE_SYSTEM = "system"


class ArtifactRevision(Base):
    """ArtifactRevision：一次逻辑修改（一个 operation batch）产生的版本（Revision ≈ commit）。

    线性 revision：每个 Artifact 独立从 1 递增；revision_no 并发安全由
    apply_operations 的条件 UPDATE（WHERE current_revision = expected）在事务层裁决。
    base_revision 记录该修订基于的 revision_no（线性下 = revision_no - 1；根 = 0）。
    conversation_id/run_id 仅为 nullable 审计元数据，不建 FK —— Artifact 不耦合 Conversation。
    """

    __tablename__ = "artifact_revision"
    __table_args__ = (
        UniqueConstraint("artifact_id", "revision_no", name="uq_artifact_revision_no"),
    )

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(Integer, ForeignKey("test_artifact.id", ondelete="RESTRICT"), nullable=False, index=True,
                         comment="所属 Artifact")
    revision_no = Column(Integer, nullable=False, comment="Artifact 内线性版本号，从 1 起")
    base_revision = Column(Integer, nullable=False, default=0, comment="基于的 revision_no（根=0）")
    actor_type = Column(String(20), nullable=False, default=ACTOR_TYPE_SYSTEM, comment="user/agent/system")
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True,
                           comment="发起用户（agent/system 可空）")
    conversation_id = Column(Integer, nullable=True, index=True,
                             comment="审计元数据：来源会话 ID，不建 FK（Artifact 不依赖 Conversation）")
    run_id = Column(Integer, nullable=True, index=True,
                    comment="审计元数据：来源 Run ID，不建 FK")
    summary = Column(String(500), nullable=False, default="", comment="本次修改摘要")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
