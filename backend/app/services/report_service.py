from datetime import datetime
import json

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_case import APICase
from app.models.report import Report
from app.models.scene import Scene
from app.models.scene_step import SceneStep
from app.services.run_service import execute_case_test


# 构造“项目场景清单 + 执行结果摘要”
def build_project_snapshot(db: Session) -> tuple[list[dict], dict]:
    scenes = db.query(Scene).order_by(Scene.id.asc()).all()
    if not scenes:
        raise ValueError("当前没有可用于生成报告的场景，请先在场景管理中配置场景")

    scene_results = []
    total_steps = 0
    passed_steps = 0
    failed_steps = 0

    for scene in scenes:
        steps = (
            db.query(SceneStep)
            .filter(SceneStep.scene_id == scene.id)
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
def generate_project_report(db: Session):
    # 1. 自动执行全部场景并收集结果
    scene_results, stats = build_project_snapshot(db)

    # 2. 构造 Prompt
    prompt = build_project_report_prompt(scene_results, stats)

    # 3. 调 LLM 生成正文
    report_summary = call_llm_generate_project_report(prompt)

    # 4. 生成风险总结
    risk_summary = extract_risk_summary(report_summary, stats["failed_steps"])

    report_name = f"项目接口测试报告_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

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


# 报告列表
def get_report_list(db: Session):
    reports = db.query(Report).order_by(Report.id.desc()).all()
    return reports


# 按报告 ID 查详情
def get_report_by_id(db: Session, report_id: int):
    return db.query(Report).filter(Report.id == report_id).first()

