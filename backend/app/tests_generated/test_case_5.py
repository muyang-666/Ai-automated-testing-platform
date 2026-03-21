from app.utils.parameter import *
import httpx

def test_case_5():
    # 准备请求参数
    method = "POST"
    url = f"http://{HOST}/loan/loanVerify/listData?restatus=first"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Cookie': Cookieb,
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest'
    }
    data = {
        'current_page': aaa,
        'userName': '197'
    }

    # 发起请求
    response = httpx.request(method, url, headers=headers, data=data, timeout=10.0, trust_env=False)

    # 打印响应信息
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200