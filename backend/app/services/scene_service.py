from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.scene import Scene
from app.models.scene_step import SceneStep
from app.schemas.scene import (
    ReorderSceneStepsRequest,
    SceneCreate,
    SceneStepCreate,
    SceneStepUpdate,
    SceneUpdate,
)
from app.services.run_service import execute_case_test
from app.services.test_module_service import get_child_module_ids


def serialize_scene(scene: Scene) -> dict:
    return {
        "id": scene.id,
        "project_id": scene.project_id,
        "module_id": scene.module_id,
        "name": scene.name,
        "description": scene.description,
        "status": scene.status,
        "created_at": scene.created_at,
        "updated_at": scene.updated_at,
    }


def serialize_scene_step(step: SceneStep, api_case: APICase | None) -> dict:
    return {
        "id": step.id,
        "scene_id": step.scene_id,
        "step_order": step.step_order,
        "case_id": step.case_id,
        "case_name": api_case.name if api_case else "已删除用例",
        "case_url": api_case.url if api_case else "",
        "step_name": step.step_name,
        "extract_rules_json": step.extract_rules_json,
        "request_override_json": step.request_override_json,
        "assertions_json": step.assertions_json,
        "enabled": step.enabled,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


def create_scene(db: Session, data: SceneCreate) -> dict:
    scene = Scene(
        name=data.name,
        description=data.description,
        project_id=data.project_id,
        module_id=data.module_id,
        status=data.status,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return serialize_scene(scene)


def get_scene_list(
    db: Session,
    project_id: int = None,
    module_id: int = None,
    unbound_module: bool = False,
    include_children: bool = False,
    keyword: str = None,
    status: str = None,
):
    query = db.query(Scene).filter(Scene.is_deleted == False)

    if project_id is not None:
        query = query.filter(Scene.project_id == project_id)

    if unbound_module:
        query = query.filter(Scene.module_id.is_(None))
    elif module_id is not None:
        if include_children:
            child_ids = get_child_module_ids(db, module_id)
            query = query.filter(Scene.module_id.in_([module_id] + child_ids))
        else:
            query = query.filter(Scene.module_id == module_id)

    if keyword:
        query = query.filter(
            (Scene.name.contains(keyword)) | (Scene.description.contains(keyword))
        )

    if status:
        query = query.filter(Scene.status == status)

    scenes = query.order_by(Scene.id.desc()).all()
    return [serialize_scene(scene) for scene in scenes]


def get_scene_by_id(db: Session, scene_id: int):
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        return None
    return serialize_scene(scene)


def update_scene(db: Session, scene_id: int, data: SceneUpdate):
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(scene, field, value)

    db.commit()
    db.refresh(scene)
    return serialize_scene(scene)


def delete_scene(db: Session, scene_id: int) -> bool:
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        return False

    scene.is_deleted = True

    db.query(SceneStep).filter(
        SceneStep.scene_id == scene_id,
        SceneStep.is_deleted == False,
    ).update({"is_deleted": True})

    db.commit()
    return True


def get_scene_steps(db: Session, scene_id: int):
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        return None

    steps = (
        db.query(SceneStep)
        .filter(
            SceneStep.scene_id == scene_id,
            SceneStep.is_deleted == False,
        )
        .order_by(SceneStep.step_order.asc(), SceneStep.id.asc())
        .all()
    )

    result = []
    for step in steps:
        api_case = db.query(APICase).filter(APICase.id == step.case_id).first()
        result.append(serialize_scene_step(step, api_case))

    return result


def create_scene_step(db: Session, scene_id: int, data: SceneStepCreate):
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        raise ValueError("场景不存在")

    api_case = db.query(APICase).filter(
        APICase.id == data.case_id,
        APICase.is_deleted == False,
    ).first()
    if not api_case:
        raise ValueError("关联测试用例不存在或已删除")

    existing = (
        db.query(SceneStep)
        .filter(
            SceneStep.scene_id == scene_id,
            SceneStep.step_order == data.step_order,
            SceneStep.is_deleted == False,
        )
        .first()
    )
    if existing:
        raise ValueError("该场景下步骤顺序已存在，请更换 step_order")

    step = SceneStep(
        scene_id=scene_id,
        step_order=data.step_order,
        case_id=data.case_id,
        step_name=data.step_name,
        extract_rules_json=data.extract_rules_json,
        request_override_json=data.request_override_json,
        assertions_json=data.assertions_json,
        enabled=data.enabled,
    )
    db.add(step)
    db.commit()
    db.refresh(step)

    return serialize_scene_step(step, api_case)


def update_scene_step(db: Session, step_id: int, data: SceneStepUpdate) -> dict:
    step = db.query(SceneStep).filter(
        SceneStep.id == step_id,
        SceneStep.is_deleted == False,
    ).first()
    if not step:
        raise ValueError("场景步骤不存在")

    update_data = data.model_dump(exclude_unset=True)

    if "case_id" in update_data:
        api_case = db.query(APICase).filter(
            APICase.id == update_data["case_id"],
            APICase.is_deleted == False,
        ).first()
        if not api_case:
            raise ValueError("关联测试用例不存在或已删除")

    new_step_order = update_data.get("step_order", step.step_order)
    if "step_order" in update_data and new_step_order != step.step_order:
        conflict = (
            db.query(SceneStep)
            .filter(
                SceneStep.scene_id == step.scene_id,
                SceneStep.step_order == new_step_order,
                SceneStep.is_deleted == False,
                SceneStep.id != step_id,
            )
            .first()
        )
        if conflict:
            raise ValueError("该场景下步骤顺序已存在，请更换 step_order")

    for field, value in update_data.items():
        setattr(step, field, value)

    db.commit()
    db.refresh(step)

    api_case = db.query(APICase).filter(APICase.id == step.case_id).first()
    return serialize_scene_step(step, api_case)


def delete_scene_step(db: Session, step_id: int) -> bool:
    step = db.query(SceneStep).filter(
        SceneStep.id == step_id,
        SceneStep.is_deleted == False,
    ).first()
    if not step:
        return False

    step.is_deleted = True
    db.commit()
    return True


def reorder_scene_steps(db: Session, scene_id: int, data: ReorderSceneStepsRequest) -> bool:
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        raise ValueError("场景不存在")

    if not data.ordered_step_ids:
        raise ValueError("排序列表不能为空")

    steps = (
        db.query(SceneStep)
        .filter(
            SceneStep.id.in_(data.ordered_step_ids),
            SceneStep.is_deleted == False,
        )
        .all()
    )

    if len(steps) != len(data.ordered_step_ids):
        raise ValueError("排序列表中存在不存在的步骤或已删除的步骤")

    for s in steps:
        if s.scene_id != scene_id:
            raise ValueError("排序列表中的步骤不属于该场景")

    for idx, step_id in enumerate(data.ordered_step_ids):
        db.query(SceneStep).filter(SceneStep.id == step_id).update(
            {"step_order": idx + 1}
        )

    db.commit()
    return True


def execute_scene(db: Session, scene_id: int):
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.is_deleted == False,
    ).first()
    if not scene:
        raise ValueError("场景不存在")
    if scene.status != "active":
        raise ValueError("场景状态不是 active，无法执行")

    steps = (
        db.query(SceneStep)
        .filter(
            SceneStep.scene_id == scene_id,
            SceneStep.is_deleted == False,
            SceneStep.enabled == True,
        )
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
