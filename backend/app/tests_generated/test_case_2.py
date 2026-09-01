from app.utils.parameter import *

import httpx


def test_case_2():
    # 请求地址
    url = "https://httpbin.org/anything"
    # 请求方法
    method = "POST"
    # 请求头（已做基础规范化）
    headers = {'Authorization': 'Bearer ${token}', 'Content-Type': 'application/json'}
    # 请求体（JSON）
    json_data = {'user_id': '${user_id}'}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {'exact_fields': {}, 'nested_exact_fields': {}, 'range_fields': {}, 'list_checks': []}

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
    assert response.status_code == 200

    # 当前没有可稳定断言的 JSON 字段，这里只断言状态码