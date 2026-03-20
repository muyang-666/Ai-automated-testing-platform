from datetime import datetime  # 导入时间模块

from urllib.parse import parse_qsl, urlsplit
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

# 处理 JSON 字符串数据（保留原有函数名，兼容现有调用）
def safe_json_loads_any(raw_text: str | None):
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except Exception:
        return {}


def safe_json_loads(raw_text: str | None) -> dict:
    data = safe_json_loads_any(raw_text)
    return data if isinstance(data, dict) else {}


# 解析 URL 中自带的 query 参数
def parse_url_query(raw_url: str | None) -> dict:
    normalized_url = normalize_url(raw_url)
    if not normalized_url:
        return {}
    try:
        return dict(parse_qsl(urlsplit(normalized_url).query, keep_blank_values=True))
    except Exception:
        return {}


# 对请求头做基础规范化
# 目标不是“胡乱猜测”，而是修正常见的低级脏数据，例如把 Accept 错写成 key
def sanitize_headers(headers_dict: dict) -> dict:
    if not isinstance(headers_dict, dict):
        return {}

    normalized_headers = {}
    for raw_key, raw_value in headers_dict.items():
        key = str(raw_key).strip() if raw_key is not None else ""
        value = str(raw_value).strip() if raw_value is not None else ""
        if not key:
            continue

        lower_key = key.lower()

        # 常见脏数据修正：
        # 例如 {"application/json": "text/plain, */*"} 这种很像把 Accept/Content-Type 填反了
        # 这里先尽量保守：如果 key 看起来像 MIME 类型，而 value 又像 Accept 值，则把它当成 Accept
        if lower_key.startswith(("application/", "text/")) and ("," in value or "*/*" in value):
            normalized_headers.setdefault("Accept", value)
            continue

        normalized_headers[key] = value

    return normalized_headers


# 判断 body 更像 json 还是 form
# 这是当前 V1 最重要的“翻译层”：不是让模型瞎猜，而是先给模型一个更清晰的请求语义
def infer_body_type(api_case: APICase, headers_dict: dict, body_dict: dict, query_dict: dict) -> str:
    method = (api_case.method or "").upper()
    content_type = str(headers_dict.get("Content-Type", "")).lower()

    if "application/x-www-form-urlencoded" in content_type:
        return "form"

    if "application/json" in content_type:
        return "json"

    if method not in {"POST", "PUT", "PATCH"}:
        return "none"

    if not body_dict:
        return "none"

    # 如果 body 是扁平标量字典，且 URL query 与 body 有重叠，优先认为更像表单请求
    # 这能覆盖你现在这种 ?restatus=first + body里也有 restatus 的场景
    is_flat_scalar_dict = all(not isinstance(v, (dict, list)) for v in body_dict.values())
    has_overlap_with_query = any(k in query_dict for k in body_dict.keys())

    if is_flat_scalar_dict and has_overlap_with_query:
        return "form"

    # 如果没有显式 Content-Type，但 body 很像浏览器表单的扁平字典，也优先按 form 处理
    if is_flat_scalar_dict and "Content-Type" not in headers_dict:
        return "form"

    return "json"


# 构建“升级版断言计划”
# 核心思想：
# 1. 稳定字段 -> 精确断言
# 2. 易波动字段 -> 范围断言
# 3. 列表字段 -> 只做结构断言，不做全量相等
def build_assertion_plan(expected_dict: dict) -> dict:
    plan = {
        # 精确断言：适合断死值
        "exact_fields": {},
        # 嵌套对象下的精确断言
        "nested_exact_fields": {},
        # 范围/类型断言：适合分页统计类字段
        "range_fields": {},
        # 列表断言：只断结构，不断整表全量相等
        "list_checks": [],
    }

    if not isinstance(expected_dict, dict) or not expected_dict:
        return plan

    # ----------------------------
    # 1）顶层稳定字段：适合精确断言
    # ----------------------------
    stable_top_keys = ["status", "code", "message", "description", "success"]
    for key in stable_top_keys:
        value = expected_dict.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            plan["exact_fields"][key] = value

    # ----------------------------
    # 2）处理 data 对象
    # ----------------------------
    data = expected_dict.get("data")
    if isinstance(data, dict):
        # 2.1 data 下稳定字段：适合精确断言
        stable_data_keys = [
            "page",
            "epage",
            "page_size",
            "size",
            "current_page",
        ]
        data_exact_fields = {}
        for key in stable_data_keys:
            value = data.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                data_exact_fields[key] = value

        if data_exact_fields:
            plan["nested_exact_fields"]["data"] = data_exact_fields

        # 2.2 data 下易波动字段：适合范围断言，不断死具体值
        range_data_fields = {}
        if isinstance(data.get("total_items"), int):
            range_data_fields["total_items"] = {
                "type": "int",
                "min": 0,
            }

        if isinstance(data.get("total_pages"), int):
            range_data_fields["total_pages"] = {
                "type": "int",
                "min": 1,
            }

        if range_data_fields:
            plan["range_fields"]["data"] = range_data_fields

        # 2.3 items 列表：只做结构校验
        items = data.get("items")
        if isinstance(items, list):
            item_check = {
                "path": "data.items",
                "check": "list",
                # 如果 expected_result 里本来就有列表，这里默认要求至少返回 list
                "allow_empty": False,
            }

            # 如果列表里第一条是字典，可以顺便提取少量稳定字段做“首项结构断言”
            # 注意：这里不是断第一条所有值完全相等，只是校验它应包含哪些关键字段
            if len(items) > 0 and isinstance(items[0], dict):
                # 只保留更像“结构字段”的 key，不把 name / status / amount 这类业务值全断死
                preferred_sample_keys = [
                    "id",
                    "serialno",
                    "status",
                    "member_name",
                    "category_id",
                ]
                sample_required_keys = [k for k in preferred_sample_keys if k in items[0]]
                if sample_required_keys:
                    item_check["sample_required_keys"] = sample_required_keys

            plan["list_checks"].append(item_check)

    # ----------------------------
    # 3）兜底：如果没有提炼出任何计划，至少保留顶层简单标量字段
    # ----------------------------
    if (
        not plan["exact_fields"]
        and not plan["nested_exact_fields"]
        and not plan["range_fields"]
        and not plan["list_checks"]
    ):
        for key, value in expected_dict.items():
            if not isinstance(value, (dict, list)):
                plan["exact_fields"][key] = value

    return plan


# 输入质量检查：不急着拦死，只先形成“风险提示”
def validate_case_input_quality(api_case: APICase, raw_headers_dict: dict, body_dict: dict, query_dict: dict) -> list[str]:
    issues = []

    # 请求头 key 看起来像 MIME 类型，通常说明用户录入有问题
    for key in raw_headers_dict.keys():
        lower_key = str(key).lower()
        if lower_key.startswith(("application/", "text/")):
            issues.append("请求头键名疑似写成了 MIME 类型，请检查是否应为 Accept 或 Content-Type。")
            break

    # URL query 和 body 存在重复字段，说明请求语义可能不清晰
    overlap_keys = [k for k in body_dict.keys() if k in query_dict]
    if overlap_keys:
        issues.append(f"URL query 与 body 存在重复字段：{overlap_keys}，需要确认它们到底属于 query 还是 form/json body。")

    # 预期结果过重提醒
    expected_dict = safe_json_loads(api_case.expected_result)
    data = expected_dict.get("data") if isinstance(expected_dict, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and len(items) > 0:
        issues.append("expected_result 中包含完整 items 列表，生成代码时应避免做全量相等断言。")

    return issues


# 统一构建“规范化上下文”
def build_case_context(api_case: APICase) -> dict:
    raw_headers_dict = safe_json_loads(api_case.headers)
    headers_dict = sanitize_headers(raw_headers_dict)
    body_dict = safe_json_loads(api_case.body)
    expected_dict = safe_json_loads(api_case.expected_result)

    normalized_url = normalize_url(api_case.url)
    query_dict = parse_url_query(normalized_url)
    body_type = infer_body_type(api_case, headers_dict, body_dict, query_dict)
    assertion_plan = build_assertion_plan(expected_dict)
    input_issues = validate_case_input_quality(api_case, raw_headers_dict, body_dict, query_dict)

    return {
        "normalized_url": normalized_url,
        "query_dict": query_dict,
        "headers_dict": headers_dict,
        "body_dict": body_dict,
        "expected_dict": expected_dict,
        "body_type": body_type,
        "assertion_plan": assertion_plan,
        "input_issues": input_issues,
    }


# 把“升级版断言计划”翻译成 mock 代码里的 assert 语句
def build_assertion_code_from_plan(assertion_plan: dict) -> str:
    exact_fields = assertion_plan.get("exact_fields", {})
    nested_exact_fields = assertion_plan.get("nested_exact_fields", {})
    range_fields = assertion_plan.get("range_fields", {})
    list_checks = assertion_plan.get("list_checks", [])

    has_json_assertion = bool(exact_fields or nested_exact_fields or range_fields or list_checks)
    if not has_json_assertion:
        return "    # 当前没有可稳定断言的 JSON 字段，这里只断言状态码"

    lines = ["    response_json = response.json()"]

    # ----------------------------
    # 1）顶层精确断言
    # ----------------------------
    for key, value in exact_fields.items():
        lines.append(f"    assert response_json.get({key!r}) == {value!r}")

    # ----------------------------
    # 2）data 对象精确断言
    # ----------------------------
    needs_data_obj = (
        "data" in nested_exact_fields
        or "data" in range_fields
        or any(item.get("path", "").startswith("data.") for item in list_checks)
    )
    if needs_data_obj:
        lines.append("    data = response_json.get('data') or {}")
        lines.append("    assert isinstance(data, dict)")

    data_exact_fields = nested_exact_fields.get("data", {})
    for key, value in data_exact_fields.items():
        lines.append(f"    assert data.get({key!r}) == {value!r}")

    # ----------------------------
    # 3）data 对象范围/类型断言
    # ----------------------------
    data_range_fields = range_fields.get("data", {})
    for key, rule in data_range_fields.items():
        field_expr = f"data.get({key!r})"

        if rule.get("type") == "int":
            lines.append(f"    assert isinstance({field_expr}, int)")

        if "min" in rule:
            lines.append(f"    assert {field_expr} >= {rule['min']!r}")

        if "max" in rule:
            lines.append(f"    assert {field_expr} <= {rule['max']!r}")

    # ----------------------------
    # 4）列表结构断言
    # ----------------------------
    for item in list_checks:
        if item.get("path") == "data.items" and item.get("check") == "list":
            lines.append("    items = data.get('items') or []")
            lines.append("    assert isinstance(items, list)")

            allow_empty = item.get("allow_empty", True)
            if not allow_empty:
                lines.append("    assert len(items) > 0")

            sample_required_keys = item.get("sample_required_keys", [])
            if sample_required_keys:
                lines.append("    first_item = items[0]")
                lines.append("    assert isinstance(first_item, dict)")
                for key in sample_required_keys:
                    lines.append(f"    assert {key!r} in first_item")

    return "\n".join(lines)


# AI 生成链的核心：拼 Prompt
def build_case_prompt(api_case: APICase) -> str:
    ctx = build_case_context(api_case)

    body_type = ctx["body_type"]
    body_instruction = {
        "json": "本用例更像 JSON 请求，请优先使用 httpx.request(..., json=...) 传参。",
        "form": "本用例更像表单请求，请优先使用 httpx.request(..., data=...) 传参，不要使用 json=...",
        "none": "当前没有明确有效的请求体，请不要虚构 body 参数。",
    }.get(body_type, "请根据接口信息选择最合理的请求参数形式。")

    input_issues_text = "\n".join([f"- {item}" for item in ctx["input_issues"]]) if ctx["input_issues"] else "- 无明显输入风险"

    return f"""
你是一名资深测试开发工程师。请严格根据下面的接口测试信息，生成一段可直接运行的 pytest 测试代码。

【硬性要求，必须全部满足】
1. 只输出 Python 代码，不要输出任何解释、说明、Markdown 代码块。
2. 只生成一个测试函数，函数名必须为 test_case_{api_case.id}。
3. 不要定义 class。
4. 不要使用 fixture。
5. 必须使用 httpx.request(...) 发起请求。
6. 必须直接使用下面提供的 method、url、headers、body、expected_result，但允许你根据 Content-Type、query 参数和 body 结构，选择更合理的参数传递方式（json=... 或 data=...）。
7. 不要虚构 base_url，不要替换、改写或猜测 URL，不要使用示例网站。
8. 不要凭空虚构 Cookie、鉴权 token、业务字段值；如果接口信息里没有提供，就不要自己编造。
9. 代码必须与当前项目执行器兼容。
10. 必须先打印响应结果，再做断言。
11. 如果响应内容不是 JSON，不要调用 response.json()。
12. 不要对 data.items 这样的长列表做全量相等断言，优先只断言稳定字段。
13. 可以添加简短中文注释，但不要添加解释性段落。
14. 断言应优先依据“轻量断言计划”生成，而不是机械遍历整个 expected_result。
15. 如果 url 明显是网页首页或非接口地址，优先只断言状态码，不要虚构 message 等字段断言。
16. 在发起请求并拿到 response 后、任何断言前，必须打印响应状态码，格式必须严格为：
   print(f"===RESPONSE_STATUS_CODE==={{response.status_code}}")
17. 在发起请求并拿到 response 后、任何断言前，必须打印响应内容开始/结束标记，格式必须严格为：
   print("===RESPONSE_CONTENT_START===")
   print(response.text)
   print("===RESPONSE_CONTENT_END===")
18. 上述响应打印必须放在断言前，保证即使断言失败，也能采集到接口响应结果。

【规范化后的测试上下文】
- 规范化后的 URL: {ctx["normalized_url"]}
- URL query 参数: {ctx["query_dict"]}
- 规范化后的 headers: {ctx["headers_dict"]}
- 规范化后的 body: {ctx["body_dict"]}
- 识别出的 body_type: {body_type}
- body_type 指导: {body_instruction}
- 轻量断言计划: {ctx["assertion_plan"]}
- 输入风险提示:
{input_issues_text}

【原始接口测试信息】
- 用例名称: {api_case.name}
- 用例描述: {api_case.description}
- 请求方法: {api_case.method}
- 请求地址: {api_case.url}
- 请求头: {api_case.headers}
- 请求体: {api_case.body}
- 预期结果: {api_case.expected_result}
""".strip()


# 即使没有真正调用大模型，这个项目也能生成一份“更稳的规则式测试代码”
def generate_mock_test_code(api_case: APICase) -> str:
    ctx = build_case_context(api_case)

    headers_dict = ctx["headers_dict"]
    body_dict = ctx["body_dict"]
    normalized_url = ctx["normalized_url"]
    body_type = ctx["body_type"]
    assertion_plan = ctx["assertion_plan"]

    if body_type == "form":
        payload_declaration = f"    # 请求体（表单）\n    form_data = {repr(body_dict)}"
        request_arg = ",\n        data=form_data"
    elif body_type == "json":
        payload_declaration = f"    # 请求体（JSON）\n    json_data = {repr(body_dict)}"
        request_arg = ",\n        json=json_data"
    else:
        payload_declaration = "    # 当前没有明确有效的请求体"
        request_arg = ""

    assertion_code = build_assertion_code_from_plan(assertion_plan)

    return f'''import httpx


def test_case_{api_case.id}():
    # 请求地址
    url = "{normalized_url}"
    # 请求方法
    method = "{api_case.method.upper()}"
    # 请求头（已做基础规范化）
    headers = {repr(headers_dict)}
{payload_declaration}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {repr(assertion_plan)}

    response = httpx.request(
        method=method,
        url=url,
        headers=headers{request_arg}
    )

    # 在断言前先打印响应结果，供执行器解析并入库
    print(f"===RESPONSE_STATUS_CODE==={{response.status_code}}")
    print("===RESPONSE_CONTENT_START===")
    print(response.text)
    print("===RESPONSE_CONTENT_END===")

    # 断言状态码
    assert response.status_code == 200

{assertion_code}
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
        "temperature": 0.0,  # 它表示生成的随机性比较低，更偏稳定。
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
    ctx = build_case_context(api_case)
    body_type = ctx["body_type"]

    # 不允许 class / fixture
    banned_keywords = ["class ", "@pytest.fixture"]
    if any(k in lower_code for k in banned_keywords):
        return False

    # 必须包含 request 通用写法
    if "httpx.request(" not in code:
        return False

    # 必须包含当前 case 的真实 URL（兼容 normalize_url 后的结果）
    normalized_url = ctx["normalized_url"]
    if normalized_url and normalized_url not in code:
        return False

    # 必须包含当前 case 的 method
    if api_case.method and api_case.method.upper() not in code.upper():
        return False

    # 如果目标更像网页而不是 JSON 接口，就不要强制 response.json()
    if looks_like_webpage_url(api_case.url) and "response.json()" in code:
        return False

    # 必须包含响应结果采集标记。这样 pytest_runner 才能稳定解析出响应状态码和响应内容
    required_response_markers = [
        "===RESPONSE_STATUS_CODE===",
        "===RESPONSE_CONTENT_START===",
        "===RESPONSE_CONTENT_END===",
    ]
    if any(marker not in code for marker in required_response_markers):
        return False

    # 如果是 form 场景，必须使用 data=，不能再用 json=
    if body_type == "form":
        if "data=" not in code:
            return False
        if "json=" in code:
            return False

    # 如果是 json 场景，且 body 不为空，优先要求使用 json=
    if body_type == "json" and ctx["body_dict"]:
        if "json=" not in code:
            return False

    # 如果预期结果里存在长列表 items，不接受“全量遍历 expected.items()”这种脆弱断言
    expected_dict = ctx["expected_dict"]
    data = expected_dict.get("data") if isinstance(expected_dict, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and "for key, value in expected.items()" in code:
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