from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.function_case import (
    FunctionCaseCreate,
    FunctionCaseResponse,
    FunctionCaseUpdate,
)
from app.schemas.function_case_generation import (
    GenerateFunctionCasesRequest,
    GenerateFunctionCasesResponse,
    SaveGeneratedFunctionCasesRequest,
    SaveGeneratedFunctionCasesResponse,
)
from app.services.function_case_service import (
    create_function_case,
    delete_function_case,
    get_function_case_by_id,
    get_function_case_list,
    update_function_case,
)
from app.services.function_case_generation_service import (
    generate_function_cases_from_requirement,
    save_generated_function_cases,
)

router = APIRouter(prefix="/function-cases", tags=["FunctionCases"])


@router.post("", response_model=FunctionCaseResponse, summary="创建功能测试用例")
def create_func_case(case_data: FunctionCaseCreate, db: Session = Depends(get_db)):
    return create_function_case(db, case_data)


@router.get("", response_model=list[FunctionCaseResponse], summary="查询功能测试用例列表")
def list_func_cases(
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    module_id: Optional[int] = Query(default=None, description="按模块筛选"),
    include_children: bool = Query(default=False, description="是否包含子模块"),
    requirement_id: Optional[int] = Query(default=None, description="按需求筛选"),
    keyword: Optional[str] = Query(default=None, description="按编号/名称/前置条件/预期结果模糊搜索"),
    case_type: Optional[str] = Query(default=None, description="按用例类型筛选"),
    source: Optional[str] = Query(default=None, description="按来源筛选"),
    priority: Optional[str] = Query(default=None, description="按优先级筛选"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_function_case_list(
        db,
        project_id=project_id,
        module_id=module_id,
        include_children=include_children,
        requirement_id=requirement_id,
        keyword=keyword,
        case_type=case_type,
        source=source,
        priority=priority,
        status=status,
    )


@router.post(
    "/generate-from-requirement",
    response_model=GenerateFunctionCasesResponse,
    summary="根据需求文本生成功能测试用例",
)
def generate_func_cases_from_requirement(
    request: GenerateFunctionCasesRequest, db: Session = Depends(get_db)
):
    return generate_function_cases_from_requirement(db, request)


@router.post(
    "/save-generated",
    response_model=SaveGeneratedFunctionCasesResponse,
    summary="保存勾选的功能测试用例",
)
def save_generated_func_cases(
    request: SaveGeneratedFunctionCasesRequest, db: Session = Depends(get_db)
):
    try:
        return save_generated_function_cases(db, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{case_id}", response_model=FunctionCaseResponse, summary="查询功能测试用例详情")
def get_func_case(case_id: int, db: Session = Depends(get_db)):
    case = get_function_case_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="功能测试用例不存在")
    return case


@router.put("/{case_id}", response_model=FunctionCaseResponse, summary="修改功能测试用例")
def update_func_case(
    case_id: int, case_data: FunctionCaseUpdate, db: Session = Depends(get_db)
):
    case = update_function_case(db, case_id, case_data)
    if not case:
        raise HTTPException(status_code=404, detail="功能测试用例不存在")
    return case


@router.delete("/{case_id}", summary="删除功能测试用例")
def delete_func_case(case_id: int, db: Session = Depends(get_db)):
    success = delete_function_case(db, case_id)
    if not success:
        raise HTTPException(status_code=404, detail="功能测试用例不存在")
    return {"message": "功能测试用例删除成功"}
