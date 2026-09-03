"""AgentArtifact 数据访问 Service。

- 只实现通用创建、版本与状态更新，不生成真实测试用例；
- 本任务不写入 api_cases/function_cases；
- 归属校验：仅会话 owner 可见；
- 事务边界：Service 只 add/flush 不 commit，由调用方控制。
"""

from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentError, AgentPermissionError
from app.models.agent.agent_artifact import AgentArtifact
from app.models.agent.agent_session import AgentSession
from app.schemas.agent.platform import ARTIFACT_STATUSES


def create_artifact(
    db: Session,
    session_id: int,
    agent_run_id: int,
    artifact_type: str,
    payload_json: dict,
    version: int = 1,
    source_refs_json: dict | None = None,
    source_hash: str | None = None,
    created_by_user_id: int | None = None,
    status: str = "draft",
) -> AgentArtifact:
    if status not in ARTIFACT_STATUSES:
        raise AgentError(f"非法产物状态: {status}", error_code="agent_invalid_artifact_status")
    artifact = AgentArtifact(
        session_id=session_id,
        agent_run_id=agent_run_id,
        artifact_type=artifact_type,
        version=version,
        status=status,
        payload_json=payload_json,
        source_refs_json=source_refs_json,
        source_hash=source_hash,
        created_by_user_id=created_by_user_id,
    )
    db.add(artifact)
    db.flush()
    return artifact


def get_artifact(db: Session, artifact_id: int, requester_user_id: int) -> AgentArtifact:
    artifact = db.query(AgentArtifact).filter(AgentArtifact.id == artifact_id).first()
    if not artifact:
        raise AgentPermissionError(f"产物 {artifact_id} 不存在或无权访问。")
    session = db.query(AgentSession).filter(AgentSession.id == artifact.session_id).first()
    if not session or session.user_id != requester_user_id:
        raise AgentPermissionError(f"用户 {requester_user_id} 无权访问产物 {artifact_id}。")
    return artifact


def create_next_version(db: Session, artifact: AgentArtifact) -> AgentArtifact:
    """基于当前产物创建下一版本（version+1，status 重置为 draft）。"""
    next_artifact = AgentArtifact(
        session_id=artifact.session_id,
        agent_run_id=artifact.agent_run_id,
        artifact_type=artifact.artifact_type,
        version=artifact.version + 1,
        status="draft",
        payload_json=artifact.payload_json,
        source_refs_json=artifact.source_refs_json,
        source_hash=artifact.source_hash,
        created_by_user_id=artifact.created_by_user_id,
    )
    db.add(next_artifact)
    db.flush()
    return next_artifact


def update_status(db: Session, artifact: AgentArtifact, new_status: str) -> AgentArtifact:
    if new_status not in ARTIFACT_STATUSES:
        raise AgentError(f"非法产物状态: {new_status}", error_code="agent_invalid_artifact_status")
    artifact.status = new_status
    db.flush()
    return artifact


def update_payload(db: Session, artifact: AgentArtifact, payload_json: dict) -> AgentArtifact:
    """更新产物 payload（如覆盖矩阵在计算后回填 matrix/missing）。"""
    artifact.payload_json = payload_json
    db.flush()
    return artifact
