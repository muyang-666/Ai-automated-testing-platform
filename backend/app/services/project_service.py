from sqlalchemy.orm import Session

from app.models.project import Project
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


def get_project_list(db: Session, keyword: str = None, status: str = None):
    query = db.query(Project).filter(Project.is_deleted == False)
    if keyword:
        query = query.filter(Project.name.contains(keyword))
    if status:
        query = query.filter(Project.status == status)
    return query.order_by(Project.id.desc()).all()


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
