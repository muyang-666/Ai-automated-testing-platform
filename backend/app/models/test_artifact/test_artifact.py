from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base

# 首期 artifact_type 值域（后续可扩 api_test_design/test_plan/rca_report）
ARTIFACT_TYPE_TEST_DESIGN = "test_design"
# status 值域（05 §6.4 只列字段名未给枚举，此处定义 P07 最小稳定集合）
ARTIFACT_STATUS_ACTIVE = "active"
ARTIFACT_STATUS_ARCHIVED = "archived"


class TestArtifact(Base):
    """TestArtifact：用户长期维护的可编辑测试资产（Artifact ≈ repository/document）。

    与 AgentArtifact 语义分离：AgentArtifact 是某次 Run 的结构化产物快照（legacy）；
    TestArtifact 是用户与 Agent 共同长期编辑的业务对象，版本化为 Revision。
    Artifact 不依赖 Agent / Conversation。
    """

    __tablename__ = "test_artifact"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
                           comment="owner 用户")
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True,
                        comment="可选项目归属")
    title = Column(String(200), nullable=False, comment="标题")
    artifact_type = Column(String(50), nullable=False, default=ARTIFACT_TYPE_TEST_DESIGN, index=True,
                           comment="资产类型：test_design（首期）")
    status = Column(String(20), nullable=False, default=ARTIFACT_STATUS_ACTIVE, index=True,
                    comment="状态：active/archived")
    current_revision = Column(Integer, nullable=False, default=0,
                              comment="当前最新 revision_no；0 = 仅创建未产生业务修订")
    root_node_id = Column(Integer, nullable=True,
                          comment="指向 artifact_node.id 的 root 指针（不建 FK：与 artifact_node 互指会造成建表环，由 Service 维护不变式）")
    schema_version = Column(Integer, nullable=False, default=1, comment="行 schema 版本")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
                        comment="更新时间")
