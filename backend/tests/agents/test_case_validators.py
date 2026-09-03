"""case_validators 纯确定性函数测试（无数据库、无副作用）。"""

import copy

from app.agents.validators.case_validators import (
    canonical_json,
    canonical_url,
    case_fingerprint,
    compute_coverage,
    find_duplicates,
    normalize_case_name,
    validate_api_case_business,
    validate_api_case_schema,
    validate_function_case_business,
    validate_function_case_schema,
)


def _fn_case(**overrides):
    case = {
        "case_name": "登录成功",
        "case_type": "正常场景",
        "priority": "P0",
        "steps_json": ["步骤1", "步骤2"],
        "expected_result": "登录成功",
    }
    case.update(overrides)
    return case


def _api_case(**overrides):
    case = {
        "name": "登录接口-正常登录",
        "method": "POST",
        "url": "https://api.example.com/v1/login",
        "headers": {"Content-Type": "application/json"},
        "body": {"username": "u1"},
        "expected_result": {"status": 200},
        "case_type": "正常场景",
        "priority": "P0",
    }
    case.update(overrides)
    return case


# ── 归一化与指纹（V2.1-T05.1 语义） ──


def test_normalize_case_name():
    assert normalize_case_name("  登录成功 ") == "登录成功"
    assert normalize_case_name(None) == ""


def test_fingerprint_is_sha256_and_contains_no_plaintext():
    fingerprint = case_fingerprint("api", _api_case(body={"username": "valid", "password": "correct"}))
    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == len("sha256:") + 64
    assert "correct" not in fingerprint
    assert "password" not in fingerprint
    assert "valid" not in fingerprint


def test_fingerprint_function_name_alias_and_normalization():
    # case_name 与 name 别名、首尾空白 → 相同指纹
    assert case_fingerprint("function", _fn_case()) == case_fingerprint(
        "function", _fn_case(case_name=" 登录成功 ")
    )
    assert case_fingerprint("function", _fn_case()) == case_fingerprint(
        "function", {"name": "登录成功", "steps": ["步骤1", "步骤2"], "expected_result": "登录成功", "case_type": "正常场景"}
    )


def test_fingerprint_api_method_url_normalization():
    assert case_fingerprint("api", _api_case()) == case_fingerprint(
        "api", _api_case(method="post", url="HTTPS://api.example.com/v1/login/")
    )


def test_canonical_json_key_order_and_string_form():
    assert canonical_json({"a": 1, "b": {"d": 2, "c": 3}}) == canonical_json({"b": {"c": 3, "d": 2}, "a": 1})
    assert canonical_json({"a": 1}) == canonical_json('{"a": 1}')
    assert canonical_json("not-json") == "not-json"  # 解析失败稳定 fallback
    assert canonical_json(None) == "<null>"


def test_canonical_url_query_order():
    assert canonical_url("https://a.com/p?b=2&a=1") == canonical_url("https://a.com/p?a=1&b=2")
    assert canonical_url("HTTPS://A.com/p/") == canonical_url("https://a.com/p")
    assert canonical_url("<<HOST>>/login?x=1") == "<<HOST>>/login?x=1"  # 变量占位不解析


# ── Schema 校验 ──


def test_function_schema_valid():
    assert validate_function_case_schema(_fn_case()) == []


def test_function_schema_type_errors():
    errors = validate_function_case_schema(
        {"case_name": 123, "steps_json": "not-list", "test_data_json": [1]}
    )
    assert any("case_name" in e for e in errors)
    assert any("steps_json" in e for e in errors)
    assert any("test_data_json" in e for e in errors)


def test_function_schema_non_dict():
    assert validate_function_case_schema("not-dict") == ["不是对象"]


def test_api_schema_valid():
    assert validate_api_case_schema(_api_case()) == []


def test_api_schema_type_errors():
    errors = validate_api_case_schema(
        {"name": "x", "method": "POST", "url": "https://a/1", "headers": [1], "body": 123, "expected_result": [1]}
    )
    assert any("headers" in e for e in errors)
    assert any("body" in e for e in errors)
    assert any("expected_result" in e for e in errors)


# ── 业务规则校验 ──


def test_function_business_valid():
    assert validate_function_case_business(_fn_case()) == []


def test_function_business_errors():
    errors = validate_function_case_business(
        {"case_name": "", "steps_json": [], "expected_result": "", "case_type": "冒烟", "priority": "P9"}
    )
    assert any("缺少 case_name" in e for e in errors)
    assert any("steps_json 为空" in e for e in errors)
    assert any("缺少 expected_result" in e for e in errors)
    assert any("case_type 非法" in e for e in errors)
    assert any("priority 非法" in e for e in errors)


def test_api_business_valid():
    assert validate_api_case_business(_api_case()) == []


def test_api_business_errors():
    errors = validate_api_case_business(
        {"name": "", "method": "FOO", "url": "", "case_type": "冒烟", "priority": "P9"}
    )
    assert any("缺少 name" in e for e in errors)
    assert any("method 非法" in e for e in errors)
    assert any("缺少 url" in e for e in errors)
    assert any("case_type 非法" in e for e in errors)
    assert any("priority 非法" in e for e in errors)


# ── 去重 ──


def test_deduplicate_candidates_keep_first():
    keep, duplicates = find_duplicates(
        "function",
        [_fn_case(), _fn_case(case_name=" 登录成功 "), _fn_case(case_name="密码错误")],
    )

    assert keep == [0, 2]
    assert len(duplicates) == 1
    assert duplicates[0]["first_position"] == 0
    assert duplicates[0]["duplicate_position"] == 1
    assert duplicates[0]["duplicate_origin"] == "candidate"


def test_deduplicate_against_existing():
    keep, duplicates = find_duplicates(
        "api",
        [_api_case()],
        existing=[_api_case(name="已存在的同名接口用例")],  # 指纹相同（method+url）
    )

    assert keep == []  # 候选与已有重复，不保留
    assert duplicates[0]["first_origin"] == "existing"
    assert duplicates[0]["duplicate_origin"] == "candidate"


def test_deduplicate_no_duplicates():
    keep, duplicates = find_duplicates(
        "function", [_fn_case(), _fn_case(case_name="密码错误提示")]
    )
    assert keep == [0, 1]
    assert duplicates == []


# ── 覆盖矩阵 ──


def test_coverage_full():
    result = compute_coverage(
        [{"clause_id": "REQ-001", "text": "登录成功"}, {"clause_id": "REQ-002", "text": "密码错误"}],
        [
            {"candidate_id": "CASE-001", "name": "A", "covered_clause_ids": ["REQ-001"]},
            {"candidate_id": "CASE-002", "name": "B", "covered_clause_ids": ["REQ-002", "REQ-001"]},
        ],
    )

    assert result["covered_count"] == 2
    assert result["uncovered_count"] == 0
    assert result["uncovered_clause_ids"] == []
    assert result["unknown_refs"] == []
    assert result["matrix"][0]["covered_by"] == ["CASE-001", "CASE-002"]


def test_coverage_gaps_and_unknown_refs():
    result = compute_coverage(
        [{"clause_id": "REQ-001", "text": "A"}, {"clause_id": "REQ-002", "text": "B"}],
        [{"candidate_id": "CASE-001", "name": "A", "covered_clause_ids": ["REQ-999"]}],
    )

    assert result["covered_count"] == 0
    assert result["uncovered_count"] == 2
    assert result["uncovered_clause_ids"] == ["REQ-001", "REQ-002"]
    assert result["unknown_refs"] == [{"candidate_id": "CASE-001", "clause_id": "REQ-999"}]


# ── V2.1-T05.1 误判回归：同一接口的不同场景不得被合并 ──


def test_same_method_url_different_body_not_duplicate():
    normal = _api_case(body={"username": "valid", "password": "correct"})
    missing_password = _api_case(name="密码缺失", body={"username": "valid"})

    keep, duplicates = find_duplicates("api", [normal, missing_password])

    assert keep == [0, 1]
    assert duplicates == []


def test_same_body_different_expected_not_duplicate():
    ok_case = _api_case(expected_result={"code": 200})
    fail_case = _api_case(name="返回401", expected_result={"code": 401})

    keep, duplicates = find_duplicates("api", [ok_case, fail_case])

    assert keep == [0, 1]
    assert duplicates == []


def test_same_scene_different_case_type_not_duplicate():
    normal = _api_case(case_type="正常场景")
    boundary = _api_case(name="边界场景用例", case_type="边界场景")

    keep, duplicates = find_duplicates("api", [normal, boundary])

    assert keep == [0, 1]
    assert duplicates == []


def test_acceptance_example_three_scenarios_all_kept():
    candidates = [
        {
            "name": "登录成功",
            "method": "POST",
            "url": "/login",
            "body": {"username": "valid", "password": "correct"},
            "expected_result": {"code": 200},
            "case_type": "正常场景",
        },
        {
            "name": "密码错误",
            "method": "POST",
            "url": "/login",
            "body": {"username": "valid", "password": "wrong"},
            "expected_result": {"code": 401},
            "case_type": "异常场景",
        },
        {
            "name": "密码缺失",
            "method": "POST",
            "url": "/login",
            "body": {"username": "valid"},
            "expected_result": {"code": 400},
            "case_type": "异常场景",
        },
    ]

    keep, duplicates = find_duplicates("api", candidates)

    assert keep == [0, 1, 2]
    assert duplicates == []


def test_same_scene_json_key_order_duplicate():
    a = _api_case(body={"username": "valid", "password": "correct"}, expected_result={"code": 200, "msg": "ok"})
    b = _api_case(body={"password": "correct", "username": "valid"}, expected_result={"msg": "ok", "code": 200})

    keep, duplicates = find_duplicates("api", [a, b])

    assert keep == [0]
    assert len(duplicates) == 1


def test_same_scene_url_query_order_duplicate():
    a = _api_case(url="https://api.example.com/login?b=2&a=1")
    b = _api_case(url="https://api.example.com/login?a=1&b=2")

    keep, duplicates = find_duplicates("api", [a, b])

    assert keep == [0]
    assert len(duplicates) == 1


def test_body_dict_and_json_string_duplicate():
    a = _api_case(body={"username": "valid", "password": "correct"})
    b = _api_case(body='{"username": "valid", "password": "correct"}')

    keep, duplicates = find_duplicates("api", [a, b])

    assert keep == [0]
    assert len(duplicates) == 1


def test_existing_api_identical_candidate_marked_duplicate():
    existing = [_api_case()]
    candidate = [_api_case(name="候选同场景")]

    keep, duplicates = find_duplicates("api", candidate, existing=existing)

    assert keep == []
    assert duplicates[0]["first_origin"] == "existing"
    assert duplicates[0]["duplicate_origin"] == "candidate"


def test_existing_function_name_alias_duplicate():
    existing = [{"name": "登录成功", "steps": ["步骤1", "步骤2"], "expected_result": "登录成功", "case_type": "正常场景"}]
    candidates = [_fn_case()]  # 使用 case_name/steps_json 形态

    keep, duplicates = find_duplicates("function", candidates, existing=existing)

    assert keep == []
    assert duplicates[0]["first_origin"] == "existing"


def test_function_same_name_different_steps_not_duplicate():
    a = _fn_case()
    b = _fn_case(steps_json=["完全不同的步骤"])

    keep, duplicates = find_duplicates("function", [a, b])

    assert keep == [0, 1]
    assert duplicates == []


def test_function_same_name_different_expected_not_duplicate():
    a = _fn_case()
    b = _fn_case(expected_result="不同的预期结果")

    keep, duplicates = find_duplicates("function", [a, b])

    assert keep == [0, 1]
    assert duplicates == []


def test_duplicates_output_contains_no_secret_plaintext():
    candidates = [
        _api_case(body={"username": "valid", "password": "correct"}),
        _api_case(name="重复场景", body={"username": "valid", "password": "correct"}),
    ]

    _, duplicates = find_duplicates("api", candidates)

    joined = repr(duplicates)
    assert "correct" not in joined
    assert "password" not in joined
    assert "valid" not in joined


def test_fingerprint_inputs_not_mutated():
    candidates = [_api_case(body={"username": "valid", "password": "correct"})]
    existing = [_fn_case()]
    candidates_before = copy.deepcopy(candidates)
    existing_before = copy.deepcopy(existing)

    find_duplicates("function", [_fn_case()], existing=existing)
    case_fingerprint("api", candidates[0])
    canonical_url("https://api.example.com/login?a=2&a=1")
    canonical_json({"z": 1, "a": {"c": 2, "b": 3}})

    assert candidates == candidates_before
    assert existing == existing_before


def test_dedup_fingerprint_field_reused_from_summary():
    """list_existing_cases 摘要自带 dedup_fingerprint 时直接复用。"""
    existing_summary = [
        {
            "id": 1,
            "name": "登录接口用例",
            "method": "POST",
            "url": "https://api.example.com/v1/login",
            "dedup_fingerprint": case_fingerprint("api", _api_case()),
        }
    ]

    keep, duplicates = find_duplicates("api", [_api_case()], existing=existing_summary)

    assert keep == []
    assert duplicates[0]["first_origin"] == "existing"
