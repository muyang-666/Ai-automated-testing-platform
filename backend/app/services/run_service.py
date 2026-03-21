from datetime import datetime
import re

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_analysis import AIAnalysis
from app.models.api_case import APICase
from app.models.test_run import TestRun


# 接口信息整理成清晰文本，供 LLM 阅读
def build_case_info_text(api_case: APICase | None) -> str:
    if not api_case:
        return "未找到关联测试用例信息"

    return (
        f"用例ID: {api_case.id}\n"
        f"用例名称: {api_case.name}\n"
        f"用例描述: {api_case.description or ''}\n"
        f"请求方法: {api_case.method or ''}\n"
        f"请求地址: {api_case.url or ''}\n"
        f"请求头: {api_case.headers or ''}\n"
        f"请求体: {api_case.body or ''}\n"
        f"预期结果: {api_case.expected_result or ''}\n"
    )


# 通用截断函数，避免把整段日志/整段响应都喂给 LLM
def truncate_text(text: str | None, max_length: int = 1500) -> str:
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\n...(已截断)"


# 从 pytest 日志中抽取最关键部分，加快分析速度
def extract_core_log(log_content: str | None) -> str:
    """
    只保留日志里最关键的部分：
    1. response 标记附近
    2. traceback / error 附近
    3. 日志末尾 short summary
    """
    if not log_content:
        return "无执行日志"

    text = str(log_content)
    parts = []

    important_markers = [
        "===RESPONSE_STATUS_CODE===",
        "===RESPONSE_CONTENT_START===",
        "Traceback",
        "E   ",
        "FAILED",
        "ERROR",
        "short test summary info",
    ]

    for marker in important_markers:
        idx = text.find(marker)
        if idx != -1:
            start = max(0, idx - 300)
            end = min(len(text), idx + 1200)
            parts.append(text[start:end])

    # 再补一段日志尾部
    parts.append(text[-1200:])

    merged = "\n\n".join(parts)
    return truncate_text(merged, max_length=2500)


# 响应结果也只保留核心部分
def extract_core_response(response_content: str | None) -> str:
    if not response_content:
        return "无响应结果"
    return truncate_text(response_content, max_length=1200)


# 运行代码也不要全量喂，保留前面关键部分就够
def extract_core_code(code: str | None) -> str:
    if not code:
        return "无运行代码"

    lines = str(code).splitlines()
    compact = "\n".join(lines[:120])
    return truncate_text(compact, max_length=2500)


# 构造“完整上下文 + 精简输入”的失败分析 Prompt
def build_failure_analysis_prompt(api_case: APICase | None, test_run: TestRun) -> str:
    case_info_text = build_case_info_text(api_case)

    run_code = extract_core_code(api_case.generated_test_code if api_case else "")
    log_content = extract_core_log(test_run.log_content)
    error_message = truncate_text(test_run.error_message or "无错误信息", max_length=800)
    response_status_code = (
        str(test_run.response_status_code)
        if test_run.response_status_code is not None
        else "无响应状态码"
    )
    response_content = extract_core_response(test_run.response_content)

    return f"""
你是一名资深测试开发工程师，请基于下面信息做“失败根因分析”。

目标：
不是复述日志，而是找出问题本质，并明确责任归属。

判断优先级：
1. 如果接口已返回响应，但测试失败，优先判断为：断言问题 / 代码生成问题
2. 如果请求未成功发出，优先判断为：参数输入问题 / 代码生成问题 / 环境问题
3. 如果响应中明确出现鉴权失败、参数缺失、URL 非法、字段类型错误，要明确指出具体属于参数问题还是代码构造问题
4. 必须给出证据链，不允许空泛结论

责任归属只能从下面 6 类中选 1 个：
参数输入问题 / 代码生成问题 / 断言问题 / 接口问题 / 环境问题 / 执行链问题

请严格按这个格式输出，全部用中文，尽量简洁：

问题现象：
问题本质：
责任归属：
关键证据：
1. ...
2. ...
3. ...

修复建议：
1. ...
2. ...
3. ...

风险等级：
low / medium / high

【接口信息】
{case_info_text}

【执行状态】
run_id: {test_run.id}
case_id: {test_run.case_id}
status: {test_run.status}
result: {test_run.result}

【错误信息】
{error_message}

【响应状态码】
{response_status_code}

【响应结果】
{response_content}

【关键执行日志】
{log_content}

【本次运行代码】
{run_code}
""".strip()


# 调用 LLM 做失败分析
def call_llm_analyze_log(prompt: str) -> str:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "mock" or not settings.LLM_API_KEY:
        raise ValueError("当前未配置可用的 LLM，无法进行 AI 日志分析")

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
                    "你是资深测试开发工程师，擅长分析自动化测试失败根因。"
                    "必须简洁输出：问题现象、问题本质、责任归属、关键证据、修复建议、风险等级。"
                    "不要写大段背景解释，不要复述无关日志。"
                    "责任归属只能从以下 6 类中选 1 个："
                    "参数输入问题 / 代码生成问题 / 断言问题 / 接口问题 / 环境问题 / 执行链问题。"
                    "风险等级只能输出 low / medium / high。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 700,
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
    return content.strip()


# 从返回文本里提取风险等级
def extract_risk_level(analysis_text: str) -> str:
    if not analysis_text:
        return "medium"

    lower_text = analysis_text.lower()

    if re.search(r"风险等级[:：]?\s*high", lower_text):
        return "high"
    if re.search(r"风险等级[:：]?\s*low", lower_text):
        return "low"
    if re.search(r"风险等级[:：]?\s*medium", lower_text):
        return "medium"

    # 兼容中文
    if "高" in analysis_text:
        return "high"
    if "低" in analysis_text:
        return "low"

    return "medium"


# 生成 AI 分析
def generate_ai_analysis(db: Session, run_id: int):
    # 1. 查执行记录
    test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not test_run:
        raise ValueError("执行记录不存在")

    # 2. 只分析失败记录
    if test_run.result != "failed":
        raise ValueError("当前执行记录不是失败结果，无需做失败日志分析")

    # 3. 至少要有日志、响应结果、错误信息中的一种，才能分析
    if not test_run.log_content and not test_run.error_message and not test_run.response_content:
        raise ValueError("当前执行记录缺少可分析信息")

    # 4. 查关联测试用例，拿接口信息和运行代码
    api_case = db.query(APICase).filter(APICase.id == test_run.case_id).first()

    # 5. 构造 Prompt
    prompt = build_failure_analysis_prompt(api_case, test_run)

    # 6. 调 LLM
    try:
        analysis_content = call_llm_analyze_log(prompt)
    except Exception as e:
        raise ValueError(f"AI 日志分析失败：{str(e)}")

    if not analysis_content:
        raise ValueError("AI 日志分析失败：模型未返回有效内容")

    risk_level = extract_risk_level(analysis_content)

    # 7. 落库
    db_analysis = AIAnalysis(
        run_id=run_id,
        analysis_type="failure_analysis",
        content=analysis_content,
        risk_level=risk_level,
    )
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)

    # 8. 返回给前端
    return {
        "run_id": run_id,
        "analysis_type": db_analysis.analysis_type,
        "content": db_analysis.content,
        "risk_level": db_analysis.risk_level,
        "message": "AI 日志分析完成",
        "created_at": datetime.now(),
    }


# 查询某次运行最新的一条分析结果
def get_ai_analysis_by_run_id(db: Session, run_id: int):
    return (
        db.query(AIAnalysis)
        .filter(AIAnalysis.run_id == run_id)
        .order_by(AIAnalysis.id.desc())
        .first()
    )