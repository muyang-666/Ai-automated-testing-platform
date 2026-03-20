from datetime import datetime
from urllib.parse import parse_qsl, urlsplit
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_case import APICase
from app.utils.file_writer import save_test_code_to_file


# 参数变量引用格式：<<变量名>>
PARAM_REF_PATTERN = re.compile(r"<<([A-Za-z_][A-Za-z0-9_]*)>>")


# 处理 JSON 字符串数据
def safe_json_loads(raw_text: str | None) -> dict:
    if not raw_text:
        return {}
    try:
        data = json.loads(raw_text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# 处理用户录入测试用例时，URL 格式
def normalize_url(raw_url: str | None) -> str:
    if not raw_url:
        return ""

    raw_url = raw_url.strip()

    # 如果 URL 中本身就包含参数变量引用，例如 <<base_url>>/mock/login
    # 这里不要强行补 http://，避免把占位语义搞坏
    if "<<" in raw_url and ">>" in raw_url:
        return raw_url

    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url

    return f"http://{raw_url}"


# 判断 URL 是否更像网页地址而不是标准 JSON 接口
def looks_like_webpage_url(url: str | None) -> bool:
    if not url:
        return False

    lower_url = url.lower().strip()
    return (
        "www." in lower_url
        or "baidu.com" in lower_url
        or "qq.com" in lower_url
        or "163.com" in lower_url
        or "sohu.com" in lower_url
    )


# 解析 URL 中自带的 query 参数
def parse_url_query(raw_url: str | None) -> dict:
    normalized_url = normalize_url(raw_url)
    if not normalized_url:
        return {}

    # 含变量占位的 URL，暂不做 query 解析，避免误判
    if "<<" in normalized_url and ">>" in normalized_url:
        return {}

    try:
        return dict(parse_qsl(urlsplit(normalized_url).query, keep_blank_values=True))
    except Exception:
        return {}


# 对请求头做基础规范化
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
        # 例如 {"application/json": "text/plain, */*"} 这种更像把 Accept/Content-Type 填反了
        if lower_key.startswith(("application/", "text/")) and ("," in value or "*/*" in value):
            normalized_headers.setdefault("Accept", value)
            continue

        normalized_headers[key] = value

    return normalized_headers


# 判断 body 更像 json 还是 form
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

    is_flat_scalar_dict = all(not isinstance(v, (dict, list)) for v in body_dict.values())
    has_overlap_with_query = any(k in query_dict for k in body_dict.keys())

    if is_flat_scalar_dict and has_overlap_with_query:
        return "form"

    if is_flat_scalar_dict and "Content-Type" not in headers_dict:
        return "form"

    return "json"


# 提取原始文本中的 <<变量名>> 参数引用
def extract_parameter_refs_from_text(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    return list(dict.fromkeys(PARAM_REF_PATTERN.findall(str(raw_text))))


# 只提取“请求相关”的参数变量引用
def extract_request_parameter_refs(api_case: APICase) -> list[str]:
    refs = []
    refs.extend(extract_parameter_refs_from_text(api_case.url))
    refs.extend(extract_parameter_refs_from_text(api_case.headers))
    refs.extend(extract_parameter_refs_from_text(api_case.body))
    return list(dict.fromkeys(refs))


# 构建“升级版断言计划”
def build_assertion_plan(expected_dict: dict) -> dict:
    plan = {
        "exact_fields": {},
        "nested_exact_fields": {},
        "range_fields": {},
        "list_checks": [],
    }

    if not isinstance(expected_dict, dict) or not expected_dict:
        return plan

    stable_top_keys = ["status", "code", "message", "description", "success"]
    for key in stable_top_keys:
        value = expected_dict.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            plan["exact_fields"][key] = value

    data = expected_dict.get("data")
    if isinstance(data, dict):
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

        items = data.get("items")
        if isinstance(items, list):
            item_check = {
                "path": "data.items",
                "check": "list",
                "allow_empty": False,
            }

            if len(items) > 0 and isinstance(items[0], dict):
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
def validate_case_input_quality(
    api_case: APICase,
    raw_headers_dict: dict,
    body_dict: dict,
    query_dict: dict,
) -> list[str]:
    issues = []

    for key in raw_headers_dict.keys():
        lower_key = str(key).lower()
        if lower_key.startswith(("application/", "text/")):
            issues.append("请求头键名疑似写成了 MIME 类型，请检查是否应为 Accept 或 Content-Type。")
            break

    overlap_keys = [k for k in body_dict.keys() if k in query_dict]
    if overlap_keys:
        issues.append(f"URL query 与 body 存在重复字段：{overlap_keys}，需要确认它们到底属于 query 还是 form/json body。")

    expected_dict = safe_json_loads(api_case.expected_result)
    data = expected_dict.get("data") if isinstance(expected_dict, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and len(items) > 0:
        issues.append("expected_result 中包含完整 items 列表，生成代码时应避免做全量相等断言。")

    if extract_request_parameter_refs(api_case):
        issues.append("原始接口信息中包含 <<变量名>> 参数引用，生成代码时必须直接使用变量名，不能加引号。")

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
    parameter_refs = extract_request_parameter_refs(api_case)

    return {
        "normalized_url": normalized_url,
        "query_dict": query_dict,
        "headers_dict": headers_dict,
        "body_dict": body_dict,
        "expected_dict": expected_dict,
        "body_type": body_type,
        "assertion_plan": assertion_plan,
        "input_issues": input_issues,
        "parameter_refs": parameter_refs,
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

    for key, value in exact_fields.items():
        lines.append(f"    assert response_json.get({key!r}) == {value!r}")

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

    data_range_fields = range_fields.get("data", {})
    for key, rule in data_range_fields.items():
        field_expr = f"data.get({key!r})"

        if rule.get("type") == "int":
            lines.append(f"    assert isinstance({field_expr}, int)")

        if "min" in rule:
            lines.append(f"    assert {field_expr} >= {rule['min']!r}")

        if "max" in rule:
            lines.append(f"    assert {field_expr} <= {rule['max']!r}")

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


# 是否更适合禁用环境代理
def should_disable_env_proxy(url: str | None) -> bool:
    if not url:
        return False

    lower_url = str(url).lower()
    return (
        "127.0.0.1" in lower_url
        or "localhost" in lower_url
    )


# AI 生成链的核心：拼 Prompt
def build_case_prompt(api_case: APICase) -> str:
    ctx = build_case_context(api_case)

    body_type = ctx["body_type"]
    body_instruction = {
        "json": "本用例更像 JSON 请求，请优先使用 httpx.request(..., json=...) 传参。",
        "form": "本用例更像表单请求，请优先使用 httpx.request(..., data=...) 传参，不要使用 json=...。",
        "none": "当前没有明确有效的请求体，请不要虚构 body 参数。",
    }.get(body_type, "请根据接口信息选择最合理的请求参数形式。")

    input_issues_text = "\n".join([f"- {item}" for item in ctx["input_issues"]]) if ctx["input_issues"] else "- 无明显输入风险"
    parameter_refs_text = ", ".join(ctx["parameter_refs"]) if ctx["parameter_refs"] else "无"

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
10. 生成的测试代码开头必须包含：
from app.utils.parameter import *
不允许省略，不允许替换成其他导入方式。
11. 如果原始接口信息中的任意字段值是 <<变量名>> 格式，表示这是参数变量引用，不是普通字符串。
12. 生成 Python 代码时，必须去掉外层 << >>，直接使用里面的变量名，不能加引号。
13. 对于 <<变量名>> 这种参数变量引用，必须严格遵守以下规则：
- 不要保留 << >>
- 不要写成 "<<变量名>>"
- 不要写成 "变量名"
- 必须直接写成变量名本身
14. 参数变量引用示例：
- 原始值：<<Cookieb>>
- 生成值：Cookieb
- 原始值：<<user_token>>
- 生成值：user_token
15. 如果某个请求头字段的值是 <<变量名>>，则生成代码时，该字段值必须直接使用这个变量名。
16. 如果某个请求体字段的值是 <<变量名>>，则生成代码时，该字段值必须直接使用这个变量名。
17. 只有 <<变量名>> 才表示变量引用；普通文本仍然按普通字符串处理。
18. 普通字符串不要误处理成变量；只有带 << >> 的内容才按变量处理。
19. 最终生成的代码中，绝对不允许出现 << 或 >>。
20. 最终生成的代码中，绝对不允许把变量引用写成字符串。
21. 必须先打印响应结果，再做断言。
22. 如果响应内容不是 JSON，不要调用 response.json()。
23. 不要对 data.items 这样的长列表做全量相等断言，优先只断言稳定字段。
24. 可以添加简短中文注释，但不要添加解释性段落。
25. 断言应优先依据“轻量断言计划”生成，而不是机械遍历整个 expected_result。
26. 如果 url 明显是网页首页或非接口地址，优先只断言状态码，不要虚构 message 等字段断言。
27. 在发起请求并拿到 response 后、任何断言前，必须打印响应状态码，格式必须严格为：
print(f"===RESPONSE_STATUS_CODE==={{response.status_code}}")
28. 在发起请求并拿到 response 后、任何断言前，必须打印响应内容开始/结束标记，格式必须严格为：
print("===RESPONSE_CONTENT_START===")
print(response.text)
print("===RESPONSE_CONTENT_END===")
29. 上述响应打印必须放在断言前，保证即使断言失败，也能采集到接口响应结果。

【规范化后的测试上下文】
- 规范化后的 URL: {ctx["normalized_url"]}
- URL query 参数: {ctx["query_dict"]}
- 规范化后的 headers: {ctx["headers_dict"]}
- 规范化后的 body: {ctx["body_dict"]}
- 识别出的 body_type: {body_type}
- body_type 指导: {body_instruction}
- 轻量断言计划: {ctx["assertion_plan"]}
- 识别出的参数变量引用: {parameter_refs_text}
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


# 对 AI 生成后的代码做参数引用后处理
def postprocess_parameter_references(code: str) -> str:
    """
    目标：
    1. 强制补上：from app.utils.parameter import *
    2. 把 "<<abc>>" / '<<abc>>' 转成 abc
    3. 把 "Bearer <<token>>" 转成 f"Bearer {token}"
    4. 把裸的 <<abc>> 转成 abc
    """
    if not code:
        return code

    result = code.strip()
    required_import = "from app.utils.parameter import *"

    if required_import not in result:
        result = f"{required_import}\n\n{result}"

    # 先处理被引号包住且包含 <<变量>> 的字符串
    quoted_placeholder_pattern = re.compile(
        r"""(['"])([^'"\n]*<<[A-Za-z_][A-Za-z0-9_]*>>[^'"\n]*)\1"""
    )

    def replace_quoted_placeholder(match):
        quote = match.group(1)
        content = match.group(2)

        # 如果整个字符串就是 <<变量名>>，直接替换成变量名
        full_match = PARAM_REF_PATTERN.fullmatch(content)
        if full_match:
            return full_match.group(1)

        # 如果字符串里混有普通文本 + <<变量名>>，转成 f-string
        transformed = PARAM_REF_PATTERN.sub(lambda m: "{" + m.group(1) + "}", content)
        return f"f{quote}{transformed}{quote}"

    result = quoted_placeholder_pattern.sub(replace_quoted_placeholder, result)

    # 再处理没有引号包住的 <<变量名>>
    result = PARAM_REF_PATTERN.sub(r"\1", result)

    return result


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

    request_extra = ",\n        timeout=10.0"
    if should_disable_env_proxy(normalized_url):
        request_extra += ",\n        trust_env=False"

    assertion_code = build_assertion_code_from_plan(assertion_plan)

    mock_code = f'''import httpx


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
        headers=headers{request_arg}{request_extra}
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
    return postprocess_parameter_references(mock_code)


# 真正调用 LLM
def call_llm_generate_code(prompt: str) -> str:
    print("LLM_PROVIDER =", settings.LLM_PROVIDER)
    print("LLM_MODEL =", settings.LLM_MODEL)
    print("LLM_BASE_URL =", settings.LLM_BASE_URL)
    print("HAS_API_KEY =", bool(settings.LLM_API_KEY))

    provider = settings.LLM_PROVIDER.lower()
    if provider == "mock" or not settings.LLM_API_KEY:
        return ""

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.LLM_MODEL or "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是资深测试开发工程师，擅长生成 pytest 接口测试代码。只输出可运行的 Python 代码，不要解释。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "stream": False,
    }

    response = httpx.post(
        url=settings.LLM_BASE_URL,
        headers=headers,
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()

    data = response.json()
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

    banned_keywords = ["class ", "@pytest.fixture"]
    if any(k in lower_code for k in banned_keywords):
        return False

    if "httpx.request(" not in code:
        return False

    # 必须固定导入参数模块
    if "from app.utils.parameter import *" not in code:
        return False

    # 最终代码里不允许残留 << >>
    if "<<" in code or ">>" in code:
        return False

    # 必须包含当前 case 的真实 URL（如果 URL 本身不含参数变量引用）
    normalized_url = ctx["normalized_url"]
    if normalized_url and not PARAM_REF_PATTERN.search(api_case.url or ""):
        if normalized_url not in code:
            return False

    if api_case.method and api_case.method.upper() not in code.upper():
        return False

    if looks_like_webpage_url(api_case.url) and "response.json()" in code:
        return False

    required_response_markers = [
        "===RESPONSE_STATUS_CODE===",
        "===RESPONSE_CONTENT_START===",
        "===RESPONSE_CONTENT_END===",
    ]
    if any(marker not in code for marker in required_response_markers):
        return False

    if "timeout=" not in code:
        return False

    if should_disable_env_proxy(normalized_url) and "trust_env=False" not in code:
        return False

    if body_type == "form":
        if "data=" not in code:
            return False
        if "json=" in code:
            return False

    if body_type == "json" and ctx["body_dict"]:
        if "json=" not in code:
            return False

    expected_dict = ctx["expected_dict"]
    data = expected_dict.get("data") if isinstance(expected_dict, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and "for key, value in expected.items()" in code:
        return False

    # 如果原始请求信息里有参数变量引用，最终代码里必须出现对应变量名
    for param_name in ctx["parameter_refs"]:
        if param_name not in code:
            return False

    return True


# 主流程函数
def generate_case_test_code(db: Session, case_id: int):
    api_case = db.query(APICase).filter(APICase.id == case_id).first()
    if not api_case:
        raise ValueError("测试用例不存在")

    prompt = build_case_prompt(api_case)
    llm_result = ""

    try:
        llm_result = call_llm_generate_code(prompt)
        llm_result = clean_generated_code(llm_result)
        llm_result = postprocess_parameter_references(llm_result)
    except Exception as e:
        print("LLM generate error:", repr(e))
        llm_result = ""

    if (
        llm_result
        and validate_python_code(llm_result)
        and validate_generated_code_rules(llm_result, api_case)
    ):
        generated_code = llm_result
    else:
        generated_code = generate_mock_test_code(api_case)

    # 再做一次兜底处理，保证最终落库/落文件的代码统一
    generated_code = postprocess_parameter_references(generated_code)

    if not validate_python_code(generated_code):
        raise ValueError("生成后的测试代码语法不合法")

    api_case.generated_test_code = generated_code
    db.commit()
    db.refresh(api_case)

    file_path = save_test_code_to_file(case_id=api_case.id, code=generated_code)

    return {
        "case_id": api_case.id,
        "case_name": api_case.name,
        "generated_test_code": generated_code,
        "file_path": file_path,
        "message": "AI 测试用例生成成功",
        "generated_at": datetime.now(),
    }