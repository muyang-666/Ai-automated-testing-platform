from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.scene import Scene
from app.models.scene_step import SceneStep
from app.schemas.scene import SceneCreate, SceneUpdate, SceneStepCreate
from app.services.run_service import execute_case_test


# 场景 ORM 对象转字典
def serialize_scene(scene: Scene):
    return {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "created_at": scene.created_at,
        "updated_at": scene.updated_at,
    }


# 场景步骤 ORM + case 信息 转字典
def serialize_scene_step(step: SceneStep, api_case: APICase):
    return {
        "id": step.id,
        "scene_id": step.scene_id,
        "step_order": step.step_order,
        "case_id": step.case_id,
        "case_name": api_case.name,
        "case_url": api_case.url,
        "created_at": step.created_at,
    }


# 创建场景
def create_scene(db: Session, data: SceneCreate):
    scene = Scene(
        name=data.name,
        description=data.description,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return serialize_scene(scene)


# 查询场景列表
def get_scene_list(db: Session):
    scenes = db.query(Scene).order_by(Scene.id.desc()).all()
    return [serialize_scene(scene) for scene in scenes]


# 查询场景详情
def get_scene_by_id(db: Session, scene_id: int):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        return None
    return serialize_scene(scene)


# 更新场景
def update_scene(db: Session, scene_id: int, data: SceneUpdate):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        return None

    scene.name = data.name
    scene.description = data.description

    db.commit()
    db.refresh(scene)
    return serialize_scene(scene)


# 删除场景
def delete_scene(db: Session, scene_id: int) -> bool:
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        return False

    # 先删场景步骤，再删场景
    db.query(SceneStep).filter(SceneStep.scene_id == scene_id).delete()
    db.delete(scene)
    db.commit()
    return True


# 查询某个场景下的步骤列表
def get_scene_steps(db: Session, scene_id: int):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        return None

    steps = (
        db.query(SceneStep)
        .filter(SceneStep.scene_id == scene_id)
        .order_by(SceneStep.step_order.asc(), SceneStep.id.asc())
        .all()
    )

    result = []
    for step in steps:
        api_case = db.query(APICase).filter(APICase.id == step.case_id).first()
        if api_case:
            result.append(serialize_scene_step(step, api_case))

    return result


# 新增场景步骤
def create_scene_step(db: Session, scene_id: int, data: SceneStepCreate):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise ValueError("场景不存在")

    api_case = db.query(APICase).filter(APICase.id == data.case_id).first()
    if not api_case:
        raise ValueError("关联测试用例不存在")

    # 同一个场景内，步骤顺序不能重复
    existed_step = (
        db.query(SceneStep)
        .filter(SceneStep.scene_id == scene_id, SceneStep.step_order == data.step_order)
        .first()
    )
    if existed_step:
        raise ValueError("该场景下步骤顺序已存在，请更换 step_order")

    step = SceneStep(
        scene_id=scene_id,
        step_order=data.step_order,
        case_id=data.case_id,
    )
    db.add(step)
    db.commit()
    db.refresh(step)

    return serialize_scene_step(step, api_case)


# 删除场景步骤
def delete_scene_step(db: Session, step_id: int) -> bool:
    step = db.query(SceneStep).filter(SceneStep.id == step_id).first()
    if not step:
        return False

    db.delete(step)
    db.commit()
    return True


# 执行场景：按 step_order 从小到大执行，失败即停止
def execute_scene(db: Session, scene_id: int):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise ValueError("场景不存在")

    steps = (
        db.query(SceneStep)
        .filter(SceneStep.scene_id == scene_id)
        .order_by(SceneStep.step_order.asc(), SceneStep.id.asc())
        .all()
    )

    if not steps:
        raise ValueError("当前场景下没有可执行步骤")

    step_results = []
    passed_steps = 0
    failed_steps = 0

    for step in steps:
        api_case = db.query(APICase).filter(APICase.id == step.case_id).first()
        if not api_case:
            failed_steps += 1
            step_results.append({
                "step_order": step.step_order,
                "case_id": step.case_id,
                "case_name": "未知用例",
                "run_id": None,
                "status": "completed",
                "result": "failed",
                "error_message": "关联测试用例不存在",
            })
            break

        run_result = execute_case_test(db, step.case_id)

        current_step_result = {
            "step_order": step.step_order,
            "case_id": step.case_id,
            "case_name": api_case.name,
            "run_id": run_result.get("run_id"),
            "status": run_result.get("status", "completed"),
            "result": run_result.get("result", "failed"),
            "response_status_code": run_result.get("response_status_code"),
            "response_content": run_result.get("response_content"),
            "error_message": run_result.get("error_message"),
        }
        step_results.append(current_step_result)

        if run_result.get("result") == "passed":
            passed_steps += 1
        else:
            failed_steps += 1
            # V1 先采用失败即停止
            break

    final_result = "passed" if failed_steps == 0 else "failed"

    return {
        "scene_id": scene.id,
        "scene_name": scene.name,
        "total_steps": len(steps),
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "final_result": final_result,
        "steps": step_results,
    }