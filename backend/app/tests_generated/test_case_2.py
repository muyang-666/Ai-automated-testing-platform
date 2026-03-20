import httpx


import httpx

def test_case_2():
    # 请求地址（已包含查询参数 restatus=first）
    url = "http://121.43.169.97:8082/loan/loanVerify/listData?restatus=first"
    # 请求方法
    method = "POST"
    # 修正后的请求头（匹配浏览器实际请求）
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': 'JSESSIONID=BCC21BB11B31283729A9EA5EE273BFA6',  # 实际使用时替换为有效Cookie
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'Origin': 'http://121.43.169.97:8082',
        'Referer': 'http://121.43.169.97:8082/loan/verify/list'
    }
    # 请求体：空表单数据（对应 Content-Length: 0）
    form_data = {}
    # 预期结果
    expected = {
        'status': 200,
        'data': {
            'page': 1,
            'epage': 20,
            'total_items': 207,
            'total_pages': 11
        },
        'description': 'OK'
    }

    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        data=form_data  # 表单数据用 data 参数传递，而非 json
    )

    # 打印响应结果（供执行器解析入库）
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200

    # 断言预期结果字段（简化断言，避免因items顺序/数量变化导致失败）
    response_json = response.json()
    assert response_json.get('status') == expected['status']
    assert response_json.get('description') == expected['description']
    assert response_json.get('data').get('page') == expected['data']['page']
    assert response_json.get('data').get('epage') == expected['data']['epage']
    assert response_json.get('data').get('total_items') == expected['data']['total_items']
    assert response_json.get('data').get('total_pages') == expected['data']['total_pages']
