from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.scene import (
    ReorderSceneStepsRequest,
    SceneCreate,
    SceneExecuteResponse,
    SceneResponse,
    SceneStepCreate,
    SceneStepResponse,
    SceneStepUpdate,
    SceneUpdate,
)
from app.schemas.scene_run import (
    SceneRunDetailResponse,
    SceneRunResponse,
)
from app.services.scene_chain_service import execute_scene_chain
from app.services.scene_run_service import (
    get_scene_run_detail,
    get_scene_run_list,
)
from app.services.scene_service import (
    create_scene,
    create_scene_step,
    delete_scene,
    delete_scene_step,
    execute_scene,
    get_scene_by_id,
    get_scene_list,
    get_scene_steps,
    reorder_scene_steps,
    update_scene,
    update_scene_step,
)

router = APIRouter(prefix="/scenes", tags=["Scenes"])


@router.post("", response_model=SceneResponse, summary="创建场景")
def create_scene_api(data: SceneCreate, db: Session = Depends(get_db)):
    return create_scene(db, data)


@router.get("", response_model=list[SceneResponse], summary="查询场景列表")
def list_scenes_api(
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    module_id: Optional[int] = Query(default=None, description="按模块筛选"),
    include_children: bool = Query(default=False, description="是否包含子模块"),
    keyword: Optional[str] = Query(default=None, description="按名称或描述模糊搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_scene_list(
        db,
        project_id=project_id,
        module_id=module_id,
        include_children=include_children,
        keyword=keyword,
        status=status,
    )


@router.get("/runs", response_model=list[SceneRunResponse], summary="查询场景执行历史列表")
def list_scene_runs_api(
    scene_id: Optional[int] = Query(default=None, description="按场景筛选"),
    project_id: Optional[int] = Query(default=None, description="按项目筛选"),
    status: Optional[str] = Query(default=None, description="按执行状态筛选"),
    db: Session = Depends(get_db),
):
    return get_scene_run_list(db, scene_id=scene_id, project_id=project_id, status=status)


@router.get("/runs/{run_id}", response_model=SceneRunDetailResponse, summary="查询场景执行详情")
def get_scene_run_api(run_id: int, db: Session = Depends(get_db)):
    detail = get_scene_run_detail(db, run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return detail


@router.get("/{scene_id}/runs", response_model=list[SceneRunResponse], summary="查询某个场景的执行历史")
def list_scene_runs_by_scene_api(scene_id: int, db: Session = Depends(get_db)):
    return get_scene_run_list(db, scene_id=scene_id)


@router.get("/{scene_id}", response_model=SceneResponse, summary="查询场景详情")
def get_scene_api(scene_id: int, db: Session = Depends(get_db)):
    scene = get_scene_by_id(db, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


@router.put("/{scene_id}", response_model=SceneResponse, summary="更新场景")
def update_scene_api(scene_id: int, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = update_scene(db, scene_id, data)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


@router.delete("/{scene_id}", summary="删除场景")
def delete_scene_api(scene_id: int, db: Session = Depends(get_db)):
    success = delete_scene(db, scene_id)
    if not success:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"message": "场景删除成功"}


@router.get("/{scene_id}/steps", response_model=list[SceneStepResponse], summary="查询场景步骤列表")
def list_scene_steps_api(scene_id: int, db: Session = Depends(get_db)):
    steps = get_scene_steps(db, scene_id)
    if steps is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    return steps


@router.post("/{scene_id}/steps", response_model=SceneStepResponse, summary="新增场景步骤")
def create_scene_step_api(scene_id: int, data: SceneStepCreate, db: Session = Depends(get_db)):
    try:
        return create_scene_step(db, scene_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/steps/{step_id}", response_model=SceneStepResponse, summary="编辑场景步骤")
def update_scene_step_api(step_id: int, data: SceneStepUpdate, db: Session = Depends(get_db)):
    try:
        return update_scene_step(db, step_id, data)
    except ValueError as e:
        if "不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/steps/{step_id}", summary="删除场景步骤")
def delete_scene_step_api(step_id: int, db: Session = Depends(get_db)):
    success = delete_scene_step(db, step_id)
    if not success:
        raise HTTPException(status_code=404, detail="场景步骤不存在")
    return {"message": "场景步骤删除成功"}


@router.put("/{scene_id}/steps/reorder", summary="调整场景步骤顺序")
def reorder_scene_steps_api(
    scene_id: int, data: ReorderSceneStepsRequest, db: Session = Depends(get_db)
):
    try:
        reorder_scene_steps(db, scene_id, data)
        return {"message": "步骤排序调整成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{scene_id}/execute", response_model=SceneExecuteResponse, summary="执行场景（pytest 方式）")
def execute_scene_api(scene_id: int, db: Session = Depends(get_db)):
    try:
        return execute_scene(db, scene_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{scene_id}/run-chain", summary="真实串联执行场景")
def run_chain_api(scene_id: int, db: Session = Depends(get_db)):
    try:
        return execute_scene_chain(db, scene_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"场景执行异常：{str(e)}")
