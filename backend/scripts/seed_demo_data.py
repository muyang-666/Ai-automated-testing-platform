from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import Base, SessionLocal, engine
from app.models import (
    APICase,
    ApiDocument,
    FunctionCase,
    Project,
    Report,
    RequirementDoc,
    Role,
    Scene,
    SceneRun,
    SceneStep,
    SceneStepRun,
    TestModule,
    TestRun,
    User,
)
from app.services.ai_service import generate_mock_test_code
from app.services.auth_service import hash_password, init_default_auth_data
from app.services.llm.llm_config_service import init_default_scene_configs
from app.services.user_service import replace_user_project_permissions, replace_user_roles


DEFAULT_PASSWORD = "123456"
TARGET_BASE_URL = os.getenv("DEMO_TARGET_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def role_id(db, code: str) -> int:
    role = db.query(Role).filter(Role.code == code, Role.status == "active").first()
    if not role:
        raise RuntimeError(f"角色不存在: {code}")
    return role.id


def ensure_project(db, name: str, description: str) -> Project:
    project = (
        db.query(Project)
        .filter(Project.name == name, Project.is_deleted == False)
        .first()
    )
    if not project:
        project = Project(name=name, is_deleted=False)
        db.add(project)
        db.flush()

    project.description = description
    project.status = "active"
    return project


def ensure_module(db, project: Project, name: str, description: str, parent: TestModule | None = None) -> TestModule:
    module = (
        db.query(TestModule)
        .filter(
            TestModule.project_id == project.id,
            TestModule.parent_id == (parent.id if parent else None),
            TestModule.name == name,
            TestModule.is_deleted == False,
        )
        .first()
    )
    if not module:
        module = TestModule(
            project_id=project.id,
            parent_id=parent.id if parent else None,
            name=name,
            is_deleted=False,
        )
        db.add(module)
        db.flush()

    module.description = description
    module.module_type = "api"
    module.level = (parent.level + 1) if parent else 1
    module.sort_order = module.sort_order or 0
    module.path = f"{parent.path}/{module.id}" if parent and parent.path else str(module.id)
    module.status = "active"
    return module


def ensure_user(db, username: str, display_name: str, role_code: str, project_ids: list[int] | None = None) -> User:
    user = (
        db.query(User)
        .filter(User.username == username, User.is_deleted == False)
        .first()
    )
    if not user:
        salt, password_hash = hash_password(DEFAULT_PASSWORD)
        user = User(
            username=username,
            password_hash=password_hash,
            salt=salt,
            is_deleted=False,
        )
        db.add(user)
        db.flush()

    user.display_name = display_name
    user.email = f"{username}@demo.local"
    user.status = "active"
    replace_user_roles(db, user.id, [role_id(db, role_code)])
    replace_user_project_permissions(db, user.id, project_ids or [])
    return user


def ensure_api_case(
    db,
    project: Project,
    module: TestModule,
    name: str,
    description: str,
    expected_code: int,
    expected_message: str,
    priority: str = "P1",
) -> APICase:
    case = (
        db.query(APICase)
        .filter(
            APICase.project_id == project.id,
            APICase.name == name,
            APICase.is_deleted == False,
        )
        .first()
    )
    if not case:
        case = APICase(
            project_id=project.id,
            name=name,
            method="POST",
            url=f"{TARGET_BASE_URL}/mock/login",
            is_deleted=False,
        )
        db.add(case)
        db.flush()

    case.module_id = module.id
    case.description = description
    case.method = "POST"
    case.url = f"{TARGET_BASE_URL}/mock/login"
    case.headers = dumps({"Content-Type": "application/json"})
    case.body = dumps({"username": "test", "password": DEFAULT_PASSWORD})
    case.expected_result = dumps(
        {
            "status_code": 200,
            "code": expected_code,
            "message": expected_message,
            "data": {"items": [{"id": 1, "status": "active"}], "total_items": 1},
        }
    )
    case.case_type = "正常场景" if expected_code == 200 else "异常场景"
    case.source = "rule"
    case.priority = priority
    case.status = "active"
    case.generated_test_code = generate_mock_test_code(case)
    return case


def ensure_requirement(db, project: Project, title: str, content: str) -> RequirementDoc:
    doc = (
        db.query(RequirementDoc)
        .filter(
            RequirementDoc.project_id == project.id,
            RequirementDoc.title == title,
            RequirementDoc.is_deleted == False,
        )
        .first()
    )
    if not doc:
        doc = RequirementDoc(project_id=project.id, title=title, content=content, is_deleted=False)
        db.add(doc)
        db.flush()

    doc.content = content
    doc.requirement_type = "接口自动化"
    doc.status = "confirmed"
    doc.remark = "答辩演示数据"
    return doc


def ensure_function_case(db, project: Project, requirement: RequirementDoc, case_code: str, case_name: str) -> FunctionCase:
    case = (
        db.query(FunctionCase)
        .filter(
            FunctionCase.project_id == project.id,
            FunctionCase.case_code == case_code,
            FunctionCase.is_deleted == False,
        )
        .first()
    )
    if not case:
        case = FunctionCase(project_id=project.id, case_code=case_code, case_name=case_name, is_deleted=False)
        db.add(case)
        db.flush()

    case.requirement_id = requirement.id
    case.case_name = case_name
    case.case_type = "业务规则场景"
    case.source = "llm"
    case.priority = "P1"
    case.precondition = "演示用户已存在，目标服务已启动。"
    case.steps_json = ["输入用户名密码", "调用登录接口", "校验响应状态与业务码"]
    case.test_data_json = {"username": "test", "password": DEFAULT_PASSWORD}
    case.expected_result = "接口返回 200，业务码为 200，message 为 success。"
    case.status = "active"
    case.remark = "可展示从需求到功能用例的生成链路"
    return case


def ensure_api_document(db, project: Project, module: TestModule) -> ApiDocument:
    doc = (
        db.query(ApiDocument)
        .filter(
            ApiDocument.project_id == project.id,
            ApiDocument.name == "登录接口文档",
            ApiDocument.is_deleted == False,
        )
        .first()
    )
    if not doc:
        doc = ApiDocument(project_id=project.id, name="登录接口文档", is_deleted=False)
        db.add(doc)
        db.flush()

    doc.module_id = module.id
    doc.description = "答辩演示用接口文档，可生成接口测试用例预览。"
    doc.method = "POST"
    doc.url = f"{TARGET_BASE_URL}/mock/login"
    doc.headers_json = {"Content-Type": "application/json"}
    doc.params_json = {}
    doc.body_json = {"username": "test", "password": DEFAULT_PASSWORD}
    doc.response_example_json = {"code": 200, "message": "success", "username": "test"}
    doc.content = (
        "POST /mock/login\n"
        "请求体: username, password\n"
        "响应: code=200, message=success, username=test"
    )
    doc.supplementary_prompt = "优先生成登录成功、密码错误、字段缺失三类用例。"
    doc.status = "active"
    return doc


def ensure_scene(db, project: Project, module: TestModule, cases: list[APICase]) -> Scene:
    scene = (
        db.query(Scene)
        .filter(Scene.project_id == project.id, Scene.name == "登录链路冒烟场景", Scene.is_deleted == False)
        .first()
    )
    if not scene:
        scene = Scene(project_id=project.id, name="登录链路冒烟场景", is_deleted=False)
        db.add(scene)
        db.flush()

    scene.module_id = module.id
    scene.description = "展示场景编排、步骤断言、执行记录与报告闭环。"
    scene.status = "active"

    for index, api_case in enumerate(cases, start=1):
        step = (
            db.query(SceneStep)
            .filter(
                SceneStep.scene_id == scene.id,
                SceneStep.step_order == index,
                SceneStep.is_deleted == False,
            )
            .first()
        )
        if not step:
            step = SceneStep(scene_id=scene.id, step_order=index, case_id=api_case.id, is_deleted=False)
            db.add(step)
            db.flush()

        step.case_id = api_case.id
        step.step_name = f"步骤{index}-{api_case.name}"
        step.extract_rules_json = []
        step.request_override_json = {}
        step.assertions_json = [{"type": "status_code", "operator": "eq", "expected": 200}]
        step.enabled = True

    return scene


def ensure_test_run(db, api_case: APICase, result: str, response_code: int, response_body: str) -> TestRun:
    run = (
        db.query(TestRun)
        .filter(TestRun.case_id == api_case.id)
        .order_by(TestRun.id.asc())
        .first()
    )
    if not run:
        run = TestRun(case_id=api_case.id)
        db.add(run)
        db.flush()

    started_at = datetime.utcnow() - timedelta(minutes=20)
    run.status = "completed"
    run.result = result
    run.total_count = 1
    run.passed_count = 1 if result == "passed" else 0
    run.failed_count = 0 if result == "passed" else 1
    run.log_content = f"答辩演示执行日志：{api_case.name} -> {result}"
    run.error_message = "" if result == "passed" else "业务断言不符合预期，用于展示失败分析入口。"
    run.response_status_code = response_code
    run.response_content = response_body
    run.started_at = started_at
    run.finished_at = started_at + timedelta(seconds=2)
    return run


def ensure_scene_run(db, scene: Scene, cases: list[APICase]) -> SceneRun:
    scene_run = (
        db.query(SceneRun)
        .filter(SceneRun.scene_id == scene.id)
        .order_by(SceneRun.id.asc())
        .first()
    )
    if not scene_run:
        scene_run = SceneRun(scene_id=scene.id)
        db.add(scene_run)
        db.flush()

    started_at = datetime.utcnow() - timedelta(minutes=10)
    scene_run.project_id = scene.project_id
    scene_run.module_id = scene.module_id
    scene_run.status = "passed"
    scene_run.total_steps = len(cases)
    scene_run.passed_steps = len(cases)
    scene_run.failed_steps = 0
    scene_run.skipped_steps = 0
    scene_run.context_json = {"token": "demo-token", "source": "seed_demo_data"}
    scene_run.error_message = ""
    scene_run.started_at = started_at
    scene_run.finished_at = started_at + timedelta(seconds=5)
    scene_run.duration_ms = 5000

    for index, api_case in enumerate(cases, start=1):
        step_run = (
            db.query(SceneStepRun)
            .filter(
                SceneStepRun.scene_run_id == scene_run.id,
                SceneStepRun.step_order == index,
            )
            .first()
        )
        if not step_run:
            step_run = SceneStepRun(scene_run_id=scene_run.id, step_order=index, status="passed")
            db.add(step_run)
            db.flush()

        step_run.case_id = api_case.id
        step_run.step_name = api_case.name
        step_run.status = "passed"
        step_run.request_method = api_case.method
        step_run.request_url = api_case.url
        step_run.request_headers_json = {"Content-Type": "application/json"}
        step_run.request_body_json = {"username": "test"}
        step_run.response_status_code = 200
        step_run.response_body = dumps({"code": 200, "message": "success", "username": "test"})
        step_run.extracted_variables_json = {"token": "demo-token"} if index == 1 else {}
        step_run.assertion_results_json = [{"passed": True, "message": "状态码断言通过"}]
        step_run.error_message = ""
        step_run.duration_ms = 120

    return scene_run


def ensure_report(db) -> Report:
    report = (
        db.query(Report)
        .filter(Report.report_name == "答辩演示-自动化测试总结报告")
        .first()
    )
    if not report:
        report = Report(
            report_name="答辩演示-自动化测试总结报告",
            report_type="project_scene_report",
            summary="答辩演示报告",
        )
        db.add(report)
        db.flush()

    report.summary = (
        "本报告用于答辩演示：平台已完成项目管理、需求管理、接口文档管理、规则生成 pytest、"
        "单接口执行、场景链路执行、失败分析和权限控制闭环。"
    )
    report.total_count = 6
    report.passed_count = 5
    report.failed_count = 1
    report.pass_rate = 83.33
    report.risk_summary = "当前主要风险为目标接口稳定性和测试数据隔离，已通过项目权限与演示数据隔离降低影响。"
    return report


def seed_demo_data() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        init_default_auth_data(db)
        init_default_scene_configs(db)

        order_project = ensure_project(
            db,
            "答辩演示-电商订单系统",
            "覆盖登录、订单查询、订单提交等接口自动化演示场景。",
        )
        hr_project = ensure_project(
            db,
            "答辩演示-HR请假系统",
            "用于验证测试人员只能操作被授权项目。",
        )
        readonly_project = ensure_project(
            db,
            "答辩演示-只读对照项目",
            "用于展示只读人员可查看但不能编辑、删除或执行。",
        )
        db.flush()

        auth_module = ensure_module(db, order_project, "用户认证", "登录、鉴权、Token 相关接口。")
        order_module = ensure_module(db, order_project, "订单流程", "订单查询与提交接口。")
        hr_module = ensure_module(db, hr_project, "请假审批", "请假申请与审批接口。")

        ensure_user(db, "demo_admin", "答辩管理员", "admin", [])
        ensure_user(db, "demo_tester_order", "订单项目测试人员", "tester", [order_project.id])
        ensure_user(db, "demo_tester_hr", "HR项目测试人员", "tester", [hr_project.id])
        ensure_user(db, "demo_viewer", "只读观察员", "viewer", [])

        login_case = ensure_api_case(
            db,
            order_project,
            auth_module,
            "登录成功-规则生成通过",
            "通过本地被测服务验证登录接口正常返回。",
            expected_code=200,
            expected_message="success",
            priority="P0",
        )
        fail_case = ensure_api_case(
            db,
            order_project,
            order_module,
            "订单接口-失败分析演示",
            "故意设置不匹配业务码，用于展示执行失败和 AI 分析入口。",
            expected_code=500,
            expected_message="should fail",
            priority="P1",
        )
        hr_case = ensure_api_case(
            db,
            hr_project,
            hr_module,
            "HR系统登录-权限隔离演示",
            "用于验证订单项目测试人员不能操作 HR 项目。",
            expected_code=200,
            expected_message="success",
            priority="P1",
        )

        requirement = ensure_requirement(
            db,
            order_project,
            "登录与订单查询接口自动化需求",
            "系统应支持用户登录后查询订单列表；接口返回结构稳定，失败时需要记录日志并可生成分析报告。",
        )
        ensure_function_case(db, order_project, requirement, "FC-DEMO-LOGIN-001", "登录成功后查询订单列表")
        ensure_api_document(db, order_project, auth_module)
        scene = ensure_scene(db, order_project, auth_module, [login_case])

        ensure_test_run(db, login_case, "passed", 200, dumps({"code": 200, "message": "success"}))
        ensure_test_run(db, fail_case, "failed", 200, dumps({"code": 200, "message": "success"}))
        ensure_test_run(db, hr_case, "passed", 200, dumps({"code": 200, "message": "success"}))
        ensure_scene_run(db, scene, [login_case])
        ensure_report(db)

        db.commit()
        print("答辩演示数据已初始化完成。")
        print("演示账号：admin / 123456（系统管理员）")
        print("演示账号：demo_admin / 123456（管理员）")
        print("演示账号：demo_tester_order / 123456（仅订单项目操作权限）")
        print("演示账号：demo_tester_hr / 123456（仅 HR 项目操作权限）")
        print("演示账号：demo_viewer / 123456（只读人员）")
        print(f"接口用例默认被测服务地址：{TARGET_BASE_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
