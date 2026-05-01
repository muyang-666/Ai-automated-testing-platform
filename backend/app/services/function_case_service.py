from sqlalchemy.orm import Session

from app.models.function_case import FunctionCase
from app.schemas.function_case import FunctionCaseCreate, FunctionCaseUpdate
from app.services.test_module_service import get_child_module_ids


def create_function_case(db: Session, case_data: FunctionCaseCreate) -> FunctionCase:
    db_case = FunctionCase(
        project_id=case_data.project_id,
        module_id=case_data.module_id,
        requirement_id=case_data.requirement_id,
        case_code=case_data.case_code,
        case_name=case_data.case_name,
        case_type=case_data.case_type,
        source=case_data.source,
        priority=case_data.priority,
        precondition=case_data.precondition,
        steps_json=case_data.steps_json,
        test_data_json=case_data.test_data_json,
        expected_result=case_data.expected_result,
        status=case_data.status,
        remark=case_data.remark,
    )
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


def get_function_case_list(
    db: Session,
    project_id: int = None,
    module_id: int = None,
    include_children: bool = False,
    requirement_id: int = None,
    keyword: str = None,
    case_type: str = None,
    source: str = None,
    priority: str = None,
    status: str = None,
):
    query = db.query(FunctionCase).filter(FunctionCase.is_deleted == False)

    if project_id is not None:
        query = query.filter(FunctionCase.project_id == project_id)

    if module_id is not None:
        if include_children:
            child_ids = get_child_module_ids(db, module_id)
            query = query.filter(FunctionCase.module_id.in_([module_id] + child_ids))
        else:
            query = query.filter(FunctionCase.module_id == module_id)

    if requirement_id is not None:
        query = query.filter(FunctionCase.requirement_id == requirement_id)

    if keyword:
        query = query.filter(
            (FunctionCase.case_code.contains(keyword))
            | (FunctionCase.case_name.contains(keyword))
            | (FunctionCase.precondition.contains(keyword))
            | (FunctionCase.expected_result.contains(keyword))
        )

    if case_type:
        query = query.filter(FunctionCase.case_type == case_type)

    if source:
        query = query.filter(FunctionCase.source == source)

    if priority:
        query = query.filter(FunctionCase.priority == priority)

    if status:
        query = query.filter(FunctionCase.status == status)

    return query.order_by(FunctionCase.id.desc()).all()


def get_function_case_by_id(db: Session, case_id: int) -> FunctionCase | None:
    return db.query(FunctionCase).filter(
        FunctionCase.id == case_id,
        FunctionCase.is_deleted == False,
    ).first()


def update_function_case(
    db: Session, case_id: int, case_data: FunctionCaseUpdate
) -> FunctionCase | None:
    db_case = get_function_case_by_id(db, case_id)
    if not db_case:
        return None

    update_data = case_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_case, field, value)

    db.commit()
    db.refresh(db_case)
    return db_case


def delete_function_case(db: Session, case_id: int) -> bool:
    db_case = get_function_case_by_id(db, case_id)
    if not db_case:
        return False

    db_case.is_deleted = True
    db.commit()
    return True
