"""TestArtifact 领域错误（独立于 agents/conversation 的错误族）。

error_code 用于 Router 映射 HTTP 状态与 P08 ToolResult 的 error_code；
RevisionConflictError 的 detail 携带 expected/current revision（§10 409 载荷）。
"""


class TestArtifactError(Exception):
    error_code = "test_artifact_error"

    def __init__(self, message: str = "TestArtifact 领域错误", *, error_code: str | None = None,
                 detail: dict | None = None):
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        self.detail = detail or {}


class TestArtifactNotFoundError(TestArtifactError):
    error_code = "test_artifact_not_found"


class TestArtifactPermissionError(TestArtifactError):
    error_code = "artifact_permission_denied"


class TestArtifactValidationError(TestArtifactError):
    error_code = "test_artifact_validation_error"


class RevisionConflictError(TestArtifactError):
    """乐观并发冲突：expected_revision 过期（§10 §13）。"""

    error_code = "revision_conflict"

    def __init__(self, expected_revision: int, current_revision: int,
                 message: str = "Artifact changed after it was read."):
        super().__init__(
            message,
            detail={"expected_revision": expected_revision, "current_revision": current_revision},
        )


class TestArtifactDataError(TestArtifactError):
    error_code = "test_artifact_data_error"
