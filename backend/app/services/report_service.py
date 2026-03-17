from datetime import datetime

from sqlalchemy.orm import Session

from app.models.ai_analysis import AIAnalysis
from app.models.report import Report
from app.models.test_run import TestRun

# 报告生成器的核心模板
def build_mock_report_summary(test_run: TestRun, analysis: AIAnalysis | None) -> tuple[str, str]:
    # 1.先判断本次执行是通过还是失败
    result_text = "通过" if test_run.result == "passed" else "失败"
    # 2.先拼一个基础摘要
    summary = (
        f"本次测试任务执行完成，共执行 {test_run.total_count} 条测试，"
        f"通过 {test_run.passed_count} 条，失败 {test_run.failed_count} 条，"
        f"整体结果为：{result_text}。\n\n"
    )
    # 3.如果有 AI 分析结果，就把分析内容塞进报告
    if analysis:
        summary += (
            "失败分析结论：\n"
            f"{analysis.content}\n\n"
        )
    else:
        summary += "失败分析结论：当前未生成 AI 分析结果。\n\n"

    # 4.再根据失败数给出建议和风险总结
    if test_run.failed_count > 0:
        summary += "建议：优先修复当前失败项后再重新回归执行。"
        risk_summary = "当前存在失败用例，建议关注接口可用性、请求方法配置和断言逻辑，整体风险为中等。"
    else: # 如果全通过
        summary += "建议：当前测试全部通过，可进入下一阶段验证。"
        risk_summary = "当前未发现失败用例，整体风险较低。"

    return summary, risk_summary

# 核心
def generate_report(db: Session, run_id: int):
    # 第 1 步：查 TestRun
    test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not test_run:
        raise ValueError("执行记录不存在")

    # 第 2 步：查最新一条 AIAnalysis
    analysis = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.run_id == run_id)
        .order_by(AIAnalysis.id.desc())
        .first()
    )

    # 第 3 步：计算通过率
    pass_rate = 0.0
    if test_run.total_count > 0:
        pass_rate = round((test_run.passed_count / test_run.total_count) * 100, 2)

    # 第 4 步：生成报告正文和风险总结
    summary, risk_summary = build_mock_report_summary(test_run, analysis)

    db_report = Report(
        run_id=run_id,
        summary=summary,
        total_count=test_run.total_count,
        passed_count=test_run.passed_count,
        failed_count=test_run.failed_count,
        pass_rate=pass_rate,
        risk_summary=risk_summary,
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    return {
        "run_id": run_id,
        "summary": db_report.summary,
        "total_count": db_report.total_count,
        "passed_count": db_report.passed_count,
        "failed_count": db_report.failed_count,
        "pass_rate": db_report.pass_rate,
        "risk_summary": db_report.risk_summary,
        "message": "测试报告生成成功",
        "created_at": datetime.now(),
    }

# 按 run_id 查报告，取最新一条
def get_report_by_run_id(db: Session, run_id: int):
    return (
        db.query(Report)
        .filter(Report.run_id == run_id)
        .order_by(Report.id.desc())
        .first()
    )