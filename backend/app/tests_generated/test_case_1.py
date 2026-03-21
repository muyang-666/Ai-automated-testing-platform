from app.utils.parameter import *
import httpx

def test_case_1():
    # 后台系统_初审标查询
    method = "POST"
    url = f"http://{HOST}/loan/loanVerify/listData?restatus=first"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": Cookieb,
        "Host": "121.43.169.97:8082",
        "Origin": "http://121.43.169.97:8082",
        "Proxy-Connection": "keep-alive",
        "Referer": "http://121.43.169.97:8082/loan/verify/list",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
        "X-Requested-With": "XMLHttpRequest"
    }
    form_data = {
        "userName": "197",
        "current_page": "1"
    }
    # 发起请求
    response = httpx.request(method, url, headers=headers, data=form_data, timeout=10.0, trust_env=False)
    # 打印响应状态码
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    # 打印响应内容
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")
    # 解析响应为JSON
    resp_json = response.json()
    # 轻量断言
    # 断言状态码和描述
    assert resp_json.get("status") == 200
    assert resp_json.get("description") == "OK"
    # 断言data.page和data.epage
    data = resp_json.get("data")
    assert data is not None
    assert data.get("page") == 1
    assert data.get("epage") == 20
    # 断言data.total_items和data.total_pages范围
    total_items = data.get("total_items")
    assert isinstance(total_items, int) and total_items >= 0
    total_pages = data.get("total_pages")
    assert isinstance(total_pages, int) and total_pages >= 1
    # 断言data.items列表非空且包含必要字段
    items = data.get("items")
    assert isinstance(items, list) and len(items) > 0
    for item in items:
        assert "id" in item
        assert "serialno" in item
        assert "status" in item
        assert "member_name" in item
        assert "category_id" in item