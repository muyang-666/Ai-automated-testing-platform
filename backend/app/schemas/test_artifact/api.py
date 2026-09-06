"""TestArtifact API schema（V2-P07）。API 是 Application Service 的薄壳。"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# 集中枚举（供 API 层白名单校验；取值与 models/services 常量一致）
ARTIFACT_TYPES = ("test_design",)
ARTIFACT_STATUSES = ("active", "archived")
NODE_TYPES = ("root", "module", "test_case")
OPERATION_TYPES = ("add_node", "update_node", "delete_node", "move_node", "restore")
ACTOR_TYPES = ("user", "agent", "system")


class TestArtifactSchemaBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


# ── Artifact ──


class ArtifactCreateRequest(TestArtifactSchemaBase):
    title: str = Field(..., min_length=1, max_length=200)
    artifact_type: Literal["test_design"] = Field(default="test_design")
    project_id: Optional[int] = Field(default=None)


class ArtifactEnsureRequest(TestArtifactSchemaBase):
    project_id: int = Field(..., gt=0)
    title: Optional[str] = Field(default=None, max_length=200, description="缺失时创建的标题")


class ArtifactSummary(TestArtifactSchemaBase):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)
    id: int
    owner_user_id: int
    project_id: Optional[int]
    title: str
    artifact_type: str
    status: str
    current_revision: int
    created_at: datetime
    updated_at: datetime


# ── Node / Tree ──


class OperationInput(TestArtifactSchemaBase):
    """一条客户端操作请求。各字段按 operation_type 取舍，Service 负责规范化与校验。"""

    operation_type: Literal["add_node", "update_node", "delete_node", "move_node", "restore"]
    target_node_id: Optional[int] = Field(default=None)
    parent_id: Optional[int] = Field(default=None)
    node_type: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None, max_length=500)
    content: Optional[dict[str, Any]] = Field(default=None)
    source_refs: Optional[list[dict[str, Any]]] = Field(default=None)
    order_key: Optional[int] = Field(default=None)
    patch: Optional[dict[str, Any]] = Field(default=None, description="update_node：受控字段补丁")
    new_parent_id: Optional[int] = Field(default=None)
    new_order_key: Optional[int] = Field(default=None)
    nodes: Optional[list[dict[str, Any]]] = Field(default=None, description="restore：恢复节点快照列表")


class OperationSubmitRequest(TestArtifactSchemaBase):
    expected_revision: int = Field(..., ge=0)
    summary: Optional[str] = Field(default=None, max_length=500)
    operations: list[OperationInput] = Field(..., min_length=1)


class AppliedOperationsResponse(TestArtifactSchemaBase):
    artifact_id: int
    expected_revision: int
    new_revision: int
    changed: int = Field(..., description="本次提交生效的操作数")
    summary: str = ""


class NodeTreeItem(TestArtifactSchemaBase):
    id: int
    node_type: str
    title: str
    order_key: int
    parent_id: Optional[int]
    content: Optional[dict[str, Any]] = Field(default=None)
    source_refs: Optional[list[dict[str, Any]]] = Field(default=None)
    created_revision: int = Field(default=0)
    children: list["NodeTreeItem"] = Field(default_factory=list)


class TreeResponse(TestArtifactSchemaBase):
    artifact_id: int
    current_revision: int
    root: Optional[NodeTreeItem] = Field(default=None)


# ── Revision / Operation ──


class OperationItem(TestArtifactSchemaBase):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)
    op_index: int
    operation_type: str
    target_node_id: Optional[int]
    payload: Optional[dict[str, Any]] = Field(default=None)
    before: Optional[dict[str, Any]] = Field(default=None)
    after: Optional[dict[str, Any]] = Field(default=None)


class RevisionItem(TestArtifactSchemaBase):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)
    id: int
    artifact_id: int
    revision_no: int
    base_revision: int
    actor_type: str
    actor_user_id: Optional[int]
    conversation_id: Optional[int]
    run_id: Optional[int]
    summary: str
    created_at: datetime


class RevisionDetail(RevisionItem):
    operations: list[OperationItem] = Field(default_factory=list)


class UndoResponse(TestArtifactSchemaBase):
    artifact_id: int
    previous_revision: int
    new_revision: int
    summary: str = ""


class RestoreRequest(TestArtifactSchemaBase):
    target_revision: int = Field(..., ge=1)


class RestoreResponse(TestArtifactSchemaBase):
    artifact_id: int
    target_revision: int
    new_revision: int
    summary: str = ""


# ── Diff（从 Operation 派生） ──


class DiffChangeItem(TestArtifactSchemaBase):
    change: Literal["added", "updated", "deleted", "moved"]
    node_id: int
    parent_id: Optional[int] = Field(default=None)
    node_type: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    fields: Optional[dict[str, Any]] = Field(default=None, description="updated：字段 before/after")
    before: Optional[dict[str, Any]] = Field(default=None)
    after: Optional[dict[str, Any]] = Field(default=None)
    descendant_count: Optional[int] = Field(default=None)


class DiffResponse(TestArtifactSchemaBase):
    artifact_id: int
    from_revision: int
    to_revision: int
    changes: list[DiffChangeItem] = Field(default_factory=list)
