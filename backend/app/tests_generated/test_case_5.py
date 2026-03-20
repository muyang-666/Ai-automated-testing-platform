from app.utils.parameter import *

import httpx


def test_case_5():
    # 请求地址
    url = f"http://{HOST}/loan/loanVerify/listData?restatus=first"
    # 请求方法
    method = "POST"
    # 请求头（已做基础规范化）
    headers = {'Accept': 'application/json, text/plain, */*', 'Cookie': Cookieb, 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest'}
    # 请求体（表单）
    form_data = {'current_page': aaa, 'userName': '197'}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {'exact_fields': {}, 'nested_exact_fields': {}, 'range_fields': {}, 'list_checks': []}

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

    # 当前没有可稳定断言的 JSON 字段，这里只断言状态码