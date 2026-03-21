from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.report import ReportResponse
from app.services.report_service import (
    generate_project_report,
    get_report_by_id,
    get_report_list,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# 一键生成项目级测试报告
@router.post("/generate-project", response_model=ReportResponse, summary="一键生成项目级测试报告")
def generate_project_report_api(db: Session = Depends(get_db)):
    try:
        return generate_project_report(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# 查询报告列表
@router.get("", response_model=list[ReportResponse], summary="查询测试报告列表")
def list_reports_api(db: Session = Depends(get_db)):
    return get_report_list(db)


# 查询报告详情
@router.get("/{report_id}", response_model=ReportResponse, summary="查询测试报告详情")
def get_report_api(report_id: int, db: Session = Depends(get_db)):
    report = get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="测试报告不存在")
    return report