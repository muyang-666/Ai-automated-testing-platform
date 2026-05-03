from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api_document import ApiDocumentCreate, ApiDocumentResponse, ApiDocumentUpdate
from app.schemas.api_document_generation import (
    GenerateApiCasesRequest,
    GenerateApiCasesResponse,
    SaveGeneratedApiCasesRequest,
    SaveGeneratedApiCasesResponse,
)
from app.services.api_document_generation_service import (
    generate_api_cases_from_document,
    save_generated_api_cases,
)
from app.services.api_document_service import (
    create_api_document,
    delete_api_document,
    get_api_document_by_id,
    get_api_document_list,
    update_api_document,
)

router = APIRouter(prefix="/api-documents", tags=["API Documents"])


# ── 生成接口必须在 {document_id} 之前定义 ──

@router.post("/generate-cases", response_model=GenerateApiCasesResponse, summary="根据接口文档生成接口测试用例预览")
def generate_cases_api(request: GenerateApiCasesRequest, db: Session = Depends(get_db)):
    return generate_api_cases_from_document(db, request)


@router.post("/save-generated-cases", response_model=SaveGeneratedApiCasesResponse, summary="保存生成的接口测试用例")
def save_generated_cases_api(request: SaveGeneratedApiCasesRequest, db: Session = Depends(get_db)):
    try:
        return save_generated_api_cases(db, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── CRUD 接口 ──

@router.post("", response_model=ApiDocumentResponse, summary="创建接口文档")
def create_document_api(data: ApiDocumentCreate, db: Session = Depends(get_db)):
    return create_api_document(db, data)


@router.get("", response_model=list[ApiDocumentResponse], summary="查询接口文档列表")
def list_documents(
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    module_id: Optional[int] = Query(default=None, description="按模块筛选"),
    include_children: bool = Query(default=False, description="包含子模块"),
    keyword: Optional[str] = Query(default=None, description="关键词搜索"),
    method: Optional[str] = Query(default=None, description="按请求方法筛选"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_api_document_list(
        db,
        project_id=project_id,
        module_id=module_id,
        include_children=include_children,
        keyword=keyword,
        method=method,
        status=status,
    )


@router.get("/{document_id}", response_model=ApiDocumentResponse, summary="查询接口文档详情")
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = get_api_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="接口文档不存在")
    return doc


@router.put("/{document_id}", response_model=ApiDocumentResponse, summary="修改接口文档")
def update_document(document_id: int, data: ApiDocumentUpdate, db: Session = Depends(get_db)):
    doc = update_api_document(db, document_id, data)
    if not doc:
        raise HTTPException(status_code=404, detail="接口文档不存在")
    return doc


@router.delete("/{document_id}", summary="删除接口文档")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    success = delete_api_document(db, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="接口文档不存在")
    return {"message": "接口文档删除成功"}
