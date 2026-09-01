from typing import Optional

from sqlalchemy.orm import Session

from app.models.api_document import ApiDocument
from app.schemas.api_document import ApiDocumentCreate, ApiDocumentUpdate
from app.services.test_module_service import get_child_module_ids


def create_api_document(db: Session, data: ApiDocumentCreate) -> ApiDocument:
    doc = ApiDocument(
        project_id=data.project_id,
        module_id=data.module_id,
        name=data.name,
        description=data.description,
        method=(data.method or "").upper(),
        url=data.url or "",
        headers_json=data.headers_json,
        params_json=data.params_json,
        body_json=data.body_json,
        response_example_json=data.response_example_json,
        content=data.content,
        supplementary_prompt=data.supplementary_prompt,
        status=data.status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_api_document_list(
    db: Session,
    project_id: Optional[int] = None,
    module_id: Optional[int] = None,
    include_children: bool = False,
    keyword: Optional[str] = None,
    method: Optional[str] = None,
    status: Optional[str] = None,
    allowed_project_ids: list[int] | None = None,
) -> list[ApiDocument]:
    query = db.query(ApiDocument).filter(ApiDocument.is_deleted == False)

    if allowed_project_ids is not None:
        if not allowed_project_ids:
            return []
        query = query.filter(ApiDocument.project_id.in_(allowed_project_ids))

    if project_id is not None:
        query = query.filter(ApiDocument.project_id == project_id)

    if module_id is not None:
        if include_children:
            child_ids = get_child_module_ids(db, module_id)
            query = query.filter(ApiDocument.module_id.in_([module_id] + child_ids))
        else:
            query = query.filter(ApiDocument.module_id == module_id)

    if keyword:
        query = query.filter(
            (ApiDocument.name.contains(keyword))
            | (ApiDocument.description.contains(keyword))
            | (ApiDocument.url.contains(keyword))
            | (ApiDocument.content.contains(keyword))
        )

    if method:
        query = query.filter(ApiDocument.method == method.upper())

    if status:
        query = query.filter(ApiDocument.status == status)

    return query.order_by(ApiDocument.id.desc()).all()


def get_api_document_by_id(db: Session, document_id: int) -> Optional[ApiDocument]:
    return db.query(ApiDocument).filter(
        ApiDocument.id == document_id,
        ApiDocument.is_deleted == False,
    ).first()


def update_api_document(
    db: Session, document_id: int, data: ApiDocumentUpdate
) -> Optional[ApiDocument]:
    doc = get_api_document_by_id(db, document_id)
    if not doc:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "method" and value is not None:
            setattr(doc, field, value.upper())
        else:
            setattr(doc, field, value)

    db.commit()
    db.refresh(doc)
    return doc


def delete_api_document(db: Session, document_id: int) -> bool:
    doc = get_api_document_by_id(db, document_id)
    if not doc:
        return False
    doc.is_deleted = True
    db.commit()
    return True
