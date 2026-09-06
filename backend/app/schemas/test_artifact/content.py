"""ArtifactNode content_json 受控校验（V2-P07 §6）。

test_case 使用强 schema（preconditions/steps/expected_results/priority/tags），
root/group/test_point 不承载自由 JSON（只允许空），避免 content_json 变成无约束垃圾桶。
source_refs 走 SourceRef 数据合同。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TestArtifactSchemaBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


# ── SourceRef 数据合同（§21；P07 只定义/校验，不做解析/追溯 UI） ──


class SourceRef(TestArtifactSchemaBase):
    source_type: str = Field(..., max_length=50, description="来源类型，如 requirement")
    source_id: str = Field(..., max_length=200, description="来源 ID，如 REQ-123")
    fragment_id: Optional[str] = Field(default=None, max_length=200, description="来源片段，如 clause-7")
    snapshot_hash: Optional[str] = Field(default=None, max_length=128, description="来源内容快照哈希")


# ── test_case 内容 schema（§6） ──

PRIORITY_VALUES = ("P0", "P1", "P2", "P3", "P4")


class TestCaseStep(TestArtifactSchemaBase):
    action: str = Field(..., max_length=1000)
    data: Optional[str] = Field(default=None, max_length=1000)


class TestCaseContent(TestArtifactSchemaBase):
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestCaseStep] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: Literal["P0", "P1", "P2", "P3", "P4"] = "P2"
    tags: list[str] = Field(default_factory=list)


# root/group/test_point 不承载正文内容：只允许空
_TITLE_ONLY_TYPES = ("root", "group", "test_point")


def validate_node_content(node_type: str, content: Any) -> Optional[dict[str, Any]]:
    """校验并规范化节点 content。

    - root/group/test_point：content 必须为 None/{} → 返回 None。
    - test_case：content 必须为 dict（或省略 → 空）→ 返回规范化 dict。
    非法输入抛 ValueError（由 Service 翻译为领域校验错误）。
    """
    if node_type in _TITLE_ONLY_TYPES:
        if content in (None, {}):
            return None
        raise ValueError(f"{node_type} 节点不承载自由 content_json")
    if node_type == "test_case":
        if content in (None, {}):
            normalized = TestCaseContent().model_dump(mode="json")
        elif isinstance(content, dict):
            try:
                normalized = TestCaseContent.model_validate(content).model_dump(mode="json")
            except ValidationError as exc:
                raise ValueError(f"test_case content 不合法: {exc.errors()[0].get('msg', 'schema')}") from None
        else:
            raise ValueError("test_case content 必须是对象")
        return normalized
    raise ValueError(f"未知 node_type: {node_type}")


def validate_source_refs(source_refs: Any) -> Optional[list[dict[str, Any]]]:
    if source_refs in (None, [], ()):
        return None
    if not isinstance(source_refs, list):
        raise ValueError("source_refs 必须是数组")
    try:
        return [SourceRef.model_validate(item).model_dump(mode="json") for item in source_refs]
    except ValidationError as exc:
        raise ValueError(f"source_refs 不合法: {exc.errors()[0].get('msg', 'schema')}") from None
