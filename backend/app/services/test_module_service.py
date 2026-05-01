from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.test_module import TestModule
from app.schemas.test_module import (
    MoveModuleRequest,
    ReorderRequest,
    TestModuleCreate,
    TestModuleUpdate,
)


def _get_max_sort_order(db: Session, parent_id: int | None) -> int:
    query = db.query(TestModule).filter(
        TestModule.parent_id == parent_id,
        TestModule.is_deleted == False,
    )
    last = query.order_by(TestModule.sort_order.desc()).first()
    return last.sort_order if last else 0


def _build_path(parent: TestModule | None, module_id: int) -> str:
    if parent is None:
        return str(module_id)
    parent_path = parent.path or str(parent.id)
    return f"{parent_path}/{module_id}"


def create_module(db: Session, module_data: TestModuleCreate) -> TestModule:
    project = db.query(Project).filter(
        Project.id == module_data.project_id,
        Project.is_deleted == False,
    ).first()
    if not project:
        raise ValueError("项目不存在")

    parent = None
    if module_data.parent_id is not None:
        parent = db.query(TestModule).filter(
            TestModule.id == module_data.parent_id,
            TestModule.is_deleted == False,
        ).first()
        if not parent:
            raise ValueError("父模块不存在")
        if parent.project_id != module_data.project_id:
            raise ValueError("父模块不属于该项目")

    level = parent.level + 1 if parent else 1

    db_module = TestModule(
        project_id=module_data.project_id,
        parent_id=module_data.parent_id,
        name=module_data.name,
        description=module_data.description,
        module_type=module_data.module_type,
        level=level,
        sort_order=0,
        status="active",
    )
    db.add(db_module)
    db.flush()

    db_module.path = _build_path(parent, db_module.id)
    db_module.sort_order = _get_max_sort_order(db, module_data.parent_id) + 1

    db.commit()
    db.refresh(db_module)
    return db_module


def get_module_tree(db: Session, project_id: int):
    modules = (
        db.query(TestModule)
        .filter(
            TestModule.project_id == project_id,
            TestModule.is_deleted == False,
        )
        .order_by(TestModule.sort_order)
        .all()
    )

    if not modules:
        return []

    children_map: dict[int | None, list[TestModule]] = {}
    for m in modules:
        children_map.setdefault(m.parent_id, []).append(m)

    def attach_children(node: TestModule):
        node.children = children_map.get(node.id, [])
        for child in node.children:
            attach_children(child)

    roots = children_map.get(None, [])
    for root in roots:
        attach_children(root)

    return roots


def get_module_by_id(db: Session, module_id: int) -> TestModule | None:
    return db.query(TestModule).filter(
        TestModule.id == module_id,
        TestModule.is_deleted == False,
    ).first()


def update_module(db: Session, module_id: int, module_data: TestModuleUpdate) -> TestModule | None:
    db_module = get_module_by_id(db, module_id)
    if not db_module:
        return None

    update_data = module_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_module, field, value)

    db.commit()
    db.refresh(db_module)
    return db_module


def delete_module(db: Session, module_id: int) -> tuple[bool, str | None]:
    db_module = get_module_by_id(db, module_id)
    if not db_module:
        return False, "模块不存在"

    child_count = db.query(TestModule).filter(
        TestModule.parent_id == module_id,
        TestModule.is_deleted == False,
    ).count()

    if child_count > 0:
        return False, "模块下存在子模块，无法删除"

    db_module.is_deleted = True
    db.commit()
    return True, None


def move_module(db: Session, module_id: int, move_data: MoveModuleRequest) -> TestModule | None:
    db_module = get_module_by_id(db, module_id)
    if not db_module:
        return None

    child_count = db.query(TestModule).filter(
        TestModule.parent_id == module_id,
        TestModule.is_deleted == False,
    ).count()
    if child_count > 0:
        raise ValueError("模块下存在子模块，暂不支持移动")

    new_parent = None
    if move_data.new_parent_id is not None:
        if move_data.new_parent_id == module_id:
            raise ValueError("不能将模块移动到自身下")
        new_parent = db.query(TestModule).filter(
            TestModule.id == move_data.new_parent_id,
            TestModule.is_deleted == False,
        ).first()
        if not new_parent:
            raise ValueError("目标父模块不存在")
        if new_parent.project_id != db_module.project_id:
            raise ValueError("目标父模块不属于同一项目")

    db_module.parent_id = move_data.new_parent_id
    db_module.level = new_parent.level + 1 if new_parent else 1
    db_module.path = _build_path(new_parent, db_module.id)
    db_module.sort_order = _get_max_sort_order(db, move_data.new_parent_id) + 1

    db.commit()
    db.refresh(db_module)
    return db_module


def reorder_modules(db: Session, reorder_data: ReorderRequest) -> tuple[bool, str | None]:
    if not reorder_data.ordered_module_ids:
        return False, "排序列表不能为空"

    modules = (
        db.query(TestModule)
        .filter(
            TestModule.id.in_(reorder_data.ordered_module_ids),
            TestModule.is_deleted == False,
        )
        .all()
    )

    if len(modules) != len(reorder_data.ordered_module_ids):
        return False, "排序列表中存在不存在的模块或已删除的模块"

    module_map = {m.id: m for m in modules}
    for mid in reorder_data.ordered_module_ids:
        m = module_map[mid]
        if m.parent_id != reorder_data.parent_id:
            return False, "排序列表中的模块不属于同一父模块"

    for idx, mid in enumerate(reorder_data.ordered_module_ids):
        module_map[mid].sort_order = idx + 1

    db.commit()
    return True, None
