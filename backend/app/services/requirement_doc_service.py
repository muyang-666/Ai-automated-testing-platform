from sqlalchemy.orm import Session

from app.models.requirement_doc import RequirementDoc
from app.schemas.requirement_doc import RequirementDocCreate, RequirementDocUpdate
from app.services.test_module_service import get_child_module_ids


def create_requirement_doc(db: Session, doc_data: RequirementDocCreate) -> RequirementDoc:
    db_doc = RequirementDoc(
        project_id=doc_data.project_id,
        module_id=doc_data.module_id,
        title=doc_data.title,
        content=doc_data.content,
        requirement_type=doc_data.requirement_type,
        status=doc_data.status,
        remark=doc_data.remark,
        supplementary_prompt=doc_data.supplementary_prompt,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


def get_requirement_doc_list(
    db: Session,
    project_id: int = None,
    module_id: int = None,
    include_children: bool = False,
    keyword: str = None,
    status: str = None,
    requirement_type: str = None,
):
    query = db.query(RequirementDoc).filter(RequirementDoc.is_deleted == False)

    if project_id is not None:
        query = query.filter(RequirementDoc.project_id == project_id)

    if module_id is not None:
        if include_children:
            child_ids = get_child_module_ids(db, module_id)
            query = query.filter(RequirementDoc.module_id.in_([module_id] + child_ids))
        else:
            query = query.filter(RequirementDoc.module_id == module_id)

    if keyword:
        query = query.filter(
            (RequirementDoc.title.contains(keyword)) | (RequirementDoc.content.contains(keyword))
        )

    if status:
        query = query.filter(RequirementDoc.status == status)

    if requirement_type:
        query = query.filter(RequirementDoc.requirement_type == requirement_type)

    return query.order_by(RequirementDoc.id.desc()).all()


def get_requirement_doc_by_id(db: Session, requirement_id: int) -> RequirementDoc | None:
    return db.query(RequirementDoc).filter(
        RequirementDoc.id == requirement_id,
        RequirementDoc.is_deleted == False,
    ).first()


def update_requirement_doc(
    db: Session, requirement_id: int, doc_data: RequirementDocUpdate
) -> RequirementDoc | None:
    db_doc = get_requirement_doc_by_id(db, requirement_id)
    if not db_doc:
        return None

    update_data = doc_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_doc, field, value)

    db.commit()
    db.refresh(db_doc)
    return db_doc


def delete_requirement_doc(db: Session, requirement_id: int) -> bool:
    db_doc = get_requirement_doc_by_id(db, requirement_id)
    if not db_doc:
        return False

    db_doc.is_deleted = True
    db.commit()
    return True
