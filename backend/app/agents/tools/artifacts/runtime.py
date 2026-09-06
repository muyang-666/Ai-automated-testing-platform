from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ArtifactRuntimeContext:
    """Server-created identity and persistence dependencies unavailable to the model."""

    session_factory: Callable
    user_id: int
    conversation_id: int
    run_id: int
    artifact_id: int | None
    project_id: int | None
    requirement_id: int | None = None
    permissions: frozenset[str] = frozenset()
    worker_id: str | None = None
    execution_token: int | None = None


def build_artifact_runtime_context(session_factory: Callable, **values) -> ArtifactRuntimeContext:
    from app.models.user import User
    from app.services.test_artifacts import artifact_service

    permissions: frozenset[str] = frozenset()
    artifact_id = values.get("artifact_id")
    if artifact_id is not None:
        db = session_factory()
        try:
            requester = db.get(User, values["user_id"])
            if requester is not None:
                permissions = artifact_service.permissions_for_artifact(
                    db, artifact_id=artifact_id, requester=requester,
                )
        finally:
            db.close()
    return ArtifactRuntimeContext(session_factory=session_factory, permissions=permissions, **values)
