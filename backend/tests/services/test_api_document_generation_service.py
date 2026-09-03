"""V1 接口文档 → 接口测试用例生成链路的 Baseline 测试。

只冻结当前行为，不修复业务缺陷；发现的现有行为差异登记到开发记录。
模型调用通过 monkeypatch 替换 service 模块命名空间中的 call_llm_by_scene，
绝不发起真实网络请求。
"""

import json
from pathlib import Path

import pytest

from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.schemas.api_document_generation import (
    GenerateApiCasesRequest,
    SaveGeneratedApiCasesRequest,
)
from app.services import api_document_generation_service as adg

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

SCENE_CODE = "api_doc_to_api_case"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FakeSceneLLM:
    """记录每次调用参数，并把固定 fixture 文本当作模型输出返回。"""

    def __init__(self, output: str):
        self.output = output
        self.calls: list[dict] = []

    def __call__(self, db, scene_code, prompt):
        self.calls.append({"scene_code": scene_code, "prompt": prompt})
        return self.output


def _seed_api_doc(db, project_id=202, module_id=None):
    doc = ApiDocument(
        project_id=project_id,
        module_id=module_id,
        name="用户登录接口",
        description="登录接口文档",
        method="POST",
        url="https://api.example.com/v1/login",
        content="POST /v1/login\n请求体包含 username 与 password 两个字段，校验通过后返回 token。",
        supplementary_prompt="补充要求：同时覆盖密码错误 4 次和 5 次的边界。",
        status="active",
        is_deleted=False,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _generate(db, monkeypatch, document_id, output):
    fake = FakeSceneLLM(output)
    monkeypatch.setattr(adg, "call_llm_by_scene", fake)
    response = adg.generate_api_cases_from_document(
        db, GenerateApiCasesRequest(document_id=document_id)
    )
    return fake, response


# ── B.1 有效文档 + Fake LLM JSON → 结构化候选 ──


def test_generate_returns_structured_candidates(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    fake, response = _generate(
        db_session, monkeypatch, doc.id, _load_fixture("api_cases_valid.json")
    )

    assert len(fake.calls) == 1
    assert len(response.cases) == 1
    case = response.cases[0]
    assert case.name == "登录接口-正常登录"
    assert case.description == "使用合法的用户名和密码登录"
    assert case.method == "POST"  # fixture 中为小写 post，冻结规范化行为
    assert case.priority == "P0"  # fixture 中为小写 p0
    assert case.url == "https://api.example.com/v1/login"
    assert case.headers == {"Content-Type": "application/json"}
    assert case.body == {"username": "testuser01", "password": "Test@123456"}
    assert case.expected_result == {"status": 200, "body": {"code": 0, "token": "fake-token"}}
    assert case.case_type == "正常场景"
    assert response.project_id == doc.project_id
    assert response.module_id == doc.module_id
    assert response.raw_output == _load_fixture("api_cases_valid.json")
    assert response.errors == []


# ── B.2 生成阶段不直接写入 api_cases ──


def test_generate_does_not_write_to_db(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    _generate(db_session, monkeypatch, doc.id, _load_fixture("api_cases_valid.json"))

    assert db_session.query(APICase).count() == 0


# ── B.3 使用业务场景 api_doc_to_api_case ──


def test_generate_uses_scene_code(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    fake, _ = _generate(db_session, monkeypatch, doc.id, _load_fixture("api_cases_valid.json"))

    assert fake.calls[0]["scene_code"] == SCENE_CODE


# ── B.4 Prompt 包含文档内容和 supplementary_prompt ──


def test_prompt_contains_document_fields(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    fake, _ = _generate(db_session, monkeypatch, doc.id, _load_fixture("api_cases_valid.json"))

    prompt = fake.calls[0]["prompt"]
    assert doc.content in prompt
    assert doc.supplementary_prompt in prompt
    assert doc.name not in prompt  # content 非空时 prompt 使用 content，不使用 name（当前事实）


def test_prompt_uses_name_when_content_empty(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    doc.content = None
    db_session.commit()
    fake, _ = _generate(db_session, monkeypatch, doc.id, _load_fixture("api_cases_valid.json"))

    assert doc.name in fake.calls[0]["prompt"]  # 冻结 content or name 回退行为


# ── B.5 method 和 priority 按现有规则规范化 ──


def test_method_priority_case_type_normalization(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    raw = json.dumps(
        [
            {"name": "小写方法", "method": "post", "url": "https://a.example.com/1", "priority": "p1"},
            {"name": "非法取值", "method": "FOO", "url": "https://a.example.com/2", "priority": "P9", "case_type": "冒烟场景"},
        ],
        ensure_ascii=False,
    )
    _, response = _generate(db_session, monkeypatch, doc.id, raw)

    assert response.cases[0].method == "POST"
    assert response.cases[0].priority == "P1"
    assert response.cases[0].case_type == "正常场景"  # 未提供时默认
    assert response.cases[1].method == "GET"  # 非法 method 回退 GET
    assert response.cases[1].priority == "P1"  # 非法 priority 回退 P1
    assert response.cases[1].case_type == "其他"  # 非法 case_type 回退其他


# ── B.6 非法 JSON → cases 为空并返回解析错误 ──


def test_invalid_json_returns_parse_error(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    _, response = _generate(db_session, monkeypatch, doc.id, "模型输出了一段纯文本，没有 JSON。")

    assert response.cases == []
    assert response.errors
    assert response.errors[0].startswith("无法解析 LLM 返回内容为 JSON 数组")


# ── B.7 缺少 name/url 等字段时，冻结当前 fallback 行为 ──


def test_missing_fields_fallback(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    raw = json.dumps(
        [
            {
                "method": "post",
                "url": "",
                "headers": "不是字典",
                "expected_result": ["不是对象"],
            }
        ],
        ensure_ascii=False,
    )
    _, response = _generate(db_session, monkeypatch, doc.id, raw)

    assert response.errors == []
    case = response.cases[0]
    assert case.name == f"{doc.name}_用例_1"  # 缺 name 时回退文档名
    assert case.url == doc.url  # 缺 url 时回退文档 url
    assert case.headers == {}  # headers 非 dict 回退空对象
    assert case.expected_result == {}  # expected_result 非 dict/str 回退空对象
    assert case.body is None  # body 缺省保持 None
    assert case.description == ""
    assert case.remark == ""


# ── B.8 LLM 调用异常 → 返回当前错误合同 ──


def test_llm_exception_returns_error_contract(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)

    def boom(db, scene_code, prompt):
        raise RuntimeError("模拟 LLM 故障")

    monkeypatch.setattr(adg, "call_llm_by_scene", boom)

    response = adg.generate_api_cases_from_document(
        db_session, GenerateApiCasesRequest(document_id=doc.id)
    )

    assert response.cases == []
    assert response.errors
    assert response.errors[0] == "LLM 调用失败: 模拟 LLM 故障"


# ── B.9 保存 → source=llm，headers/body/expected_result 保持 JSON 存储 ──


def test_save_generated_cases_json_storage(db_session):
    doc = _seed_api_doc(db_session)

    response = adg.save_generated_api_cases(
        db_session,
        SaveGeneratedApiCasesRequest(
            document_id=doc.id,
            project_id=doc.project_id,
            cases=[
                {
                    "name": "登录接口-保存基线",
                    "description": "保存行为基线",
                    "method": "POST",
                    "url": "https://api.example.com/v1/login",
                    "headers": {"X-Token": "fake-token"},
                    "body": {"username": "testuser01"},
                    "expected_result": {"status": 200},
                    "case_type": "正常场景",
                    "priority": "P0",
                    "remark": "备注",
                },
                {
                    "name": "登录接口-空字段",
                    "method": "POST",
                    "url": "https://api.example.com/v1/login",
                    "headers": {},
                    "body": None,
                    "expected_result": None,
                    "case_type": "异常场景",
                    "priority": "P1",
                },
            ],
        ),
    )

    assert response.saved_count == 2
    assert len(response.case_ids) == 2
    rows = db_session.query(APICase).order_by(APICase.id.asc()).all()
    assert rows[0].source == "llm"
    assert rows[0].status == "active"
    assert rows[0].headers == '{"X-Token": "fake-token"}'  # dict → JSON 字符串
    assert rows[0].body == '{"username": "testuser01"}'
    assert rows[0].expected_result == '{"status": 200}'
    assert "remark" not in APICase.__table__.columns  # api_cases 表无 remark 列，保存时丢弃（当前事实）
    assert rows[1].headers is None  # 空 headers → None
    assert rows[1].body is None
    assert rows[1].expected_result is None


# ── B.10 保存时 project_id 以后端 ApiDocument 为准 ──


def test_save_ignores_frontend_project_id(db_session):
    doc = _seed_api_doc(db_session, project_id=202)

    adg.save_generated_api_cases(
        db_session,
        SaveGeneratedApiCasesRequest(
            document_id=doc.id,
            project_id=9999,  # 前端伪造的归属项目，应被忽略
            module_id=8888,  # 前端 module_id 会优先于文档 module_id（冻结当前行为）
            cases=[
                {
                    "name": "任意用例",
                    "method": "GET",
                    "url": "https://a.example.com/1",
                    "priority": "P1",
                }
            ],
        ),
    )

    saved = db_session.query(APICase).one()
    assert saved.project_id == doc.project_id
    assert saved.project_id != 9999
    assert saved.module_id == 8888


# ── 附加冻结：保存不规范化 priority/case_type（与生成校验不一致的当前事实） ──


def test_save_priority_and_case_type_stored_as_is(db_session):
    doc = _seed_api_doc(db_session)

    adg.save_generated_api_cases(
        db_session,
        SaveGeneratedApiCasesRequest(
            document_id=doc.id,
            project_id=doc.project_id,
            cases=[
                {
                    "name": "保存原样值",
                    "method": "post",
                    "url": "https://a.example.com/1",
                    "priority": "p9",
                    "case_type": "冒烟场景",
                }
            ],
        ),
    )

    saved = db_session.query(APICase).one()
    assert saved.priority == "p9"
    assert saved.case_type == "冒烟场景"
    assert saved.method == "POST"  # method 保存时会大写


# ── B.11 文档不存在 → 不调用模型并返回当前错误合同 ──


def test_document_not_found_returns_error_without_model_call(db_session, monkeypatch):
    fake = FakeSceneLLM(_load_fixture("api_cases_valid.json"))
    monkeypatch.setattr(adg, "call_llm_by_scene", fake)

    response = adg.generate_api_cases_from_document(
        db_session, GenerateApiCasesRequest(document_id=404404)
    )

    assert response.errors == ["接口文档不存在或已删除"]
    assert response.cases == []
    assert fake.calls == []


def test_soft_deleted_document_treated_as_missing(db_session, monkeypatch):
    doc = _seed_api_doc(db_session)
    doc.is_deleted = True
    db_session.commit()
    fake = FakeSceneLLM(_load_fixture("api_cases_valid.json"))
    monkeypatch.setattr(adg, "call_llm_by_scene", fake)

    response = adg.generate_api_cases_from_document(
        db_session, GenerateApiCasesRequest(document_id=doc.id)
    )

    assert response.errors == ["接口文档不存在或已删除"]
    assert fake.calls == []


def test_save_missing_document_raises(db_session):
    with pytest.raises(ValueError, match="接口文档不存在或已删除"):
        adg.save_generated_api_cases(
            db_session,
            SaveGeneratedApiCasesRequest(document_id=404404, project_id=1, cases=[]),
        )
