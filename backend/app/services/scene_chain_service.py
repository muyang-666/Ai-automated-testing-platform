import json
import time
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.scene import Scene
from app.models.scene_run import SceneRun
from app.models.scene_step import SceneStep
from app.models.scene_step_run import SceneStepRun
from app.utils.assertion_runner import run_assertions
from app.utils.variable_resolver import extract_variables, replace_variables


def parse_json_text(text: str | None) -> dict | list | None:
    """Try to parse text as JSON, return None on failure."""
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_headers(raw_headers: str | None) -> dict | None:
    """Parse api_case.headers into a dict. Returns None if parse failed and not empty."""
    if not raw_headers or not raw_headers.strip():
        return {}
    parsed = parse_json_text(raw_headers)
    if isinstance(parsed, dict):
        return parsed
    return None  # signal error: headers exist but are not valid JSON dict


def _parse_body(raw_body: str | None) -> tuple[any, bool]:
    """Parse api_case.body. Returns (parsed_value, is_error).
    is_error=True means body is invalid JSON and should cause step error.
    """
    if not raw_body or not raw_body.strip():
        return None, False
    try:
        return json.loads(raw_body), False
    except (json.JSONDecodeError, TypeError):
        # body parse failed → keep original string for content=
        return raw_body, False


def _normalize_url(raw_url: str | None) -> str:
    """Ensure URL has a protocol prefix."""
    if not raw_url:
        return ""
    url = raw_url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"http://{url}"


def build_request_from_case(
    api_case: APICase,
    scene_step: SceneStep,
    context: dict,
) -> dict:
    """Build an HTTP request dict from api_case data, override rules, and variable context."""

    # Parse headers
    headers = _parse_headers(api_case.headers)
    if headers is None:
        return {"error": "headers 不是合法 JSON 对象"}

    # Parse body
    body, _ = _parse_body(api_case.body)

    method = (api_case.method or "GET").upper()
    url = _normalize_url(api_case.url)

    # Apply request_override_json
    override = scene_step.request_override_json
    if override is not None:
        if not isinstance(override, dict):
            return {"error": "request_override_json 不是合法 dict"}
        if "method" in override:
            method = str(override["method"]).upper()
        if "url" in override:
            url = _normalize_url(str(override["url"]))
        if "headers" in override and isinstance(override["headers"], dict):
            headers = {**headers, **override["headers"]}
        if "body" in override:
            if isinstance(override["body"], dict) and isinstance(body, dict):
                body = {**body, **override["body"]}
            else:
                body = override["body"]

    # Replace variables
    replace_errors = []

    # Replace in url
    url_replaced = replace_variables(url, context)
    url = url_replaced["data"]
    replace_errors.extend(url_replaced["errors"])

    # Replace in headers
    if headers:
        headers_replaced = replace_variables(headers, context)
        headers = headers_replaced["data"]
        replace_errors.extend(headers_replaced["errors"])

    # Replace in body
    if body is not None:
        body_replaced = replace_variables(body, context)
        body = body_replaced["data"]
        replace_errors.extend(body_replaced["errors"])

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "replace_errors": replace_errors,
        "error": None,
    }


def execute_http_request(request_data: dict) -> dict:
    """Execute HTTP request using httpx. Never raises."""
    method = request_data.get("method", "GET").upper()
    url = request_data.get("url", "")
    headers = request_data.get("headers") or {}
    body = request_data.get("body")

    start = time.time()
    try:
        kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": 15.0,
        }

        if method.upper() != "GET" and body is not None:
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                kwargs["content"] = str(body)

        response = httpx.request(**kwargs)
        duration_ms = int((time.time() - start) * 1000)

        resp_json = parse_json_text(response.text)

        return {
            "status_code": response.status_code,
            "text": response.text,
            "json": resp_json,
            "duration_ms": duration_ms,
            "error": None,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "status_code": None,
            "text": None,
            "json": None,
            "duration_ms": duration_ms,
            "error": str(e),
        }


def _is_2xx(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return 200 <= status_code <= 299


def execute_scene_chain(
    db: Session,
    scene_id: int,
    selected_step_ids: list[int] | None = None,
) -> dict:
    """Execute a scene by chaining HTTP requests in sequence.

    Steps:
    1. Validate scene
    2. Get enabled, non-deleted steps ordered by step_order
    3. Create SceneRun (running)
    4. For each step: build request → replace vars → httpx → assert → extract → save
    5. Skip remaining on first failure
    6. Update SceneRun final status
    """

    # 1. Validate scene
    scene = (
        db.query(Scene)
        .filter(Scene.id == scene_id, Scene.is_deleted == False)
        .first()
    )
    if not scene:
        raise ValueError("场景不存在")
    if scene.status != "active":
        raise ValueError("场景状态不是 active，无法执行")

    # 2. Get enabled steps
    step_query = (
        db.query(SceneStep)
        .filter(
            SceneStep.scene_id == scene_id,
            SceneStep.is_deleted == False,
            SceneStep.enabled == True,
        )
    )
    if selected_step_ids:
        step_query = step_query.filter(SceneStep.id.in_(selected_step_ids))

    steps = step_query.order_by(SceneStep.step_order.asc(), SceneStep.id.asc()).all()

    if not steps:
        raise ValueError("当前场景下没有可执行步骤")

    # 3. Create SceneRun
    scene_run = SceneRun(
        scene_id=scene.id,
        project_id=scene.project_id,
        module_id=scene.module_id,
        status="running",
        total_steps=len(steps),
        started_at=datetime.now(),
    )
    db.add(scene_run)
    db.commit()
    db.refresh(scene_run)

    # 4. Execute steps
    context = {}
    step_results = []
    total_start = time.time()
    should_stop = False

    for step in steps:
        if should_stop:
            # Mark as skipped
            _save_skipped_step(db, scene_run.id, step, "前置步骤失败，跳过执行")
            step_results.append(_serialize_step(step, None, "skipped", "前置步骤失败，跳过执行"))
            continue

        step_start = time.time()

        # a. Get APICase
        api_case = (
            db.query(APICase)
            .filter(APICase.id == step.case_id, APICase.is_deleted == False)
            .first()
        )
        if not api_case:
            _save_step_run(
                db, scene_run.id, step, status="error",
                error_message="关联测试用例不存在或已删除",
                duration_ms=int((time.time() - step_start) * 1000),
            )
            step_results.append(_serialize_step(step, None, "error", "关联测试用例不存在或已删除"))
            should_stop = True
            continue

        # b. Build request
        request_data = build_request_from_case(api_case, step, context)
        if request_data.get("error"):
            _save_step_run(
                db, scene_run.id, step, status="error",
                error_message=request_data["error"],
                duration_ms=int((time.time() - step_start) * 1000),
            )
            step_results.append(_serialize_step(step, None, "error", request_data["error"]))
            should_stop = True
            continue

        if request_data.get("replace_errors"):
            error_msg = "; ".join(request_data["replace_errors"])
            _save_step_run(
                db, scene_run.id, step, status="failed",
                request_data=request_data,
                error_message=f"变量替换失败: {error_msg}",
                duration_ms=int((time.time() - step_start) * 1000),
            )
            step_results.append(
                _serialize_step(step, None, "failed", f"变量替换失败: {error_msg}")
            )
            should_stop = True
            continue

        # c. Execute HTTP request
        http_result = execute_http_request(request_data)

        if http_result["error"]:
            _save_step_run(
                db, scene_run.id, step, status="error",
                request_data=request_data,
                http_result=http_result,
                error_message=http_result["error"],
                duration_ms=http_result["duration_ms"],
            )
            step_results.append(
                _serialize_step(step, http_result, "error", http_result["error"])
            )
            should_stop = True
            continue

        # d. Run assertions
        assertions = step.assertions_json
        if assertions:
            assertion_result = run_assertions(
                http_result["status_code"], http_result["json"], assertions
            )
            step_passed = assertion_result["passed"]
            assertion_data = assertion_result["results"]
        else:
            # Default: 2xx = passed
            step_passed = _is_2xx(http_result["status_code"])
            assertion_data = [
                {
                    "type": "status_code",
                    "operator": "2xx_check",
                    "expected": "200-299",
                    "actual": http_result["status_code"],
                    "passed": step_passed,
                    "message": "" if step_passed else f"状态码 {http_result['status_code']} 不在 2xx 范围",
                }
            ]

        # e. Extract variables
        extracted = {}
        extract_errors = []
        if http_result["json"] and step.extract_rules_json:
            extract_result = extract_variables(http_result["json"], step.extract_rules_json)
            extracted = extract_result["variables"]
            extract_errors = extract_result["errors"]
            context.update(extracted)

        # f. Determine step status
        if step_passed:
            step_status = "passed"
            step_error = None
        else:
            step_status = "failed"
            step_error = None
            should_stop = True

        step_duration = int((time.time() - step_start) * 1000)

        # g. Save SceneStepRun
        _save_step_run(
            db, scene_run.id, step,
            status=step_status,
            request_data=request_data,
            http_result=http_result,
            extracted_variables=extracted,
            assertion_results=assertion_data,
            error_message=step_error,
            duration_ms=step_duration,
        )

        step_results.append(
            _serialize_step(
                step, http_result, step_status, step_error,
                extracted=extracted, extract_errors=extract_errors,
            )
        )

    # 5. Finalize SceneRun
    total_duration = int((time.time() - total_start) * 1000)

    passed = sum(1 for s in step_results if s["status"] == "passed")
    failed = sum(1 for s in step_results if s["status"] == "failed")
    skipped = sum(1 for s in step_results if s["status"] == "skipped")
    errors = sum(1 for s in step_results if s["status"] == "error")

    if errors > 0:
        final_status = "error"
    elif failed > 0:
        final_status = "failed"
    else:
        final_status = "passed"

    scene_run.status = final_status
    scene_run.passed_steps = passed
    scene_run.failed_steps = failed + errors
    scene_run.skipped_steps = skipped
    scene_run.context_json = context if context else None
    scene_run.duration_ms = total_duration
    scene_run.finished_at = datetime.now()
    db.commit()
    db.refresh(scene_run)

    return {
        "scene_run_id": scene_run.id,
        "scene_id": scene.id,
        "scene_name": scene.name,
        "status": final_status,
        "total_steps": len(steps),
        "passed_steps": passed,
        "failed_steps": failed + errors,
        "skipped_steps": skipped,
        "context": context if context else {},
        "duration_ms": total_duration,
        "steps": step_results,
    }


def _save_step_run(
    db: Session,
    scene_run_id: int,
    step: SceneStep,
    status: str,
    request_data: dict = None,
    http_result: dict = None,
    extracted_variables: dict = None,
    assertion_results: list = None,
    error_message: str = None,
    duration_ms: int = None,
):
    """Create and commit a SceneStepRun record."""
    step_run = SceneStepRun(
        scene_run_id=scene_run_id,
        scene_step_id=step.id,
        case_id=step.case_id,
        step_order=step.step_order,
        step_name=step.step_name,
        status=status,
        request_method=request_data.get("method") if request_data else None,
        request_url=request_data.get("url") if request_data else None,
        request_headers_json=request_data.get("headers") if request_data else None,
        request_body_json=request_data.get("body") if request_data else None,
        response_status_code=http_result.get("status_code") if http_result else None,
        response_body=http_result.get("text") if http_result else None,
        extracted_variables_json=extracted_variables or None,
        assertion_results_json=assertion_results or None,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    db.add(step_run)
    db.commit()
    db.refresh(step_run)


def _save_skipped_step(db: Session, scene_run_id: int, step: SceneStep, reason: str):
    """Save a skipped step record."""
    _save_step_run(
        db, scene_run_id, step,
        status="skipped",
        error_message=reason,
    )


def _serialize_step(
    step: SceneStep,
    http_result: dict | None,
    status: str,
    error_message: str | None,
    extracted: dict = None,
    extract_errors: list = None,
) -> dict:
    return {
        "step_order": step.step_order,
        "step_name": step.step_name,
        "case_id": step.case_id,
        "status": status,
        "response_status_code": http_result.get("status_code") if http_result else None,
        "extracted_variables": extracted or {},
        "extract_errors": extract_errors or [],
        "error_message": error_message,
        "duration_ms": http_result.get("duration_ms") if http_result else None,
    }
