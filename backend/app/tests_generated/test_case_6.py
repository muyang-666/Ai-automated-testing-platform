import httpx
import pytest

def test_case_6():
    # 登录接口正常场景测试
    method = "POST"
    url = "http://127.0.0.1:8001/mock/login"
    headers = {"Content-Type": "application/json"}
    body = {"username": "test", "password": "123456"}
    expected_result = {"code": 200, "message": "success", "username": "test"}

    response = httpx.request(method=method, url=url, headers=headers, json=body)
    # 断言响应状态码
    assert response.status_code == 200
    # 断言响应体为JSON格式并验证字段
    response_json = response.json()
    assert response_json["code"] == expected_result["code"]
    assert response_json["message"] == expected_result["message"]
    assert response_json["username"] == expected_result["username"]