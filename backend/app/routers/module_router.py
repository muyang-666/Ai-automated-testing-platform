from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.test_module import (
    MoveModuleRequest,
    ReorderRequest,
    TestModuleCreate,
    TestModuleResponse,
    TestModuleTreeResponse,
    TestModuleUpdate,
)
from app.services.test_module_service import (
    create_module,
    delete_module,
    get_module_by_id,
    get_module_tree,
    move_module,
    reorder_modules,
    update_module,
)

router = APIRouter(prefix="/modules", tags=["Modules"])


@router.post("", response_model=TestModuleResponse, summary="创建模块")
def create_module_api(module_data: TestModuleCreate, db: Session = Depends(get_db)):
    try:
        return create_module(db, module_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tree", response_model=list[TestModuleTreeResponse], summary="查询模块树")
def get_tree(project_id: int = Query(..., description="项目ID"), db: Session = Depends(get_db)):
    return get_module_tree(db, project_id)


@router.put("/reorder", summary="调整同级排序")
def reorder(reorder_data: ReorderRequest, db: Session = Depends(get_db)):
    success, error = reorder_modules(db, reorder_data)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "排序调整成功"}


@router.get("/{module_id}", response_model=TestModuleResponse, summary="查询模块详情")
def get_module(module_id: int, db: Session = Depends(get_db)):
    module = get_module_by_id(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    return module


@router.put("/{module_id}", response_model=TestModuleResponse, summary="修改模块")
def update_module_api(module_id: int, module_data: TestModuleUpdate, db: Session = Depends(get_db)):
    module = update_module(db, module_id, module_data)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    return module


@router.delete("/{module_id}", summary="删除模块")
def delete_module_api(module_id: int, db: Session = Depends(get_db)):
    success, error = delete_module(db, module_id)
    if not success:
        if error == "模块不存在":
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)
    return {"message": "模块删除成功"}


@router.put("/{module_id}/move", response_model=TestModuleResponse, summary="移动模块")
def move_module_api(module_id: int, move_data: MoveModuleRequest, db: Session = Depends(get_db)):
    try:
        module = move_module(db, module_id, move_data)
        if not module:
            raise HTTPException(status_code=404, detail="模块不存在")
        return module
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
