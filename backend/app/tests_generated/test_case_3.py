from app.utils.parameter import *

import httpx


def test_case_3():
    # 请求地址
    url = "http://121.43.169.97:8081/member/public/login"
    # 请求方法
    method = "POST"
    # 请求头（已做基础规范化）
    headers = {'Accept': 'application/json, text/plain, */*', 'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6', 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': 'JSESSIONID=D144A706834CC4641771C6C12634B7E6', 'Host': '121.43.169.97:8081', 'Origin': 'http://121.43.169.97:8081', 'Proxy-Connection': 'keep-alive', 'Referer': 'http://121.43.169.97:8081/common/member/login', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0', 'X-Requested-With': 'XMLHttpRequest'}
    # 请求体（表单）
    form_data = {}

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