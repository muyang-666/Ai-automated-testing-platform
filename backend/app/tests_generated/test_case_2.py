import httpx


def test_case_2():
    url = "http://example.com/api/login"
    method = "POST"
    headers = {'Content-Type': 'application/json'}
    json_data = {'username': 'test', 'password': '123456'}
    expected = {'code': 200, 'message': 'success'}

    response = httpx.request(
        method=method,
        url=url,
        headers=headers,
        json=json_data
    )

    assert response.status_code == 200

    response_json = response.json()
    for key, value in expected.items():
        assert response_json.get(key) == value
