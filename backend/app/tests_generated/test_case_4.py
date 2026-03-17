import httpx


def test_case_4():
    # 请求地址
    url = "http://httpbin.org/post"
    # 请求方法
    method = "POST"
    # 请求头
    headers = {'Content-Type': 'application/json'}
    # 请求体
    json_data = {'username': 'test', 'password': '123456'}
    # 预期结果
    expected = {'username': 'test'}

    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        json=json_data
    )

    # 断言状态码
    assert response.status_code == 200

    # 断言预期结果字段
    response_json = response.json()
    for key, value in expected.items():
        assert response_json.get(key) == value
