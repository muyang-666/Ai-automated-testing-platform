from datetime import datetime  # 导入时间模块

import json
import re
import httpx  # 给当前后端服务自己调用 LLM 接口用的
from sqlalchemy.orm import Session  # 说明 service 会操作数据库

from app.core.config import settings  # 表示大模型配置不是写死在代码里的，而是从配置对象里拿：
from app.models.api_case import APICase  # AI 生成代码的原材料，就是数据库里的测试用例对象
# 它说明生成出来的代码不会只停留在内存里，也不会只存数据库，而是会：真正写到文件系统里
from app.utils.file_writer import save_test_code_to_file


# 处理 JSON 字符串数据
def safe_json_loads(raw_text: str | None) -> dict:
    # 如果本来就是空，直接返回空字典。
    if not raw_text:
        return {}
    # 如果是合法 JSON 字符串，就解析成字典。
    try:
        return json.loads(raw_text)
    # 如果解析失败，不报错，直接兜底成空字典。
    except Exception:
        return {}


# 处理用户录入测试用例时，URL 格式
def normalize_url(raw_url: str | None) -> str:
    # 如果 URL 根本没填，返回空字符串。
    if not raw_url:
        return ""
    # 去掉前后空格，避免脏输入。
    raw_url = raw_url.strip()
    # 如果已经有协议头，直接原样返回
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    # 否则补一个默认前缀
    return f"http://{raw_url}"


# 判断 URL 是否更像网页地址而不是标准 JSON 接口
def looks_like_webpage_url(url: str | None) -> bool:
    if not url:
        return False
    lower_url = url.lower().strip()
    # 这里先做一个简单规则：包含 www 或常见门户域名时，先认为更像网页地址
    return (
        "www." in lower_url
        or "baidu.com" in lower_url
        or "qq.com" in lower_url
        or "163.com" in lower_url
        or "sohu.com" in lower_url
    )


# AI 生成链的核心：拼 Prompt
def build_case_prompt(api_case: APICase) -> str:
    return f"""
你是一名资深测试开发工程师。请严格根据下面的接口测试信息，生成一段可直接运行的 pytest 测试代码。

【硬性要求，必须全部满足】
1. 只输出 Python 代码，不要输出任何解释、说明、Markdown 代码块。
2. 只生成一个测试函数，函数名必须为 test_case_{api_case.id}。
3. 不要定义 class。
4. 不要使用 fixture。
5. 必须使用 httpx.request(method=..., url=..., headers=..., json=...) 发起请求。
6. 必须直接使用下面提供的 method、url、headers、body、expected_result。
7. 不要虚构 base_url、expected_result、message、success 等变量内容。
8. 不要替换、改写或猜测 URL，不要使用示例网站。
9. 代码必须与当前项目执行器兼容。
10. 断言必须包含：
   - 响应状态码断言
   - expected_result 中字段的断言
11. 若 headers、body、expected_result 是 JSON 字符串，请按 Python 字典处理。
12. 可以添加简短中文注释，但不要添加解释性段落。
13. 如果响应内容不是 JSON，不要调用 response.json()。
14. 只有当 expected_result 明确适合 JSON 字段断言时，才对 response.json() 结果做字段断言。
15. 如果 url 明显是网页首页或非接口地址，优先只断言状态码，不要虚构 message 等字段断言。

接口测试信息：
- 用例名称: {api_case.name}
- 用例描述: {api_case.description}
- 请求方法: {api_case.method}
- 请求地址: {api_case.url}
- 请求头: {api_case.headers}
- 请求体: {api_case.body}
- 预期结果: {api_case.expected_result}
""".strip()  # .strip()作用是去掉多行字符串开头结尾的多余空白，让 Prompt 更干净。


# 即使没有真正调用大模型，这个项目也能生成一份“模拟测试代码”
def generate_mock_test_code(api_case: APICase) -> str:
    headers_dict = safe_json_loads(api_case.headers)
    body_dict = safe_json_loads(api_case.body)
    expected_dict = safe_json_loads(api_case.expected_result)
    normalized_url = normalize_url(api_case.url)

    return f'''import httpx


def test_case_{api_case.id}():
    # 请求地址
    url = "{normalized_url}"
    # 请求方法
    method = "{api_case.method.upper()}"
    # 请求头
    headers = {repr(headers_dict)}
    # 请求体
    json_data = {repr(body_dict)}
    # 预期结果
    expected = {repr(expected_dict)}

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
'''


# 真正调用 LLM
def call_llm_generate_code(prompt: str) -> str:
    print("LLM_PROVIDER =", settings.LLM_PROVIDER)
    print("LLM_MODEL =", settings.LLM_MODEL)
    print("LLM_BASE_URL =", settings.LLM_BASE_URL)
    print("HAS_API_KEY =", bool(settings.LLM_API_KEY))

    provider = settings.LLM_PROVIDER.lower()
    if provider == "mock" or not settings.LLM_API_KEY:
        return ""

    # 请求头
    headers = {
        # 用 Bearer Token 传 API Key。
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    # 请求体
    payload = {
        # 指定具体模型名，比如某个 GPT 风格模型。
        "model": settings.LLM_MODEL or "deepseek-chat",
        # 说明你走的是 Chat 接口，而不是纯 prompt 接口。
        "messages": [
            {
                "role": "system",
                "content": "你是资深测试开发工程师，擅长生成 pytest 接口测试代码。只输出可运行的 Python 代码，不要解释。",
            },
            {"role": "user", "content": prompt},  # user 塞入真正任务内容，也就是 build_case_prompt() 拼出来的 Prompt。
        ],
        "temperature": 0.2,  # 它表示生成的随机性比较低，更偏稳定。
        "stream": False,
    }

    # 这一步是真正往 LLM 服务发 HTTP 请求。
    response = httpx.post(
        url=settings.LLM_BASE_URL,
        headers=headers,
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()  # 如果 HTTP 状态码不是 2xx，就直接抛异常。

    data = response.json()  # 把模型响应转成 Python 字典。
    content = data["choices"][0]["message"]["content"]
    print("LLM raw result preview:", content[:300] if content else "EMPTY")
    return content


# “去 markdown 代码块”的清洗
def clean_generated_code(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"^```python\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# 生成代码后做语法校验
def validate_python_code(code: str) -> bool:
    if not code:
        return False
    try:
        compile(code, "<generated_test_code>", "exec")
        return True
    except Exception:
        return False


# 生成代码后做规则校验
def validate_generated_code_rules(code: str, api_case: APICase) -> bool:
    if not code:
        return False

    lower_code = code.lower()

    # 不允许 class / fixture
    banned_keywords = ["class ", "@pytest.fixture"]
    if any(k in lower_code for k in banned_keywords):
        return False

    # 必须包含 request 通用写法
    if "httpx.request(" not in code:
        return False

    # 必须包含当前 case 的真实 URL（兼容 normalize_url 后的结果）
    normalized_url = normalize_url(api_case.url)
    if normalized_url and normalized_url not in code:
        return False

    # 必须包含当前 case 的 method
    if api_case.method and api_case.method.upper() not in code.upper():
        return False

    # 如果目标更像网页而不是 JSON 接口，就不要强制 response.json()
    if looks_like_webpage_url(api_case.url) and "response.json()" in code:
        return False

    return True


# 主流程函数。 这是整条链最终串起来的地方。
def generate_case_test_code(db: Session, case_id: int):
    # 第 1 步：查数据库拿 case
    api_case = db.query(APICase).filter(APICase.id == case_id).first()
    if not api_case:
        raise ValueError("测试用例不存在")

    prompt = build_case_prompt(api_case)
    llm_result = ""

    try:
        llm_result = call_llm_generate_code(prompt)
        llm_result = clean_generated_code(llm_result)
    except Exception as e:
        print("LLM generate error:", repr(e))
        llm_result = ""

    # 优先使用 LLM 结果；如果语法不合法或不符合项目规则，就 fallback 到 mock
    if (
        llm_result
        and validate_python_code(llm_result)
        and validate_generated_code_rules(llm_result, api_case)
    ):
        generated_code = llm_result
    else:
        generated_code = generate_mock_test_code(api_case)

    # 第 5 步：把生成代码写回数据库
    api_case.generated_test_code = generated_code
    db.commit()
    db.refresh(api_case)

    # 第 6 步：把代码写入文件系统
    file_path = save_test_code_to_file(case_id=api_case.id, code=generated_code)

    # 第 7 步：返回给前端
    return {
        "case_id": api_case.id,
        "case_name": api_case.name,
        "generated_test_code": generated_code,
        "file_path": file_path,
        "message": "AI 测试用例生成成功",
        "generated_at": datetime.now(),
    }