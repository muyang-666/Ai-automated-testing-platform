import httpx


def test_case_1():
    url = "string"
    method = "STRING"
    headers = {}
    json_data = {}
    expected = {}

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
