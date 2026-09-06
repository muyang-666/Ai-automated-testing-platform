"""TestArtifact schema 分组（V2-P07）。

包级重导出，路由与测试统一从本包或 .api 导入，避免 magic string 散落。
"""

from app.schemas.test_artifact.api import (  # noqa: F401
    AppliedOperationsResponse,
    ArtifactCreateRequest,
    DiffChangeItem,
    DiffResponse,
    NodeTreeItem,
    OperationInput,
    OperationItem,
    OperationSubmitRequest,
    RestoreRequest,
    RevisionDetail,
    RevisionItem,
    TreeResponse,
    ArtifactSummary,
    UndoResponse,
)
from app.schemas.test_artifact.content import (  # noqa: F401
    SourceRef,
    TestCaseContent,
    validate_node_content,
)

__all__ = [
    "ArtifactCreateRequest",
    "ArtifactSummary",
    "OperationInput",
    "OperationSubmitRequest",
    "AppliedOperationsResponse",
    "NodeTreeItem",
    "TreeResponse",
    "RevisionItem",
    "RevisionDetail",
    "OperationItem",
    "DiffResponse",
    "DiffChangeItem",
    "UndoResponse",
    "RestoreRequest",
    "SourceRef",
    "TestCaseContent",
    "validate_node_content",
]
