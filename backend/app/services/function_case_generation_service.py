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
from app.services.llm_client_service import call_llm_with_model, get_model_config_by_scene
from app.services.api_document_generation_service import parse_llm_api_cases as robust_parse_json

ALLOWED_CASE_TYPES = {"正常场景", "异常场景", "边界场景", "业务规则场景", "其他"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


def build_function_case_prompt(
    requirement: RequirementDoc, generate_count: int, case_types: list[str]
) -> str:
    lines = ["你是一名资深测试分析师。请根据以下需求文本，设计功能测试用例。"]

    if requirement.supplementary_prompt:
        lines.append("")
        lines.append("【补充提示词 - 必须严格遵守】")
        lines.append(requirement.supplementary_prompt)

    lines.append("")
    lines.append("【需求信息】")
    lines.append(f"- 需求标题：{requirement.title}")
    lines.append(f"- 需求内容：{requirement.content}")
    lines.append(f"- 需求类型：{requirement.requirement_type or '未指定'}")

    lines.append("")
    lines.append("【输出要求】")
    lines.append("1. 只返回一个 JSON 数组，不要 Markdown、不要解释、不要 ```。")
    lines.append("2. 由你根据需求内容判断生成多少条用例，以覆盖全面为准，最多 50 条。")
    lines.append("3. 每条用例字段：case_code, case_name, case_type, priority, precondition, steps_json(string[]), test_data_json({}), expected_result, remark")
    lines.append(f"4. case_type 从 [{', '.join(case_types)}] 中选，priority 从 P0/P1/P2 中选")
    lines.append("5. 简洁输出，expected_result 和 steps_json 精简但明确")

    return "\n".join(lines)


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

    # 从模型配置中心获取 requirement_to_function_case 场景绑定的模型
    try:
        config = get_model_config_by_scene(db, "requirement_to_function_case")
    except ValueError as e:
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            project_id=requirement.project_id,
            module_id=requirement.module_id,
            errors=[
                f"需求生成功能测试用例未配置可用模型，请先在模型管理中配置 requirement_to_function_case 场景模型。详情: {e}"
            ],
        )

    model = config["model"]
    provider = config["provider"]
    scene_config = config["scene_config"]

    prompt = build_function_case_prompt(requirement, request.generate_count, request.case_types)

    # 应用场景 prompt_template
    if scene_config.prompt_template:
        if "{input}" in scene_config.prompt_template:
            prompt = scene_config.prompt_template.replace("{input}", prompt)
        else:
            prompt = scene_config.prompt_template + "\n\n" + prompt

    try:
        raw_output = call_llm_with_model(
            provider, model, prompt,
            temperature=0.0,
            max_tokens=16384,
        )
    except Exception as e:
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            project_id=requirement.project_id,
            module_id=requirement.module_id,
            model_name=model.model_name,
            provider_name=provider.name,
            errors=[f"LLM 调用失败：{str(e)}"],
        )

    parsed, parse_errors = robust_parse_json(raw_output)

    if parse_errors:
        # robust_parse_json 部分成功时也会返回数据，errors 作为警告
        pass

    all_errors = list(parse_errors)

    if not parsed:
        all_errors.insert(0, "LLM 返回内容无法解析为 JSON 数组")
        return GenerateFunctionCasesResponse(
            requirement_id=request.requirement_id,
            project_id=requirement.project_id,
            module_id=requirement.module_id,
            model_name=model.model_name,
            provider_name=provider.name,
            raw_output=raw_output,
            errors=all_errors,
        )

    # 将通用格式转为功能用例格式
    normalized = []
    for item in parsed:
        normalized.append({
            "case_code": item.get("case_code", ""),
            "case_name": item.get("case_name", item.get("name", "")),
            "case_type": item.get("case_type", "其他"),
            "priority": item.get("priority", "P1"),
            "precondition": item.get("precondition", ""),
            "steps_json": item.get("steps_json", item.get("steps", [])),
            "test_data_json": item.get("test_data_json", item.get("test_data", {})),
            "expected_result": item.get("expected_result", ""),
            "remark": item.get("remark", ""),
        })

    valid_cases, errors = validate_generated_function_cases(normalized)
    all_errors.extend(errors)

    # 不强制数量，AI 自行判断
    actual = len(valid_cases)
    if actual > 50:
        valid_cases = valid_cases[:50]
        all_errors.append(f"模型返回数量为 {actual}，已截取前 50 条")

    return GenerateFunctionCasesResponse(
        requirement_id=request.requirement_id,
        project_id=requirement.project_id,
        module_id=requirement.module_id,
        cases=[GeneratedFunctionCaseItem(**c) for c in valid_cases],
        raw_output=raw_output,
        errors=all_errors,
        model_name=model.model_name,
        provider_name=provider.name,
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
