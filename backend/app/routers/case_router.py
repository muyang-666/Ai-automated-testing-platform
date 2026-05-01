from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api_case import APICaseCreate, APICaseResponse, APICaseUpdate
from app.services.case_service import (
    create_case,
    delete_case,
    get_case_by_id,
    get_case_list,
    update_case,
)

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("", response_model=APICaseResponse, summary="创建测试用例")
def create_api_case(case_data: APICaseCreate, db: Session = Depends(get_db)):
    return create_case(db, case_data)


@router.get("", response_model=list[APICaseResponse], summary="查询测试用例列表")
def list_api_cases(
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    module_id: Optional[int] = Query(default=None, description="按模块筛选"),
    include_children: bool = Query(default=False, description="是否包含子模块下的用例"),
    keyword: Optional[str] = Query(default=None, description="按名称或描述模糊搜索"),
    case_type: Optional[str] = Query(default=None, description="按用例类型筛选"),
    source: Optional[str] = Query(default=None, description="按来源筛选"),
    priority: Optional[str] = Query(default=None, description="按优先级筛选"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_case_list(
        db,
        project_id=project_id,
        module_id=module_id,
        include_children=include_children,
        keyword=keyword,
        case_type=case_type,
        source=source,
        priority=priority,
        status=status,
    )


@router.get("/{case_id}", response_model=APICaseResponse, summary="查询测试用例详情")
def get_api_case(case_id: int, db: Session = Depends(get_db)):
    case = get_case_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return case


@router.put("/{case_id}", response_model=APICaseResponse, summary="更新测试用例")
def update_api_case(case_id: int, case_data: APICaseUpdate, db: Session = Depends(get_db)):
    case = update_case(db, case_id, case_data)
    if not case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return case


@router.delete("/{case_id}", summary="删除测试用例")
def delete_api_case(case_id: int, db: Session = Depends(get_db)):
    success = delete_case(db, case_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return {"message": "测试用例删除成功"}
