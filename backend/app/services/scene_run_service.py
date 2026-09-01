from sqlalchemy.orm import Session

from app.models.scene_run import SceneRun
from app.models.scene_step_run import SceneStepRun


def get_scene_run_list(
    db: Session,
    scene_id: int = None,
    project_id: int = None,
    status: str = None,
    allowed_project_ids: list[int] | None = None,
):
    query = db.query(SceneRun)

    if allowed_project_ids is not None:
        if not allowed_project_ids:
            return []
        query = query.filter(SceneRun.project_id.in_(allowed_project_ids))

    if scene_id is not None:
        query = query.filter(SceneRun.scene_id == scene_id)

    if project_id is not None:
        query = query.filter(SceneRun.project_id == project_id)

    if status:
        query = query.filter(SceneRun.status == status)

    return query.order_by(SceneRun.id.desc()).all()


def get_scene_run_by_id(db: Session, run_id: int) -> SceneRun | None:
    return db.query(SceneRun).filter(SceneRun.id == run_id).first()


def get_scene_step_runs_by_run_id(db: Session, run_id: int):
    return (
        db.query(SceneStepRun)
        .filter(SceneStepRun.scene_run_id == run_id)
        .order_by(SceneStepRun.step_order.asc(), SceneStepRun.id.asc())
        .all()
    )


def get_scene_run_detail(db: Session, run_id: int):
    scene_run = get_scene_run_by_id(db, run_id)
    if not scene_run:
        return None
    step_runs = get_scene_step_runs_by_run_id(db, run_id)
    scene_run.steps = step_runs
    return scene_run
