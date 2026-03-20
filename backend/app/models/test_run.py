# 测试运行记录表

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, String
from sqlalchemy.sql import func

from app.core.database import Base

# 测试运行记录表
class TestRun(Base):
    __tablename__ = "test_runs"

    # 这不是“用例 ID”，而是“运行记录 ID”。 可能运行多次
    id = Column(Integer, primary_key=True, index=True)
    # 这条执行记录，属于哪一条测试用例。ForeignKey("api_cases.id")表示：test_runs.case_id 指向 api_cases.id
    case_id = Column(Integer, ForeignKey("api_cases.id"), nullable=False, comment="关联用例ID")
    # 执行过程状态。 默认值是 pending “待执行”状态
    status = Column(String(20), nullable=False, default="pending", comment="执行状态")
    # 最终测试结果。 为什么允许 nullable=True 因为在测试还没执行完的时候，结果可能还不知道
    result = Column(String(20), nullable=True, comment="执行结果")
    # 这次执行一共统计到了多少条测试结果。
    total_count = Column(Integer, default=0, comment="总执行数")
    # 表示这次执行里通过了几个。
    passed_count = Column(Integer, default=0, comment="通过数")
    # 表示这次执行里失败了几个。
    failed_count = Column(Integer, default=0, comment="失败数")
    # pytest 执行过程的完整输出日志
    log_content = Column(Text, nullable=True, comment="执行日志")
    # 这个字段是“错误摘要”或者“错误内容”。
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 这个字段表示：接口实际返回的 HTTP 状态码。它不是 pytest 的 passed/failed，而是目标接口真实返回码
    response_status_code = Column(Integer, nullable=True, comment="接口响应状态码")
    # 这个字段表示：接口实际返回的响应内容。比如 JSON / HTML / 文本字符串
    response_content = Column(Text, nullable=True, comment="接口响应结果")

    # 表示这次测试什么时候开始执行。
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始时间")
    # 表示这次执行什么时候结束。
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    # 数据库里这条记录是什么时候被创建出来的。
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")