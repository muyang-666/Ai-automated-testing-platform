from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base

# operation_type 值域
OP_ADD_NODE = "add_node"
OP_UPDATE_NODE = "update_node"
OP_DELETE_NODE = "delete_node"
OP_MOVE_NODE = "move_node"
OP_RESTORE = "restore"


class ArtifactOperation(Base):
    """ArtifactOperation：一个 Revision 内按序排列的补丁（Operation ≈ patch）。

    payload_json 记录客户端/内部请求（含派生信息如 delete 的 affected_node_ids、
    restore 的恢复快照）；before_json/after_json 记录该节点在操作前后的快照，
    Diff 由 Operation 直接派生（不重新比较整棵 JSON Tree）。
    """

    __tablename__ = "artifact_operation"
    __table_args__ = (
        UniqueConstraint("revision_id", "op_index", name="uq_artifact_operation_idx"),
    )

    id = Column(Integer, primary_key=True, index=True)
    revision_id = Column(Integer, ForeignKey("artifact_revision.id", ondelete="RESTRICT"), nullable=False,
                         index=True, comment="所属 Revision")
    op_index = Column(Integer, nullable=False, comment="Revision 内操作序号，从 0 起")
    operation_type = Column(String(20), nullable=False, comment="add_node/update_node/delete_node/move_node/restore")
    target_node_id = Column(Integer, nullable=True, index=True, comment="作用节点（add=新建节点；restore=根节点）")
    payload_json = Column(JSON, nullable=True, comment="请求/派生数据")
    before_json = Column(JSON, nullable=True, comment="操作前节点快照")
    after_json = Column(JSON, nullable=True, comment="操作后节点快照")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
