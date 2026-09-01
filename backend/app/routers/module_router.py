from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.test_module import (
    MoveModuleRequest,
    ReorderRequest,
    TestModuleCreate,
    TestModuleResponse,
    TestModuleTreeResponse,
    TestModuleUpdate,
)
from app.services.permission_service import require_project_read, require_project_write
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
def create_module_api(
    module_data: TestModuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_write(db, current_user, module_data.project_id)
    try:
        return create_module(db, module_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tree", response_model=list[TestModuleTreeResponse], summary="查询模块树")
def get_tree(
    project_id: int = Query(..., description="项目ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_read(db, current_user, project_id)
    return get_module_tree(db, project_id)


@router.put("/reorder", summary="调整同级排序")
def reorder(
    reorder_data: ReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not reorder_data.ordered_module_ids:
        raise HTTPException(status_code=400, detail="排序列表不能为空")
    first_module = get_module_by_id(db, reorder_data.ordered_module_ids[0])
    if not first_module:
        raise HTTPException(status_code=404, detail="模块不存在")
    require_project_write(db, current_user, first_module.project_id)
    success, error = reorder_modules(db, reorder_data)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "排序调整成功"}


@router.get("/{module_id}", response_model=TestModuleResponse, summary="查询模块详情")
def get_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    module = get_module_by_id(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    require_project_read(db, current_user, module.project_id)
    return module


@router.put("/{module_id}", response_model=TestModuleResponse, summary="修改模块")
def update_module_api(
    module_id: int,
    module_data: TestModuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = get_module_by_id(db, module_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模块不存在")
    require_project_write(db, current_user, existing.project_id)
    module = update_module(db, module_id, module_data)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    return module


@router.delete("/{module_id}", summary="删除模块")
def delete_module_api(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = get_module_by_id(db, module_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模块不存在")
    require_project_write(db, current_user, existing.project_id)
    success, error = delete_module(db, module_id)
    if not success:
        if error == "模块不存在":
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)
    return {"message": "模块删除成功"}


@router.put("/{module_id}/move", response_model=TestModuleResponse, summary="移动模块")
def move_module_api(
    module_id: int,
    move_data: MoveModuleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = get_module_by_id(db, module_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模块不存在")
    require_project_write(db, current_user, existing.project_id)
    try:
        module = move_module(db, module_id, move_data)
        if not module:
            raise HTTPException(status_code=404, detail="模块不存在")
        return module
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
