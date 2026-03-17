from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.report import ReportGenerateResponse, ReportResponse
from app.services.report_service import generate_report, get_report_by_run_id

router = APIRouter(prefix="/reports", tags=["Reports"])

# 根据某次执行记录 run_id，生成一份报告
@router.post("/{run_id}/generate", response_model=ReportGenerateResponse, summary="生成测试总结报告")
def generate_test_report(run_id: int, db: Session = Depends(get_db)):
    try:
        return generate_report(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成测试报告失败: {str(e)}")

# 查看某次 run 最新的一份报告
@router.get("/{run_id}", response_model=ReportResponse, summary="查看测试报告")
def get_test_report(run_id: int, db: Session = Depends(get_db)):
    report = get_report_by_run_id(db, run_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到对应测试报告")
    return report