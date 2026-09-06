from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base

# node_type 值域（P09.1 收敛：root / module / test_case）
NODE_TYPE_ROOT = "root"
NODE_TYPE_MODULE = "module"
NODE_TYPE_TEST_CASE = "test_case"


class ArtifactNode(Base):
    """ArtifactNode：Artifact 的用例树节点（root/module/test_case）。

    删除采用逻辑删除：deleted_revision 置为删除发生的 revision_no，历史不物理抹除；
    默认 tree/API 不返回已删除节点，也不能作为后续 parent/target。
    order_key 为同 parent 下的兄弟序号（int，新增=末尾自增；move 可显式指定），
    非 fractional index —— 满足首期确定性、可测试的稳定顺序。
    """

    __tablename__ = "artifact_node"
    __table_args__ = (
        Index("ix_artifact_node_artifact_parent_order", "artifact_id", "parent_id", "order_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(Integer, ForeignKey("test_artifact.id", ondelete="RESTRICT"), nullable=False, index=True,
                         comment="所属 Artifact")
    parent_id = Column(Integer, ForeignKey("artifact_node.id", ondelete="RESTRICT"), nullable=True, index=True,
                       comment="父节点；仅 root 为 NULL")
    node_type = Column(String(20), nullable=False, index=True, comment="root/module/test_case")
    order_key = Column(Integer, nullable=False, default=0, comment="同 parent 下兄弟序号")
    title = Column(String(500), nullable=False, default="", comment="标题")
    content_json = Column(JSON, nullable=True, comment="按 node_type 校验的结构化内容（test_case 强 schema）")
    source_refs_json = Column(JSON, nullable=True, comment="来源引用数组（source_refs 数据合同）")
    created_revision = Column(Integer, nullable=False, default=0, comment="创建时的 revision_no")
    deleted_revision = Column(Integer, nullable=True, index=True, comment="逻辑删除时的 revision_no；NULL=存活")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
                        comment="创建者用户 ID，可空")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
                        comment="更新时间")
