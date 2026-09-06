from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyInput(StrictModel):
    pass


class OutlineInput(StrictModel):
    root_node_id: int | None = Field(default=None, gt=0)
    max_depth: int = Field(default=4, ge=0, le=8)
    max_nodes: int = Field(default=50, ge=1, le=100)


class ReadNodesInput(StrictModel):
    node_ids: list[int] = Field(min_length=1, max_length=20)


class SearchInput(StrictModel):
    keyword: str | None = Field(default=None, max_length=200)
    node_type: Literal["root", "group", "test_point", "test_case"] | None = None
    tag: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


class RecentDiffInput(StrictModel):
    revision_count: int = Field(default=1, ge=1, le=10)
    max_changes: int = Field(default=50, ge=1, le=100)


class RequirementInput(StrictModel):
    requirement_id: int | None = Field(default=None, gt=0)
    max_chars: int = Field(default=12000, ge=100, le=20000)


class SourceRefInput(StrictModel):
    source_type: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=200)
    fragment_id: str | None = Field(default=None, max_length=200)
    snapshot_hash: str | None = Field(default=None, max_length=128)


class TestCaseStepInput(StrictModel):
    action: str = Field(min_length=1, max_length=1000)
    data: str | None = Field(default=None, max_length=1000)


class TestCaseContentInput(StrictModel):
    preconditions: list[str] = Field(default_factory=list, max_length=50)
    steps: list[TestCaseStepInput] = Field(default_factory=list, max_length=100)
    expected_results: list[str] = Field(default_factory=list, max_length=50)
    priority: Literal["P0", "P1", "P2", "P3", "P4"] = "P2"
    tags: list[str] = Field(default_factory=list, max_length=50)


class NodeInput(StrictModel):
    node_type: Literal["group", "test_point", "test_case"]
    title: str = Field(min_length=1, max_length=500)
    content: TestCaseContentInput | None = None
    source_refs: list[SourceRefInput] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def content_matches_type(self):
        if self.node_type != "test_case" and self.content is not None:
            raise ValueError("只有 test_case 可以携带 content")
        return self


class AddNodeInput(StrictModel):
    expected_revision: int = Field(ge=1)
    parent_id: int = Field(gt=0)
    node: NodeInput
    order_key: int | None = Field(default=None, ge=0)


class NodePatch(StrictModel):
    """Node 补丁合同（P08.1）：null 不代表清空。

    - 显式出现但值为 null 的字段 → 整体拒绝（避免单/批 Handler 静默丢弃语义）；
    - 未出现的字段 = 不改动；
    - 清空来源引用用 source_refs=[]。
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: TestCaseContentInput | None = None
    source_refs: list[SourceRefInput] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("patch 不能为空")
        return self

    @model_validator(mode="after")
    def reject_explicit_null(self):
        for field_name in ("title", "content", "source_refs"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(
                    f"patch.{field_name} 不能为 null（null 不代表清空；source_refs=[] 表示清空）")
        return self


class UpdateNodeInput(StrictModel):
    expected_revision: int = Field(ge=1)
    target_node_id: int = Field(gt=0)
    patch: NodePatch


class DeleteNodeInput(StrictModel):
    expected_revision: int = Field(ge=1)
    target_node_id: int = Field(gt=0)


class MoveNodeInput(StrictModel):
    expected_revision: int = Field(ge=1)
    target_node_id: int = Field(gt=0)
    new_parent_id: int = Field(gt=0)
    new_order_key: int | None = Field(default=None, ge=0)


class BatchAdd(StrictModel):
    operation_type: Literal["add_node"]
    parent_id: int | str
    node: NodeInput
    order_key: int | None = Field(default=None, ge=0)
    ref: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


class BatchUpdate(StrictModel):
    operation_type: Literal["update_node"]
    target_node_id: int = Field(gt=0)
    patch: NodePatch


class BatchDelete(StrictModel):
    operation_type: Literal["delete_node"]
    target_node_id: int = Field(gt=0)


class BatchMove(StrictModel):
    operation_type: Literal["move_node"]
    target_node_id: int = Field(gt=0)
    new_parent_id: int | str
    new_order_key: int | None = Field(default=None, ge=0)


BatchOperation = Annotated[
    Union[BatchAdd, BatchUpdate, BatchDelete, BatchMove],
    Field(discriminator="operation_type"),
]


class BatchInput(StrictModel):
    expected_revision: int = Field(ge=1)
    operations: list[BatchOperation] = Field(min_length=1, max_length=10)
    summary: str | None = Field(default=None, max_length=500)


class QualityInput(StrictModel):
    root_node_id: int | None = Field(default=None, gt=0)


class DuplicateInput(QualityInput):
    threshold: float = Field(default=0.88, ge=0.5, le=1.0)
    limit: int = Field(default=20, ge=1, le=50)


class CoverageInput(QualityInput):
    pass
