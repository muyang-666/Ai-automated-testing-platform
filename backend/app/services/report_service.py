from datetime import datetime
import json

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_case import APICase
from app.models.function_case import FunctionCase
from app.models.project import Project
from app.models.report import Report
from app.models.requirement_doc import RequirementDoc
from app.models.scene import Scene
from app.models.scene_run import SceneRun
from app.models.scene_step import SceneStep
from app.models.test_module import TestModule
from app.models.test_run import TestRun
from app.services.run_service import execute_case_test
from app.services.test_module_service import get_child_module_ids


def _module_filter_ids(db: Session, module_id: int | None) -> list[int] | None:
    if module_id is None:
        return None
    return [module_id] + get_child_module_ids(db, module_id)


# 构造“项目场景清单 + 执行结果摘要”
def build_project_snapshot(
    db: Session,
    project_id: int | None = None,
    module_id: int | None = None,
) -> tuple[list[dict], dict]:
    module_ids = _module_filter_ids(db, module_id)
    scene_query = db.query(Scene).filter(Scene.is_deleted == False)
    if project_id is not None:
        scene_query = scene_query.filter(Scene.project_id == project_id)
    if module_ids is not None:
        scene_query = scene_query.filter(Scene.module_id.in_(module_ids))

    scenes = scene_query.order_by(Scene.id.asc()).all()
    if not scenes:
        raise ValueError("当前项目或模块下没有可用于生成报告的场景，请先在场景管理中配置场景")

    scene_results = []
    total_steps = 0
    passed_steps = 0
    failed_steps = 0

    for scene in scenes:
        steps = (
            db.query(SceneStep)
            .filter(
                SceneStep.scene_id == scene.id,
                SceneStep.is_deleted == False,
                SceneStep.enabled == True,
            )
            .order_by(SceneStep.step_order.asc(), SceneStep.id.asc())
            .all()
        )

        if not steps:
            scene_results.append({
                "scene_id": scene.id,
                "scene_name": scene.name,
                "total_steps": 0,
                "passed_steps": 0,
                "failed_steps": 0,
                "final_result": "failed",
                "step_results": [],
                "scene_issue": "当前场景没有配置步骤",
            })
            continue

        current_scene_step_results = []
        scene_passed_steps = 0
        scene_failed_steps = 0

        # 场景级执行仍沿用当前 V1 规则：失败即停止
        for step in steps:
            api_case = db.query(APICase).filter(APICase.id == step.case_id).first()
            if not api_case:
                current_scene_step_results.append({
                    "step_order": step.step_order,
                    "case_id": step.case_id,
                    "case_name": "未知用例",
                    "method": "",
                    "url": "",
                    "status": "completed",
                    "result": "failed",
                    "response_status_code": None,
                    "response_content": None,
                    "error_message": "关联测试用例不存在",
                })
                scene_failed_steps += 1
                failed_steps += 1
                total_steps += 1
                break

            run_result = execute_case_test(db, step.case_id)

            current_scene_step_results.append({
                "step_order": step.step_order,
                "case_id": step.case_id,
                "case_name": api_case.name,
                "method": api_case.method,
                "url": api_case.url,
                "status": run_result.get("status"),
                "result": run_result.get("result"),
                "response_status_code": run_result.get("response_status_code"),
                "response_content": run_result.get("response_content"),
                "error_message": run_result.get("error_message"),
            })

            total_steps += 1

            if run_result.get("result") == "passed":
                scene_passed_steps += 1
                passed_steps += 1
            else:
                scene_failed_steps += 1
                failed_steps += 1
                break

        final_result = "passed" if scene_failed_steps == 0 else "failed"

        scene_results.append({
            "scene_id": scene.id,
            "scene_name": scene.name,
            "total_steps": len(steps),
            "passed_steps": scene_passed_steps,
            "failed_steps": scene_failed_steps,
            "final_result": final_result,
            "step_results": current_scene_step_results,
            "scene_issue": None,
        })

    summary_stats = {
        "scene_count": len(scenes),
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "pass_rate": round((passed_steps / total_steps) * 100, 2) if total_steps > 0 else 0.0,
    }

    return scene_results, summary_stats


# 把场景与步骤信息整理成给 LLM 的精简文本
def build_scene_inventory_text(scene_results: list[dict]) -> str:
    lines = []
    for scene in scene_results:
        lines.append(
            f"场景[{scene['scene_id']}] {scene['scene_name']}："
            f"总步骤={scene['total_steps']}，通过={scene['passed_steps']}，失败={scene['failed_steps']}，结果={scene['final_result']}"
        )

        for step in scene["step_results"]:
            response_preview = (step.get("response_content") or "")[:200]
            lines.append(
                f"  - 步骤{step['step_order']} | case_id={step['case_id']} | 名称={step['case_name']} | "
                f"方法={step.get('method') or ''} | URL={step.get('url') or ''} | "
                f"结果={step.get('result')} | 响应状态码={step.get('response_status_code')} | "
                f"错误={step.get('error_message') or ''} | 响应预览={response_preview}"
            )

        if scene.get("scene_issue"):
            lines.append(f"  - 场景问题：{scene['scene_issue']}")

    text = "\n".join(lines)
    if len(text) > 6000:
        text = text[:6000] + "\n...(场景执行明细已截断)"
    return text


# 构造项目级报告 Prompt
def build_project_report_prompt(scene_results: list[dict], stats: dict) -> str:
    scene_inventory_text = build_scene_inventory_text(scene_results)

    return f"""
你是一名资深测试开发工程师，请基于“项目全部场景的自动执行结果”，生成一份项目级接口测试报告。

要求：
1. 语言使用中文
2. 不要复述原始日志大段内容
3. 要站在“项目整体接口质量”的角度做总结
4. 要指出：
   - 当前覆盖情况
   - 通过/失败概览
   - 主要问题类型
   - 风险评估
   - 后续建议
5. 如果失败主要集中在鉴权、参数、断言、接口跳转/重定向、代码生成问题，要明确指出
6. 输出要适合直接展示在测试报告页面

请严格按下面结构输出：

一、测试范围概述
二、执行结果概览
三、主要问题分析
四、项目接口风险评估
五、后续建议
六、总结结论

项目统计信息：
- 场景数：{stats['scene_count']}
- 总步骤数：{stats['total_steps']}
- 通过步骤数：{stats['passed_steps']}
- 失败步骤数：{stats['failed_steps']}
- 通过率：{stats['pass_rate']}%

场景执行明细：
{scene_inventory_text}
""".strip()


# 调用 LLM 生成项目级测试报告
def call_llm_generate_project_report(prompt: str) -> str:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "mock" or not settings.LLM_API_KEY:
        raise ValueError("当前未配置可用的 LLM，无法生成项目级测试报告")

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.LLM_MODEL or "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是资深测试开发工程师，擅长基于自动化测试执行结果生成项目级接口测试报告。"
                    "请输出结构化、清晰、适合展示的项目测试报告。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
        "stream": False,
    }

    response = httpx.post(
        url=settings.LLM_BASE_URL,
        headers=headers,
        json=payload,
        timeout=90.0,
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


# 从 LLM 报告中提取风险总结
def extract_risk_summary(summary: str, failed_count: int) -> str:
    if failed_count == 0:
        return "当前所有已纳入场景的接口步骤均通过，整体接口风险较低。"

    lower_summary = summary.lower()
    if "高风险" in summary or "high" in lower_summary:
        return "当前项目接口测试中存在较明显风险，建议优先处理失败场景及核心链路问题。"
    if "低风险" in summary or "low" in lower_summary:
        return "当前项目接口整体风险较低，但仍建议关注个别失败场景。"

    return "当前项目接口测试中存在失败步骤，建议重点关注失败场景、参数配置、断言策略和接口稳定性。"


# 一键生成项目级测试报告
def generate_project_report(
    db: Session,
    project_id: int | None = None,
    module_id: int | None = None,
):
    # 1. 自动执行全部场景并收集结果
    scene_results, stats = build_project_snapshot(db, project_id=project_id, module_id=module_id)

    # 2. 构造 Prompt
    prompt = build_project_report_prompt(scene_results, stats)

    # 3. 调 LLM 生成正文
    report_summary = call_llm_generate_project_report(prompt)

    # 4. 生成风险总结
    risk_summary = extract_risk_summary(report_summary, stats["failed_steps"])

    scope_parts = []
    if project_id is not None:
        project = db.query(Project).filter(Project.id == project_id).first()
        scope_parts.append(project.name if project else f"项目{project_id}")
    if module_id is not None:
        module = db.query(TestModule).filter(TestModule.id == module_id).first()
        scope_parts.append(module.name if module else f"模块{module_id}")
    scope_name = "_".join(scope_parts) if scope_parts else "全部项目"
    report_name = f"{scope_name}_接口测试报告_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    db_report = Report(
        report_name=report_name,
        report_type="project_scene_report",
        summary=report_summary,
        total_count=stats["total_steps"],
        passed_count=stats["passed_steps"],
        failed_count=stats["failed_steps"],
        pass_rate=stats["pass_rate"],
        risk_summary=risk_summary,
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    return {
        "id": db_report.id,
        "report_name": db_report.report_name,
        "report_type": db_report.report_type,
        "summary": db_report.summary,
        "total_count": db_report.total_count,
        "passed_count": db_report.passed_count,
        "failed_count": db_report.failed_count,
        "pass_rate": db_report.pass_rate,
        "risk_summary": db_report.risk_summary,
        "created_at": db_report.created_at,
        "updated_at": db_report.updated_at,
        "message": "项目级测试报告生成成功",
    }


def calculate_pass_rate(passed_count: int, total_count: int) -> float:
    if total_count == 0:
        return 0.0
    return round((passed_count / total_count) * 100, 2)


# 报告统计汇总
def get_report_summary(
    db: Session,
    project_id: int | None = None,
    module_id: int | None = None,
):
    module_ids = _module_filter_ids(db, module_id)

    project_query = db.query(Project).filter(Project.is_deleted == False)
    module_query = db.query(TestModule).filter(TestModule.is_deleted == False)
    api_case_query = db.query(APICase).filter(APICase.is_deleted == False)
    function_case_query = db.query(FunctionCase).filter(FunctionCase.is_deleted == False)
    requirement_query = db.query(RequirementDoc).filter(RequirementDoc.is_deleted == False)
    scene_query = db.query(Scene).filter(Scene.is_deleted == False)

    if project_id is not None:
        project_query = project_query.filter(Project.id == project_id)
        module_query = module_query.filter(TestModule.project_id == project_id)
        api_case_query = api_case_query.filter(APICase.project_id == project_id)
        function_case_query = function_case_query.filter(FunctionCase.project_id == project_id)
        requirement_query = requirement_query.filter(RequirementDoc.project_id == project_id)
        scene_query = scene_query.filter(Scene.project_id == project_id)

    if module_ids is not None:
        module_query = module_query.filter(TestModule.id.in_(module_ids))
        api_case_query = api_case_query.filter(APICase.module_id.in_(module_ids))
        function_case_query = function_case_query.filter(FunctionCase.module_id.in_(module_ids))
        requirement_query = requirement_query.filter(RequirementDoc.module_id.in_(module_ids))
        scene_query = scene_query.filter(Scene.module_id.in_(module_ids))

    project_count = project_query.count()
    module_count = module_query.count()
    api_case_count = api_case_query.count()
    function_case_count = function_case_query.count()
    requirement_count = requirement_query.count()
    scene_count = scene_query.count()

    function_total_cases = function_case_count
    function_passed_cases = function_case_query.filter(FunctionCase.status == "通过").count()
    function_failed_cases = function_case_query.filter(FunctionCase.status == "失败").count()

    api_run_query = db.query(TestRun).join(APICase, TestRun.case_id == APICase.id)
    if project_id is not None:
        api_run_query = api_run_query.filter(APICase.project_id == project_id)
    if module_ids is not None:
        api_run_query = api_run_query.filter(APICase.module_id.in_(module_ids))

    api_total_runs = api_run_query.count()
    api_passed_runs = api_run_query.filter(TestRun.result == "passed").count()
    api_failed_runs = api_run_query.filter(TestRun.result == "failed").count()

    scene_run_query = db.query(SceneRun)
    if project_id is not None:
        scene_run_query = scene_run_query.filter(SceneRun.project_id == project_id)
    if module_ids is not None:
        scene_run_query = scene_run_query.filter(SceneRun.module_id.in_(module_ids))

    scene_total_runs = scene_run_query.count()
    scene_passed_runs = scene_run_query.filter(SceneRun.status == "passed").count()
    scene_failed_runs = scene_run_query.filter(SceneRun.status == "failed").count()
    scene_error_runs = scene_run_query.filter(SceneRun.status == "error").count()

    recent_api_runs = api_run_query.order_by(TestRun.id.desc()).limit(10).all()
    recent_scene_runs = scene_run_query.order_by(SceneRun.id.desc()).limit(10).all()

    return {
        "overview": {
            "project_count": project_count,
            "module_count": module_count,
            "api_case_count": api_case_count,
            "function_case_count": function_case_count,
            "requirement_count": requirement_count,
            "scene_count": scene_count,
        },
        "api_test": {
            "total_runs": api_total_runs,
            "passed_runs": api_passed_runs,
            "failed_runs": api_failed_runs,
            "pass_rate": calculate_pass_rate(api_passed_runs, api_total_runs),
        },
        "function_test": {
            "total_cases": function_total_cases,
            "passed_cases": function_passed_cases,
            "failed_cases": function_failed_cases,
            "pass_rate": calculate_pass_rate(function_passed_cases, function_total_cases),
        },
        "scene_chain": {
            "total_runs": scene_total_runs,
            "passed_runs": scene_passed_runs,
            "failed_runs": scene_failed_runs,
            "error_runs": scene_error_runs,
            "pass_rate": calculate_pass_rate(scene_passed_runs, scene_total_runs),
        },
        "recent_api_runs": [
            {
                "id": run.id,
                "case_id": run.case_id,
                "status": run.status,
                "result": run.result,
                "response_status_code": run.response_status_code,
                "created_at": run.created_at,
            }
            for run in recent_api_runs
        ],
        "recent_scene_runs": [
            {
                "id": run.id,
                "scene_id": run.scene_id,
                "status": run.status,
                "total_steps": run.total_steps,
                "passed_steps": run.passed_steps,
                "failed_steps": run.failed_steps,
                "skipped_steps": run.skipped_steps,
                "duration_ms": run.duration_ms,
                "created_at": run.created_at,
            }
            for run in recent_scene_runs
        ],
    }


# 报告列表
def get_report_list(db: Session):
    reports = db.query(Report).order_by(Report.id.desc()).all()
    return reports


# 按报告 ID 查详情
def get_report_by_id(db: Session, report_id: int):
    return db.query(Report).filter(Report.id == report_id).first()

