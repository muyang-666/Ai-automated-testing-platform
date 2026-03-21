from app.utils.parameter import *

import httpx


def test_case_4():
    # 请求地址
    url = f"http://{HOST}/loan/loanVerify/listData?restatus=first"
    # 请求方法
    method = "POST"
    # 请求头（已做基础规范化）
    headers = {'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest', 'Cookie': Cookieb}
    # 请求体（表单）
    form_data = {'current_page': '1', 'userName': '197'}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {'exact_fields': {'status': 200, 'description': 'OK'}, 'nested_exact_fields': {'data': {'page': 1, 'epage': 20}}, 'range_fields': {'data': {'total_items': {'type': 'int', 'min': 0}, 'total_pages': {'type': 'int', 'min': 1}}}, 'list_checks': []}

    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        data=form_data,
        timeout=10.0
    )

    # 在断言前先打印响应结果，供执行器解析并入库
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200

    response_json = response.json()
    assert response_json.get('status') == 200
    assert response_json.get('description') == 'OK'
    data = response_json.get('data') or {}
    assert isinstance(data, dict)
    assert data.get('page') == 1
    assert data.get('epage') == 20
    assert isinstance(data.get('total_items'), int)
    assert data.get('total_items') >= 0
    assert isinstance(data.get('total_pages'), int)
    assert data.get('total_pages') >= 1