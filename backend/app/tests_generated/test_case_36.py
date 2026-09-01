from app.utils.parameter import *

import httpx


def test_case_36():
    # 请求地址
    url = 'http:///api/v1/auth/logout'
    # 请求方法
    method = 'POST'
    # 请求头（已做基础规范化）
    headers = {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...', 'Content-Type': 'application/json'}
    # 请求体（JSON）
    json_data = {}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {'exact_fields': {'code': 401, 'message': '未登录或token已失效'}, 'nested_exact_fields': {}, 'range_fields': {}, 'list_checks': []}
    expected_status_code = 200

    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        json=json_data,
        timeout=10.0
    )

    # 在断言前先打印响应结果，供执行器解析并入库
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == expected_status_code

    try:
        response_json = response.json()
    except ValueError:
        assert False, f"响应不是合法 JSON，无法执行字段断言: {response.text[:500]}"
    assert response_json.get('code') == 401
    assert response_json.get('message') == '未登录或token已失效'