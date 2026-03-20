# 把 HTTP 请求接进来，再转交给 service 处理

# APIRouter:用来创建“路由组”把一类相关接口放进一个小组里
# Depends:自动给接口注入数据库会话 db
# HTTPException:用来主动抛 HTTP 错误。
from fastapi import APIRouter, Depends, HTTPException

# 这个 Session 是 SQLAlchemy 的数据库会话类型。 这个接口里传进来的 db，是一个数据库操作工具
from sqlalchemy.orm import Session

# 每次请求进来，给这个接口分配一个数据库会话
from app.core.database import get_db

# APICaseCreate用于接收“创建测试用例”的请求体。也就是：前端传进来的 JSON，先按这个 schema 校验
from app.schemas.api_case import APICaseCreate, APICaseResponse, APICaseUpdate

# 这里说明 router 并不自己写业务逻辑，而是把工作交给 service。
# create_case：创建测试用例。 get_case_by_id：按 id 查详情。 get_case_list：查列表
from app.services.case_service import (
    create_case,
    delete_case,
    get_case_by_id,
    get_case_list,
    update_case,
)

# APIRouter(...)表示我要创建一个路由对象。这个对象专门装“测试用例相关接口”。
# prefix="/cases" 表示： 这个 router 下面所有接口，统一都带 /cases 前缀
# tags=["Cases"] 这个主要用于 Swagger 文档分类展示。这样在接口文档里，这几个接口会被归到 Cases 分组下面。
router = APIRouter(prefix="/cases", tags=["Cases"])

# 创建测试用例
# @router.post("") 意思是：这是一个 POST 请求接口，路径是当前 router 的根路径。
# response_model=APICaseResponse 它表示：这个接口返回的数据，必须符合 APICaseResponse 这个 schema
@router.post("", response_model=APICaseResponse, summary="创建测试用例") #summary Swagger 页面上，你会看到“创建测试用例”这个标题。
# case_data: APICaseCreate 这一句表示：这个接口接收一个请求体，格式必须符合 APICaseCreate。
# db: Session = Depends(get_db) 这一句表示：这个接口还需要一个数据库会话对象 db，请 FastAPI 自动通过 get_db() 提供。
def create_api_case(case_data: APICaseCreate, db: Session = Depends(get_db)):
    return create_case(db, case_data)  # 把db给service。 把case_data给service。 接收service返回结果 再返回给前端

# 查询测试用例列表
# APICaseResponse → 单个对象 list[APICaseResponse] → 对象列表
@router.get("", response_model=list[APICaseResponse], summary="查询测试用例列表")
def list_api_cases(db: Session = Depends(get_db)): # “查列表”这个接口不需要前端传请求体。 它只需要一个数据库会话去查数据
    return get_case_list(db)   # 把查列表这件事交给 service

# 查询测试用例详情
# 这是一个 GET 接口，路径里带一个变量 case_id。因为 prefix 是 /cases，所以完整路径是：GET /cases/{case_id}
@router.get("/{case_id}", response_model=APICaseResponse, summary="查询测试用例详情")
def get_api_case(case_id: int, db: Session = Depends(get_db)):  # 从 URL 路径里取出 case_id，并且要求它必须是整数
    case = get_case_by_id(db, case_id)  # 把查详情这件事交给 service。
    if not case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return case  # 查到了，就把这个 ORM 对象返回。

# 更新测试用例
@router.put("/{case_id}", response_model=APICaseResponse, summary="更新测试用例")
def update_api_case(case_id: int, case_data: APICaseUpdate, db: Session = Depends(get_db)):
    case = update_case(db, case_id, case_data)
    if not case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return case

# 删除测试用例
@router.delete("/{case_id}", summary="删除测试用例")
def delete_api_case(case_id: int, db: Session = Depends(get_db)):
    success = delete_case(db, case_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return {"message": "测试用例删除成功"}