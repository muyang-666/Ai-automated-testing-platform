from datetime import datetime
import httpx
from app.core.config import settings
from sqlalchemy.orm import Session

from app.core.config import settings  # 配置接入真实 LLM
from app.models.ai_analysis import AIAnalysis   # 说明这条链最终的分析结果，会落到：ai_analyses 表
from app.models.test_run import TestRun  # 输入数据来自：TestRun

# 日志分析链里的 Prompt 构造器
def build_failure_analysis_prompt(log_content: str) -> str:
    return f"""
你是一名资深测试开发工程师，请分析下面的 pytest 失败日志，并输出：

1. 问题现象
2. 根本原因
3. 修复建议
4. 风险等级（low / medium / high）

要求：
- 语言使用中文
- 分析清晰简洁
- 明确指出是代码问题、接口问题、请求方法问题、断言问题还是环境问题
- 不要输出无关内容

pytest 失败日志如下：
{log_content}
""".strip()


# 模拟兜底
def generate_mock_analysis(log_content: str) -> tuple[str, str]:
    lower_log = log_content.lower() # 把日志统一转成小写。

    # 日志里有没有 405，同时有没有 not allowed
    if "405" in lower_log and "not allowed" in lower_log:
        content = (
            "问题现象：测试用例执行失败，接口返回 405 Not Allowed，断言期望 200 实际为 405。\n\n"
            "根本原因：请求已经成功到达服务端，但当前请求方法与接口实际允许的方法不匹配，"
            "或者目标地址不支持当前 POST 请求。\n\n"
            "修复建议：\n"
            "1. 检查接口文档，确认该 URL 是否支持 POST 方法；\n"
            "2. 核对生成测试代码中的 method 字段是否正确；\n"
            "3. 若接口需要 GET/PUT/其他方法，修改测试用例后重新执行；\n"
            "4. 若这是示例地址，请替换为真实可测接口地址。\n\n"
            "风险等级：medium"
        )
        return content, "medium"

    # 只要日志里出现 nameerror，就判定为：生成的 Python 代码里出现了未定义变量
    if "nameerror" in lower_log:
        content = (
            "问题现象：测试代码执行时报 NameError，说明生成的 Python 代码中存在未定义变量。\n\n"
            "根本原因：AI 生成测试代码时未正确处理输入数据，导致变量名或字段内容被错误写入代码。\n\n"
            "修复建议：\n"
            "1. 对 headers/body/expected_result 做 JSON 安全解析；\n"
            "2. 在代码生成后增加语法检查；\n"
            "3. 对生成结果增加可执行性校验。\n\n"
            "风险等级：high"
        )
        return content, "high"

    # URL 缺协议头
    if "unsupportedprotocol" in lower_log or "missing an 'http://' or 'https://' protocol" in lower_log:
        content = (
            "问题现象：请求发送失败，URL 缺少 http:// 或 https:// 协议头。\n\n"
            "根本原因：测试用例中的 URL 配置不合法，或代码生成阶段未对 URL 做规范化处理。\n\n"
            "修复建议：\n"
            "1. 检查数据库中保存的 url 字段；\n"
            "2. 在生成测试代码前统一补全协议头；\n"
            "3. 增加 URL 合法性校验。\n\n"
            "风险等级：medium"
        )
        return content, "medium"

    # 如果上面几类典型错误都没匹配到，就走这个默认模板。
    content = (
        "问题现象：pytest 执行失败。\n\n"
        "根本原因：当前日志未匹配到已内置的典型失败模式，可能涉及断言失败、环境问题、接口响应异常或生成代码质量问题。\n\n"
        "修复建议：\n"
        "1. 重点查看失败栈顶部报错；\n"
        "2. 核对请求地址、请求方法、请求参数与预期断言；\n"
        "3. 必要时结合接口文档和原始响应内容进一步排查。\n\n"
        "风险等级：medium"
    )
    return content, "medium"

# 模型生成
def call_llm_analyze_log(prompt: str) -> str:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "mock" or not settings.LLM_API_KEY:
        return ""

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
                    "你是资深测试开发工程师，擅长分析 pytest 失败日志。"
                    "请严格输出四部分：问题现象、根本原因、修复建议、风险等级。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
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
    return data["choices"][0]["message"]["content"]


# 核心主流程 AI分析链真正把所有环节串起来
def generate_ai_analysis(db: Session, run_id: int):
    # 第 1 步：根据 run_id 查执行记录
    test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not test_run:
        raise ValueError("执行记录不存在")

    # 第 2 步：检查有没有日志可分析
    if not test_run.log_content:
        raise ValueError("当前执行记录没有可分析的日志")

    # 第 3 步：构造分析 Prompt
    prompt = build_failure_analysis_prompt(test_run.log_content)

    # 第 4 步：尝试调用 LLM
    llm_result = ""
    try:
        llm_result = call_llm_analyze_log(prompt).strip()
    except Exception:
        llm_result = ""

    if llm_result:
        analysis_content = llm_result

        lower_result = llm_result.lower()
        if "high" in lower_result or "高" in lower_result:
            risk_level = "high"
        elif "low" in lower_result or "低" in lower_result:
            risk_level = "low"
        else:
            risk_level = "medium"
    else:
        analysis_content, risk_level = generate_mock_analysis(test_run.log_content)

    # 第 6 步：创建 AIAnalysis 数据库对象。这一步是把分析结果包装成 ORM 对象。
    db_analysis = AIAnalysis(
        run_id=run_id,
        analysis_type="failure_analysis",
        content=analysis_content,
        risk_level=risk_level,
    )
    # # 第 7 步：写入数据库
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)

    # 第 8 步：返回给前端
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