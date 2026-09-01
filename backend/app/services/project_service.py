from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.api_case import APICase
from app.models.function_case import FunctionCase
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.scene import Scene
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(db: Session, project_data: ProjectCreate) -> Project:
    db_project = Project(
        name=project_data.name,
        description=project_data.description,
        status=project_data.status,
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def get_project_list(
    db: Session,
    keyword: str = None,
    status: str = None,
    allowed_project_ids: list[int] | None = None,
):
    query = db.query(Project).filter(Project.is_deleted == False)
    if allowed_project_ids is not None:
        if not allowed_project_ids:
            return []
        query = query.filter(Project.id.in_(allowed_project_ids))
    if keyword:
        query = query.filter(Project.name.contains(keyword))
    if status:
        query = query.filter(Project.status == status)
    return query.order_by(Project.id.desc()).all()


def get_project_summary_list(
    db: Session,
    keyword: str = None,
    status: str = None,
    allowed_project_ids: list[int] | None = None,
):
    api_counts = (
        db.query(
            APICase.project_id.label("project_id"),
            func.count(APICase.id).label("api_case_count"),
        )
        .filter(APICase.is_deleted == False)
        .group_by(APICase.project_id)
        .subquery()
    )
    function_counts = (
        db.query(
            FunctionCase.project_id.label("project_id"),
            func.count(FunctionCase.id).label("function_case_count"),
        )
        .filter(FunctionCase.is_deleted == False)
        .group_by(FunctionCase.project_id)
        .subquery()
    )
    requirement_counts = (
        db.query(
            RequirementDoc.project_id.label("project_id"),
            func.count(RequirementDoc.id).label("requirement_count"),
        )
        .filter(RequirementDoc.is_deleted == False)
        .group_by(RequirementDoc.project_id)
        .subquery()
    )
    scene_counts = (
        db.query(
            Scene.project_id.label("project_id"),
            func.count(Scene.id).label("scene_count"),
        )
        .filter(Scene.is_deleted == False)
        .group_by(Scene.project_id)
        .subquery()
    )

    query = (
        db.query(
            Project.id,
            Project.name,
            Project.description,
            Project.status,
            Project.created_at,
            Project.updated_at,
            func.coalesce(api_counts.c.api_case_count, 0).label("api_case_count"),
            func.coalesce(function_counts.c.function_case_count, 0).label("function_case_count"),
            func.coalesce(requirement_counts.c.requirement_count, 0).label("requirement_count"),
            func.coalesce(scene_counts.c.scene_count, 0).label("scene_count"),
        )
        .outerjoin(api_counts, api_counts.c.project_id == Project.id)
        .outerjoin(function_counts, function_counts.c.project_id == Project.id)
        .outerjoin(requirement_counts, requirement_counts.c.project_id == Project.id)
        .outerjoin(scene_counts, scene_counts.c.project_id == Project.id)
        .filter(Project.is_deleted == False)
    )
    if allowed_project_ids is not None:
        if not allowed_project_ids:
            return []
        query = query.filter(Project.id.in_(allowed_project_ids))
    if keyword:
        query = query.filter(Project.name.contains(keyword))
    if status:
        query = query.filter(Project.status == status)

    return [dict(row._mapping) for row in query.order_by(Project.id.desc()).all()]


def get_project_by_id(db: Session, project_id: int):
    return db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False,
    ).first()


def update_project(db: Session, project_id: int, project_data: ProjectUpdate) -> Project | None:
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return None

    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_project, field, value)

    db.commit()
    db.refresh(db_project)
    return db_project


def soft_delete_project(db: Session, project_id: int) -> bool:
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return False

    db_project.is_deleted = True
    db.commit()
    return True
