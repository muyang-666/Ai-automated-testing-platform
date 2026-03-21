from app.utils.parameter import *
import httpx

def test_case_2():
    # 后台系统_初审失败查询
    method = "POST"
    url = f"http://{HOST}/loan/loanVerify/listData?restatus=false"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": Cookieb,
        "Host": "121.43.169.97:8082",
        "Origin": "http://121.43.169.97:8082",
        "Proxy-Connection": "keep-alive",
        "Referer": "http://121.43.169.97:8082/loan/verifyfail/list",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
        "X-Requested-With": "XMLHttpRequest"
    }
    body = {
        "userName": "18760696230"
    }

    response = httpx.request(method, url, headers=headers, data=body, timeout=10.0, trust_env=False)
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get("description") == "OK"
    data = resp_json.get("data")
    assert data is not None
    assert data.get("page") == 1
    assert data.get("epage") == 20
    assert isinstance(data.get("total_items"), int) and data.get("total_items") >= 0
    assert isinstance(data.get("total_pages"), int) and data.get("total_pages") >= 1
    items = data.get("items")
    assert isinstance(items, list) and len(items) > 0
    for item in items:
        assert "id" in item
        assert "serialno" in item
        assert "status" in item
        assert "member_name" in item
        assert "category_id" in item