# 规范接口的数据输入和输出

from datetime import datetime # 用于表示时间类型 比如：created_at updated_at 说明返回数据里会带时间。
from typing import Optional   # Optional 表示：这个字段可以有值，也可以是 None

# BaseModel:这是 Pydantic 最核心的基类。 只要继承它 Pydantic 就会帮你做很多事：校验字段类型 校验必填项 生成接口文档 自动把数据转成对象
# Field:是用来给字段加规则和说明的
from pydantic import BaseModel, Field

# 当前端调用“创建测试用例接口”时，请求体必须满足这些规则
class APICaseCreate(BaseModel):
    # name: str 表示这个字段叫 name，类型必须是字符串。 Field(...) 它表示：这个字段必填。 min_length=1 表示最少 1 个字符。 max_length=100 表示最多 100 个字符。
    name: str = Field(..., min_length=1, max_length=100, description="用例名称") # description="用例名称" 这个主要用于 Swagger 文档展示。
    # Optional[str] 说明这个字段可以是：字符串或者 None。 default=None 表示如果前端不传，默认就是空。
    description: Optional[str] = Field(default=None, max_length=255, description="用例描述")
    # 这个字段表示 HTTP 请求方法
    method: str = Field(..., min_length=1, max_length=10, description="请求方法")
    # 表示请求地址
    url: str = Field(..., min_length=1, max_length=255, description="请求地址")
    # 这个字段可选，用来存请求头
    headers: Optional[str] = Field(default=None, description="请求头JSON字符串")
    # 表示请求体，可选，类型是字符串
    body: Optional[str] = Field(default=None, description="请求体JSON字符串")
    # 测试完成后，系统可以拿真实结果和预期结果做对比
    expected_result: Optional[str] = Field(default=None, description="预期结果JSON字符串")

# 后端返回给前端的数据格式，必须符合这个结构
class APICaseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    method: str
    url: str
    headers: Optional[str]
    body: Optional[str]
    expected_result: Optional[str]
    generated_test_code: Optional[str]
    created_at: datetime
    updated_at: datetime

    # 它允许 Pydantic 直接把 ORM 对象转成响应模型
    class Config:
        from_attributes = True # 让响应模型可以直接读取 ORM 对象属性
        # 所以它本质是：让 response schema 和 SQLAlchemy model 更好配合。