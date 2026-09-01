from datetime import datetime  # 导入时间模块
from urllib.parse import parse_qsl, urlsplit
import json
import re

from sqlalchemy.orm import Session  # 说明 service 会操作数据库

from app.models.api_case import APICase  # 规则生成代码的原材料，就是数据库里的测试用例对象
from app.utils.file_writer import save_test_code_to_file  # 把最终生成代码写入 tests_generated 目录


# 参数变量引用格式：<<变量名>>
PARAM_REF_PATTERN = re.compile(r"<<([A-Za-z_][A-Za-z0-9_]*)>>")
SUPPORTED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
DEFAULT_EXPECTED_STATUS_CODE = 200
EXPECTED_HTTP_STATUS_KEYS = (
    "status_code",
    "http_status",
    "httpStatus",
    "http_status_code",
    "response_status_code",
)


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

    # 如果 URL 中本身就包含参数变量引用，例如 <<HOST>>/mock/login
    # 这里不要强行补 http://，避免把占位语义搞坏
    if "<<" in raw_url and ">>" in raw_url:
        return raw_url

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


def infer_expected_status_code(expected_dict: dict) -> int:
    if not isinstance(expected_dict, dict):
        return DEFAULT_EXPECTED_STATUS_CODE

    for key in EXPECTED_HTTP_STATUS_KEYS:
        raw_value = expected_dict.get(key)
        if raw_value is None or isinstance(raw_value, bool):
            continue
        try:
            status_code = int(raw_value)
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599:
            return status_code

    return DEFAULT_EXPECTED_STATUS_CODE


def validate_rule_generation_input(api_case: APICase, ctx: dict) -> None:
    method = (api_case.method or "").upper().strip()
    if not method:
        raise ValueError("请求方法不能为空，无法规则生成")
    if method not in SUPPORTED_HTTP_METHODS:
        raise ValueError(f"规则生成暂不支持请求方法：{api_case.method}")

    if not ctx.get("normalized_url"):
        raise ValueError("请求地址不能为空，无法规则生成")


# 对请求头做基础规范化
# 目标不是“胡乱猜测”，而是修正常见的低级脏数据
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
# 这是当前 V1 最重要的“翻译层”
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
    is_flat_scalar_dict = all(not isinstance(v, (dict, list)) for v in body_dict.values())
    has_overlap_with_query = any(k in query_dict for k in body_dict.keys())

    if is_flat_scalar_dict and has_overlap_with_query:
        return "form"

    # 如果没有显式 Content-Type，但 body 很像浏览器表单的扁平字典，也优先按 form 处理
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
# 核心思想：
# 1. 稳定字段 -> 精确断言
# 2. 易波动字段 -> 范围断言
# 3. 列表字段 -> 只做结构断言，不做全量相等
def build_assertion_plan(expected_dict: dict) -> dict:
    plan = {
        "exact_fields": {},
        "nested_exact_fields": {},
        "range_fields": {},
        "list_checks": [],
    }

    if not isinstance(expected_dict, dict) or not expected_dict:
        return plan

    # 1）顶层稳定字段：适合精确断言
    stable_top_keys = ["status", "code", "message", "description", "success"]
    for key in stable_top_keys:
        value = expected_dict.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            plan["exact_fields"][key] = value

    # 2）处理 data 对象
    data = expected_dict.get("data")
    if isinstance(data, dict):
        # 2.1 data 下稳定字段：适合精确断言
        stable_data_keys = ["page", "epage", "page_size", "size", "current_page"]
        data_exact_fields = {}
        for key in stable_data_keys:
            value = data.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                data_exact_fields[key] = value

        if data_exact_fields:
            plan["nested_exact_fields"]["data"] = data_exact_fields

        # 2.2 data 下易波动字段：适合范围断言
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
                "allow_empty": False,
            }

            # 如果列表里第一条是字典，顺便提取少量稳定字段做“首项结构断言”
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

    # 3）兜底：如果没有提炼出任何计划，至少保留顶层简单标量字段
    if (
        not plan["exact_fields"]
        and not plan["nested_exact_fields"]
        and not plan["range_fields"]
        and not plan["list_checks"]
    ):
        for key, value in expected_dict.items():
            if key in EXPECTED_HTTP_STATUS_KEYS:
                continue
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
    expected_status_code = infer_expected_status_code(expected_dict)
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
        "expected_status_code": expected_status_code,
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

    lines = [
        "    try:",
        "        response_json = response.json()",
        "    except ValueError:",
        '        assert False, f"响应不是合法 JSON，无法执行字段断言: {response.text[:500]}"',
    ]

    # 1）顶层精确断言
    for key, value in exact_fields.items():
        lines.append(f"    assert response_json.get({key!r}) == {value!r}")

    # 2）data 对象精确断言
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

    # 3）data 对象范围/类型断言
    data_range_fields = range_fields.get("data", {})
    for key, rule in data_range_fields.items():
        field_expr = f"data.get({key!r})"

        if rule.get("type") == "int":
            lines.append(f"    assert isinstance({field_expr}, int)")

        if "min" in rule:
            lines.append(f"    assert {field_expr} >= {rule['min']!r}")

        if "max" in rule:
            lines.append(f"    assert {field_expr} <= {rule['max']!r}")

    # 4）列表结构断言
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


# 对生成后的代码做参数引用后处理
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
    validate_rule_generation_input(api_case, ctx)

    headers_dict = ctx["headers_dict"]
    body_dict = ctx["body_dict"]
    normalized_url = ctx["normalized_url"]
    method = (api_case.method or "").upper().strip()
    body_type = ctx["body_type"]
    assertion_plan = ctx["assertion_plan"]
    expected_status_code = ctx["expected_status_code"]

    if looks_like_webpage_url(api_case.url):
        assertion_plan = {
            "exact_fields": {},
            "nested_exact_fields": {},
            "range_fields": {},
            "list_checks": [],
        }

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
    url = {normalized_url!r}
    # 请求方法
    method = {method!r}
    # 请求头（已做基础规范化）
    headers = {repr(headers_dict)}
{payload_declaration}

    # 轻量断言计划（只保留更稳定的预期字段）
    expected_plan = {repr(assertion_plan)}
    expected_status_code = {expected_status_code}

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
    assert response.status_code == expected_status_code

{assertion_code}
'''
    return postprocess_parameter_references(mock_code)


# 生成代码后做语法校验
def validate_python_code(code: str) -> bool:
    if not code:
        return False
    try:
        compile(code, "<generated_test_code>", "exec")
        return True
    except Exception:
        return False


# 规则校验：返回失败原因，方便前端展示规则生成失败细节
def validate_generated_code_rules_with_reason(code: str, api_case: APICase) -> tuple[bool, str]:
    if not code:
        return False, "代码为空"

    lower_code = code.lower()
    ctx = build_case_context(api_case)
    body_type = ctx["body_type"]

    banned_keywords = ["class ", "@pytest.fixture"]
    if any(k in lower_code for k in banned_keywords):
        return False, "包含被禁止的 class 或 fixture"

    if "httpx.request(" not in code:
        return False, "未使用 httpx.request"

    if "from app.utils.parameter import *" not in code:
        return False, "缺少固定导入 from app.utils.parameter import *"

    if "<<" in code or ">>" in code:
        return False, "最终代码里仍残留 << >> 参数占位符"

    normalized_url = ctx["normalized_url"]
    if normalized_url and not PARAM_REF_PATTERN.search(api_case.url or ""):
        if normalized_url not in code:
            return False, f"代码中未包含规范化后的 URL: {normalized_url}"

    if api_case.method and api_case.method.upper() not in code.upper():
        return False, f"代码中未包含请求方法: {api_case.method}"

    if looks_like_webpage_url(api_case.url) and "response.json()" in code:
        return False, "网页类地址不应调用 response.json()"

    required_response_markers = [
        "===RESPONSE_STATUS_CODE===",
        "===RESPONSE_CONTENT_START===",
        "===RESPONSE_CONTENT_END===",
    ]
    for marker in required_response_markers:
        if marker not in code:
            return False, f"缺少响应采集标记: {marker}"

    if "timeout=" not in code:
        return False, "缺少 timeout 参数"

    if "expected_status_code =" not in code or "response.status_code == expected_status_code" not in code:
        return False, "缺少规则生成状态码断言"

    if should_disable_env_proxy(normalized_url) and "trust_env=False" not in code:
        return False, "本地/内网地址缺少 trust_env=False"

    if body_type == "form":
        if "data=" not in code:
            return False, "form 场景未使用 data="
        if "json=" in code:
            return False, "form 场景错误使用了 json="

    if body_type == "json" and ctx["body_dict"]:
        if "json=" not in code:
            return False, "json 场景未使用 json="

    expected_dict = ctx["expected_dict"]
    data = expected_dict.get("data") if isinstance(expected_dict, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and "for key, value in expected.items()" in code:
        return False, "长列表场景仍在全量遍历 expected.items()"

    for param_name in ctx["parameter_refs"]:
        if param_name not in code:
            return False, f"缺少参数变量引用: {param_name}"

    return True, "校验通过"


# 保留原函数名，兼容其他旧调用
def validate_generated_code_rules(code: str, api_case: APICase) -> bool:
    is_valid, _ = validate_generated_code_rules_with_reason(code, api_case)
    return is_valid


# 公共保存逻辑：规则生成后统一写回数据库和文件系统
def save_generated_code_result(db: Session, api_case: APICase, generated_code: str, generated_by: str):
    generated_code = postprocess_parameter_references(generated_code)

    if not validate_python_code(generated_code):
        raise ValueError("生成后的测试代码语法不合法")

    # 把生成代码写回数据库
    api_case.generated_test_code = generated_code
    db.commit()
    db.refresh(api_case)

    # 把代码写入文件系统（自动覆盖 tests_generated 下同名文件）
    file_path = save_test_code_to_file(case_id=api_case.id, code=generated_code)

    return {
        "case_id": api_case.id,
        "case_name": api_case.name,
        "generated_test_code": generated_code,
        "file_path": file_path,
        "generated_by": generated_by,
        "message": "测试代码生成成功",
        "generated_at": datetime.now(),
    }


# 只走规则生成
def generate_case_test_code_by_rule(db: Session, case_id: int):
    api_case = db.query(APICase).filter(APICase.id == case_id).first()
    if not api_case:
        raise ValueError("测试用例不存在")

    generated_code = generate_mock_test_code(api_case)
    is_valid, reason = validate_generated_code_rules_with_reason(generated_code, api_case)
    if not is_valid:
        raise ValueError(f"规则生成代码未通过项目规则校验：{reason}")

    return save_generated_code_result(db, api_case, generated_code, generated_by="rule")


# 兼容旧内部调用：接口用例执行代码统一走规则生成
def generate_case_test_code(db: Session, case_id: int):
    return generate_case_test_code_by_rule(db, case_id)
