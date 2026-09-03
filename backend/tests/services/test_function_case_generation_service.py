"""V1 需求文本 → 功能测试用例生成链路的 Baseline 测试。

只冻结当前行为，不修复业务缺陷；发现的现有行为差异登记到开发记录。
模型调用通过 monkeypatch 替换 service 模块命名空间中的 call_llm_with_model，
绝不发起真实网络请求。
"""

import json
from pathlib import Path

import pytest

from app.models.function_case import FunctionCase
from app.models.llm_model import LLMModel
from app.models.llm_provider import LLMProvider
from app.models.llm_scene_config import LLMSceneConfig
from app.models.requirement_doc import RequirementDoc
from app.schemas.function_case_generation import (
    GenerateFunctionCasesRequest,
    SaveGeneratedFunctionCasesRequest,
)
from app.services import function_case_generation_service as fcg

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

SCENE_CODE = "requirement_to_function_case"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FakeFunctionLLM:
    """记录每次调用参数，并把固定 fixture 文本当作模型输出返回。"""

    def __init__(self, output: str):
        self.output = output
        self.calls: list[dict] = []

    def __call__(self, provider, model, prompt, temperature=None, max_tokens=None):
        self.calls.append(
            {
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.output


def _seed_requirement(db, project_id=101, module_id=None):
    requirement = RequirementDoc(
        project_id=project_id,
        module_id=module_id,
        title="用户登录功能需求",
        content="用户使用用户名和密码登录系统，密码错误 5 次后锁定账号 30 分钟。",
        requirement_type="功能需求",
        status="confirmed",
        supplementary_prompt="重点覆盖账号锁定与解锁场景。",
        is_deleted=False,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def _seed_llm_scene(db, scene_code=SCENE_CODE):
    provider = LLMProvider(
        name="FakeProvider",
        provider_type="openai_compatible",
        base_url="https://fake-llm.invalid/v1",
        api_key="fake-key-for-test",
        status="active",
        is_deleted=False,
    )
    db.add(provider)
    db.flush()
    model = LLMModel(
        provider_id=provider.id,
        model_name="fake-model",
        display_name="Fake Model",
        temperature=0.0,
        max_tokens=16384,
        timeout_seconds=60,
        status="active",
        is_deleted=False,
    )
    db.add(model)
    db.flush()
    scene = LLMSceneConfig(
        scene_code=scene_code,
        scene_name="需求生成功能用例",
        model_id=model.id,
        enabled=True,
        prompt_template=None,
    )
    db.add(scene)
    db.commit()
    return provider, model, scene


def _generate(db, monkeypatch, requirement_id, output):
    fake = FakeFunctionLLM(output)
    monkeypatch.setattr(fcg, "call_llm_with_model", fake)
    response = fcg.generate_function_cases_from_requirement(
        db, GenerateFunctionCasesRequest(requirement_id=requirement_id)
    )
    return fake, response


# ── A.1 有效需求 + Fake LLM JSON → 结构化候选 ──


def test_generate_returns_structured_candidates(db_session, monkeypatch):
    requirement = _seed_requirement(db_session, project_id=101, module_id=None)
    _seed_llm_scene(db_session)
    fake, response = _generate(
        db_session, monkeypatch, requirement.id, _load_fixture("function_cases_valid.json")
    )

    assert len(fake.calls) == 1
    assert len(response.cases) == 2
    first = response.cases[0]
    assert first.case_code == "FC-LOGIN-001"
    assert first.case_name == "登录成功"
    assert first.case_type == "正常场景"
    assert first.priority == "P0"
    assert first.steps_json == ["打开登录页", "输入正确的用户名和密码", "点击登录按钮"]
    assert first.expected_result == "登录成功并跳转到首页"
    # 第二条 fixture 使用 steps/test_data 别名，冻结别名回退行为
    assert response.cases[1].steps_json == ["打开登录页", "输入正确用户名和错误密码", "点击登录按钮"]
    assert response.cases[1].test_data_json == {"username": "testuser01", "password": "wrong-password"}
    # 响应归属信息来自后端 RequirementDoc 与场景配置
    assert response.project_id == requirement.project_id
    assert response.module_id == requirement.module_id
    assert response.model_name == "fake-model"
    assert response.provider_name == "FakeProvider"
    assert response.raw_output == _load_fixture("function_cases_valid.json")
    assert response.errors == []


# ── A.2 生成阶段只返回预览，不写入 function_cases ──


def test_generate_does_not_write_to_db(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    _seed_llm_scene(db_session)
    _generate(db_session, monkeypatch, requirement.id, _load_fixture("function_cases_valid.json"))

    assert db_session.query(FunctionCase).count() == 0


# ── A.3 Prompt 包含需求标题、内容和 supplementary_prompt ──


def test_prompt_contains_requirement_fields(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    _seed_llm_scene(db_session)
    fake, _ = _generate(
        db_session, monkeypatch, requirement.id, _load_fixture("function_cases_valid.json")
    )

    prompt = fake.calls[0]["prompt"]
    assert requirement.title in prompt
    assert requirement.content in prompt
    assert requirement.supplementary_prompt in prompt
    # 冻结固定调用参数（不断言 Prompt 全文）
    assert fake.calls[0]["temperature"] == 0.0
    assert fake.calls[0]["max_tokens"] == 16384


# ── A.4 非法 JSON → cases 为空并返回解析错误 ──


def test_invalid_json_returns_parse_error(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    _seed_llm_scene(db_session)
    _, response = _generate(
        db_session, monkeypatch, requirement.id, "这不是一个 JSON 数组，模型直接输出了自由文本。"
    )

    assert response.cases == []
    assert response.errors
    assert response.errors[0] == "LLM 返回内容无法解析为 JSON 数组"


# ── A.5 缺少 case_name / steps_json / expected_result → 校验拒绝 ──


def test_missing_required_fields_rejected(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    _seed_llm_scene(db_session)
    raw = json.dumps(
        [
            {"case_type": "正常场景", "priority": "P1", "steps_json": ["步骤1"], "expected_result": "通过"},
            {"case_name": "缺步骤", "case_type": "正常场景", "priority": "P1", "expected_result": "通过"},
            {"case_name": "缺预期", "case_type": "正常场景", "priority": "P1", "steps_json": ["步骤1"]},
        ],
        ensure_ascii=False,
    )
    _, response = _generate(db_session, monkeypatch, requirement.id, raw)

    assert response.cases == []
    joined = "".join(response.errors)
    assert "缺少 case_name" in joined
    assert "steps_json 为空" in joined
    assert "缺少 expected_result" in joined


# ── A.6 模型场景未配置 → 配置错误，不调用模型 ──


def test_scene_not_configured_returns_config_error(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    # 不种入任何 LLMSceneConfig
    fake = FakeFunctionLLM(_load_fixture("function_cases_valid.json"))
    monkeypatch.setattr(fcg, "call_llm_with_model", fake)

    response = fcg.generate_function_cases_from_requirement(
        db_session, GenerateFunctionCasesRequest(requirement_id=requirement.id)
    )

    assert response.cases == []
    assert fake.calls == []  # 未配置场景时绝不调用模型
    assert response.errors
    assert "未配置可用模型" in response.errors[0]


# ── A.7 保存候选 → source=llm ──


def test_save_generated_cases_creates_llm_source_rows(db_session):
    requirement = _seed_requirement(db_session)

    response = fcg.save_generated_function_cases(
        db_session,
        SaveGeneratedFunctionCasesRequest(
            requirement_id=requirement.id,
            project_id=requirement.project_id,
            cases=[
                {
                    "case_code": "FC-LOGIN-001",
                    "case_name": "登录成功",
                    "case_type": "正常场景",
                    "priority": "P0",
                    "precondition": "用户已注册",
                    "steps_json": ["打开登录页", "点击登录"],
                    "test_data_json": {"username": "testuser01"},
                    "expected_result": "登录成功",
                    "remark": None,
                }
            ],
        ),
    )

    assert response.saved_count == 1
    assert len(response.case_ids) == 1
    saved = db_session.query(FunctionCase).one()
    assert saved.id == response.case_ids[0]
    assert saved.source == "llm"
    assert saved.status == "active"
    assert saved.requirement_id == requirement.id
    assert saved.case_name == "登录成功"


# ── A.8 保存时 project_id 以后端 RequirementDoc 为准 ──


def test_save_ignores_frontend_project_id(db_session):
    requirement = _seed_requirement(db_session, project_id=101)

    fcg.save_generated_function_cases(
        db_session,
        SaveGeneratedFunctionCasesRequest(
            requirement_id=requirement.id,
            project_id=9999,  # 前端伪造的归属项目，应被忽略
            module_id=8888,  # 前端 module_id 会优先于需求 module_id（冻结当前行为）
            cases=[
                {
                    "case_name": "任意用例",
                    "case_type": "正常场景",
                    "priority": "P1",
                    "steps_json": ["步骤1"],
                    "expected_result": "通过",
                }
            ],
        ),
    )

    saved = db_session.query(FunctionCase).one()
    assert saved.project_id == requirement.project_id
    assert saved.project_id != 9999
    assert saved.module_id == 8888


# ── A.9 需求不存在 → 不调用模型并返回当前错误合同 ──


def test_requirement_not_found_returns_error_without_model_call(db_session, monkeypatch):
    fake = FakeFunctionLLM(_load_fixture("function_cases_valid.json"))
    monkeypatch.setattr(fcg, "call_llm_with_model", fake)

    response = fcg.generate_function_cases_from_requirement(
        db_session, GenerateFunctionCasesRequest(requirement_id=404404)
    )

    assert response.errors == ["需求文本不存在"]
    assert response.cases == []
    assert fake.calls == []


def test_soft_deleted_requirement_treated_as_missing(db_session, monkeypatch):
    requirement = _seed_requirement(db_session)
    requirement.is_deleted = True
    db_session.commit()
    fake = FakeFunctionLLM(_load_fixture("function_cases_valid.json"))
    monkeypatch.setattr(fcg, "call_llm_with_model", fake)

    response = fcg.generate_function_cases_from_requirement(
        db_session, GenerateFunctionCasesRequest(requirement_id=requirement.id)
    )

    assert response.errors == ["需求文本不存在"]
    assert fake.calls == []


def test_save_missing_requirement_raises(db_session):
    with pytest.raises(ValueError, match="需求文本不存在"):
        fcg.save_generated_function_cases(
            db_session,
            SaveGeneratedFunctionCasesRequest(requirement_id=404404, project_id=1, cases=[]),
        )
