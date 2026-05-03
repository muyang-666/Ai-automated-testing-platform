import json
import re

from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.schemas.api_document_generation import (
    GenerateApiCasesRequest,
    GenerateApiCasesResponse,
    GeneratedApiCaseItem,
    SaveGeneratedApiCasesRequest,
    SaveGeneratedApiCasesResponse,
)
from app.services.llm_client_service import call_llm_by_scene

ALLOWED_CASE_TYPES = {"正常场景", "异常场景", "边界场景", "业务规则场景", "其他"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


def _json_dumps(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_api_doc_to_case_prompt(api_doc: ApiDocument) -> str:
    lines = [
        "你是一名资深测试工程师。请根据以下接口文档，设计接口测试用例。",
        "",
        "【最重要 - 输出格式】",
        "你的整个回复必须是一个纯 JSON 数组，除此之外一个字符都不要。",
        "不要 Markdown 代码块（禁止 ```），不要任何解释，不要\"以下是生成的用例\"这类开头语。",
        "你的回复的第一个字符必须是 [，最后一个字符必须是 ]。",
        "数组中每个元素是一个对象，包含以下字段：",
        "- name: 用例名称",
        "- description: 用例描述",
        "- method: GET/POST/PUT/DELETE/PATCH",
        "- url: 接口地址",
        "- headers: 请求头 JSON 对象，无则为 {}",
        "- body: 请求体，JSON 对象/数组/字符串/null",
        "- expected_result: 预期结果 JSON 对象",
        "- case_type: 正常场景/异常场景/边界场景/业务规则场景/其他",
        "- priority: P0/P1/P2",
        "- remark: 备注或空字符串",
    ]

    # supplementary_prompt 优先级最高
    if api_doc.supplementary_prompt:
        lines.append("")
        lines.append("【补充提示词 - 必须严格遵守】")
        lines.append(api_doc.supplementary_prompt)

    lines.append("")
    lines.append("【接口文档内容】")
    lines.append(api_doc.content or api_doc.name)

    if api_doc.method or api_doc.url:
        lines.append("")
        lines.append("【参考信息】")
        if api_doc.method:
            lines.append(f"- 主要方法：{api_doc.method}")
        if api_doc.url:
            lines.append(f"- 基础地址：{api_doc.url}")

    lines.extend([
        "",
        "【用例设计要求】",
        "1. 文档中可能描述多个接口，请为每个接口生成对应的测试用例。",
        "2. 为每个接口覆盖：正常场景、异常场景（参数缺失/格式错误/值非法）、边界场景。",
        "3. 如果文档中体现了登录态或 Token，也要覆盖鉴权异常场景。",
        "4. 由你自行判断生成多少条用例，以覆盖全面为准。",
        "",
        "再次强调：只输出纯 JSON 数组，第一个字符是 [，最后一个字符是 ]。",
    ])

    return "\n".join(lines)


def _try_parse_json(text: str) -> tuple[list[dict] | None, str]:
    """尝试把 text 解析或用常见方式修复后解析。返回 (cases, error_msg)。"""
    err_msgs = []

    # 预处理：去掉 BOM、零宽字符
    cleaned = text.strip().lstrip("﻿​‌‍⁠ï»¿")

    # 策略 1：直接解析
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data, ""
        if isinstance(data, dict):
            for key in ("cases", "test_cases", "items", "results", "data"):
                if isinstance(data.get(key), list):
                    return data[key], ""
            for val in data.values():
                if isinstance(val, list):
                    return val, ""
        err_msgs.append("策略1: 解析成功但未找到数组")
    except json.JSONDecodeError as e:
        err_msgs.append(f"策略1: {e}")

    # 策略 2：提取 ``` ... ``` 代码块
    for pattern in [r"```json\s*([\s\S]*?)```", r"```\s*([\s\S]*?)```"]:
        for m in re.finditer(pattern, cleaned):
            block = m.group(1).strip()
            result, _ = _try_parse_json(block)
            if result:
                return result, ""
            err_msgs.append("策略2: 代码块内解析失败")

    # 策略 3：截取第一个 [ 到最后一个 ]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        segment = cleaned[start:end + 1]
        try:
            data = json.loads(segment)
            if isinstance(data, list):
                return data, ""
            err_msgs.append("策略3: 截取段解析为非数组")
        except json.JSONDecodeError as e:
            err_msgs.append(f"策略3(截取): {e}")

        # 策略 3b：修复尾部逗号后再试
        fixed = re.sub(r",\s*([}\]])", r"\1", segment)
        if fixed != segment:
            try:
                data = json.loads(fixed)
                if isinstance(data, list):
                    return data, ""
            except json.JSONDecodeError as e:
                err_msgs.append(f"策略3b(去尾逗号): {e}")

    # 策略 4：正则匹配 JSON 对象再拼成数组
    obj_texts = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned)
    if len(obj_texts) >= 1:
        possible_json = "[" + ",".join(obj_texts) + "]"
        try:
            data = json.loads(possible_json)
            if isinstance(data, list) and len(data) > 0:
                return data, ""
        except json.JSONDecodeError as e:
            err_msgs.append(f"策略4(正则拼装): {e}")

    # 策略 5：逐个 JSON 对象解析，跳过非法项（最强兜底）
    if len(obj_texts) >= 1:
        parsed = []
        skipped = 0
        for obj_text in obj_texts:
            try:
                obj = json.loads(obj_text)
                if isinstance(obj, dict):
                    parsed.append(obj)
                else:
                    skipped += 1
            except json.JSONDecodeError:
                # 尝试修复尾部逗号
                fixed_obj = re.sub(r",\s*([}\]])", r"\1", obj_text)
                try:
                    obj = json.loads(fixed_obj)
                    if isinstance(obj, dict):
                        parsed.append(obj)
                    else:
                        skipped += 1
                except json.JSONDecodeError:
                    skipped += 1
        if parsed:
            return parsed, f"部分成功: {len(parsed)}条解析成功, {skipped}条跳过"

    return None, "; ".join(err_msgs) if err_msgs else "未知错误"


def parse_llm_api_cases(raw_output: str) -> tuple[list[dict], list[str]]:
    if not raw_output or not raw_output.strip():
        return [], ["LLM 返回内容为空"]

    cases, err = _try_parse_json(raw_output)
    if cases is not None:
        if err:
            # 部分成功，附带警告
            return cases, [err]
        return cases, []

    # 所有策略失败，返回详细错误
    detail = raw_output.strip()[:500]
    return [], [f"无法解析 LLM 返回内容为 JSON 数组。解析详情: {err}。原始返回前500字符: {detail}"]


def validate_generated_api_cases(
    cases: list[dict], api_doc: ApiDocument
) -> tuple[list[dict], list[str]]:
    errors = []
    validated = []

    for i, item in enumerate(cases):
        if not isinstance(item, dict):
            errors.append(f"第 {i + 1} 条不是有效对象，已跳过")
            continue

        name = str(item.get("name", "")).strip()
        if not name:
            name = f"{api_doc.name}_用例_{i + 1}"

        method = str(item.get("method", "GET")).strip().upper()
        if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            method = "GET"

        url = str(item.get("url", "")).strip()
        if not url:
            url = api_doc.url or ""

        headers = item.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}

        body = item.get("body")
        # body can be dict, list, string, or None

        expected_result = item.get("expected_result", {})
        if not isinstance(expected_result, (dict, str)):
            expected_result = {}

        case_type = str(item.get("case_type", "正常场景")).strip()
        if case_type not in ALLOWED_CASE_TYPES:
            case_type = "其他"

        priority = str(item.get("priority", "P1")).strip().upper()
        if priority not in ALLOWED_PRIORITIES:
            priority = "P1"

        remark = str(item.get("remark", "")).strip()

        validated.append({
            "name": name,
            "description": str(item.get("description", "")).strip(),
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "expected_result": expected_result,
            "case_type": case_type,
            "priority": priority,
            "remark": remark,
        })

    return validated, errors


def generate_api_cases_from_document(
    db: Session, request: GenerateApiCasesRequest
) -> GenerateApiCasesResponse:
    api_doc = db.query(ApiDocument).filter(
        ApiDocument.id == request.document_id,
        ApiDocument.is_deleted == False,
    ).first()
    if not api_doc:
        return GenerateApiCasesResponse(
            document_id=request.document_id,
            errors=["接口文档不存在或已删除"],
        )

    prompt = build_api_doc_to_case_prompt(api_doc)

    try:
        raw_output = call_llm_by_scene(db, "api_doc_to_api_case", prompt)
    except Exception as e:
        return GenerateApiCasesResponse(
            document_id=request.document_id,
            project_id=api_doc.project_id,
            module_id=api_doc.module_id,
            errors=[f"LLM 调用失败: {str(e)}"],
        )

    raw_cases, parse_errors = parse_llm_api_cases(raw_output)
    validated_cases, validate_errors = validate_generated_api_cases(raw_cases, api_doc)
    all_errors = parse_errors + validate_errors

    case_items = [
        GeneratedApiCaseItem(
            name=c["name"],
            description=c["description"],
            method=c["method"],
            url=c["url"],
            headers=c["headers"],
            body=c["body"],
            expected_result=c["expected_result"],
            case_type=c["case_type"],
            priority=c["priority"],
            remark=c["remark"],
        )
        for c in validated_cases
    ]

    return GenerateApiCasesResponse(
        document_id=request.document_id,
        project_id=api_doc.project_id,
        module_id=api_doc.module_id,
        cases=case_items,
        raw_output=raw_output[:2000] if raw_output else None,
        errors=all_errors,
    )


def save_generated_api_cases(
    db: Session, request: SaveGeneratedApiCasesRequest
) -> SaveGeneratedApiCasesResponse:
    api_doc = db.query(ApiDocument).filter(
        ApiDocument.id == request.document_id,
        ApiDocument.is_deleted == False,
    ).first()
    if not api_doc:
        raise ValueError("接口文档不存在或已删除")

    project_id = api_doc.project_id
    module_id = request.module_id if request.module_id is not None else api_doc.module_id

    saved_ids = []
    for item in request.cases:
        case = APICase(
            name=item.name or "未命名用例",
            description=item.description or "",
            method=(item.method or "GET").upper(),
            url=item.url or "",
            headers=_json_dumps(item.headers) if item.headers else None,
            body=_json_dumps(item.body),
            expected_result=_json_dumps(item.expected_result),
            project_id=project_id,
            module_id=module_id,
            case_type=item.case_type or "其他",
            source="llm",
            priority=item.priority or "P1",
            status="active",
        )
        db.add(case)
        db.flush()
        saved_ids.append(case.id)

    db.commit()
    return SaveGeneratedApiCasesResponse(
        saved_count=len(saved_ids),
        case_ids=saved_ids,
    )
