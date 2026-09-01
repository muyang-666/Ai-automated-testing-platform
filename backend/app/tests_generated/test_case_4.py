from app.utils.parameter import *

import httpx


def test_case_4():
    # 请求地址
    url = "http://121.43.169.97:8081/loan/loan/listtender"
    # 请求方法
    method = "POST"
    # 请求头（已做基础规范化）
    headers = {}
    # 请求体（表单）
    form_data = {'page': 1, 'loan_type': 1}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {'exact_fields': {'Accept': 'application/json, text/plain, */*', 'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6', 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': 'JSESSIONID=FE147B72218E97D656753C9AD4ED7001', 'Host': '121.43.169.97:8081', 'Origin': 'http://121.43.169.97:8081', 'Proxy-Connection': 'keep-alive', 'Referer': 'http://121.43.169.97:8081/loan/tender/index', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0', 'X-Requested-With': 'XMLHttpRequest'}, 'nested_exact_fields': {}, 'range_fields': {}, 'list_checks': []}

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
    assert response_json.get('Accept') == 'application/json, text/plain, */*'
    assert response_json.get('Accept-Encoding') == 'gzip, deflate'
    assert response_json.get('Accept-Language') == 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
    assert response_json.get('Content-Type') == 'application/x-www-form-urlencoded'
    assert response_json.get('Cookie') == 'JSESSIONID=FE147B72218E97D656753C9AD4ED7001'
    assert response_json.get('Host') == '121.43.169.97:8081'
    assert response_json.get('Origin') == 'http://121.43.169.97:8081'
    assert response_json.get('Proxy-Connection') == 'keep-alive'
    assert response_json.get('Referer') == 'http://121.43.169.97:8081/loan/tender/index'
    assert response_json.get('User-Agent') == 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0'
    assert response_json.get('X-Requested-With') == 'XMLHttpRequest'