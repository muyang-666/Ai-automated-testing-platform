import httpx

def test_case_1():
    # 请求地址
    url = "http://121.43.169.97:8082/system/public/verifyLogin"
    # 请求方法
    method = "POST"
    # 请求头（表单提交的标准Content-Type）
    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    # 请求体：表单数据（对应 username=&password=&valicode=）
    form_data = {
        'username': 'admin',    # 空用户名
        'password': 'HM_2025_test',    # 空密码
        'valicode': '8888'     # 空验证码
    }
    # 预期结果
    expected = {}

    # 发送请求（用data参数传递表单数据，而非json参数）
    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        data=form_data  # 关键：表单数据用data传递，json用于JSON格式
    )
    # 在断言前先打印响应结果，供执行器解析并入库
    print(f"===RESPONSE_STATUS_CODE==={response.status_code}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200

    # 断言预期结果字段
    response_json = response.json()
    for key, value in expected.items():
        assert response_json.get(key) == value

