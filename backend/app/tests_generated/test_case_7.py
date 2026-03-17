import httpx
import pytest


def test_case_7():
    # 后台管理搜索
    method = "POST"
    url = "http://121.43.169.97:8082/loan/loanVerify/listData?restatus=first"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "JSESSIONID=你的会话值",
        "X-Requested-With": "XMLHttpRequest"
    }
    body = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "JSESSIONID=88A62FA3741FA9E43CB565420A022239",
        "X-Requested-With": "XMLHttpRequest"
    }
    expected_result = {
        "status": 200,
        "description": "OK"
    }

    # 发起请求
    response = httpx.request(method=method, url=url, headers=headers, json=body)

    # 断言状态码
    assert response.status_code == expected_result["status"]

    # 断言响应字段
    response_json = response.json()
    assert response_json.get("description") == expected_result["description"]