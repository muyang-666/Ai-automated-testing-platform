from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_case import APICase
from app.models.test_run import TestRun
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.services.permission_service import require_project_read, require_project_write
from app.services.ai_service import generate_case_test_code_by_rule
from app.services.analysis_service import (
    generate_ai_analysis,
    get_ai_analysis_by_run_id,
)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/generate-rule-case/{case_id}", summary="规则生成测试代码")
def generate_case_by_rule(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    api_case = db.query(APICase).filter(APICase.id == case_id, APICase.is_deleted == False).first()
    if not api_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    require_project_write(db, current_user, api_case.project_id)
    try:
        return generate_case_test_code_by_rule(db, case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analyze/{run_id}", summary="AI分析失败日志")
def analyze_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    api_case = db.query(APICase).filter(APICase.id == run.case_id).first()
    require_project_write(db, current_user, api_case.project_id if api_case else None)
    try:
        return generate_ai_analysis(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/analyze/{run_id}", summary="查询最新AI分析结果")
def get_latest_analysis(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    api_case = db.query(APICase).filter(APICase.id == run.case_id).first()
    require_project_read(db, current_user, api_case.project_id if api_case else None)
    result = get_ai_analysis_by_run_id(db, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到分析结果")
    return result

