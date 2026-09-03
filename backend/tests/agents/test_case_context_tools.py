"""case_context_tools 只读工具测试：权限（跨项目拒绝）、快照哈希、限量查询。"""

import pytest

from app.agents.runtime.errors import AgentPermissionError
from app.agents.tools.base import ToolContext
from app.agents.tools.case_context_tools import (
    ListExistingCasesTool,
    ListRelatedApiDocumentsTool,
    LoadProjectModuleContextTool,
    LoadSourceContextTool,
)
from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.models.function_case import FunctionCase
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.role import Role
from app.models.test_module import TestModule as ModuleModel
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole

PROJECT_A = 101
PROJECT_B = 202
TESTER_ID = 1
VIEWER_ID = 2
ADMIN_ID = 3


def _seed_role(db, code):
    role = Role(code=code, name=code, status="active")
    db.add(role)
    db.flush()
    return role


def _seed_user(db, user_id, role_codes):
    user = User(
        id=user_id,
        username=f"tool_user_{user_id}",
        password_hash="x",
        salt="y",
        status="active",
        is_deleted=False,
    )
    db.add(user)
    db.flush()
    for code in role_codes:
        role = db.query(Role).filter(Role.code == code).one()
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    return user


def _seed_permission(db, user_id, project_id, can_operate=True):
    db.add(UserProjectPermission(user_id=user_id, project_id=project_id, can_operate=can_operate))


def _seed_base(db):
    """项目 A/B + tester/viewer/admin + tester 只授权项目 A。"""
    for project_id in (PROJECT_A, PROJECT_B):
        db.add(Project(id=project_id, name=f"项目{project_id}", status="active", is_deleted=False))
    for code in ("tester", "viewer", "admin"):
        _seed_role(db, code)
    _seed_user(db, TESTER_ID, ["tester"])
    _seed_user(db, VIEWER_ID, ["viewer"])
    _seed_user(db, ADMIN_ID, ["admin"])
    _seed_permission(db, TESTER_ID, PROJECT_A, can_operate=True)
    db.commit()


def _ctx(db, user_id=TESTER_ID):
    return ToolContext(user_id=user_id, db=db)


def _seed_source_data(db):
    module_a = ModuleModel(project_id=PROJECT_A, name="登录模块")
    db.add(module_a)
    db.flush()
    requirement = RequirementDoc(
        project_id=PROJECT_A,
        module_id=module_a.id,
        title="用户登录需求",
        content="用户名密码登录，5 次错误锁定 30 分钟。",
        requirement_type="功能需求",
        status="confirmed",
        supplementary_prompt="重点覆盖锁定场景。",
        is_deleted=False,
    )
    db.add(requirement)
    db.flush()
    api_doc = ApiDocument(
        project_id=PROJECT_A,
        module_id=module_a.id,
        name="登录接口文档",
        method="POST",
        url="https://api.example.com/v1/login",
        content="POST /v1/login",
        status="active",
        is_deleted=False,
    )
    db.add(api_doc)
    db.flush()
    function_case = FunctionCase(
        project_id=PROJECT_A,
        module_id=module_a.id,
        requirement_id=requirement.id,
        case_code="FC-001",
        case_name="登录成功",
        case_type="正常场景",
        source="manual",
        priority="P0",
        steps_json=["步骤"],
        expected_result="成功",
        status="active",
        is_deleted=False,
    )
    db.add(function_case)
    db.flush()
    api_case = APICase(
        project_id=PROJECT_A,
        module_id=module_a.id,
        name="登录接口用例",
        method="POST",
        url="https://api.example.com/v1/login",
        source="manual",
        priority="P0",
        status="active",
        is_deleted=False,
    )
    db.add(api_case)
    db.commit()
    return module_a, requirement, api_doc, function_case, api_case


# ── load_source_context ──


def test_load_requirement_snapshot_and_stable_hash(db_session):
    _seed_base(db_session)
    _, requirement, _, _, _ = _seed_source_data(db_session)
    tool = LoadSourceContextTool()

    first = tool.execute(_ctx(db_session), tool.input_model(source_type="requirement", source_id=requirement.id))

    assert first.found is True
    assert first.source["title"] == "用户登录需求"
    assert first.source["content"] == requirement.content
    assert first.source["supplementary_prompt"] == "重点覆盖锁定场景。"
    assert first.source["project_id"] == PROJECT_A
    assert first.source_hash is not None

    second = tool.execute(_ctx(db_session), tool.input_model(source_type="requirement", source_id=requirement.id))
    assert second.source_hash == first.source_hash  # 相同内容 → 稳定哈希

    requirement.content = "改过的内容"
    db_session.commit()
    third = tool.execute(_ctx(db_session), tool.input_model(source_type="requirement", source_id=requirement.id))
    assert third.source_hash != first.source_hash  # 内容变化 → 哈希变化


def test_load_api_document_snapshot(db_session):
    _seed_base(db_session)
    _, _, api_doc, _, _ = _seed_source_data(db_session)
    tool = LoadSourceContextTool()

    result = tool.execute(_ctx(db_session), tool.input_model(source_type="api_document", source_id=api_doc.id))

    assert result.found is True
    assert result.source["name"] == "登录接口文档"
    assert result.source["method"] == "POST"


def test_load_source_not_found(db_session):
    _seed_base(db_session)
    tool = LoadSourceContextTool()

    result = tool.execute(_ctx(db_session), tool.input_model(source_type="requirement", source_id=404404))

    assert result.found is False


def test_cross_project_rejected(db_session):
    _seed_base(db_session)
    _, requirement, _, _, _ = _seed_source_data(db_session)
    requirement.project_id = PROJECT_B  # 把来源挪到 tester 未授权项目
    db_session.commit()
    tool = LoadSourceContextTool()

    with pytest.raises(AgentPermissionError) as exc:
        tool.execute(_ctx(db_session, TESTER_ID), tool.input_model(source_type="requirement", source_id=requirement.id))
    assert "读取权限" in str(exc.value)
    assert str(PROJECT_B) in str(exc.value)


def test_viewer_and_admin_can_read(db_session):
    _seed_base(db_session)
    _, requirement, _, _, _ = _seed_source_data(db_session)
    tool = LoadSourceContextTool()

    viewer_result = tool.execute(_ctx(db_session, VIEWER_ID), tool.input_model(source_type="requirement", source_id=requirement.id))
    admin_result = tool.execute(_ctx(db_session, ADMIN_ID), tool.input_model(source_type="requirement", source_id=requirement.id))

    assert viewer_result.found is True
    assert admin_result.found is True


# ── load_project_module_context ──


def test_project_module_context(db_session):
    _seed_base(db_session)
    module_a, _, _, _, _ = _seed_source_data(db_session)
    tool = LoadProjectModuleContextTool()

    result = tool.execute(
        _ctx(db_session),
        tool.input_model(project_id=PROJECT_A, module_id=module_a.id),
    )

    assert result.project == {"id": PROJECT_A, "name": f"项目{PROJECT_A}", "status": "active"}
    assert result.module["name"] == "登录模块"
    assert result.module_mismatch is False


def test_project_module_mismatch(db_session):
    _seed_base(db_session)
    module_a, _, _, _, _ = _seed_source_data(db_session)
    other_project_module = ModuleModel(project_id=PROJECT_B, name="B 项目模块")
    db_session.add(other_project_module)
    db_session.commit()
    tool = LoadProjectModuleContextTool()

    result = tool.execute(
        _ctx(db_session),
        tool.input_model(project_id=PROJECT_A, module_id=other_project_module.id),
    )

    assert result.module_mismatch is True
    assert result.module is None


def test_project_context_cross_project_rejected(db_session):
    _seed_base(db_session)
    tool = LoadProjectModuleContextTool()

    with pytest.raises(AgentPermissionError):
        tool.execute(_ctx(db_session, TESTER_ID), tool.input_model(project_id=PROJECT_B))


# ── list_existing_cases / list_related_api_documents ──


def test_list_existing_function_cases_filters(db_session):
    _seed_base(db_session)
    module_a, requirement, _, function_case, _ = _seed_source_data(db_session)
    tool = ListExistingCasesTool()

    result = tool.execute(
        _ctx(db_session),
        tool.input_model(project_id=PROJECT_A, case_kind="function", module_id=module_a.id, requirement_id=requirement.id),
    )

    assert result.total == 1
    assert result.cases[0]["case_name"] == "登录成功"
    assert result.cases[0]["case_code"] == "FC-001"
    assert "content" not in result.cases[0]  # 摘要只含限量字段
    # V2.1-T05.1：摘要带安全去重指纹，不返回 steps/expected 明文
    assert result.cases[0]["dedup_fingerprint"].startswith("sha256:")
    assert "steps_json" not in result.cases[0]
    assert "expected_result" not in result.cases[0]


def test_list_existing_api_cases(db_session):
    _seed_base(db_session)
    _, _, _, _, api_case = _seed_source_data(db_session)
    tool = ListExistingCasesTool()

    result = tool.execute(_ctx(db_session), tool.input_model(project_id=PROJECT_A, case_kind="api"))

    assert result.total == 1
    assert result.cases[0]["method"] == "POST"
    # 不返回 body/expected_result 明文，仅提供安全去重指纹
    assert result.cases[0]["dedup_fingerprint"].startswith("sha256:")
    assert "body" not in result.cases[0]
    assert "expected_result" not in result.cases[0]


def test_list_cases_limit(db_session):
    _seed_base(db_session)
    _, _, _, _, _ = _seed_source_data(db_session)
    for i in range(3):
        db_session.add(
            APICase(project_id=PROJECT_A, name=f"额外用例{i}", method="GET", url=f"https://a/{i}", status="active", is_deleted=False)
        )
    db_session.commit()
    tool = ListExistingCasesTool()

    result = tool.execute(_ctx(db_session), tool.input_model(project_id=PROJECT_A, case_kind="api", limit=2))

    assert result.total == 4
    assert len(result.cases) == 2


def test_list_cases_cross_project_rejected(db_session):
    _seed_base(db_session)
    tool = ListExistingCasesTool()

    with pytest.raises(AgentPermissionError):
        tool.execute(_ctx(db_session, TESTER_ID), tool.input_model(project_id=PROJECT_B, case_kind="api"))


def test_list_related_api_documents(db_session):
    _seed_base(db_session)
    _, _, api_doc, _, _ = _seed_source_data(db_session)
    tool = ListRelatedApiDocumentsTool()

    result = tool.execute(_ctx(db_session), tool.input_model(project_id=PROJECT_A))

    assert result.total == 1
    assert result.documents[0]["name"] == "登录接口文档"
    assert result.documents[0]["url"] == "https://api.example.com/v1/login"
