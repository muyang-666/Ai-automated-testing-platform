#models/api_case.py 负责定义：数据库里的“测试用例表”长什么样。

from sqlalchemy import Column, DateTime, Integer, Text, String
from sqlalchemy.sql import func

from app.core.database import Base

# 我要定义一个数据库模型类，这个类对应数据库里的一张表 即 APICase 是“测试用例表”在 Python 世界里的代表
class APICase(Base): # 一定要继承 Base 只有继承了 Base，SQLAlchemy 才知道你这个类是“表模型”
    __tablename__ = "api_cases" # 它告诉 SQLAlchemy：这张表在数据库里的名字叫 api_cases

    # 这张表有哪几列，每列是什么规则
    # Integer:表示这一列是整数类型。primary_key=True:表示这是主键 这张表里每一条记录的唯一标识。index=True：表示给这列加索引。
    id = Column(Integer, primary_key=True, index=True)
    # String(100)：表示字符串类型，长度最多 100。nullable=False：表示这个字段不能为空。
    name = Column(String(100), nullable=False, comment="用例名称")
    # 这是一个字符串字段。 最多 255 个字符 可以为空。
    description = Column(String(255), nullable=True, comment="用例描述")
    # 这个字段存 HTTP 请求方法 不能为空。
    method = Column(String(10), nullable=False, comment="请求方法")
    # 这个字段用来存接口地址 不能为空。
    url = Column(String(255), nullable=False, comment="请求地址")
    # headers 是可选的扩展信息。为什么不用 String，而用 Text？ 因为请求头可能稍微长一点 所以用 Text 更宽松
    headers = Column(Text, nullable=True, comment="请求头JSON字符串")
    # body 是请求内容，可有可无
    body = Column(Text, nullable=True, comment="请求体JSON字符串")
    # 这个字段非常关键，它表示：你预期接口应该返回什么结果。为什么允许为空？因为有些初版平台可能先只存基础信息，期望结果后续补充。
    expected_result = Column(Text, nullable=True, comment="预期结果JSON字符串")
    # 它用来存：AI 生成的 pytest 测试代码。它是连接 测试用例描述 AI生成代码 pytest执行 之间的桥梁。
    generated_test_code = Column(Text, nullable=True, comment="AI生成的pytest代码")
    # 补充用例创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")