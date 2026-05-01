import json
import re

from sqlalchemy.orm import Session

from app.models.function_case import FunctionCase
from app.models.requirement_doc import RequirementDoc
from app.schemas.function_case_generation import (
    GeneratedFunctionCaseItem,
    GenerateFunctionCasesRequest,
    GenerateFunctionCasesResponse,
    SaveGeneratedFunctionCasesRequest,
    SaveGeneratedFunctionCasesResponse,
)
from app.services.ai_service import call_llm_generate_code

ALLOWED_CASE_TYPES = {"正常场景", "异常场景", "边界场景", "业务规则场景", "其他"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


def build_function_case_prompt(
    requirement: RequirementDoc, generate_count: int, case_types: list[str]
) -> str:
    return f"""你是一名资深测试分析师。请根据以下需求文本，设计 {generate_count} 条功能测试用例。

【需求信息】
- 需求标题：{requirement.title}
- 需求内容：{requirement.content}
- 需求类型：{requirement.requirement_type or "未指定"}

【覆盖的场景类型】{", ".join(case_types)}

【输出要求 - 必须严格遵守】
1. 只返回一个 JSON 数组，不要任何解释、说明、Markdown 代码块。
2. 数组中每个元素是一个对象，字段如下：
   - case_code: 用例编号，如 FC-LOGIN-001（可为空字符串）
   - case_name: 用例名称，必须简洁明确
   - case_type: 只能从 [{", ".join(case_types)}] 中选择
   - priority: 只能从 P0、P1、P2 中选择
   - precondition: 前置条件，可为空字符串
   - steps_json: 必须是字符串数组，如 ["步骤1", "步骤2"]
   - test_data_json: 必须是 JSON 对象，如 {{"phone": "13800000000"}}（无数据用空对象 {{}}）
   - expected_result: 预期结果，必须具体明确
   - remark: 备注，可为空字符串
3. expected_result 必须具体明确，不能含糊。
4. steps_json 必须具体可执行。
5. 不要返回任何解释文字。
6. 不要使用 Markdown 代码块（不要 ```json）。
7. 只返回 JSON 数组本身。"""


def parse_llm_function_cases(raw_output: str) -> list[dict]:
    if not raw_output:
        return []

    text = raw_output.strip()

    # Step 1: try direct json.loads
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            return data["cases"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 2: try extracting ```json ... ``` code block
    json_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_block_match:
        try:
            data = json.loads(json_block_match.group(1).strip())
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("cases"), list):
                return data["cases"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Step 3: extract everything between first [ and last ]
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        try:
            data = json.loads(text[first_bracket : last_bracket + 1])
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    return []


def _normalize_case_item(item: dict) -> dict:
    case_type = item.get("case_type", "其他")
    if case_type not in ALLOWED_CASE_TYPES:
        case_type = "其他"

    priority = item.get("priority", "P1")
    if priority not in ALLOWED_PRIORITIES:
        priority = "P1"

    steps = item.get("steps_json", [])
    if not isinstance(steps, list):
        steps = []

    test_data = item.get("test_data_json", {})
    if not isinstance(test_data, dict):
        test_data = {}

    return {
        "case_code": item.get("case_code", ""),
        "case_name": item.get("case_name", ""),
        "case_type": case_type,
        "priority": priority,
        "precondition": item.get("precondition", ""),
        "steps_json": steps,
        "test_data_json": test_data,
        "expected_result": item.get("expected_result", ""),
        "remark": item.get("remark", ""),
    }


def validate_generated_function_cases(cases: list[dict]) -> tuple[list[dict], list[str]]:
    valid_cases = []
    errors = []

    for i, raw_item in enumerate(cases):
        item = _normalize_case_item(raw_item)
        item_errors = []

        if not item["case_name"]:
            item_errors.append(f"第{i+1}条：缺少 case_name")
        if not item["case_type"]:
            item_errors.append(f"第{i+1}条：缺少 case_type")
        if not item["steps_json"]:
            item_errors.append(f"第{i+1}条：steps_json 为空")
        if not item["expected_result"]:
            item_errors.append(f"第{i+1}条：缺少 expected_result")

        if item_errors:
            errors.extend(item_errors)
            continue

        valid_cases.append(item)

    return valid_cases, errors


def generate_function_cases_from_requirement(
    db: Session, request: GenerateFunctionCasesRequest
) -> GenerateFunctionCasesResponse:
    requirement = (
        db.query(RequirementDoc)
        .filter(
            RequirementDoc.id == request.requirement_id,
            RequirementDoc.is_deleted == False,
        )
        .first()
    )
    if not requirement:
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            errors=["需求文本不存在"],
        )

    prompt = build_function_case_prompt(requirement, request.generate_count, request.case_types)

    try:
        raw_output = call_llm_generate_code(prompt)
    except Exception as e:
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            project_id=requirement.project_id,
            module_id=requirement.module_id,
            errors=[f"LLM 调用失败：{str(e)}"],
        )

    parsed = parse_llm_function_cases(raw_output)

    if not parsed:
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            project_id=requirement.project_id,
            module_id=requirement.module_id,
            raw_output=raw_output,
            errors=["LLM 返回内容无法解析为 JSON 数组"],
        )

    valid_cases, errors = validate_generated_function_cases(parsed)

    return GenerateFunctionCasesResponse(
        requirement_id=request.requirement_id,
        project_id=requirement.project_id,
        module_id=requirement.module_id,
        cases=[GeneratedFunctionCaseItem(**c) for c in valid_cases],
        raw_output=raw_output,
        errors=errors,
    )


def save_generated_function_cases(
    db: Session, request: SaveGeneratedFunctionCasesRequest
) -> SaveGeneratedFunctionCasesResponse:
    requirement = (
        db.query(RequirementDoc)
        .filter(
            RequirementDoc.id == request.requirement_id,
            RequirementDoc.is_deleted == False,
        )
        .first()
    )
    if not requirement:
        raise ValueError("需求文本不存在")

    project_id = requirement.project_id
    module_id = request.module_id if request.module_id is not None else requirement.module_id

    db_cases = []
    for item in request.cases:
        case_type = item.case_type if item.case_type in ALLOWED_CASE_TYPES else "其他"
        priority = item.priority if item.priority in ALLOWED_PRIORITIES else "P1"
        steps = item.steps_json if isinstance(item.steps_json, list) else []
        test_data = item.test_data_json if isinstance(item.test_data_json, dict) else {}
        precondition = item.precondition if item.precondition else None
        remark = item.remark if item.remark else None

        db_case = FunctionCase(
            project_id=project_id,
            module_id=module_id,
            requirement_id=request.requirement_id,
            case_code=item.case_code or None,
            case_name=item.case_name or "未命名用例",
            case_type=case_type,
            source="llm",
            priority=priority,
            precondition=precondition,
            steps_json=steps if steps else None,
            test_data_json=test_data if test_data else None,
            expected_result=item.expected_result or None,
            status="active",
            remark=remark,
        )
        db_cases.append(db_case)

    if db_cases:
        db.add_all(db_cases)
        db.commit()
        for db_case in db_cases:
            db.refresh(db_case)

    return SaveGeneratedFunctionCasesResponse(
        saved_count=len(db_cases),
        case_ids=[c.id for c in db_cases],
    )
