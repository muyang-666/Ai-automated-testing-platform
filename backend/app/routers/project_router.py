from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectSummaryResponse, ProjectUpdate
from app.services.project_service import (
    create_project,
    get_project_by_id,
    get_project_list,
    get_project_summary_list,
    soft_delete_project,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectResponse, summary="创建项目")
def create_project_api(project_data: ProjectCreate, db: Session = Depends(get_db)):
    return create_project(db, project_data)


@router.get("", response_model=list[ProjectResponse], summary="查询项目列表")
def list_projects(
    keyword: Optional[str] = Query(default=None, description="按名称模糊搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_project_list(db, keyword=keyword, status=status)


@router.get("/summary", response_model=list[ProjectSummaryResponse], summary="查询项目统计列表")
def list_project_summaries(
    keyword: Optional[str] = Query(default=None, description="按名称模糊搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_project_summary_list(db, keyword=keyword, status=status)


@router.get("/{project_id}", response_model=ProjectResponse, summary="查询项目详情")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectResponse, summary="修改项目")
def update_project_api(project_id: int, project_data: ProjectUpdate, db: Session = Depends(get_db)):
    project = update_project(db, project_id, project_data)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.delete("/{project_id}", summary="删除项目")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    success = soft_delete_project(db, project_id)
    if not success:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"message": "项目删除成功"}
