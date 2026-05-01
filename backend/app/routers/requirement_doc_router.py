from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.requirement_doc import (
    RequirementDocCreate,
    RequirementDocResponse,
    RequirementDocUpdate,
)
from app.services.requirement_doc_service import (
    create_requirement_doc,
    delete_requirement_doc,
    get_requirement_doc_by_id,
    get_requirement_doc_list,
    update_requirement_doc,
)

router = APIRouter(prefix="/requirements", tags=["Requirements"])


@router.post("", response_model=RequirementDocResponse, summary="创建需求文本")
def create_requirement(doc_data: RequirementDocCreate, db: Session = Depends(get_db)):
    return create_requirement_doc(db, doc_data)


@router.get("", response_model=list[RequirementDocResponse], summary="查询需求文本列表")
def list_requirements(
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    module_id: Optional[int] = Query(default=None, description="按模块筛选"),
    include_children: bool = Query(default=False, description="是否包含子模块"),
    keyword: Optional[str] = Query(default=None, description="按标题或内容模糊搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    requirement_type: Optional[str] = Query(default=None, description="按需求类型筛选"),
    db: Session = Depends(get_db),
):
    return get_requirement_doc_list(
        db,
        project_id=project_id,
        module_id=module_id,
        include_children=include_children,
        keyword=keyword,
        status=status,
        requirement_type=requirement_type,
    )


@router.get("/{requirement_id}", response_model=RequirementDocResponse, summary="查询需求文本详情")
def get_requirement(requirement_id: int, db: Session = Depends(get_db)):
    doc = get_requirement_doc_by_id(db, requirement_id)
    if not doc:
        raise HTTPException(status_code=404, detail="需求文本不存在")
    return doc


@router.put("/{requirement_id}", response_model=RequirementDocResponse, summary="修改需求文本")
def update_requirement(
    requirement_id: int, doc_data: RequirementDocUpdate, db: Session = Depends(get_db)
):
    doc = update_requirement_doc(db, requirement_id, doc_data)
    if not doc:
        raise HTTPException(status_code=404, detail="需求文本不存在")
    return doc


@router.delete("/{requirement_id}", summary="删除需求文本")
def delete_requirement(requirement_id: int, db: Session = Depends(get_db)):
    success = delete_requirement_doc(db, requirement_id)
    if not success:
        raise HTTPException(status_code=404, detail="需求文本不存在")
    return {"message": "需求文本删除成功"}
