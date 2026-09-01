from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.schemas.api_case import APICaseCreate, APICaseUpdate
from app.services.test_module_service import get_child_module_ids


def create_case(db: Session, case_data: APICaseCreate) -> APICase:
    db_case = APICase(
        name=case_data.name,
        description=case_data.description,
        method=case_data.method.upper(),
        url=case_data.url,
        headers=case_data.headers,
        body=case_data.body,
        expected_result=case_data.expected_result,
        project_id=case_data.project_id,
        module_id=case_data.module_id,
        case_type=case_data.case_type,
        source=case_data.source,
        priority=case_data.priority,
        status=case_data.status,
    )
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


def get_case_list(
    db: Session,
    project_id: int = None,
    module_id: int = None,
    include_children: bool = False,
    keyword: str = None,
    case_type: str = None,
    source: str = None,
    priority: str = None,
    status: str = None,
    allowed_project_ids: list[int] | None = None,
):
    query = db.query(APICase).filter(APICase.is_deleted == False)

    if allowed_project_ids is not None:
        if not allowed_project_ids:
            return []
        query = query.filter(APICase.project_id.in_(allowed_project_ids))

    if project_id is not None:
        query = query.filter(APICase.project_id == project_id)

    if module_id is not None:
        if include_children:
            child_ids = get_child_module_ids(db, module_id)
            query = query.filter(APICase.module_id.in_([module_id] + child_ids))
        else:
            query = query.filter(APICase.module_id == module_id)

    if keyword:
        query = query.filter(
            (APICase.name.contains(keyword)) | (APICase.description.contains(keyword))
        )

    if case_type:
        query = query.filter(APICase.case_type == case_type)

    if source:
        query = query.filter(APICase.source == source)

    if priority:
        query = query.filter(APICase.priority == priority)

    if status:
        query = query.filter(APICase.status == status)

    return query.order_by(APICase.id.desc()).all()


def get_case_by_id(db: Session, case_id: int):
    return db.query(APICase).filter(
        APICase.id == case_id,
        APICase.is_deleted == False,
    ).first()


def update_case(db: Session, case_id: int, case_data: APICaseUpdate) -> APICase | None:
    db_case = get_case_by_id(db, case_id)
    if not db_case:
        return None

    update_data = case_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "method" and value is not None:
            setattr(db_case, field, value.upper())
        else:
            setattr(db_case, field, value)

    db_case.generated_test_code = None

    db.commit()
    db.refresh(db_case)
    return db_case


def delete_case(db: Session, case_id: int) -> bool:
    db_case = get_case_by_id(db, case_id)
    if not db_case:
        return False

    db_case.is_deleted = True
    db.commit()
    return True
