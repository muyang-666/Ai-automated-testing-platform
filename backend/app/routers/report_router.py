from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.report import ReportResponse, ReportSummaryResponse
from app.services.permission_service import require_admin_role, require_project_read, require_project_write
from app.services.report_service import (
    generate_project_report,
    get_report_by_id,
    get_report_list,
    get_report_summary,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# 一键生成项目级测试报告
@router.post("/generate-project", response_model=ReportResponse, summary="一键生成项目级测试报告")
def generate_project_report_api(
    project_id: Optional[int] = Query(default=None, description="按项目生成报告"),
    module_id: Optional[int] = Query(default=None, description="按模块生成报告"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_write(db, current_user, project_id)
    try:
        return generate_project_report(db, project_id=project_id, module_id=module_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# 查询报告统计汇总
@router.get("/summary", response_model=ReportSummaryResponse, summary="查询报告统计汇总")
def get_report_summary_api(
    project_id: Optional[int] = Query(default=None, description="按项目统计"),
    module_id: Optional[int] = Query(default=None, description="按模块统计"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_read(db, current_user, project_id)
    try:
        return get_report_summary(db, project_id=project_id, module_id=module_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取报告统计失败: {str(e)}")


# 查询报告列表
@router.get("", response_model=list[ReportResponse], summary="查询测试报告列表")
def list_reports_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 报告表当前未保存 project_id，非管理员暂不开放全量报告列表，避免跨项目泄露。
    require_admin_role(db, current_user)
    return get_report_list(db)


# 查询报告详情
@router.get("/{report_id}", response_model=ReportResponse, summary="查询测试报告详情")
def get_report_api(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin_role(db, current_user)
    report = get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="测试报告不存在")
    return report
