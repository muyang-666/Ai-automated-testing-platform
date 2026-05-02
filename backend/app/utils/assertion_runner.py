from typing import Any

from app.utils.variable_resolver import get_by_json_path


def run_assertions(
    response_status_code: int,
    response_json: Any,
    assertions: list[dict] | None,
) -> dict:
    """执行轻量断言规则，返回断言结果。

    assertions 示例:
    [
        {"type": "status_code", "operator": "eq", "expected": 200},
        {"type": "json_path", "path": "$.code", "operator": "eq", "expected": 200},
        {"type": "json_path", "path": "$.data.token", "operator": "not_empty"},
        {"type": "json_path", "path": "$.data.token", "operator": "exists"},
    ]

    返回: {"passed": bool, "results": [...]}
    """
    if assertions is None or (isinstance(assertions, list) and len(assertions) == 0):
        return {"passed": True, "results": []}

    if not isinstance(assertions, list):
        return {
            "passed": False,
            "results": [
                {
                    "type": "",
                    "operator": "",
                    "expected": None,
                    "actual": None,
                    "passed": False,
                    "message": "assertions 必须是 list 或 None",
                }
            ],
        }

    results = []
    all_passed = True

    for rule in assertions:
        if not isinstance(rule, dict):
            results.append(_error_result(rule, "断言规则必须是 dict"))
            all_passed = False
            continue

        result = _run_single_assertion(response_status_code, response_json, rule)
        results.append(result)
        if not result["passed"]:
            all_passed = False

    return {"passed": all_passed, "results": results}


def _error_result(rule: Any, message: str) -> dict:
    return {
        "type": rule.get("type", "") if isinstance(rule, dict) else "",
        "operator": rule.get("operator", "") if isinstance(rule, dict) else "",
        "expected": rule.get("expected") if isinstance(rule, dict) else None,
        "actual": None,
        "passed": False,
        "message": message,
    }


def _run_single_assertion(
    response_status_code: int,
    response_json: Any,
    rule: dict,
) -> dict:
    rule_type = rule.get("type", "")
    operator = rule.get("operator", "")
    expected = rule.get("expected")

    if rule_type == "status_code":
        return _assert_status_code(response_status_code, operator, expected)
    elif rule_type == "json_path":
        path = rule.get("path", "")
        actual = get_by_json_path(response_json, path)
        return _assert_json_path(actual, operator, expected, path)
    else:
        return {
            "type": rule_type,
            "operator": operator,
            "expected": expected,
            "actual": None,
            "passed": False,
            "message": f"不支持的断言类型: {rule_type}",
        }


def _assert_status_code(
    status_code: int,
    operator: str,
    expected: Any,
) -> dict:
    actual = status_code

    if operator == "eq":
        passed = actual == expected
        return {
            "type": "status_code",
            "operator": "eq",
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "message": "" if passed else f"期望状态码 {expected}，实际 {actual}",
        }
    else:
        return {
            "type": "status_code",
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "passed": False,
            "message": f"status_code 不支持的 operator: {operator}",
        }


def _assert_json_path(
    actual: Any,
    operator: str,
    expected: Any,
    path: str,
) -> dict:
    base = {
        "type": "json_path",
        "path": path,
        "operator": operator,
        "expected": expected,
        "actual": actual,
    }

    if operator == "eq":
        passed = actual == expected
        return {
            **base,
            "passed": passed,
            "message": "" if passed else f"路径 {path} 期望 {expected}，实际 {actual}",
        }

    elif operator == "contains":
        if actual is None:
            return {**base, "passed": False, "message": f"路径 {path} 值为 None，无法 contains"}
        if isinstance(actual, str):
            passed = str(expected) in actual
        elif isinstance(actual, list):
            passed = expected in actual
        elif isinstance(actual, dict):
            passed = expected in actual.keys() or expected in actual.values()
        else:
            passed = False
        return {
            **base,
            "passed": passed,
            "message": "" if passed else f"路径 {path} 值不包含 {expected}",
        }

    elif operator == "exists":
        passed = actual is not None
        return {
            **base,
            "expected": None,
            "passed": passed,
            "message": "" if passed else f"路径 {path} 不存在",
        }

    elif operator == "not_empty":
        passed = actual is not None and actual != "" and actual != [] and actual != {}
        return {
            **base,
            "expected": None,
            "passed": passed,
            "message": "" if passed else f"路径 {path} 为空",
        }

    else:
        return {
            **base,
            "passed": False,
            "message": f"json_path 不支持的 operator: {operator}",
        }
