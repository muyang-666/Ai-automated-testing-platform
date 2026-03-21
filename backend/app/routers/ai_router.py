from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ai_service import (
    generate_case_test_code_by_llm,
    generate_case_test_code_by_rule,
)
from app.services.analysis_service import (
    generate_ai_analysis,
    get_ai_analysis_by_run_id,
)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/generate-case/{case_id}", summary="AI生成测试代码")
def generate_case_by_llm(case_id: int, db: Session = Depends(get_db)):
    try:
        return generate_case_test_code_by_llm(db, case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-rule-case/{case_id}", summary="规则生成测试代码")
def generate_case_by_rule(case_id: int, db: Session = Depends(get_db)):
    try:
        return generate_case_test_code_by_rule(db, case_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analyze/{run_id}", summary="AI分析失败日志")
def analyze_run(run_id: int, db: Session = Depends(get_db)):
    try:
        return generate_ai_analysis(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/analyze/{run_id}", summary="查询最新AI分析结果")
def get_latest_analysis(run_id: int, db: Session = Depends(get_db)):
    result = get_ai_analysis_by_run_id(db, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到分析结果")
    return result

