from app.utils.parameter import *
import httpx

def test_case_1():
    # 后台系统登录
    method = "POST"
    url = "http://121.43.169.97:8082/system/public/verifyLogin"
    # 请求头键名疑似写成了 MIME 类型，请检查是否应为 Accept 或 Content-Type。
    headers = {'application/x-www-form-urlencoded': 'charset=UTF-8'}
    # 当前没有明确有效的请求体，请不要虚构 body 参数。
    body = {}
    # 使用 data 传递表单数据
    data = {"username": "", "password": "", "valicode": "112233"}

    response = httpx.request(method, url, headers=headers, data=data, timeout=10.0, trust_env=False)
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200
    # 断言响应体为JSON
    resp_json = response.json()
    # 轻量断言：只断言稳定字段
    assert resp_json.get("status") == 100
    assert resp_json.get("description") == "用户名不能为空"