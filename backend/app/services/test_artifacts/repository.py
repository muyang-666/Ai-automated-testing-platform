"""TestArtifact 只读仓储（读路径）。

写路径一律集中在 artifact_service（Application Service 是唯一写入口）；
本模块只提供 SELECT 助手，不包含任何 db.add/commit。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.test_artifact.artifact_operation import ArtifactOperation
from app.models.test_artifact.artifact_revision import ArtifactRevision
from app.models.test_artifact.test_artifact import TestArtifact


def get_artifact(db: Session, artifact_id: int) -> TestArtifact | None:
    return db.get(TestArtifact, artifact_id)


def list_artifacts(db: Session) -> list[TestArtifact]:
    return list(db.execute(select(TestArtifact).order_by(TestArtifact.id.desc())).scalars())


def get_node(db: Session, node_id: int) -> ArtifactNode | None:
    return db.get(ArtifactNode, node_id)


def list_nodes(db: Session, artifact_id: int) -> list[ArtifactNode]:
    """返回某 Artifact 的全部节点（含逻辑删除），按稳定顺序。"""
    rows = db.execute(
        select(ArtifactNode).where(ArtifactNode.artifact_id == artifact_id)
    ).scalars().all()
    return list(rows)


def list_visible_nodes(db: Session, artifact_id: int) -> list[ArtifactNode]:
    return list(db.execute(
        select(ArtifactNode)
        .where(ArtifactNode.artifact_id == artifact_id,
               ArtifactNode.deleted_revision.is_(None))
    ).scalars().all())


def list_revisions(db: Session, artifact_id: int) -> list[ArtifactRevision]:
    return list(db.execute(
        select(ArtifactRevision).where(ArtifactRevision.artifact_id == artifact_id)
        .order_by(ArtifactRevision.revision_no.asc())
    ).scalars().all())


def get_revision(db: Session, artifact_id: int, revision_no: int) -> ArtifactRevision | None:
    return db.execute(
        select(ArtifactRevision).where(
            ArtifactRevision.artifact_id == artifact_id,
            ArtifactRevision.revision_no == revision_no,
        )
    ).scalars().first()


def list_operations_for_revision(db: Session, revision_id: int) -> list[ArtifactOperation]:
    return list(db.execute(
        select(ArtifactOperation).where(ArtifactOperation.revision_id == revision_id)
        .order_by(ArtifactOperation.op_index.asc())
    ).scalars().all())


def list_operations_range(db: Session, artifact_id: int, from_revision: int,
                          to_revision: int) -> list[ArtifactOperation]:
    """返回 (from_revision, to_revision] 区间内的全部 Operation（按 revision_no, op_index）。"""
    return list(db.execute(
        select(ArtifactOperation)
        .join(ArtifactRevision, ArtifactRevision.id == ArtifactOperation.revision_id)
        .where(ArtifactRevision.artifact_id == artifact_id,
               ArtifactRevision.revision_no > from_revision,
               ArtifactRevision.revision_no <= to_revision)
        .order_by(ArtifactRevision.revision_no.asc(), ArtifactOperation.op_index.asc())
    ).scalars().all())


def list_operations_upto(db: Session, artifact_id: int, to_revision: int) -> list[ArtifactOperation]:
    """返回 revision_no <= to_revision 的全部 Operation（用于状态回放）。"""
    return list(db.execute(
        select(ArtifactOperation)
        .join(ArtifactRevision, ArtifactRevision.id == ArtifactOperation.revision_id)
        .where(ArtifactRevision.artifact_id == artifact_id,
               ArtifactRevision.revision_no <= to_revision)
        .order_by(ArtifactRevision.revision_no.asc(), ArtifactOperation.op_index.asc())
    ).scalars().all())
