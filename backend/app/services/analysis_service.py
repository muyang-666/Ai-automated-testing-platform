from datetime import datetime
import re

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_analysis import AIAnalysis
from app.models.api_case import APICase
from app.models.test_run import TestRun


# 把接口信息整理成更清晰的文本，给 LLM 看
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


# 构造“完整上下文”的失败分析 Prompt
def build_failure_analysis_prompt(
    api_case: APICase | None,
    test_run: TestRun,
) -> str:
    case_info_text = build_case_info_text(api_case)
    run_code = (api_case.generated_test_code if api_case else "") or "无运行代码"
    log_content = test_run.log_content or "无执行日志"
    error_message = test_run.error_message or "无错误信息"
    response_status_code = (
        str(test_run.response_status_code)
        if test_run.response_status_code is not None
        else "无响应状态码"
    )
    response_content = test_run.response_content or "无响应结果"

    return f"""
你是一名资深测试开发工程师，现在需要对一次自动化测试失败做“根因分析”，目标不是复述日志，而是找出问题本质。

请严格结合以下 4 类信息综合判断：
1. 接口信息
2. 执行日志
3. 响应结果
4. 本次运行代码

请特别注意：
- 不要只盯着报错表面，要判断真正的责任归属。
- 如果响应状态码和响应结果都已经成功返回，但最终执行失败，优先考虑：断言问题、代码生成问题，而不是接口挂了。
- 如果请求根本没有成功发出，优先考虑：URL、参数、代码生成、环境问题。
- 如果接口信息中包含参数占位、Cookie、query/form/json 结构，优先检查是不是参数输入有问题。
- 如果运行代码里的请求方式、headers、body 传参方式不合理，优先判断为代码生成问题。
- 如果接口真实返回与断言不一致，但响应看起来正常，优先判断为断言问题或测试代码问题。
- 如果响应明确显示鉴权失败、参数缺失、字段类型错误、URL 非法等，要明确指出这是“参数输入问题”还是“接口请求构造问题”，不要笼统写成接口异常。
- 如果日志显示语法错误、NameError、ImportError、JSONDecodeError、response.json() 调用不当等，优先判断为代码生成问题。
- 必须尽量给出“证据链”，说明你为什么这么判断。

你必须严格按下面格式输出，且全部用中文：

问题现象：
（简要描述本次失败表现）

问题本质：
（必须说明真正根因，不要只复述日志）

责任归属：
（只能从下面 6 类中选 1 个最主要的：
参数输入问题 / 代码生成问题 / 断言问题 / 接口问题 / 环境问题 / 执行链问题）

关键证据：
1. ...
2. ...
3. ...

修复建议：
1. ...
2. ...
3. ...

风险等级：
（只能是 low / medium / high）

下面是本次失败的完整上下文：

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

【执行日志】
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
                    "你的任务不是泛泛总结，而是基于接口信息、执行日志、响应结果、运行代码定位问题本质。"
                    "必须严格输出：问题现象、问题本质、责任归属、关键证据、修复建议、风险等级。"
                    "责任归属只能从以下 6 类中选 1 个："
                    "参数输入问题 / 代码生成问题 / 断言问题 / 接口问题 / 环境问题 / 执行链问题。"
                    "风险等级只能输出 low / medium / high。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
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


# 从 LLM 返回文本里提取风险等级
def extract_risk_level(analysis_text: str) -> str:
    if not analysis_text:
        return "medium"

    lower_text = analysis_text.lower()

    # 优先匹配英文规范值
    if re.search(r"风险等级[:：]?\s*high", lower_text):
        return "high"
    if re.search(r"风险等级[:：]?\s*low", lower_text):
        return "low"
    if re.search(r"风险等级[:：]?\s*medium", lower_text):
        return "medium"

    # 再兼容中文
    if "高" in analysis_text:
        return "high"
    if "低" in analysis_text:
        return "low"

    return "medium"


# 核心主流程：生成 AI 分析
def generate_ai_analysis(db: Session, run_id: int):
    # 1. 查执行记录
    test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not test_run:
        raise ValueError("执行记录不存在")

    # 2. 至少要有日志、响应结果、错误信息中的一种，才能分析
    if not test_run.log_content and not test_run.error_message and not test_run.response_content:
        raise ValueError("当前执行记录缺少可分析信息")

    # 3. 查关联测试用例，拿接口信息和运行代码
    api_case = db.query(APICase).filter(APICase.id == test_run.case_id).first()

    # 4. 构造 Prompt
    prompt = build_failure_analysis_prompt(api_case, test_run)

    # 5. 调 LLM
    try:
        analysis_content = call_llm_analyze_log(prompt)
    except Exception as e:
        raise ValueError(f"AI 日志分析失败：{str(e)}")

    if not analysis_content:
        raise ValueError("AI 日志分析失败：模型未返回有效内容")

    risk_level = extract_risk_level(analysis_content)

    # 6. 落库
    db_analysis = AIAnalysis(
        run_id=run_id,
        analysis_type="failure_analysis",
        content=analysis_content,
        risk_level=risk_level,
    )
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)

    # 7. 返回
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