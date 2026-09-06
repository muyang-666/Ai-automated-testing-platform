"""ArtifactNode content_json 受控校验（P07 → P09.1 收敛）。

node_type 值域（P09.1 起）：root / module / test_case。
- module：不承载自由 JSON（只允许空），标题即定义；
- test_case：强 schema（preconditions/steps/expected_results/priority/tags），
  步骤/预期为结构化对象；兼容旧 list[str] 输入并规范化为统一形态。
source_refs 走 SourceRef 数据合同。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TestArtifactSchemaBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


# ── SourceRef 数据合同（§21；P09.1 只读展示，不做解析/追溯 UI） ──


class SourceRef(TestArtifactSchemaBase):
    source_type: str = Field(..., max_length=50, description="来源类型，如 requirement")
    source_id: str = Field(..., max_length=200, description="来源 ID，如 REQ-123")
    fragment_id: Optional[str] = Field(default=None, max_length=200, description="来源片段，如 clause-7")
    snapshot_hash: Optional[str] = Field(default=None, max_length=128, description="来源内容快照哈希")


# ── test_case 内容 schema（结构化；禁止 Optional[Any] 进入新写路径） ──

PRIORITY_VALUES = ("P0", "P1", "P2", "P3")


class TestCaseStep(TestArtifactSchemaBase):
    step_no: Optional[int] = Field(default=None, gt=0, description="步骤序号；写入时缺失自动按顺序补齐")
    action: str = Field(..., min_length=1, max_length=1000)
    data: Optional[str] = Field(default=None, max_length=1000)


class ExpectedResult(TestArtifactSchemaBase):
    step_no: Optional[int] = Field(default=None, gt=0, description="对应步骤；缺失表示整体预期")
    expected: str = Field(..., min_length=1, max_length=2000)


class TestCaseContent(TestArtifactSchemaBase):
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestCaseStep] = Field(default_factory=list)
    expected_results: list[ExpectedResult] = Field(default_factory=list)
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    tags: list[str] = Field(default_factory=list)


_TITLE_ONLY_TYPES = ("root", "module")


def _normalize_steps(raw_steps: Any) -> list[dict]:
    if not isinstance(raw_steps, list):
        raise ValueError("steps 必须是数组")
    normalized: list[dict] = []
    for index, item in enumerate(raw_steps, start=1):
        if isinstance(item, str):  # 旧 list[str] 兼容：视为单步 action
            step = {"action": item}
        elif isinstance(item, dict):
            step = dict(item)
            if not isinstance(step.get("action"), str) or not step["action"].strip():
                raise ValueError(f"steps[{index}].action 必须是非空字符串")
        else:
            raise ValueError(f"steps[{index}] 必须是字符串或对象")
        if "step_no" not in step:
            step["step_no"] = index
        normalized.append(step)
    return normalized


def _normalize_expected(raw_results: Any, steps_count: int) -> list[dict]:
    if not isinstance(raw_results, list):
        raise ValueError("expected_results 必须是数组")
    normalized: list[dict] = []
    for index, item in enumerate(raw_results, start=1):
        if isinstance(item, str):  # 旧形态：整体/末步预期
            normalized.append({"step_no": None, "expected": item})
        elif isinstance(item, dict):
            expected = item.get("expected")
            if not isinstance(expected, str) or not expected.strip():
                raise ValueError(f"expected_results[{index}].expected 必须是非空字符串")
            normalized.append({"step_no": item.get("step_no"), "expected": expected})
        else:
            raise ValueError(f"expected_results[{index}] 必须是字符串或对象")
    _ = steps_count
    return normalized


def validate_node_content(node_type: str, content: Any) -> Optional[dict[str, Any]]:
    """校验并规范化节点 content（root/module 仅标题；test_case 强 schema）。

    非法输入抛 ValueError（由 Service 翻译为领域校验错误）。
    """
    if node_type in _TITLE_ONLY_TYPES:
        if content in (None, {}):
            return None
        raise ValueError(f"{node_type} 节点不承载自由 content_json")
    if node_type == "test_case":
        if content in (None, {}):
            raw: dict[str, Any] = {}
        elif isinstance(content, dict):
            raw = content
        else:
            raise ValueError("test_case content 必须是对象")
        steps = _normalize_steps(raw.get("steps", []))
        expected = _normalize_expected(raw.get("expected_results", []), len(steps))
        payload = {
            "preconditions": list(raw.get("preconditions") or []),
            "steps": steps,
            "expected_results": expected,
            "priority": raw.get("priority", "P1"),
            "tags": list(raw.get("tags") or []),
        }
        for item in payload["preconditions"]:
            if not isinstance(item, str):
                raise ValueError("preconditions 必须是字符串数组")
        for tag in payload["tags"]:
            if not isinstance(tag, str):
                raise ValueError("tags 必须是字符串数组")
        try:
            normalized = TestCaseContent.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise ValueError(f"test_case content 不合法: {exc.errors()[0].get('msg', 'schema')}") from None
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
